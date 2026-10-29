"""Clientul HTTP pentru www.digi.ro.

Login ca în browser / aplicația MyDigi: formularul /auth/login, apoi verificarea în doi pași prin
SMS (acțiunile AJAX ale paginii 2FA, executate exact ca site-ul). Sesiunea = cookie-ul
DGROSESSV3PRI; se păstrează în config entry, ca după repornire să nu mai fie nevoie de cod.

Cookie-urile le ține clientul (câte un set pe cont), iar redirecturile se urmează manual, ca
fiecare Set-Cookie să fie preluat. Sesiunea HTTP e una singură pe domeniu, fără cookie jar —
conturile nu se amestecă între ele și nici cu sesiunea comună a Home Assistant.

Un login nou cere mereu cod prin SMS, deci clientul NU se reautentifică niciodată singur: o
sesiune expirată ridică DigiAuthError, iar Home Assistant pornește reautentificarea.

Clientul doar citește: nicio acțiune care schimbă contul (plată, parolă, Wi-Fi, activări).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    ACCOUNT_DETAILS_PATH,
    BASE_URL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    INVOICE_DETAILS_PATH,
    INVOICES_PATH,
    LOGIN_PATH,
    SERVICES_PATH,
    USER_AGENT,
    USER_INFO_PATH,
)
from .parser import (
    action_selectors,
    find_action,
    has_captcha,
    has_code_field,
    login_form,
    masked_phone,
    page_messages,
    resolve_params,
    user_main,
)

_LOGGER = logging.getLogger(__name__)


class DigiError(Exception):
    """Eroare generală DIGI."""


class DigiConnectionError(DigiError):
    """digi.ro nu răspunde (rețea, timeout, HTTP 5xx / 429)."""


class DigiAuthError(DigiError):
    """Sesiunea a expirat sau contul nu e autentificat — e nevoie de login (cu cod SMS)."""


class DigiInvalidAuth(DigiAuthError):
    """Email / ID client sau parolă greșite."""


class DigiCaptchaError(DigiError):
    """Formularul de login cere captcha — integrarea nu îl ocolește."""


class DigiTwoFactorError(DigiError):
    """Pasul cu cod SMS a eșuat."""


class DigiCodeWait(DigiTwoFactorError):
    """Digi nu trimite încă un cod nou („Poți genera un cod nou peste 1 minut!")."""


class DigiInvalidCode(DigiTwoFactorError):
    """Codul introdus a fost respins."""


@dataclass
class TwoFactorChallenge:
    """Pasul 2FA în curs: pagina /auth/2fa și, după trimiterea SMS-ului, formularul pentru cod."""

    url: str
    html: str
    phone: str | None
    form_html: str | None = None


def mask_email(value: str | None) -> str:
    text = str(value or "")
    if "@" not in text:
        return f"{'*' * max(len(text) - 3, 0)}{text[-3:]}" if text else ""
    local, _, domain = text.partition("@")
    return f"{local[:1]}***@{domain}"


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _message(resp: dict[str, Any]) -> str:
    message = resp.get("message")
    if isinstance(message, list):
        return " / ".join(str(m) for m in message)
    if message == "Array":  # PHP: listă de erori afișată ca text — de obicei un parametru lipsă
        return "parametri lipsă sau greșiți"
    return str(message or "")


_SESSION_KEY = f"{DOMAIN}_http_session"
_REDIRECTS = (301, 302, 303, 307, 308)


def digi_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Sesiunea HTTP a domeniului (fără cookie jar); Home Assistant o închide la oprire."""
    session: aiohttp.ClientSession | None = hass.data.get(_SESSION_KEY)
    if session is None or session.closed:
        session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
        hass.data[_SESSION_KEY] = session
    return session


def _expired(morsel: Any) -> bool:
    """Cookie șters de server (Max-Age=0, „deleted" sau Expires în trecut)."""
    if morsel["max-age"] == "0" or morsel.value in ("", "deleted"):
        return True
    if morsel["expires"]:
        try:
            return parsedate_to_datetime(morsel["expires"]) <= datetime.now(UTC)
        except (TypeError, ValueError):
            return False
    return False


class DigiApiClient:
    """Sesiunea unui cont DIGI: cookie-urile proprii + cererile către digi.ro."""

    def __init__(
        self, session: aiohttp.ClientSession, cookies: list[dict[str, Any]] | None = None
    ) -> None:
        self._session = session
        self._cookies: dict[str, str] = {}
        if cookies:
            self.import_cookies(cookies)

    # ── cookie-uri ──

    def export_cookies(self) -> list[dict[str, str]]:
        """Cookie-urile sesiunii, pentru config entry."""
        host = urlparse(BASE_URL).hostname or ""
        return [{"name": k, "value": v, "domain": host, "path": "/"} for k, v in sorted(self._cookies.items())]

    def import_cookies(self, cookies: list[dict[str, Any]]) -> None:
        for cookie in cookies:
            if cookie.get("name"):
                self._cookies[str(cookie["name"])] = str(cookie.get("value", ""))

    def _store_cookies(self, resp: aiohttp.ClientResponse) -> None:
        for name, morsel in resp.cookies.items():
            if _expired(morsel):
                self._cookies.pop(name, None)
            else:
                self._cookies[name] = morsel.value

    # ── cereri ──

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        xhr: bool = False,
        referer: str | None = None,
    ) -> tuple[str, str]:
        """(adresa finală după redirecturi, textul răspunsului)."""
        url = urljoin(BASE_URL, path)
        start_path = urlparse(url).path
        host = urlparse(BASE_URL).hostname
        base_headers = {"User-Agent": USER_AGENT, "Accept-Language": "ro-RO,ro;q=0.9"}
        if xhr:
            base_headers.update({
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-Protection": "1",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            })
        if referer:
            base_headers["Referer"] = referer
        started = time.monotonic()
        try:
            for _ in range(10):
                headers = dict(base_headers)
                if self._cookies:
                    headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
                async with self._session.request(
                    method,
                    url,
                    data=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                    allow_redirects=False,
                ) as resp:
                    self._store_cookies(resp)
                    location = resp.headers.get("Location")
                    if resp.status in _REDIRECTS and location:
                        url = urljoin(url, location)
                        if urlparse(url).hostname != host:
                            raise DigiError(f"{start_path}: redirect în afara digi.ro ({urlparse(url).hostname})")
                        if resp.status in (301, 302, 303):
                            method, data = "GET", None
                        continue
                    text = await resp.text(errors="replace")
                    final, status = url, resp.status
                    break
            else:
                raise DigiError(f"{start_path}: prea multe redirecturi")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("[Digi] %s %s → %s", method, start_path, type(err).__name__)
            raise DigiConnectionError(f"{start_path}: {type(err).__name__}") from err
        _LOGGER.debug(
            "[Digi] %s → HTTP %s %s (%.1f s, %d caractere)",
            start_path,
            status,
            urlparse(final).path,
            time.monotonic() - started,
            len(text),
        )
        if status >= 500 or status in (408, 429):
            raise DigiConnectionError(f"{start_path}: HTTP {status}")
        if status >= 400:
            raise DigiError(f"{start_path}: HTTP {status}")
        return final, text

    @staticmethod
    def _ensure_session(final_url: str) -> None:
        """Paginile contului redirecționează la /auth/… când sesiunea nu mai e validă."""
        path = urlparse(final_url).path
        if path.startswith("/auth/"):
            raise DigiAuthError(f"sesiunea DIGI nu mai e validă (redirect la {path})")

    # ── login + cod SMS ──

    async def async_start_login(self, username: str, password: str) -> TwoFactorChallenge | None:
        """Trimite formularul de login. None = autentificat direct; altfel pasul cu cod SMS."""
        self._cookies.clear()
        page_url, html = await self._request("GET", LOGIN_PATH)
        form = login_form(html)
        if form is None:
            raise DigiError("formularul de login nu a fost găsit pe /auth/login")
        markers = has_captcha(form["html"])
        if markers:
            raise DigiCaptchaError(", ".join(markers))

        data = dict(form["fields"])
        email_field = next((n for n in data if "email" in n.lower()), "signin-input-email")
        data[email_field] = username
        data[form["password"] or "signin-input-password"] = password
        remember = next((n for n in form["checkboxes"] if "remember" in n.lower()), None)
        if remember:  # „ține-mă minte": sesiunea trebuie să supraviețuiască între actualizări
            data[remember] = "1"
        _LOGGER.debug("[Digi] Login pentru %s", mask_email(username))
        final, html = await self._request(
            "POST", urljoin(page_url, form["action"] or LOGIN_PATH), data=data, referer=page_url
        )
        path = urlparse(final).path
        if path.startswith("/auth/2fa"):
            challenge = TwoFactorChallenge(url=final, html=html, phone=masked_phone(html))
            _LOGGER.debug("[Digi] Login acceptat — urmează codul prin SMS (telefon %s)", challenge.phone)
            return challenge
        if path.startswith("/auth/login"):
            messages = page_messages(html)
            raise DigiInvalidAuth(messages[0] if messages else "login respins")
        if await self.async_logged_in():
            _LOGGER.debug("[Digi] Login reușit fără cod SMS")
            return None
        raise DigiError(f"login neconfirmat (pagina {path})")

    async def async_send_code(self, challenge: TwoFactorChallenge) -> None:
        """„Trimite SMS": acțiunea myAccount2FASend de pe pagina 2FA (telefonul = hash-ul din pagină).

        Răspunsul e formularul pentru cod (cu acțiunea de verificare), salvat în challenge.form_html.
        Dacă Digi cere o pauză, formularul anterior rămâne valabil (codul deja trimis nu expiră încă).
        """
        action = find_action(challenge.html, r"2FA.?Send")
        if action is None:
            raise DigiTwoFactorError("acțiunea de trimitere a codului lipsește din pagina 2FA")
        _, cfg = action
        params = resolve_params(cfg, challenge.html)
        _, text = await self._request(
            (cfg.get("method") or "POST").upper(),
            urljoin(challenge.url, cfg["relUrl"]),
            data=params,
            xhr=True,
            referer=challenge.url,
        )
        resp = _json(text)
        fragment: str | None = text
        if isinstance(resp, dict):
            if resp.get("success") is False:
                raise DigiTwoFactorError(_message(resp) or "trimiterea codului a fost refuzată")
            message = str(resp.get("message") or "")
            fragment = message if "<form" in message else None
        if not fragment or not has_code_field(fragment):
            messages = page_messages(fragment or "")
            if messages:
                _LOGGER.debug("[Digi] Codul nu a fost retrimis: %s", messages[0])
                raise DigiCodeWait(messages[0])
            raise DigiTwoFactorError("formularul pentru cod nu a venit în răspuns")
        challenge.form_html = fragment
        _LOGGER.debug("[Digi] Cod trimis prin SMS (telefon %s)", challenge.phone)

    async def async_verify_code(self, challenge: TwoFactorChallenge, code: str) -> None:
        """Verifică codul (acțiunea myAccount2FAVerify din formularul primit) și confirmă sesiunea."""
        if not challenge.form_html:
            raise DigiTwoFactorError("codul nu a fost cerut încă")
        action = find_action(challenge.form_html, r"2FA.?(Verify|Valid|Confirm)")
        if action is None:
            raise DigiTwoFactorError("acțiunea de verificare a codului lipsește")
        _, cfg = action
        overrides = {selector: code for selector in action_selectors(cfg, "code")}
        params = resolve_params(cfg, challenge.form_html, overrides)
        if not overrides:
            params["code"] = code
        _, text = await self._request(
            (cfg.get("method") or "POST").upper(),
            urljoin(challenge.url, cfg["relUrl"]),
            data=params,
            xhr=True,
            referer=challenge.url,
        )
        resp = _json(text)
        if not isinstance(resp, dict):
            raise DigiTwoFactorError("răspuns neașteptat la verificarea codului")
        if not resp.get("success"):
            raise DigiInvalidCode(_message(resp) or "cod respins")
        target = str(resp.get("message") or "")
        if target.startswith(("/", "http")):
            # pagina de continuare (alegerea adresei pentru magazin) — doar deschisă, ca în browser
            try:
                await self._request("GET", urljoin(BASE_URL, target), referer=challenge.url)
            except DigiError as err:
                _LOGGER.debug("[Digi] Pagina de după cod nu s-a deschis: %s", err)
        if not await self.async_logged_in():
            raise DigiTwoFactorError("codul a fost acceptat, dar sesiunea nu e activă")
        _LOGGER.debug("[Digi] Cod acceptat — sesiune activă")

    # ── date ──

    async def async_user_info(self) -> dict[str, Any]:
        """my-user.main: idclient, email, name, loggedin, type."""
        _, text = await self._request("POST", USER_INFO_PATH, data={}, xhr=True, referer=f"{BASE_URL}/")
        return user_main(_json(text))

    async def async_logged_in(self) -> bool:
        return bool((await self.async_user_info()).get("loggedin"))

    async def async_get_user(self) -> dict[str, Any]:
        """Datele utilizatorului; DigiAuthError dacă sesiunea nu mai e activă."""
        user = await self.async_user_info()
        if not user.get("loggedin"):
            raise DigiAuthError("sesiunea DIGI a expirat (utilizator neautentificat)")
        return user

    async def async_get_invoices_page(self) -> str:
        final, html = await self._request("GET", INVOICES_PATH)
        self._ensure_session(final)
        return html

    async def async_get_invoice_details(self, invoice_id: str) -> str:
        """Popup-ul „Vezi factura" — exact cererea din pagină: POST {url, id}."""
        path = f"{INVOICE_DETAILS_PATH}?invoice_id={invoice_id}"
        final, html = await self._request(
            "POST", path, data={"url": path, "id": invoice_id}, xhr=True, referer=urljoin(BASE_URL, INVOICES_PATH)
        )
        self._ensure_session(final)
        return html

    async def async_get_account_details_page(self) -> str:
        final, html = await self._request("GET", ACCOUNT_DETAILS_PATH)
        self._ensure_session(final)
        return html

    async def async_get_services_page(self) -> str:
        final, html = await self._request("GET", SERVICES_PATH)
        self._ensure_session(final)
        return html

    async def async_get_service_tab(self, cfg: dict[str, Any], page_html: str, address_id: str) -> str:
        """Un tab din „Serviciile mele" (Overview, Internet, TV) pentru o adresă — ca la click pe tab."""
        overrides = {selector: address_id for selector in action_selectors(cfg, "address")}
        params = resolve_params(cfg, page_html, overrides)
        final, html = await self._request(
            (cfg.get("method") or "POST").upper(),
            cfg["relUrl"],
            data=params,
            xhr=True,
            referer=urljoin(BASE_URL, SERVICES_PATH),
        )
        self._ensure_session(final)
        return html
