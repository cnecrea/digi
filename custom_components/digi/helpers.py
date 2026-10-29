"""Utilitare pentru integrarea DIGI România: formatări în română și calcule pe facturi."""

from __future__ import annotations

from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

from .const import ARCHIVE_MONTHS, MONTHS_RO

# Scadențele DIGI sunt zile din calendarul României
RO_TZ = ZoneInfo("Europe/Bucharest")


def today_ro() -> date:
    return dt_util.now().astimezone(RO_TZ).date()


def format_amount(value: Any) -> str:
    """19.99 → „19,99 lei"; 1234.5 → „1.234,50 lei"."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    text = f"{number:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} lei"


def format_eur(value: Any) -> str | None:
    try:
        return f"{float(value):.2f}".replace(".", ",") + " EUR"
    except (TypeError, ValueError):
        return None


def format_date(value: date | None) -> str | None:
    return value.strftime("%d.%m.%Y") if value else None


def month_label(value: date | None) -> str:
    return f"{MONTHS_RO[value.month - 1]} {value.year}" if value else "Fără dată"


def days_word(days: int) -> str:
    return "1 zi" if abs(days) == 1 else f"{abs(days)} zile"


# ── facturi ──


def invoice_rest(invoice: dict[str, Any]) -> float:
    """Cât mai e de plată: „Rest" din detalii (ține cont de plățile parțiale), altfel suma facturii."""
    details = invoice.get("details") or {}
    if details.get("rest") is not None:
        return float(details["rest"])
    return 0.0 if invoice.get("paid") else float(invoice.get("amount") or 0.0)


def invoice_total(invoice: dict[str, Any]) -> float | None:
    details = invoice.get("details") or {}
    total = details.get("total")
    return float(total) if total is not None else invoice.get("amount")


def unpaid_invoices(invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [inv for inv in invoices if not inv.get("paid") and invoice_rest(inv) > 0]


def is_overdue(invoice: dict[str, Any], today: date) -> bool:
    """Restantă = neplătită și cu scadența depășită (din ziua de după scadență)."""
    due = invoice.get("due")
    return bool(due and due < today and not invoice.get("paid") and invoice_rest(invoice) > 0)


def invoice_label(invoice: dict[str, Any]) -> str:
    """Eticheta unei facturi în atribute: numărul real (din detalii) sau data emiterii."""
    number = (invoice.get("details") or {}).get("number")
    if number:
        return f"Factura {number}"
    return f"Factura din {format_date(invoice.get('issued')) or '?'}"


def due_text(invoice: dict[str, Any], today: date) -> str:
    """„19,99 lei, scadentă pe 31.10.2026 (peste 2 zile)" / „…, termen depășit cu 3 zile"."""
    amount = format_amount(invoice_rest(invoice))
    due = invoice.get("due")
    if not due:
        return f"{amount}, fără dată de scadență"
    days = (due - today).days
    if days < 0:
        return f"{amount}, scadentă pe {format_date(due)} (termen depășit cu {days_word(days)})"
    if days == 0:
        return f"{amount}, scadentă astăzi"
    return f"{amount}, scadentă pe {format_date(due)} (peste {days_word(days)})"


def latest_invoice(invoices: list[dict[str, Any]]) -> dict[str, Any] | None:
    dated = [inv for inv in invoices if inv.get("issued")]
    return max(dated, key=lambda inv: inv["issued"]) if dated else (invoices[0] if invoices else None)


def archive_start(today: date) -> date:
    """Prima zi a lunii de acum ARCHIVE_MONTHS - 1 luni (ultimele 12 luni, inclusiv cea curentă)."""
    month_index = today.year * 12 + today.month - 1 - (ARCHIVE_MONTHS - 1)
    return date(month_index // 12, month_index % 12 + 1, 1)


def archive_invoices(invoices: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    start = archive_start(today)
    items = [inv for inv in invoices if inv.get("issued") and inv["issued"] >= start]
    return sorted(items, key=lambda inv: inv["issued"], reverse=True)


def service_line(invoice: dict[str, Any] | None, *keywords: str) -> dict[str, Any] | None:
    """Linia de serviciu din detaliile facturii (ex. „Internet", „Cablu TV") după cuvinte cheie."""
    for line in ((invoice or {}).get("details") or {}).get("lines") or []:
        if line.get("level", 0) >= 1 and any(k in (line.get("label") or "").lower() for k in keywords):
            return line
    return None


def latest_service_line(invoices: list[dict[str, Any]], *keywords: str) -> dict[str, Any] | None:
    """Linia serviciului din cea mai recentă factură care are detalii și conține serviciul."""
    for invoice in sorted((i for i in invoices if i.get("issued")), key=lambda i: i["issued"], reverse=True):
        line = service_line(invoice, *keywords)
        if line:
            return line
    return None


def has_service(services: dict[str, Any], key: str, overview_type: str) -> bool:
    """Serviciul e instalat: are tab citit (internet / tv) sau apare activ în Overview."""
    if services.get(key):
        return True
    return any(o.get("active") and (o.get("type") or "").lower() == overview_type for o in services.get("overview") or [])


def mask(value: Any, keep: int = 3) -> str:
    """Identificator mascat pentru diagnostic / jurnal: „*****336"."""
    text = str(value or "")
    return f"{'*' * max(len(text) - keep, 0)}{text[-keep:]}" if text else ""
