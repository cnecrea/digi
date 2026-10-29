"""Senzori pentru DIGI România.

Dispozitive:
  - „DIGI — Cont <ID client>": Total de plată (toate adresele), Date client;
  - „DIGI — <adresă>" (câte unul pe adresă, legat de cont): Total de plată, Ultima factură,
    Arhivă facturi (12 luni), Internet / Televiziune (doar dacă serviciul e instalat),
    Servicii active; plus senzorul binar Factură restantă (binary_sensor.py).

Numele entităților vin din traduceri; atributele sunt în română (multe sunt dinamice: o factură,
o lună), ca la celelalte integrări.

Conform STANDARD-LICENTA.md: licență invalidă → doar „Licență necesară"; licență validă →
senzorul de licență rămas se șterge și se creează senzorii normali.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DigiConfigEntry
from .const import CONF_CLIENT_ID, DOMAIN, LICENSE_DATA_KEY
from .coordinator import DigiCoordinator
from .entity import (
    DigiAccountEntity,
    DigiAddressEntity,
    account_device,
    license_sensor_unique_id,
    license_valid,
    remove_entities_without_license,
)
from .helpers import (
    archive_invoices,
    due_text,
    format_amount,
    format_date,
    format_eur,
    has_service,
    invoice_label,
    invoice_rest,
    invoice_total,
    is_overdue,
    latest_invoice,
    latest_service_line,
    month_label,
    today_ro,
    unpaid_invoices,
)


def _next_due(invoices: list[dict[str, Any]]) -> dict[str, Any]:
    """„Următoarea scadență" + „Zile până la scadență" (negativ după scadență) — cea mai apropiată
    scadență a facturilor neplătite, ca la celelalte integrări."""
    today = today_ro()
    dues = [inv["due"] for inv in unpaid_invoices(invoices) if inv.get("due")]
    if not dues:
        return {}
    nearest = min(dues)
    return {"Următoarea scadență": format_date(nearest), "Zile până la scadență": (nearest - today).days}


def _unique_key(attrs: dict[str, Any], key: str) -> str:
    if key not in attrs:
        return key
    index = 2
    while f"{key} ({index})" in attrs:
        index += 1
    return f"{key} ({index})"


class LicentaNecesaraSensor(SensorEntity):
    """Apare DOAR când licența nu e validă (STANDARD-LICENTA.md)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:license"
    _attr_translation_key = "licenta_necesara"

    def __init__(self, entry_id: str, client_id: str) -> None:
        self._entry_id = entry_id
        self._client_id = client_id
        self._attr_unique_id = license_sensor_unique_id(entry_id)
        self.entity_id = f"sensor.{DOMAIN}_licenta_{entry_id.lower()}"

    @property
    def device_info(self) -> DeviceInfo:
        return account_device(self._client_id)

    @property
    def native_value(self) -> str:
        mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if mgr is not None:
            if mgr.status == "expired":
                return "Licență expirată"
            if mgr.status == "trial":
                days = mgr.trial_days_remaining
                return f"Trial — {days} zile rămase" if days > 0 else "Trial expirat"
        return "Licență necesară"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"nr_identificare": self._entry_id}
        mgr = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if mgr is not None:
            attrs["status_licență"] = mgr.status
            if mgr.status == "trial":
                attrs["zile_trial_rămase"] = mgr.trial_days_remaining
            attrs["informații"] = "Achiziționează o licență de pe hubinteligent.org sau din Buy Me a Coffee."
        return attrs


# ─────────────────────────────── Cont ───────────────────────────────


