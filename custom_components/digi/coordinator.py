"""DataUpdateCoordinator pentru DIGI România.

La fiecare actualizare (implicit la 6 ore):
  1. datele utilizatorului — confirmă că sesiunea e încă activă;
  2. pagina de facturi (toate facturile, curente + achitate, cu adresa fiecăreia);
  3. detaliile („Vezi factura") facturilor neplătite și ale ultimei facturi de pe fiecare adresă —
     cele achitate nu se mai schimbă, deci se citesc o singură dată;
  4. o dată pe zi: „Serviciile mele" — adresele și, pe fiecare, tabul Overview + Internet / TV
     (doar pentru serviciile instalate) — plus „Administrare cont" (datele clientului).

Sesiune expirată → ConfigEntryAuthFailed (reautentificare cu cod SMS, cerută utilizatorului).
Integrarea nu face niciodată login singură: fiecare login trimite un SMS.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .api import DigiApiClient, DigiAuthError, DigiError
from .const import (
    CONF_COOKIES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LICENSE_DATA_KEY,
    REQUEST_PAUSE,
    SERVICES_REFRESH_INTERVAL,
    TAB_INTERNET,
    TAB_OVERVIEW,
    TAB_TV,
)
from .helpers import has_service, invoice_rest, mask
from .parser import (
    match_address,
    parse_account_details,
    parse_internet,
    parse_invoice_popup,
    parse_invoices,
    parse_overview,
    parse_services_page,
    parse_tv,
)

_LOGGER = logging.getLogger(__name__)


def short_label(label: str) -> str:
    """„Strada X nr. 1, Oraș, județul Y" → „Strada X nr. 1, Oraș" (numele dispozitivului)."""
    return label.split(", județul")[0].split(", judetul")[0].strip() or label


def build_addresses(invoice_addresses: dict[str, str], services: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Adresele contului, unite din „Serviciile mele" (id DIGI) și pagina de facturi (cheie text).

    Cheia unei adrese e id-ul DIGI din „Serviciile mele"; o adresă care apare doar în facturi
    (ex. servicii reziliate) primește cheia „f_<adresa>".
    """
    addresses: dict[str, dict[str, Any]] = {}
    labels = {a["id"]: a["label"] for a in services.get("addresses") or []}
    for service_id, label in labels.items():
        addresses[service_id] = {
            "key": service_id, "service_id": service_id, "invoice_key": None,
            "label": short_label(label), "full_label": label,
        }
    for invoice_key, label in invoice_addresses.items():
        service_id = match_address(label, labels)
        if service_id and addresses[service_id]["invoice_key"] is None:
            addresses[service_id]["invoice_key"] = invoice_key
            addresses[service_id]["label"] = label
            continue
        key = f"f_{slugify(invoice_key.removeprefix('address-'))}"
        addresses[key] = {"key": key, "service_id": None, "invoice_key": invoice_key, "label": label, "full_label": label}
    return addresses


def layout(data: dict[str, Any] | None) -> tuple:
    """Ce entități trebuie să existe — dacă se schimbă (adresă / serviciu nou), intrarea se reîncarcă."""
    items = []
    for key, address in ((data or {}).get("addresses") or {}).items():
        services = ((data or {}).get("services") or {}).get(key) or {}
        items.append((
            key,
            bool(address.get("service_id")),
            has_service(services, "internet", "internet"),
            has_service(services, "tv", "televiziune"),
        ))
    return tuple(sorted(items))


class DigiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Datele unui cont DIGI (doar citire)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: DigiApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        self.client = client
        self._details: dict[str, dict[str, Any]] = {}
        self._services: dict[str, Any] | None = None
        self._services_at: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        license_mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if license_mgr and not license_mgr.is_valid:
            _LOGGER.debug("[Digi] Licență invalidă — se omit cererile către digi.ro")
            return self.data or {}

        started = time.monotonic()
        try:
            user = await self.client.async_get_user()
            invoices = parse_invoices(await self.client.async_get_invoices_page())
            await self._async_details(invoices["invoices"])
            services = await self._async_services()
        except DigiAuthError as err:
            _LOGGER.warning("[Digi] Sesiunea a expirat — e nevoie de reautentificare cu cod SMS (%s)", err)
            raise ConfigEntryAuthFailed(f"Sesiunea DIGI a expirat: {err}") from err
        except DigiError as err:
            raise UpdateFailed(f"Datele DIGI nu au putut fi actualizate: {err}") from err

        self._persist_cookies()
        addresses = build_addresses(invoices["addresses"], services)
        by_key = {a["invoice_key"]: key for key, a in addresses.items() if a.get("invoice_key")}
        invoices_by_address: dict[str, list[dict[str, Any]]] = {key: [] for key in addresses}
        for invoice in invoices["invoices"]:
            key = by_key.get(invoice["address_key"])
            if key is None:  # rând cu o adresă care lipsește din selector
                key = f"f_{slugify(invoice['address_key'].removeprefix('address-'))}"
                addresses.setdefault(key, {"key": key, "service_id": None, "invoice_key": invoice["address_key"],
                                           "label": invoice["address"], "full_label": invoice["address"]})
                invoices_by_address.setdefault(key, [])
            invoices_by_address[key].append({**invoice, "details": self._details.get(invoice["id"] or "")})
        for items in invoices_by_address.values():
            items.sort(key=lambda inv: inv["issued"] or datetime.min.date(), reverse=True)

        data = {
            "client": {
                "id": str(user.get("idclient") or ""),
                "name": user.get("name") or user.get("displayname"),
                "email": user.get("email"),
                "type": user.get("type"),
            },
            "addresses": addresses,
            "invoices": invoices_by_address,
            "account": services.get("account") or {},
            "invoice_channel": invoices.get("invoice_channel"),
            "unpaid_count": invoices["unpaid_count"],
            "unpaid_total": invoices["unpaid_total"]
            if invoices["unpaid_total"] is not None
            else round(sum(invoice_rest(i) for i in invoices["invoices"] if not i["paid"]), 2),
            "services": {
                key: (services.get("by_address") or {}).get(a["service_id"]) or {}
                for key, a in addresses.items()
                if a.get("service_id")
            },
            "services_updated": self._services_at,
        }
        _LOGGER.debug(
            "[Digi] Actualizare în %.1f s: %d adrese, %d facturi (%d neplătite, %.2f lei), %d detalii în cache; %s",
            time.monotonic() - started,
            len(addresses),
            len(invoices["invoices"]),
            data["unpaid_count"],
            data["unpaid_total"] or 0.0,
            len(self._details),
            "; ".join(
                f"adresa {mask(key)}: {len(invoices_by_address.get(key) or [])} facturi, servicii "
                + (", ".join(o["type"] for o in (data["services"].get(key) or {}).get("overview") or [] if o["active"]) or "—")
                for key in addresses
            ),
        )
        return data

    async def _async_details(self, invoices: list[dict[str, Any]]) -> None:
        """„Vezi factura" pentru facturile neplătite (restul se poate schimba) și ultima de pe fiecare adresă.

        Detaliile facturilor achitate rămân în cache; o eroare la o factură nu oprește actualizarea.
        """
        latest: dict[str, dict[str, Any]] = {}
        for invoice in invoices:
            current = latest.get(invoice["address_key"])
            if invoice["issued"] and (current is None or invoice["issued"] > current["issued"]):
                latest[invoice["address_key"]] = invoice
        wanted = {inv["id"]: inv for inv in invoices if inv["id"] and not inv["paid"]}
        wanted.update({inv["id"]: inv for inv in latest.values() if inv["id"]})
        present = {inv["id"] for inv in invoices if inv["id"]}
        self._details = {k: v for k, v in self._details.items() if k in present}

        for invoice_id, invoice in wanted.items():
            if invoice["paid"] and invoice_id in self._details:
                continue
            try:
                self._details[invoice_id] = parse_invoice_popup(await self.client.async_get_invoice_details(invoice_id))
            except DigiAuthError:
                raise
            except DigiError as err:
                _LOGGER.debug("[Digi] Detaliile facturii %s nu au putut fi citite: %s", mask(invoice_id), err)
            await asyncio.sleep(REQUEST_PAUSE)

    async def _async_services(self) -> dict[str, Any]:
        """„Serviciile mele", o dată pe zi. La eroare se păstrează datele anterioare (dacă există)."""
        now = dt_util.utcnow()
        if self._services is not None and self._services_at and now - self._services_at < SERVICES_REFRESH_INTERVAL:
            return self._services
        try:
            services = await self._async_fetch_services()
        except DigiAuthError:
            raise
        except DigiError as err:
            if self._services is None:
                raise
            _LOGGER.warning("[Digi] Serviciile nu au putut fi actualizate, rămân cele de la ultima citire: %s", err)
            return self._services
        self._services, self._services_at = services, now
        return services

    async def _async_fetch_services(self) -> dict[str, Any]:
        page = await self.client.async_get_services_page()
        parsed = parse_services_page(page)
        tabs = parsed["tabs"]
        if TAB_OVERVIEW not in tabs:
            raise DigiError("pagina „Serviciile mele” nu conține tabul Overview")
        by_address: dict[str, dict[str, Any]] = {}
        for address in parsed["addresses"]:
            address_id = address["id"]
            overview = parse_overview(await self.client.async_get_service_tab(tabs[TAB_OVERVIEW], page, address_id))
            await asyncio.sleep(REQUEST_PAUSE)
            active = {item.get("action") for item in overview if item["active"]}
            entry: dict[str, Any] = {"overview": overview, "internet": None, "tv": None}
            for tab, key, parse in ((TAB_INTERNET, "internet", parse_internet), (TAB_TV, "tv", parse_tv)):
                if tab in active and tab in tabs:
                    entry[key] = parse(await self.client.async_get_service_tab(tabs[tab], page, address_id))
                    await asyncio.sleep(REQUEST_PAUSE)
            by_address[address_id] = entry
        _LOGGER.debug(
            "[Digi] Servicii citite pentru %d adrese: %s",
            len(by_address),
            "; ".join(
                f"{mask(aid)}: " + (", ".join(f"{o['type']} ({o['package']})" for o in e["overview"] if o["active"]) or "niciun serviciu activ")
                for aid, e in by_address.items()
            ),
        )
        # „Administrare cont": datele clientului (o eroare aici nu oprește serviciile)
        try:
            account = parse_account_details(await self.client.async_get_account_details_page())
        except DigiAuthError:
            raise
        except DigiError as err:
            _LOGGER.debug("[Digi] Datele clientului nu au putut fi citite: %s", err)
            account = (self._services or {}).get("account") or {}
        return {"addresses": parsed["addresses"], "by_address": by_address, "account": account}

    def _persist_cookies(self) -> None:
        """Salvează cookie-urile sesiunii dacă s-au schimbat, ca să supraviețuiască unui restart."""
        cookies = self.client.export_cookies()
        if cookies and cookies != self.entry.data.get(CONF_COOKIES):
            self.hass.config_entries.async_update_entry(self.entry, data={**self.entry.data, CONF_COOKIES: cookies})
            _LOGGER.debug("[Digi] Cookie-urile sesiunii au fost salvate în configurație")
