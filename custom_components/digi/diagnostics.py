"""Diagnostic pentru DIGI România — structura datelor, fără date personale.

Fără: email, parolă, cookie-uri, nume, adrese, numere de factură, cont PPPoE, seriile echipamentelor.
Adresele apar ca „adresa 1", „adresa 2"; sumele și datele facturilor rămân (sunt necesare la depanare).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import DigiConfigEntry
from .const import CONF_COOKIES, DOMAIN, LICENSE_DATA_KEY
from .helpers import is_overdue, latest_invoice, mask, today_ro


def _invoice(invoice: dict[str, Any], today) -> dict[str, Any]:
    details = invoice.get("details") or {}
    return {
        "emisa": str(invoice.get("issued")),
        "scadenta": str(invoice.get("due")),
        "suma": invoice.get("amount"),
        "achitata": invoice.get("paid"),
        "restanta": is_overdue(invoice, today),
        "are_id": bool(invoice.get("id")),
        "detalii": {
            "are_numar": bool(details.get("number")),
            "total": details.get("total"),
            "rest": details.get("rest"),
            "status": details.get("status"),
            "linii": [
                {"nivel": line.get("level"), "serviciu": line.get("label"), "lei": line.get("lei"), "eur": line.get("eur")}
                for line in details.get("lines") or []
            ],
            "are_pdf": details.get("has_pdf"),
        }
        if details
        else None,
    }


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: DigiConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    license_mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    today = today_ro()

    addresses = []
    for index, (key, address) in enumerate((data.get("addresses") or {}).items(), start=1):
        invoices = (data.get("invoices") or {}).get(key) or []
        services = (data.get("services") or {}).get(key) or {}
        tv = services.get("tv") or {}
        latest = latest_invoice(invoices)
        addresses.append({
            "adresa": f"adresa {index}",
            "cheie": "din facturi" if key.startswith("f_") else mask(key),
            "in_servicii": bool(address.get("service_id")),
            "in_facturi": bool(address.get("invoice_key")),
            "facturi": len(invoices),
            "neachitate": sum(1 for i in invoices if not i.get("paid")),
            "cu_detalii": sum(1 for i in invoices if i.get("details")),
            "ultima_factura": _invoice(latest, today) if latest else None,
            "overview": [
                {"tip": o.get("type"), "activ": o.get("active"), "pachet": o.get("package"), "status": o.get("status")}
                for o in services.get("overview") or []
            ],
            "internet": {
                "pachet": (services.get("internet") or {}).get("package"),
                "are_cont_pppoe": bool((services.get("internet") or {}).get("account")),
                "are_echipament": bool((services.get("internet") or {}).get("device")),
            }
            if services.get("internet")
            else None,
            "tv": {
                "echipamente": len(tv.get("devices") or []),
                "extraoptiuni": [{"nume": o["name"], "activa": o["active"]} for o in tv.get("extra_options") or []],
            }
            if tv
            else None,
        })

    return {
        "rezumat": {
            "ultima_actualizare_reusita": coordinator.last_update_success,
            "interval_s": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
            "servicii_citite_la": str(data.get("services_updated")),
            "tip_client": (data.get("client") or {}).get("type"),
            "date_client": {
                "are_nume": bool((data.get("account") or {}).get("name")),
                "are_email": bool((data.get("account") or {}).get("email")),
                "are_telefon_2fa": bool((data.get("account") or {}).get("phone")),
                "aplicatii_partenere": len((data.get("account") or {}).get("partner_apps") or []),
                "factura_prin": data.get("invoice_channel"),
            },
            "adrese": len(addresses),
            "facturi_neachitate": data.get("unpaid_count"),
            "total_de_plata": data.get("unpaid_total"),
            # doar numele cookie-urilor, niciodată valorile
            "cookie_uri_salvate": sorted(c.get("name", "?") for c in entry.data.get(CONF_COOKIES) or []),
        },
        "licenta": license_mgr.as_dict() if license_mgr else {"status": "indisponibil"},
        "adrese": addresses,
    }