class TotalContSensor(DigiAccountEntity, SensorEntity):
    """Total de plată pe toate adresele — ca „Ai N facturi neplătite în valoare de…" de pe site."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:cash-clock"

    def __init__(self, coordinator: DigiCoordinator, client_id: str) -> None:
        super().__init__(coordinator, client_id, "total_cont", "cont_total_de_plata")

    @property
    def native_value(self) -> float | None:
        value = (self.coordinator.data or {}).get("unpaid_total")
        return round(float(value), 2) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {"Facturi neplătite": data.get("unpaid_count", 0)}
        everything: list[dict[str, Any]] = []
        today = today_ro()
        for key, invoices in (data.get("invoices") or {}).items():
            everything.extend(invoices)
            rest = round(sum(invoice_rest(inv) for inv in unpaid_invoices(invoices)), 2)
            if rest > 0:
                label = ((data.get("addresses") or {}).get(key) or {}).get("label") or key
                attrs[_unique_key(attrs, label)] = format_amount(rest)
        overdue = [inv for inv in everything if is_overdue(inv, today)]
        if overdue:
            attrs["Facturi cu scadența depășită"] = len(overdue)
        attrs.update(_next_due(everything))
        return attrs


# Tipul clientului din datele utilizatorului (confirmat: „F" = persoană fizică)
_CLIENT_TYPES = {"F": "Persoană fizică", "J": "Persoană juridică"}


class DateClientSensor(DigiAccountEntity, SensorEntity):
    """Datele clientului: codul de client ca valoare; numele, contactul, adresele și setările ca atribute."""

    _attr_icon = "mdi:account-card-outline"

    def __init__(self, coordinator: DigiCoordinator, client_id: str) -> None:
        super().__init__(coordinator, client_id, "date_client", "cont_date_client")

    @property
    def _details(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("account") or {}

    @property
    def native_value(self) -> str:
        return self._details.get("client_code") or (self.coordinator.data or {}).get("client", {}).get("id") or self._client_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        client = data.get("client") or {}
        details = self._details
        client_type = client.get("type")
        attrs: dict[str, Any] = {
            "Nume": details.get("name") or client.get("name"),
            "Email": details.get("email") or client.get("email"),
            "Tip client": _CLIENT_TYPES.get(client_type or "", client_type),
            "Telefon autentificare": details.get("phone"),
            "Factura se primește prin": data.get("invoice_channel"),
        }
        addresses = list((data.get("addresses") or {}).values())
        attrs["Adrese"] = len(addresses)
        for index, address in enumerate(addresses, start=1):
            attrs[f"Adresa {index}"] = address.get("full_label") or address.get("label")
        active = sum(
            1 for services in (data.get("services") or {}).values() for item in services.get("overview") or [] if item.get("active")
        )
        attrs["Servicii active"] = active
        apps = details.get("partner_apps")
        if apps is not None:
            enabled = [app["name"] for app in apps if app.get("enabled")]
            attrs["Aplicații cu acces la date"] = ", ".join(enabled) if enabled else "niciuna"
        return {k: v for k, v in attrs.items() if v is not None}


# ─────────────────────────────── Adresă ───────────────────────────────


class TotalAdresaSensor(DigiAddressEntity, SensorEntity):
    """Total de plată pe adresă, cu fiecare factură neplătită și scadența ei."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:cash-clock"

    def __init__(self, coordinator: DigiCoordinator, client_id: str, key: str) -> None:
        super().__init__(coordinator, client_id, key, "total_adresa")

    @property
    def native_value(self) -> float:
        return round(sum(invoice_rest(inv) for inv in unpaid_invoices(self._invoices)), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        today = today_ro()
        unpaid = sorted(unpaid_invoices(self._invoices), key=lambda inv: inv.get("due") or inv.get("issued"))
        attrs: dict[str, Any] = {}
        for invoice in unpaid:
            attrs[_unique_key(attrs, invoice_label(invoice))] = due_text(invoice, today)
        attrs["Facturi neplătite"] = len(unpaid)
        attrs.update(_next_due(self._invoices))
        return attrs


class UltimaFacturaSensor(DigiAddressEntity, SensorEntity):
    """Cea mai recentă factură a adresei: totalul și detaliile din „Vezi factura"."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "RON"
    _attr_icon = "mdi:receipt-text-outline"

    def __init__(self, coordinator: DigiCoordinator, client_id: str, key: str) -> None:
        super().__init__(coordinator, client_id, key, "ultima_factura")

    @property
    def _invoice(self) -> dict[str, Any] | None:
        return latest_invoice(self._invoices)

    @property
    def native_value(self) -> float | None:
        invoice = self._invoice
        total = invoice_total(invoice) if invoice else None
        return round(float(total), 2) if total is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        invoice = self._invoice
        if not invoice:
            return {}
        details = invoice.get("details") or {}
        lines = [line for line in details.get("lines") or [] if line.get("level", 0) >= 1]
        period = next((line for line in lines if line.get("period_from")), None)
        attrs: dict[str, Any] = {
            "Număr factură": details.get("number"),
            "Data emiterii": format_date(invoice.get("issued")),
            "Scadență": format_date(invoice.get("due")),
            "Perioadă facturată": f"{format_date(period['period_from'])} – {format_date(period['period_to'])}"
            if period and period.get("period_to")
            else None,
            "Status": details.get("status") or ("Achitată" if invoice.get("paid") else "Neachitată"),
            "Rest de plată": format_amount(invoice_rest(invoice)),
        }
        for line in lines:
            value = format_amount(line.get("lei"))
            if line.get("eur") is not None:
                value += f" ({format_eur(line['eur'])})"
            attrs[_unique_key(attrs, line.get("label") or "Serviciu")] = value
        return {k: v for k, v in attrs.items() if v is not None}


class ArhivaFacturiSensor(DigiAddressEntity, SensorEntity):
    """Facturile ultimelor 12 luni (inclusiv luna curentă): câte una pe lună, cu suma și starea."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:archive-outline"

    def __init__(self, coordinator: DigiCoordinator, client_id: str, key: str) -> None:
        super().__init__(coordinator, client_id, key, "arhiva_facturi")

    @property
    def _items(self) -> list[dict[str, Any]]:
        return archive_invoices(self._invoices, today_ro())

    @property
    def native_value(self) -> int:
        return len(self._items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self._items
        attrs: dict[str, Any] = {}
        for invoice in items:
            state = "achitată" if invoice.get("paid") else "neachitată"
            attrs[_unique_key(attrs, month_label(invoice.get("issued")))] = (
                f"{format_amount(invoice_total(invoice))} · {state}"
            )
        total = sum(float(invoice_total(inv) or 0) for inv in items)
        months = len({(inv["issued"].year, inv["issued"].month) for inv in items})
        attrs["Total 12 luni"] = format_amount(total)
        if months:
            attrs["Medie lunară"] = format_amount(total / months)
        return attrs


class InternetSensor(DigiAddressEntity, SensorEntity):
    """Pachetul de internet al adresei (ex. „FiberLink 1000")."""

    _attr_icon = "mdi:router-wireless"

    def __init__(self, coordinator: DigiCoordinator, client_id: str, key: str) -> None:
        super().__init__(coordinator, client_id, key, "internet")

    @property
    def native_value(self) -> str | None:
        internet = self._services.get("internet") or {}
        overview = next((o for o in self._services.get("overview") or [] if o["type"].lower() == "internet"), {})
        return internet.get("package") or overview.get("package")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        internet = self._services.get("internet") or {}
        line = latest_service_line(self._invoices, "internet")
        attrs = {
            "Cont PPPoE": internet.get("account"),
            "Echipament": internet.get("device"),
            "Abonament": f"{format_eur(line['eur'])}/lună" if line and line.get("eur") is not None else None,
            "Contract din": format_date(line.get("contract_date")) if line else None,
        }
        return {k: v for k, v in attrs.items() if v is not None}


class TeleviziuneSensor(DigiAddressEntity, SensorEntity):
    """Pachetul TV al adresei (ex. „Digital"), cu echipamentele și extraopțiunile active."""

    _attr_icon = "mdi:television-classic"

    def __init__(self, coordinator: DigiCoordinator, client_id: str, key: str) -> None:
        super().__init__(coordinator, client_id, key, "televiziune")

    @property
    def native_value(self) -> str | None:
        overview = next((o for o in self._services.get("overview") or [] if o["type"].lower() == "televiziune"), {})
        return overview.get("package")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tv = self._services.get("tv") or {}
        attrs: dict[str, Any] = {}
        devices = tv.get("devices") or []
        for index, device in enumerate(devices, start=1):
            attrs["Echipament" if len(devices) == 1 else f"Echipament {index}"] = device
        active = [o["name"] for o in tv.get("extra_options") or [] if o.get("active")]
        attrs["Extraopțiuni active"] = ", ".join(active) if active else "niciuna"
        line = latest_service_line(self._invoices, "tv", "cablu", "televiz")
        if line and line.get("eur") is not None:
            attrs["Abonament"] = f"{format_eur(line['eur'])}/lună"
        if line and line.get("contract_date"):
            attrs["Contract din"] = format_date(line["contract_date"])
        return attrs


class ServiciiActiveSensor(DigiAddressEntity, SensorEntity):
    """Câte servicii sunt instalate la adresă; fiecare serviciu din Overview, ca atribut."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:format-list-checks"

    def __init__(self, coordinator: DigiCoordinator, client_id: str, key: str) -> None:
        super().__init__(coordinator, client_id, key, "servicii_active")

    @property
    def native_value(self) -> int:
        return sum(1 for item in self._services.get("overview") or [] if item["active"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        for item in self._services.get("overview") or []:
            value = (item.get("package") or "activ") if item["active"] else (item.get("status") or "neinstalat")
            attrs[_unique_key(attrs, item["type"])] = value
        return attrs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DigiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Creează senzorii contului și pe cei ai fiecărei adrese."""
    client_id = entry.unique_id or entry.data.get(CONF_CLIENT_ID) or entry.entry_id
    if not license_valid(hass):
        remove_entities_without_license(hass, entry.entry_id, "sensor")
        async_add_entities([LicentaNecesaraSensor(entry.entry_id, client_id)])
        return

    registry = er.async_get(hass)
    orphan = registry.async_get_entity_id("sensor", DOMAIN, license_sensor_unique_id(entry.entry_id))
    if orphan is not None:
        registry.async_remove(orphan)

    coordinator = entry.runtime_data
    data = coordinator.data or {}
    entities: list[SensorEntity] = [TotalContSensor(coordinator, client_id), DateClientSensor(coordinator, client_id)]
    for key, address in (data.get("addresses") or {}).items():
        services = (data.get("services") or {}).get(key) or {}
        entities += [
            TotalAdresaSensor(coordinator, client_id, key),
            UltimaFacturaSensor(coordinator, client_id, key),
            ArhivaFacturiSensor(coordinator, client_id, key),
        ]
        if has_service(services, "internet", "internet"):
            entities.append(InternetSensor(coordinator, client_id, key))
        if has_service(services, "tv", "televiziune"):
            entities.append(TeleviziuneSensor(coordinator, client_id, key))
        if address.get("service_id"):
            entities.append(ServiciiActiveSensor(coordinator, client_id, key))
    async_add_entities(entities)
