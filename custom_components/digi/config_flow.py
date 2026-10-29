"""Config flow pentru DIGI România.

Autentificare în doi pași, ca pe digi.ro / în aplicația MyDigi:
  1. email (sau ID client) și parola;
  2. codul primit prin SMS pe telefonul contului (trimis automat după pasul 1; se poate retrimite).

Fluxuri:
- `user`: adăugarea contului;
- `reauth`: pornit de Home Assistant când sesiunea DIGI expiră — un login nou, deci un cod SMS nou;
- `reconfigure`: schimbarea emailului / parolei din meniul integrării.

Se salvează: emailul, parola (pentru reautentificare) și cookie-urile sesiunii.
OptionsFlow („Configurează"): activarea / vizualizarea licenței.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .api import (
    DigiApiClient,
    DigiCaptchaError,
    DigiCodeWait,
    DigiConnectionError,
    DigiError,
    DigiInvalidAuth,
    DigiInvalidCode,
    TwoFactorChallenge,
    digi_session,
    mask_email,
)
from .const import (
    CONF_CLIENT_ID,
    CONF_COOKIES,
    CONF_LICENSE_KEY,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    LICENSE_DATA_KEY,
    LICENSE_PURCHASE_URL,
    NAME,
)
from .license import LicenseManager

_LOGGER = logging.getLogger(__name__)

CONF_CODE = "code"
CONF_RESEND = "resend"


class DigiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gestionează configurarea prin UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: DigiApiClient | None = None
        self._challenge: TwoFactorChallenge | None = None
        self._username = ""
        self._password = ""
        self._send_error: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DigiOptionsFlow:
        return DigiOptionsFlow()

    # ── clientul fluxului (cookie-uri proprii, sesiunea HTTP a domeniului) ──

    def _new_client(self) -> DigiApiClient:
        self._client = DigiApiClient(digi_session(self.hass))
        return self._client

    # ── pasul 1: login ──

    async def _async_login(self, username: str, password: str) -> str | None:
        """Login + trimiterea codului. Întoarce cheia erorii, „two_factor" sau None (logat fără cod)."""
        client = self._new_client()
        self._username, self._password = username, password
        try:
            self._challenge = await client.async_start_login(username, password)
        except DigiInvalidAuth as err:
            _LOGGER.debug("[Digi] Configurare: login respins pentru %s (%s)", mask_email(username), err)
            return "invalid_auth"
        except DigiCaptchaError as err:
            _LOGGER.warning("[Digi] Formularul de login DIGI cere captcha (%s) — integrarea nu îl ocolește", err)
            return "captcha"
        except DigiConnectionError as err:
            _LOGGER.debug("[Digi] Configurare: digi.ro nu răspunde (%s)", err)
            return "cannot_connect"
        except DigiError as err:
            _LOGGER.warning("[Digi] Configurare: login eșuat — %s", err)
            return "login_failed"
        except Exception:  # noqa: BLE001 — orice altceva trebuie să ajungă în jurnal
            _LOGGER.exception("[Digi] Configurare: eroare neașteptată la login")
            return "unknown"
        if self._challenge is None:
            return None
        self._send_error = await self._async_send_code()
        return "two_factor"

    async def _async_send_code(self) -> str | None:
        assert self._client is not None and self._challenge is not None
        try:
            await self._client.async_send_code(self._challenge)
        except DigiCodeWait:
            return "code_wait"
        except DigiConnectionError:
            return "cannot_connect"
        except DigiError as err:
            _LOGGER.warning("[Digi] Codul SMS nu a putut fi trimis: %s", err)
            return "code_send_failed"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_login(user_input[CONF_USERNAME].strip(), user_input[CONF_PASSWORD])
            if result == "two_factor":
                return await self.async_step_two_factor()
            if result is None:
                return await self._async_finish()
            errors["base"] = result

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=(user_input or {}).get(CONF_USERNAME, "")): str,
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    # ── pasul 2: codul SMS ──

    async def async_step_two_factor(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._client is not None and self._challenge is not None
        errors: dict[str, str] = {}
        if user_input is None:
            if self._send_error:  # SMS-ul nu a plecat la login (ex. „peste 1 minut") — se poate retrimite
                errors["base"], self._send_error = self._send_error, None
        elif user_input.get(CONF_RESEND):
            error = await self._async_send_code()
            if error:
                errors["base"] = error
        else:
            code = "".join((user_input.get(CONF_CODE) or "").split())
            if not code:
                errors["base"] = "code_required"
            elif not self._challenge.form_html:
                errors["base"] = "code_not_sent"
            else:
                try:
                    await self._client.async_verify_code(self._challenge, code)
                except DigiInvalidCode as err:
                    _LOGGER.debug("[Digi] Cod respins: %s", err)
                    errors["base"] = "code_invalid"
                except DigiConnectionError:
                    errors["base"] = "cannot_connect"
                except DigiError as err:
                    _LOGGER.warning("[Digi] Verificarea codului a eșuat: %s", err)
                    errors["base"] = "code_failed"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("[Digi] Eroare neașteptată la verificarea codului")
                    errors["base"] = "unknown"
                else:
                    return await self._async_finish()

        return self.async_show_form(
            step_id="two_factor",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CODE): str,
                    vol.Optional(CONF_RESEND, default=False): bool,
                }
            ),
            description_placeholders={"phone": self._challenge.phone or "telefonul contului"},
            errors=errors,
        )

    # ── finalizare ──

    async def _async_finish(self) -> ConfigFlowResult:
        assert self._client is not None
        try:
            user = await self._client.async_get_user()
        except DigiError as err:
            _LOGGER.warning("[Digi] Datele contului nu au putut fi citite după login: %s", err)
            return self.async_abort(reason="cannot_connect")
        client_id = str(user.get("idclient") or "")
        if not client_id:
            return self.async_abort(reason="unknown")
        data = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_CLIENT_ID: client_id,
            CONF_COOKIES: self._client.export_cookies(),
        }
        _LOGGER.debug("[Digi] Cont autentificat: client %s", f"***{client_id[-3:]}")

        if self.source in (SOURCE_REAUTH, SOURCE_RECONFIGURE):
            entry = self._get_reauth_entry() if self.source == SOURCE_REAUTH else self._get_reconfigure_entry()
            if entry.unique_id and entry.unique_id != client_id:
                return self.async_abort(reason="wrong_account")
            return self.async_update_reload_and_abort(entry, data_updates=data)

        await self.async_set_unique_id(client_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=user.get("email") or self._username or NAME, data=data)

    # ── reautentificare (sesiune expirată) ──

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        _LOGGER.debug("[Digi] Reautentificare: sesiunea DIGI a expirat, e nevoie de un cod SMS nou")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        username = entry.data.get(CONF_USERNAME, "")
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input.get(CONF_PASSWORD) or entry.data.get(CONF_PASSWORD, "")
            result = await self._async_login(username, password)
            if result == "two_factor":
                return await self.async_step_two_factor()
            if result is None:
                return await self._async_finish()
            errors["base"] = result

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            description_placeholders={"username": username},
            errors=errors,
        )

    # ── reconfigurare (din meniul integrării) ──

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_login(user_input[CONF_USERNAME].strip(), user_input[CONF_PASSWORD])
            if result == "two_factor":
                return await self.async_step_two_factor()
            if result is None:
                return await self._async_finish()
            errors["base"] = result

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )


