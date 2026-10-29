"""Citirea paginilor www.digi.ro (HTML, fără API JSON).

Funcții pure, fără rețea — testabile pe pagini salvate. Structura paginilor (confirmată pe un cont
real, 10.2026):

- /auth/login: formularul #form-signin; după login cu 2FA, redirect la /auth/2fa.
- /auth/2fa: acțiunile AJAX ale site-ului stau în <script type="text/template" id="…-cfg"> (JSON:
  {nume: {relUrl, method, params, paramsCfg}}); paramsCfg spune din ce element al paginii se ia
  fiecare parametru (selector jQuery + .val() / .attr()).
- /my-account/invoices: rândurile .my-account-tbl-row (adresă, emisă, tip, scadență, sumă); ID-urile
  tuturor facturilor, în ordinea rândurilor, în <script id="client-invoices-cfg">.
- popup-ul „Vezi factura": număr, total, rest, status, liniile facturii, link PDF.
- /my-account/my-services: adresele (#my-services-address-select) și taburile (my-services-nav-cfg);
  taburile Overview / Internet / TV vin ca fragmente HTML.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from html import unescape
from typing import Any

# Markeri de captcha / verificare anti-bot în formularul de login (azi: niciunul)
CAPTCHA_MARKERS = ("invisible-captcha", "g-recaptcha", 'name="dpxTk"', "h-captcha", "cf-turnstile")

_COMMENTS = re.compile(r"<!--.*?-->", re.S)
_SCRIPTS = re.compile(r"<script\b.*?</script>", re.S | re.I)
_TAG = re.compile(r"<([a-zA-Z][\w-]*)\b([^>]*)>")
_TAG_ATTR = re.compile(r"""([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?""")
_SIMPLE_SELECTOR = re.compile(r"^([a-zA-Z][\w-]*)?(?:#([\w-]+))?((?:\[[^\]]+\])*)$")
_ATTR_COND = re.compile(r"""\[\s*([\w-]+)\s*(?:=\s*["']?([^"'\]]*)["']?)?\s*\]""")


# ─────────────────────────── utilitare text / numere / date ───────────────────────────


def html_text(fragment: str | None) -> str:
    """Textul unui fragment HTML: fără etichete, cu entitățile decodate, spațiile comprimate."""
    if not fragment:
        return ""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def clean_html(html: str) -> str:
    """HTML fără comentarii și scripturi (pagina are elemente vechi comentate, ex. un <input> sau routerul)."""
    return _SCRIPTS.sub("", _COMMENTS.sub("", html or ""))


def to_float(text: Any) -> float | None:
    """„77&period;30 LEI", „1,25 EUR/lună", „1.234,56" → float (zecimalele: ultimul separator)."""
    if isinstance(text, (int, float)):
        return float(text)
    raw = unescape(str(text or ""))
    match = re.search(r"\d[\d.,]*", raw.replace(" ", ""))
    if not match:
        return None
    number = match.group(0).rstrip(".,")
    if "," in number and "." in number:
        if number.rfind(",") > number.rfind("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    elif "," in number:
        number = number.replace(",", ".")
    try:
        return float(number)
    except ValueError:
        return None


def parse_ro_date(text: Any) -> date | None:
    """„06-10-2026" / „01.10.2026" / „06/10/2026" → date."""
    match = re.search(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})", str(text or ""))
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def normalize_tokens(text: str) -> list[str]:
    """Cuvintele unei adrese, fără diacritice și punctuație (pentru potrivirea adreselor)."""
    plain = unicodedata.normalize("NFKD", unescape(text or "")).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", plain.lower())


# ─────────────────────────── elemente, formulare, acțiuni AJAX ───────────────────────────


def _attrs(raw: str) -> dict[str, str]:
    return {k.lower(): unescape(v1 or v2 or v3 or "") for k, v1, v2, v3 in _TAG_ATTR.findall(raw)}


def find_element(html: str, selector: str) -> dict[str, str] | None:
    """Atributele primului element care se potrivește unui selector simplu, ca jQuery:
    tag, #id, [atribut], [atribut="valoare"] și combinațiile lor (ex. input[name="x"])."""
    match = _SIMPLE_SELECTOR.match((selector or "").strip())
    if not match:
        return None
    tag, el_id, attr_part = match.groups()
    conds = _ATTR_COND.findall(attr_part or "")
    if el_id:
        conds.append(("id", el_id))
    html = clean_html(html)
    for found in _TAG.finditer(html):
        if tag and found.group(1).lower() != tag.lower():
            continue
        attrs = _attrs(found.group(2))
        if all(name.lower() in attrs and (not value or attrs[name.lower()] == value) for name, value in conds):
            if found.group(1).lower() == "select":  # valoarea = opțiunea selectată (sau prima)
                block = html[found.end():html.find("</select>", found.end())]
                options = re.findall(r"<option\b([^>]*)>", block, re.I)
                chosen = next((o for o in options if re.search(r"\bselected\b", o)), options[0] if options else "")
                attrs["value"] = _attrs(chosen).get("value", "")
            return attrs
    return None


def templates_json(html: str) -> dict[str, Any]:
    """<script type="text/template" id="…">JSON</script> → {id: obiectul JSON}."""
    out: dict[str, Any] = {}
    for match in re.finditer(r'<script\b[^>]*\btype="text/template"[^>]*\bid="([^"]+)"[^>]*>(.*?)</script>', html or "", re.S):
        try:
            out[match.group(1)] = json.loads(unescape(match.group(2).strip()))
        except ValueError:
            continue
    return out


def find_action(html: str, pattern: str) -> tuple[str, dict[str, Any]] | None:
    """Acțiunea AJAX din template-urile -cfg al cărei nume se potrivește (ex. „2FA.?Send")."""
    for data in templates_json(html).values():
        if not isinstance(data, dict):
            continue
        for name, cfg in data.items():
            if isinstance(cfg, dict) and cfg.get("relUrl") and re.search(pattern, name, re.I):
                return name, cfg
    return None


def resolve_params(cfg: dict[str, Any], html: str, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Parametrii unei acțiuni, exact ca site-ul: `params` + valorile din pagină după `paramsCfg`.

    `overrides`: selector → valoare (ce ar tasta utilizatorul în câmp, ex. codul primit prin SMS).
    """
    overrides = overrides or {}
    params = {k: "" if v is None else str(v) for k, v in (cfg.get("params") or {}).items()}
    for key, spec in (cfg.get("paramsCfg") or {}).items():
        jq = (spec or {}).get("jQuery") or {}
        selector = str(jq.get("selector") or "")
        if selector in overrides:
            params[key] = overrides[selector]
            continue
        nxt = jq.get("next") or {}
        method, args = nxt.get("method"), nxt.get("args") or []
        element = find_element(html, selector)
        if element is None:
            params[key] = ""
        elif method in (None, "val"):
            params[key] = element.get("value", "")
        elif method == "attr" and args:
            params[key] = element.get(str(args[0]).lower(), "")
        elif method == "data" and args:
            params[key] = element.get(f"data-{args[0]}".lower(), "")
        else:
            params[key] = ""
    return params


def action_selectors(cfg: dict[str, Any], word: str) -> list[str]:
    """Selectorii parametrilor acțiunii care conțin `word` în nume sau selector (ex. „code")."""
    out = []
    for key, spec in (cfg.get("paramsCfg") or {}).items():
        selector = str(((spec or {}).get("jQuery") or {}).get("selector") or "")
        if word in key.lower() or word in selector.lower():
            out.append(selector)
    return out


def login_form(html: str) -> dict[str, Any] | None:
    """Formularul de login, ca în browser.

    {"action", "fields" (inputurile cu nume, fără checkbox-urile nebifate, plus butonul de trimitere
    cu nume, cu valoarea lui), "checkboxes" (numele checkbox-urilor nebifate), "password" (numele
    câmpului de parolă), "html"}. Câmpurile de email / parolă / „ține-mă minte" le completează apelantul.
    """
    match = re.search(r'<form\b[^>]*\bid="form-signin"[^>]*>.*?</form>', html or "", re.S | re.I)
    if not match:
        match = re.search(r'<form\b(?:(?!</form>).)*type="password".*?</form>', html or "", re.S | re.I)
    if not match:
        return None
    form_tag = re.match(r"<form\b([^>]*)>", match.group(0), re.I)
    fields: dict[str, str] = {}
    checkboxes: list[str] = []
    password: str | None = None
    for found in _TAG.finditer(clean_html(match.group(0))):
        tag = found.group(1).lower()
        attrs = _attrs(found.group(2))
        name = attrs.get("name")
        if not name or tag not in ("input", "button", "textarea"):
            continue
        kind = attrs.get("type", "submit" if tag == "button" else "text").lower()
        if tag == "input" and kind in ("submit", "button", "image", "reset"):
            continue
        if kind in ("checkbox", "radio") and "checked" not in attrs:
            checkboxes.append(name)
            continue
        if kind == "password":
            password = name
        fields[name] = attrs.get("value", "")
    return {
        "action": _attrs(form_tag.group(1)).get("action") if form_tag else None,
        "fields": fields,
        "checkboxes": checkboxes,
        "password": password,
        "html": match.group(0),
    }


def has_captcha(form_html: str) -> list[str]:
    return [marker for marker in CAPTCHA_MARKERS if marker in (form_html or "")]


def page_messages(html: str) -> list[str]:
    """Mesajele de eroare / informare afișate de site (.msg, .msg-error, .alert)."""
    out = []
    for match in re.finditer(r'<(div|p|span)\b[^>]*class="[^"]*\b(?:msg-error|msg|alert|error-message)\b[^"]*"[^>]*>(.*?)</\1>', clean_html(html), re.S):
        text = html_text(match.group(2))
        if text:
            out.append(text[:300])
    return out


def masked_phone(html: str) -> str | None:
    """Numărul mascat de pe pagina 2FA („Nr tel: *******070")."""
    match = re.search(r"Nr\.?\s*tel[^:<]*:\s*([^<]+)<", html or "")
    return match.group(1).strip() if match else None


def has_code_field(html: str) -> bool:
    return bool(re.search(r'name="[^"]*2fa[^"]*code[^"]*"', clean_html(html), re.I))


# ─────────────────────────── utilizator ───────────────────────────


def user_main(info: Any) -> dict[str, Any]:
    """POST /app-user-info-bulk-mobile-xhr → my-user.main {idclient, email, name, loggedin, type}."""
    if not isinstance(info, dict):
        return {}
    return ((info.get("my-user") or {}).get("main")) or {}


# ─────────────────────────── facturi ───────────────────────────


def parse_invoices(html: str) -> dict[str, Any]:
    """/my-account/invoices → adresele, totalul neplătit și toate facturile (curente + achitate).

    Fiecare factură: id, address_key (ex. „address-Strada_X__Nr__1"), address (eticheta), issued,
    due (date), kind („TELECOMUNICAȚII"), amount (lei), paid. ID-urile facturilor achitate (care
    n-au buton de plată) vin din client-invoices-cfg, în ordinea rândurilor; dacă numărul lor nu
    se potrivește cu rândurile, nu se ghicesc.
    """
    html = html or ""
    addresses = {m.group(1): html_text(m.group(2)) for m in
                 re.finditer(r'<option\b[^>]*\bid="(address-[^"]+)"[^>]*>(.*?)</option>', html, re.S)}
    paid_at = html.find("Facturi achitate")
    rows = list(re.finditer(r'<div class="my-account-tbl-row"[^>]*\bdata-invoice-address="([^"]*)"[^>]*>', html))
    cfg = templates_json(html).get("client-invoices-cfg")
    cfg_ids = [str(item.get("id")) for item in cfg if isinstance(item, dict)] if isinstance(cfg, list) else []
    if len(cfg_ids) != len(rows):
        cfg_ids = []

    invoices: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        end = rows[index + 1].start() if index + 1 < len(rows) else row.end() + 3000
        chunk = html[row.end():end]
        cols = {c: re.search(rf'class="my-account-tbl-col {c}"[^>]*>(.*?)</div>', chunk, re.S)
                for c in ("date", "description", "amount")}
        desc = cols["description"].group(1) if cols["description"] else ""
        due = re.search(r"<span>(.*?)</span>", desc, re.S)
        own_id = re.search(r'data-invoices-id="(\d+)"', chunk)
        key = row.group(1)
        invoices.append({
            "id": own_id.group(1) if own_id else (cfg_ids[index] if cfg_ids else None),
            "address_key": key,
            "address": addresses.get(key) or key.replace("address-", "").replace("__", ", ").replace("_", " "),
            "issued": parse_ro_date(html_text(cols["date"].group(1))) if cols["date"] else None,
            "due": parse_ro_date(html_text(due.group(1))) if due else None,
            "kind": html_text(re.sub(r"<span>.*?</span>", "", desc, flags=re.S)) or None,
            "amount": to_float(html_text(cols["amount"].group(1))) if cols["amount"] else None,
            "paid": paid_at >= 0 and row.start() > paid_at,
        })

    unpaid = re.search(r"Ai\s*<strong>(\d+)</strong>\s*facturi neplătite în valoare de\s*<strong[^>]*>([^<]+)</strong>", html)
    channel = re.search(r"Primești factura DIGI prin ([^.<]+)", html)
    return {
        "addresses": addresses,
        "invoice_channel": html_text(channel.group(1)) if channel else None,
        "unpaid_count": int(unpaid.group(1)) if unpaid else sum(not i["paid"] for i in invoices),
        "unpaid_total": to_float(html_text(unpaid.group(2))) if unpaid else None,
        "invoices": invoices,
        "ids_from_cfg": bool(cfg_ids),
    }


def service_line_label(text: str) -> str:
    """„Ab. Internet, mentenanta si alte servicii cf. … (8.25 EUR)" → „Internet"."""
    label = re.sub(r"^\s*Ab\.\s*", "", text or "").split(",")[0].strip()
    return (label or text or "")[:60]


def parse_invoice_popup(html: str) -> dict[str, Any]:
    """Popup-ul „Vezi factura": titlul „Factura <număr><br>din data de <dată>", liniile facturii
    (.popup-content-item-header: „1 ABONAMENTE…" = grupă, „1.1 Ab. Internet … af. 01.10.2026 -
    31.10.2026 (8.25 EUR)" = serviciu, cu prețul în lei), Total / Rest / Status (.titles-details
    total | remaining | status) și linkul PDF (pdf-download)."""
    html = html or ""
    title = re.search(r"<h4>\s*Factura\s+#?\s*(.*?)<br\s*/?>\s*din data de\s*(.*?)</h4>", html, re.S | re.I)

    def detail(cls: str) -> str | None:
        match = re.search(rf'class="titles titles-details {cls}"[^>]*>.*?<span>(.*?)</span>', html, re.S)
        return html_text(match.group(1)) if match else None

    lines = []
    for name, price in re.findall(
        r'class="popup-content-item-header"[^>]*>(.*?)<span class="popup-content-item-price"[^>]*>(.*?)</span>', html, re.S
    ):
        text = html_text(name)
        number = re.match(r"(\d+(?:\.\d+)*)\s+(.*)", text)
        body = number.group(2) if number else text
        period = re.search(r"af\.\s*(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})", body)
        eur = re.search(r"\(([\d.,]+)\s*EUR\)", body)
        contract = re.search(r"\bcf\.\s*\S+\s+din\s+(\d{2}\.\d{2}\.\d{4})", body)
        lines.append({
            "level": number.group(1).count(".") if number else 0,
            "text": body,
            "label": service_line_label(body),
            "lei": to_float(html_text(price)),
            "eur": to_float(eur.group(1)) if eur else None,
            "period_from": parse_ro_date(period.group(1)) if period else None,
            "period_to": parse_ro_date(period.group(2)) if period else None,
            "contract_date": parse_ro_date(contract.group(1)) if contract else None,
        })
    pdf = re.search(r'href="([^"]*/my-account/invoices/pdf-download[^"]*)"', html)
    return {
        "number": html_text(title.group(1)) if title else None,
        "date": parse_ro_date(html_text(title.group(2))) if title else None,
        "total": to_float(detail("total")),
        "rest": to_float(detail("remaining")),
        "status": detail("status"),
        "lines": lines,
        "has_pdf": bool(pdf),
    }


def parse_account_details(html: str) -> dict[str, Any]:
    """„Administrare cont": nume, cod client, email, telefonul de la autentificarea în doi pași
    (mascat de DIGI) și aplicațiile partenere care pot accesa datele (Pago, Un-Doi …)."""
    html = clean_html(html)

    def field(label: str) -> str | None:
        match = re.search(rf"<strong>\s*{label}\s*:?\s*</strong>\s*([^<]+)", html)
        return (html_text(match.group(1)) or None) if match else None

    email = find_element(html, "#form-my-account-change-email-input") or {}
    phone = re.search(r"logat\s+este:\s*([^<]+)<", html)
    apps = [
        {"name": html_text(label), "enabled": "checked" in _attrs(attrs)}
        for attrs, label in re.findall(
            r'<input\b([^>]*name="form-my-account-apps-input"[^>]*)>.*?<label\b[^>]*>(.*?)</label>', html, re.S
        )
    ]
    return {
        "name": field("Nume"),
        "client_code": field("Cod client"),
        "email": email.get("value") or None,
        "phone": html_text(phone.group(1)) if phone else None,
        "partner_apps": apps,
    }


# ─────────────────────────── servicii ───────────────────────────


def parse_services_page(html: str) -> dict[str, Any]:
    """/my-account/my-services → adresele cu servicii și acțiunile taburilor.

    {"addresses": [{"id": "…", "label": "Strada X nr. 1, Oraș, județul Y"}],
     "tabs": {"digiOverview": {relUrl, params, paramsCfg}, …}}
    """
    html = html or ""
    start = html.find('id="my-services-address-select"')
    block = html[start:html.find("</select>", start)] if start >= 0 else ""
    addresses = [{"id": value, "label": html_text(label)} for value, label in
                 re.findall(r'<option\b[^>]*\bvalue="([^"]*)"[^>]*>(.*?)</option>', block, re.S) if value]
    tabs = templates_json(html).get("my-services-nav-cfg")
    return {"addresses": addresses, "tabs": tabs if isinstance(tabs, dict) else {}}


def no_subscription(html: str) -> bool:
    return "nu există niciun abonament alocat" in html_text(html).lower()


def parse_overview(html: str) -> list[dict[str, Any]]:
    """Tabul Overview: câte un element pe serviciu.

    Activ: tipul („Internet"), pachetul („FiberLink 1000"), detalii („1 echipamente 0 extraopțiuni"),
    tabul lui (data-action). Inactiv (clasa „inactive"): tipul, pachetul propus și „neinstalat".
    """
    html = clean_html(html)
    items = []
    parts = re.split(r'<div class="overview-item(?=[\s"])', html)[1:]
    for part in parts:
        cls = part.split('"', 1)[0]
        types = [html_text(t) for t in re.findall(r'class="overview-item-type"[^>]*>(.*?)</div>', part, re.S)]
        name = re.search(r'class="overview-item-name"[^>]*>(.*?)</div>', part, re.S)
        status = re.search(r'class="overview-item-status"[^>]*>(.*?)</div>', part, re.S)
        action = re.search(r'data-action="([^"]+)"', part)
        if not types:
            continue
        active = "inactive" not in cls
        items.append({
            "type": types[0],
            "active": active,
            "package": html_text(name.group(1)) if name else (types[1] if len(types) > 1 and active else None),
            "status": html_text(status.group(1)) if status else None,
            "action": action.group(1) if action else None,
        })
    return items


def parse_internet(html: str) -> dict[str, Any] | None:
    """Tabul Internet: pachetul, contul PPPoE și (dacă e afișat) echipamentul atașat."""
    if no_subscription(html):
        return None
    html = clean_html(html)
    package = re.search(r'class="my-services-title"[^>]*>\s*<div class="flex[^"]*">\s*<div class="col-6[^"]*">(.*?)</div>', html, re.S)
    account = re.search(r"<strong>\s*Cont:\s*</strong>.*?<p>(.*?)</p>", html, re.S)
    device = re.search(r"<strong>\s*Echipamente atașate:\s*</strong>.*?<p>(.*?)</p>", html, re.S)
    if not package and not account:
        return None
    return {
        "package": html_text(package.group(1)) if package else None,
        "account": html_text(account.group(1)) if account else None,
        "device": html_text(device.group(1)) if device else None,
    }


def parse_tv(html: str) -> dict[str, Any] | None:
    """Tabul TV: echipamentele instalate (decodor + card) și extraopțiunile (active / disponibile)."""
    if no_subscription(html):
        return None
    html = clean_html(html)
    devices: list[str] = []
    start = html.find("Echipamente instalate")
    if start >= 0:
        section = html[start:]
        end = section.find('<div class="popup')
        section = section[:end] if end >= 0 else section[:5000]
        pending = ""
        for paragraph in re.findall(r"<p\b[^>]*>(.*?)</p>", section, re.S):
            text = html_text(re.sub(r"<a\b.*?</a>", " ", paragraph, flags=re.S)).strip(" |")
            if not text:
                continue
            if text.endswith("împerecheat cu"):
                pending = f"{pending} {text}".strip()
                continue
            devices.append(f"{pending} {text}".strip())
            pending = ""
        if pending:
            devices.append(pending)

    options = []
    start = html.find(">Extraopțiuni<")
    if start >= 0:
        section = html[start:]
        stop = section.find('class="my-services-config-nav-link"')
        section = section[:stop] if stop >= 0 else section[:8000]
        for name, button_attrs, button_text, price in re.findall(
            r"<strong>(.*?)</strong>\s*<br>\s*<button\b([^>]*)>(.*?)</button>\s*</div>\s*"
            r'<div class="col-6 col-end[^"]*">\s*<span[^>]*>(.*?)</span>', section, re.S
        ):
            label = html_text(button_text).lower()
            active = "dezactiv" in label or "deactivate" in button_attrs.lower()
            options.append({"name": html_text(name), "price": html_text(price), "active": active})
    if not devices and not options:
        return None
    return {"devices": devices, "extra_options": options}


# ─────────────────────────── potrivirea adreselor ───────────────────────────


def match_address(invoice_label: str, service_labels: dict[str, str]) -> str | None:
    """Adresa din „Serviciile mele" (id) pentru o adresă din pagina de facturi.

    Facturi: „Calea X, Nr. 90, Ap. 17"; servicii: „Calea X nr. 90, ap. 17, Oraș, județul Y" →
    cuvintele facturii sunt începutul celor din servicii. Doar o potrivire unică e acceptată.
    """
    tokens = normalize_tokens(invoice_label)
    if not tokens:
        return None
    prefix = [sid for sid, label in service_labels.items() if normalize_tokens(label)[:len(tokens)] == tokens]
    if len(prefix) == 1:
        return prefix[0]
    contained = [sid for sid, label in service_labels.items() if set(tokens) <= set(normalize_tokens(label))]
    return contained[0] if len(contained) == 1 else None
