"""Senzorul binar „Factură restantă" (câte unul pe adresă).

Restantă = factură neplătită, ca la celelalte integrări (E·ON, Nova): „Da" cât timp adresa are
de plată. Depășirea scadenței apare în atribute („termen depășit cu N zile", „Zile până la
scadență" negativ). Stările au traduceri proprii („Da" / „Nu").
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DigiConfigEntry
from .const import CONF_CLIENT_ID
from .coordinator import DigiCoordinator
from .entity import DigiAddressEntity, license_valid, remove_entities_without_license
from .helpers import due_text, format_amount, format_date, invoice_label, invoice_rest, today_ro, unpaid_invoices


class FacturaRestantaBinarySensor(DigiAddressEntity, BinarySensorEntity):
    """Da = adresa are cel puțin o factură neplătită."""

    def __init__(self, coordinator: DigiCoordinator, client_id: str, key: str) -> None:
        super().__init__(coordinator, client_id, key, "factura_restanta")

    @property
    def _unpaid(self) -> list[dict[str, Any]]:
        return sorted(unpaid_invoices(self._invoices), key=lambda inv: inv.get("due") or inv.get("issued"))

    @property
    def is_on(self) -> bool:
        return bool(self._unpaid)

    @property
    def icon(self) -> str:
        return "mdi:file-document-alert" if self.is_on else "mdi:file-document-check-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        unpaid = self._unpaid
        if not unpaid:
            return {}  # „Nu" — fără atribute (nimic „necunoscut")
        today = today_ro()
        attrs: dict[str, Any] = {}
        for invoice in unpaid:
            label = invoice_label(invoice)
            attrs[label if label not in attrs else f"{label} ({len(attrs) + 1})"] = due_text(invoice, today)
        attrs["Total restant"] = format_amount(sum(invoice_rest(inv) for inv in unpaid))
        attrs["Facturi neachitate"] = len(unpaid)
        dues = [inv["due"] for inv in unpaid if inv.get("due")]
        if dues:
            nearest = min(dues)
            attrs["Următoarea scadență"] = format_date(nearest)
            attrs["Zile până la scadență"] = (nearest - today).days
        return attrs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DigiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if not license_valid(hass):
        remove_entities_without_license(hass, entry.entry_id, "binary_sensor")
        return
    coordinator = entry.runtime_data
    client_id = entry.unique_id or entry.data.get(CONF_CLIENT_ID) or entry.entry_id
    async_add_entities(
        FacturaRestantaBinarySensor(coordinator, client_id, key)
        for key in ((coordinator.data or {}).get("addresses") or {})
    )