# ── Licență ──

_ETICHETE_TIP_LICENTA = {
    # Tipurile emise de WebAPI (LICENSE_DURATION)
    "perpetual": ("perpetuă", "perpetual"),
    "annual": ("anuală", "annual"),
    "semi_annual": ("semestrială", "semi-annual"),
    "monthly": ("lunară", "monthly"),
}

# Codurile WebAPI /activate + erorile locale → cheile din `options.error`
_ERORI_ACTIVARE = {
    "invalid_key": "license_key_invalid",
    "already_used": "license_already_used",
    "expired_key": "license_key_expired",
    "fingerprint_mismatch": "license_fingerprint_mismatch",
    "network_error": "license_network_error",
    "http_502": "license_network_error",
    "http_503": "license_network_error",  # server temporar ocupat
    "http_504": "license_network_error",
}


def _eticheta_tip_licenta(tip: str | None, is_ro: bool) -> str:
    """Eticheta afișată pentru tipul de licență primit de la server."""
    if not tip:
        return "necunoscut" if is_ro else "unknown"
    ro, en = _ETICHETE_TIP_LICENTA.get(tip, (tip, tip))
    return ro if is_ro else en


def _data(timestamp: float) -> str:
    return dt_util.as_local(dt_util.utc_from_timestamp(timestamp)).strftime("%d.%m.%Y")


