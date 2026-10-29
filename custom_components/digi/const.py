"""Constante pentru integrarea DIGI România."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "digi"
NAME = "DIGI România"
# Prefixul numelor de dispozitive („DIGI — Cont 123", „DIGI — Strada X, Nr. 1")
DEVICE_PREFIX = "DIGI"
MANUFACTURER = "DIGI România"
ATTRIBUTION = "Date furnizate de www.digi.ro"

# ── Site (aplicația MyDigi e un WebView peste aceleași pagini) ──
BASE_URL = "https://www.digi.ro"
LOGIN_PATH = "/auth/login"
USER_INFO_PATH = "/app-user-info-bulk-mobile-xhr"
INVOICES_PATH = "/my-account/invoices"
INVOICE_DETAILS_PATH = "/my-account/invoices/details"
SERVICES_PATH = "/my-account/my-services"
ACCOUNT_DETAILS_PATH = "/my-account/account-details"
# User-Agent-ul aplicației MyDigi 2.1.37 (cu el s-au verificat toate paginile)
USER_AGENT = "Android/MyDigi/2.1.37"

# Taburile „Serviciile mele" citite (acțiunile din my-services-nav-cfg); doar afișare
TAB_OVERVIEW = "digiOverview"
TAB_INTERNET = "digiNetFiberlink"
TAB_TV = "digiTv"

# ── Config entry ──
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_COOKIES = "cookies"
CONF_CLIENT_ID = "client_id"

# ── Licențiere (STANDARD-LICENTA.md) ──
CONF_LICENSE_KEY = "license_key"
LICENSE_DATA_KEY = "digi_license_manager"
LICENSE_PURCHASE_URL = "https://hubinteligent.org/donate?ref=digi"

# ── Rețea / actualizare ──
DEFAULT_TIMEOUT = 30
DEFAULT_SCAN_INTERVAL = timedelta(hours=6)
# Pachetele și echipamentele se schimbă rar: taburile de servicii se citesc o dată pe zi
SERVICES_REFRESH_INTERVAL = timedelta(hours=24)
# Pauză între cererile consecutive către digi.ro (secunde)
REQUEST_PAUSE = 0.3

# ── Facturi ──
ARCHIVE_MONTHS = 12

MONTHS_RO = [
    "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
    "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie",
]

PLATFORMS = ["sensor", "binary_sensor"]
