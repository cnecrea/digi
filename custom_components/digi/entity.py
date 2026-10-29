"""Elemente comune entităților DIGI: licența și dispozitivele (contul, adresele)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DEVICE_PREFIX, DOMAIN, LICENSE_DATA_KEY, MANUFACTURER
from .coordinator import DigiCoordinator


def license_valid(hass: HomeAssistant) -> bool:
    """Licența (sau trial-ul) e validă acum — verificare în timp real."""
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    return bool(mgr and mgr.is_valid)


def license_sensor_unique_id(entry_id: str) -> str:
    return f"{DOMAIN}_licenta_{entry_id}"


def remove_entities_without_license(hass: HomeAssistant, entry_id: str, domain: str) -> None:
    """Licență invalidă: scoate din registry entitățile normale ale platformei."""
    registry = er.async_get(hass)
    keep = license_sensor_unique_id(entry_id)
    for reg in er.async_entries_for_config_entry(registry, entry_id):
        if reg.domain == domain and reg.unique_id != keep:
            registry.async_remove(reg.entity_id)


def account_device(client_id: str) -> DeviceInfo:
    """Dispozitivul „cont": totalul de plată pentru toate adresele."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{client_id}_cont")},
        name=f"{DEVICE_PREFIX} — Cont {client_id}",
        manufacturer=MANUFACTURER,
        model="Cont client",
        entry_type=DeviceEntryType.SERVICE,
    )


def _via_account(hass: HomeAssistant, client_id: str, entry_id: str) -> dict[str, Any]:
    """Legătura adresă → cont: `via_device_id` (HA 2026.8+; `via_device` dispare în 2027.8),
    altfel `via_device` (versiunile mai vechi). Dispozitivul contului e înregistrat la setup."""
    identifier = (DOMAIN, f"{client_id}_cont")
    getter = getattr(dr, "async_get_device_id_by_identifier", None)
    if getter is None:
        return {"via_device": identifier}
    try:
        return {"via_device_id": getter(hass, identifier, config_entry_id=entry_id)}
    except ValueError:
        return {}


def address_device(hass: HomeAssistant, entry_id: str, client_id: str, address: dict[str, Any]) -> DeviceInfo:
    """Câte un dispozitiv pentru fiecare adresă cu servicii / facturi, legat de cont."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{client_id}_{address['key']}")},
        name=f"{DEVICE_PREFIX} — {address.get('label') or address['key']}",
        manufacturer=MANUFACTURER,
        model="Adresă de instalare",
        entry_type=DeviceEntryType.SERVICE,
        **_via_account(hass, client_id, entry_id),
    )


class DigiEntity(CoordinatorEntity[DigiCoordinator]):
    """Bază: licență verificată în timp real, numele din traduceri, atribuire."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: DigiCoordinator, client_id: str, translation_key: str, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._client_id = client_id
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{DOMAIN}_{client_id}_{unique_suffix}"

    @property
    def available(self) -> bool:
        # Dacă licența expiră între două reîncărcări, entitatea devine indisponibilă (un text
        # în locul unei valori numerice ar da eroare) până când reload-ul pune „Licență necesară".
        return super().available and license_valid(self.hass)


class DigiAccountEntity(DigiEntity):
    @property
    def device_info(self) -> DeviceInfo:
        return account_device(self._client_id)


class DigiAddressEntity(DigiEntity):
    def __init__(self, coordinator: DigiCoordinator, client_id: str, address_key: str, translation_key: str) -> None:
        super().__init__(coordinator, client_id, translation_key, f"{address_key}_{translation_key}")
        self._key = address_key
        self._address_at_setup = ((coordinator.data or {}).get("addresses") or {}).get(address_key) or {"key": address_key}

    @property
    def _address(self) -> dict[str, Any]:
        return ((self.coordinator.data or {}).get("addresses") or {}).get(self._key) or {}

    @property
    def _invoices(self) -> list[dict[str, Any]]:
        return ((self.coordinator.data or {}).get("invoices") or {}).get(self._key) or []

    @property
    def _services(self) -> dict[str, Any]:
        return ((self.coordinator.data or {}).get("services") or {}).get(self._key) or {}

    @property
    def device_info(self) -> DeviceInfo:
        return address_device(
            self.hass, self.coordinator.config_entry.entry_id, self._client_id, self._address or self._address_at_setup
        )

    @property
    def available(self) -> bool:
        # adresa a dispărut din cont → indisponibilă, nu „necunoscută"
        return super().available and bool(self._address)