def _status_licenta(mgr: LicenseManager, is_ro: bool) -> str:
    """Textul de stare afișat deasupra câmpului pentru cheie."""
    cumpara = f"🛒 {'Obține licență' if is_ro else 'Get a license'}: {LICENSE_PURCHASE_URL}"
    if mgr.status == "licensed":
        tip = _eticheta_tip_licenta(mgr.license_type, is_ro)
        linii = [f"✅ {'Licență activă' if is_ro else 'Active license'} ({tip})"]
        if mgr.license_key_masked:
            linii[0] += f" — {mgr.license_key_masked}"
        if mgr.activated_at:
            linii.append(f"{'Activată la' if is_ro else 'Activated on'}: {_data(mgr.activated_at)}")
        if mgr.license_expires_at:
            linii.append(f"📅 {'Expiră la' if is_ro else 'Expires on'}: {_data(mgr.license_expires_at)}")
        elif mgr.license_type == "perpetual":
            linii.append("Valabilitate: nelimitată (perpetuă)" if is_ro else "Validity: unlimited (perpetual)")
        return "\n".join(linii)
    if mgr.status == "trial":
        zile = mgr.trial_days_remaining
        stare = f"⏳ Evaluare — {zile} zile rămase" if is_ro else f"⏳ Trial — {zile} days remaining"
        return "\n".join([stare, "", cumpara])
    if mgr.status == "expired":
        return "\n".join(["❌ Licență expirată" if is_ro else "❌ License expired", "", cumpara])
    stare = "❌ Fără licență — funcționalitate blocată" if is_ro else "❌ No license — functionality blocked"
    return "\n".join([stare, "", cumpara])


class DigiOptionsFlow(OptionsFlow):
    """Opțiuni: activarea licenței (STANDARD-LICENTA.md)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_licenta()

    async def async_step_licenta(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        is_ro = (self.hass.config.language or "").startswith("ro")

        mgr: LicenseManager | None = self.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        if mgr is None:
            # Intrarea nu rulează (ex. setup eșuat) — managerul se citește din stocare
            mgr = LicenseManager(self.hass)
            await mgr.async_load()

        if user_input is not None:
            cheie = (user_input.get(CONF_LICENSE_KEY) or "").strip()
            if not cheie:
                errors["base"] = "license_key_empty"
            elif len(cheie) < 10:
                errors["base"] = "license_key_invalid"
            else:
                result = await mgr.async_activate(cheie)
                if result.get("success"):
                    persistent_notification.async_create(
                        self.hass,
                        f"Licența {NAME} a fost activată cu succes! "
                        f"Tip: {_eticheta_tip_licenta(mgr.license_type, True)}.",
                        title="Licență activată",
                        notification_id="digi_license_activated",
                    )
                    # Opțiunile rămân neschimbate; managerul reîncarcă singur intrările
                    return self.async_create_entry(data=dict(self.config_entry.options))
                errors["base"] = _ERORI_ACTIVARE.get(result.get("error", ""), "license_server_error")

        return self.async_show_form(
            step_id="licenta",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LICENSE_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                            suffix="DIGI-XXXX-XXXX-XXXX-XXXX",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"license_status": _status_licenta(mgr, is_ro)},
        )
