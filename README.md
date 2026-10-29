# DIGI România — Integrare Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/cnecrea/digi)](https://github.com/cnecrea/digi/releases)
[![GitHub Stars](https://img.shields.io/github/stars/cnecrea/digi?style=flat&logo=github)](https://github.com/cnecrea/digi/stargazers)
[![Instalări](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/digi/main/statistici/shields/descarcari.json)](https://github.com/cnecrea/digi)
[![Ultima versiune](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/digi/main/statistici/shields/ultima_release.json)](https://github.com/cnecrea/digi/releases/latest)

Integrare custom pentru [Home Assistant](https://www.home-assistant.io/) care monitorizează contul tău [DIGI](https://www.digi.ro/) — același cont pe care îl folosești pe digi.ro sau în aplicația mobilă **MyDigi**.

Integrarea oferă un dispozitiv pentru cont (totalul de plată pe toate adresele și datele clientului) și câte un dispozitiv pentru fiecare adresă la care ai servicii DIGI: facturi, scadențe, facturi restante, arhiva facturilor și pachetele de internet și televiziune. Doar citește informațiile din cont: nu plătește facturi și nu modifică nimic.

---

## Ce face integrarea

- **Descoperire automată** a adreselor din cont — fiecare adresă devine un dispozitiv separat, legat de dispozitivul contului
- **Total de plată** — pe cont (ca „Ai N facturi neplătite în valoare de…” de pe digi.ro) și pe fiecare adresă, cu fiecare factură neplătită și scadența ei
- **Factură restantă** — senzor binar „Da / Nu” pe fiecare adresă: „Da” cât timp ai o factură neplătită, cu suma, scadența și zilele până la scadență (negative după ce a trecut)
- **Date client** — codul de client, numele, emailul, tipul clientului, telefonul de la autentificarea în doi pași (mascat), cum primești factura, adresele și aplicațiile partenere cu acces la date
- **Ultima factură** — numărul facturii, data emiterii, scadența, perioada facturată, statusul, restul de plată și fiecare serviciu facturat (ex. „Internet — 43,98 lei (8,25 EUR)”)
- **Arhiva facturilor** — ultimele 12 luni, câte o lună pe atribut, plus totalul și media lunară
- **Pachetele instalate** — internet (pachet, cont PPPoE) și televiziune (pachet, echipamente, extraopțiuni active), cu abonamentul lunar în EUR și data contractului, luate din factură
- **Servicii active** — ce servicii DIGI ai la fiecare adresă (internet, TV, mobil, DIGI TV, HBO Max, SkyShowtime, DIGI Storage)
- **Adrese și servicii noi** apar automat — integrarea se reîncarcă singură când apare o adresă sau un serviciu nou în cont
- **Autentificare cu cod prin SMS**, ca pe digi.ro — codul se cere doar la configurare și când expiră sesiunea DIGI
- **Sesiune păstrată** — după o repornire a Home Assistant nu mai e nevoie de cod
- **Reautentificare și reconfigurare** din interfață, fără a șterge integrarea
- **Diagnostic** fără date personale (fără email, nume, adrese, numere de factură, cont PPPoE sau serii de echipamente)
- **Sistem de licență** — testare gratuită 30 de zile; fără licență validă se afișează doar senzorul „Licență necesară”

---

## Sursa datelor

DIGI nu are un API public: integrarea citește paginile contului de pe www.digi.ro (aceleași pe care le afișează și aplicația MyDigi), doar prin cereri de citire.

| Pagina | Ce se citește |
|--------|---------------|
| `/app-user-info-bulk-mobile-xhr` | Datele utilizatorului (ID client, email) — confirmă că sesiunea e activă |
| `/my-account/invoices` | Toate facturile (curente și achitate), cu adresa, data emiterii, scadența și suma |
| `/my-account/invoices/details` | „Vezi factura” — numărul facturii, totalul, restul, statusul și serviciile facturate |
| `/my-account/account-details` | „Administrare cont” — numele, codul de client, emailul, telefonul 2FA (mascat), aplicațiile partenere |
| `/my-account/my-services` | Adresele cu servicii și taburile Overview, Internet și TV ale fiecărei adrese |

**Actualizare:**

- la fiecare **6 ore**: datele utilizatorului, pagina de facturi și detaliile facturilor neplătite + ale ultimei facturi de pe fiecare adresă (detaliile facturilor achitate se citesc o singură dată);
- o dată pe **zi**: serviciile — pentru fiecare adresă, tabul Overview și, doar pentru serviciile instalate, tabul Internet / TV — și pagina „Administrare cont”.

**Autentificarea** se face ca pe digi.ro: email (sau ID client) și parolă, apoi un cod de 6 cifre primit prin SMS pe telefonul contului. Sesiunea DIGI (un cookie) se păstrează în Home Assistant. Când DIGI o închide, integrarea **nu** se autentifică singură — fiecare autentificare ar trimite un SMS — ci îți cere să reconectezi contul (vezi mai jos).

---

## Instalare

### HACS (recomandat)

1. Deschide HACS în Home Assistant
2. Click pe cele 3 puncte (⋮) din colțul dreapta sus → **Custom repositories**
3. Adaugă URL-ul: `https://github.com/cnecrea/digi`
4. Categorie: **Integration**
5. Click **Add** → găsește „DIGI România” → **Install**
6. Restartează Home Assistant

### Manual

1. Copiază folderul `custom_components/digi/` în directorul `config/custom_components/` din Home Assistant
2. Restartează Home Assistant

---

## Configurare

### Pasul 1 — Adaugă integrarea

1. **Setări** → **Dispozitive și Servicii** → **Adaugă Integrare**
2. Caută „**DIGI România**”
3. Completează datele contului:

| Câmp | Descriere |
|------|-----------|
| **Email sau ID client** | Datele cu care intri pe digi.ro sau în aplicația MyDigi |
| **Parola** | Parola contului DIGI — se păstrează local, în Home Assistant, și e folosită doar la reconectarea contului |

### Pasul 2 — Codul primit prin SMS

După pasul 1, DIGI trimite un cod de 6 cifre pe telefonul contului (formularul îți arată numărul mascat, ex. `*******123`).

- Introdu codul și apasă **Trimite** — codul expiră în **2 minute**.
- Nu l-ai primit? Bifează **Trimite din nou codul** și apasă **Trimite**. DIGI permite un cod nou după un minut; dacă ceri prea devreme, formularul îți spune să mai aștepți.

Adresele și serviciile contului sunt descoperite automat.

### Pasul 3 — Licență

Integrarea poate fi testată gratuit **30 de zile**. După aceea are nevoie de o licență, de forma `DIGI-XXXX-XXXX-XXXX-XXXX`, pe care o obții de la [hubinteligent.org/donate?ref=digi](https://hubinteligent.org/donate?ref=digi).

Licența se introduce din **Setări** → **Dispozitive și Servicii** → **DIGI România** → **Configurare** (⚙️) → câmpul **Cheie de licență**. Tot acolo vezi starea licenței (evaluare, activă, expirată).

### Reconectare când expiră sesiunea

Când sesiunea DIGI expiră, actualizările se opresc și Home Assistant îți cere să **reconectezi contul** (notificare de reautentificare):

1. Deschide notificarea → **Reconfigurare**
2. Apasă **Trimite** (completează parola doar dacă ai schimbat-o între timp)
3. Introdu codul primit prin SMS → actualizările se reiau; entitățile și istoricul rămân

### Reconfigurare (opțional)

Dacă ți-ai schimbat emailul sau parola DIGI: **Setări** → **Dispozitive și Servicii** → **DIGI România** → meniul (⋮) → **Reconfigurare** → datele noi + codul SMS.

---

## Entități create

Integrarea creează:

- un dispozitiv **DIGI — Cont {ID client}**, cu senzorii „Total de plată” și „Date client”;
- câte un dispozitiv **DIGI — {adresă}** pentru fiecare adresă, cu 5–7 entități.

Entity ID-urile de mai jos sunt cele generate de Home Assistant în limba română, pentru clientul `12345678` și adresa „Strada Exemplu, Nr. 1”. Pe o instalare în engleză, ID-urile sunt generate din numele englezești (ex. `…_total_due`).

### Dispozitivul contului

| Entitate | Entity ID | Valoare principală |
|----------|-----------|-------------------|
| `Total de plată` | `sensor.digi_cont_12345678_total_de_plata` | Suma de plată pe toate adresele (lei) |
| `Date client` | `sensor.digi_cont_12345678_date_client` | Codul de client |

### Dispozitivul adresei

| Entitate | Entity ID | Valoare principală | Când apare |
|----------|-----------|-------------------|------------|
| `Total de plată` | `sensor.digi_strada_exemplu_nr_1_total_de_plata` | Suma de plată pe adresă (lei) | Mereu |
| `Factură restantă` | `binary_sensor.digi_strada_exemplu_nr_1_factura_restanta` | Da / Nu | Mereu |
| `Ultima factură` | `sensor.digi_strada_exemplu_nr_1_ultima_factura` | Totalul ultimei facturi (lei) | Mereu |
| `Arhivă facturi` | `sensor.digi_strada_exemplu_nr_1_arhiva_facturi` | Numărul facturilor din ultimele 12 luni | Mereu |
| `Internet` | `sensor.digi_strada_exemplu_nr_1_internet` | Pachetul (ex. `FiberLink 1000`) | Internet instalat |
| `Televiziune` | `sensor.digi_strada_exemplu_nr_1_televiziune` | Pachetul (ex. `Digital`) | TV instalat |
| `Servicii active` | `sensor.digi_strada_exemplu_nr_1_servicii_active` | Numărul serviciilor instalate | Adresa apare în „Serviciile mele” |

O adresă care apare doar în facturi (ex. servicii reziliate) primește doar senzorii de facturi.

### Licență

| Entitate | Entity ID | Când apare |
|----------|-----------|------------|
| `Licență necesară` | `sensor.digi_licenta_{id_intrare}` | Doar când licența (sau perioada de evaluare) nu este validă — atunci este singura entitate |

---

## Detalii senzori

Atributele sunt în română și se folosesc în șabloane cu numele lor exact, ex. `state_attr('…', 'Zile până la scadență')`. Atributele fără valoare nu se afișează.

### Senzor: Total de plată (cont)

**Valoare principală**: suma de plată pe toate adresele, în lei — aceeași cu „Ai N facturi neplătite în valoare de…” de pe digi.ro.

| Atribut | Exemplu |
|---------|---------|
| `Facturi neplătite` | `2` |
| `{adresă}` (câte unul pentru fiecare adresă cu sumă de plată) | `45,10 lei` |
| `Facturi cu scadența depășită` (doar dacă există) | `1` |
| `Următoarea scadență` | `31.10.2026` |
| `Zile până la scadență` | `2` (negativ după scadență) |

### Senzor: Date client

**Valoare principală**: codul de client DIGI.

| Atribut | Exemplu |
|---------|---------|
| `Nume` | `POPESCU ION` |
| `Email` | `client@exemplu.ro` |
| `Tip client` | `Persoană fizică` |
| `Telefon autentificare` | `*******123` (numărul pe care primești codul SMS, mascat de DIGI) |
| `Factura se primește prin` | `email` |
| `Adrese` | `2` |
| `Adresa 1`, `Adresa 2`… | `Strada Exemplu nr. 1, Oraș, județul Exemplu` |
| `Servicii active` | `3` (pe toate adresele) |
| `Aplicații cu acces la date` | `Pago` / `niciuna` |

Datele clientului se actualizează o dată pe zi.

### Senzor: Total de plată (adresă)

**Valoare principală**: suma de plată pentru adresă, în lei (restul de plată al fiecărei facturi neplătite — ține cont de plățile parțiale).

| Atribut | Exemplu |
|---------|---------|
| `Factura FDB26 1234567` (câte unul pe factură neplătită) | `45,10 lei, scadentă pe 31.10.2026 (peste 2 zile)` |
| `Facturi neplătite` | `1` |
| `Următoarea scadență` | `31.10.2026` |
| `Zile până la scadență` | `2` (negativ după scadență) |

### Senzor binar: Factură restantă

**Valoare principală**: `Da` cât timp adresa are cel puțin o factură neplătită, altfel `Nu`. La „Nu” nu are atribute.

| Atribut | Exemplu |
|---------|---------|
| `Factura FDB26 1234567` (câte unul pe factură neplătită) | `45,10 lei, scadentă pe 31.10.2026 (peste 2 zile)` / `…, termen depășit cu 3 zile` |
| `Total restant` | `45,10 lei` |
| `Facturi neachitate` | `1` |
| `Următoarea scadență` | `31.10.2026` |
| `Zile până la scadență` | `2` (negativ după scadență) |

### Senzor: Ultima factură

**Valoare principală**: totalul celei mai recente facturi a adresei, în lei.

| Atribut | Exemplu |
|---------|---------|
| `Număr factură` | `FDB26 1234567` |
| `Data emiterii` | `06.10.2026` |
| `Scadență` | `31.10.2026` |
| `Perioadă facturată` | `01.10.2026 – 31.10.2026` |
| `Status` | `Neachitată` / `Achitată` |
| `Rest de plată` | `45,10 lei` |
| `{serviciu}` (câte unul pe serviciu facturat) | `Internet` → `43,98 lei (8,25 EUR)` |

### Senzor: Arhivă facturi

**Valoare principală**: numărul facturilor adresei din ultimele 12 luni (inclusiv luna curentă).

| Atribut | Exemplu |
|---------|---------|
| `{lună} {an}` (câte unul pe factură) | `Octombrie 2026` → `45,10 lei · neachitată` |
| `Total 12 luni` | `540,20 lei` |
| `Medie lunară` | `45,02 lei` |

### Senzor: Internet

**Valoare principală**: pachetul de internet (ex. `FiberLink 1000`).

| Atribut | Exemplu |
|---------|---------|
| `Cont PPPoE` | `AB000000000` |
| `Echipament` (dacă DIGI îl afișează) | `Router …` |
| `Abonament` | `8,25 EUR/lună` (din ultima factură) |
| `Contract din` | `16.05.2023` |

### Senzor: Televiziune

**Valoare principală**: pachetul TV (ex. `Digital`).

| Atribut | Exemplu |
|---------|---------|
| `Echipament` (sau `Echipament 1`, `Echipament 2`…) | `DIGI SMART IRDETO, serie … împerecheat cu Smart Card, serie …` |
| `Extraopțiuni active` | `HBO, Film Now` / `niciuna` |
| `Abonament` | `6,25 EUR/lună` (din ultima factură) |
| `Contract din` | `31.05.2023` |

### Senzor: Servicii active

**Valoare principală**: câte servicii sunt instalate la adresă.

| Atribut | Exemplu |
|---------|---------|
| `Internet` | `FiberLink 1000` |
| `Televiziune` | `Digital` |
| `Mobil`, `DIGI TV`, `HBO Max`, `SkyShowtime`, `DIGI Storage` | `neinstalat` |

### Senzor: Licență necesară

Apare doar când licența nu este validă; în acest caz celelalte entități sunt eliminate până la activarea licenței.

| Stare | Semnificație |
|-------|--------------|
| `Trial — N zile rămase` | Perioadă de evaluare |
| `Trial expirat` | Perioada de evaluare s-a încheiat |
| `Licență expirată` | Licența a expirat |
| `Licență necesară` | Fără licență |

**Atribute**: `nr_identificare`, `status_licență`, `zile_trial_rămase` (în evaluare), `informații`.

---

## Exemple de automatizări

### Notificare cu 3 zile înainte de scadență

```yaml
automation:
  - alias: "DIGI — factură aproape de scadență"
    trigger:
      - platform: template
        value_template: >
          {{ state_attr('sensor.digi_cont_12345678_total_de_plata', 'Zile până la scadență') | int(99) <= 3 }}
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "Factura DIGI e aproape de scadență"
          message: >
            De plată: {{ states('sensor.digi_cont_12345678_total_de_plata') }} lei,
            scadență {{ state_attr('sensor.digi_cont_12345678_total_de_plata', 'Următoarea scadență') }}.
```

### Alertă când scadența a trecut și factura nu e plătită

```yaml
automation:
  - alias: "DIGI — factură restantă"
    trigger:
      - platform: template
        value_template: >
          {{ is_state('binary_sensor.digi_strada_exemplu_nr_1_factura_restanta', 'on')
             and state_attr('binary_sensor.digi_strada_exemplu_nr_1_factura_restanta', 'Zile până la scadență') | int(0) < 0 }}
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "Factură DIGI cu scadența depășită"
          message: >
            De plată: {{ state_attr('binary_sensor.digi_strada_exemplu_nr_1_factura_restanta', 'Total restant') }},
            scadența a fost {{ state_attr('binary_sensor.digi_strada_exemplu_nr_1_factura_restanta', 'Următoarea scadență') }}.
```

În automatizări, senzorul binar are stările `on` (Da) și `off` (Nu).

### Card pentru Dashboard

```yaml
type: entities
title: DIGI
entities:
  - entity: sensor.digi_cont_12345678_total_de_plata
    name: Total de plată
  - type: attribute
    entity: sensor.digi_cont_12345678_total_de_plata
    attribute: Următoarea scadență
    name: Următoarea scadență
  - entity: binary_sensor.digi_strada_exemplu_nr_1_factura_restanta
    name: Factură restantă
  - entity: sensor.digi_strada_exemplu_nr_1_ultima_factura
    name: Ultima factură
  - entity: sensor.digi_strada_exemplu_nr_1_internet
    name: Internet
```

---

## Structura fișierelor

```
custom_components/digi/
├── __init__.py          # Setup/unload integrare, manager licență (runtime_data pattern)
├── api.py               # Client read-only — login cu cod SMS, cookie-urile sesiunii, paginile contului
├── binary_sensor.py     # Factură restantă (factură neplătită)
├── config_flow.py       # ConfigFlow (adăugare + cod SMS, reautentificare, reconfigurare) + OptionsFlow (licență)
├── const.py             # Constante, adrese, intervale
├── coordinator.py       # DataUpdateCoordinator — facturi la 6 ore, servicii zilnic, adresele contului
├── diagnostics.py       # Export diagnostic fără date personale
├── entity.py            # Dispozitivele (cont, adrese) și verificarea licenței
├── helpers.py           # Formatări în română, calcule pe facturi (rest, scadențe, arhivă)
├── license.py           # Manager licență (server-side, Ed25519, HMAC-SHA256)
├── manifest.json        # Metadata integrare
├── parser.py            # Citirea paginilor digi.ro (facturi, detalii factură, servicii, 2FA)
├── sensor.py            # Senzorii contului și ai adreselor, „Licență necesară”
├── strings.json         # Traduceri implicite (engleză)
├── brand/               # Pictograma și logo-ul integrării (temă deschisă și întunecată)
└── translations/
    ├── en.json          # Traduceri engleză
    └── ro.json          # Traduceri române
```

---

## Cerințe

- **Home Assistant** 2025.11 sau mai nou
- **HACS** (opțional, pentru instalare ușoară)
- **Cont DIGI** activ pe digi.ro / în aplicația MyDigi, cu acces la telefonul contului pentru codul SMS
- **Licență** validă după perioada de evaluare — [hubinteligent.org/donate?ref=digi](https://hubinteligent.org/donate?ref=digi)

Singura dependență, `cryptography` (pentru verificarea licenței), este deja inclusă în Home Assistant.

---

## Limitări cunoscute

1. **Cod SMS la fiecare autentificare** — DIGI cere codul la fiecare login, deci integrarea nu se poate reconecta singură. Cât rămâne valabilă sesiunea decide DIGI; când expiră, primești notificarea de reconectare.

2. **Fără API oficial** — datele sunt citite din paginile digi.ro. Dacă DIGI își schimbă paginile, integrarea poate avea nevoie de o actualizare.

3. **Captcha** — dacă DIGI activează o verificare anti-robot (captcha) la login, integrarea nu o ocolește: configurarea afișează un mesaj, iar conturile deja conectate funcționează până la expirarea sesiunii.

4. **Doar citire** — integrarea nu plătește facturi și nu schimbă nimic în cont (parole, Wi-Fi, pachete, extraopțiuni).

5. **Mobil, DIGI Energy, DIGI Tel** — apar în „Servicii active”, dar nu au încă senzori dedicați. Dacă ai aceste servicii și vrei să fie adăugate, deschide un issue.

6. **PDF-ul facturii** nu se descarcă.

7. **Servicii** — pachetele se actualizează o dată pe zi, deci o schimbare de pachet apare în cel mult 24 de ore.

8. **O singură intrare per cont DIGI** — dacă adaugi din nou același cont, vei primi eroarea „Acest cont DIGI este deja adăugat în Home Assistant”.

---

## ☕ Susține dezvoltatorul

Dacă ți-a plăcut această integrare și vrei să sprijini munca depusă, **invită-mă la o cafea**! 🫶
Nu costă nimic, iar contribuția ta ajută la dezvoltarea viitoare a proiectului. 🙌

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Susține%20dezvoltatorul-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/cnecrea)

---

## 🧑‍💻 Contribuții

Contribuțiile sunt binevenite! Simte-te liber să trimiți un pull request sau să raportezi probleme [aici](https://github.com/cnecrea/digi/issues).

---

## 🌟 Suport
Dacă îți place această integrare, oferă-i un ⭐ pe [GitHub](https://github.com/cnecrea/digi/)! 😊


## Licență

[Licență proprietară](LICENSE.md) — © 2026 Ciprian Nicolae. Toate drepturile rezervate.
