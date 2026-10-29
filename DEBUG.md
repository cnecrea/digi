# Ghid de depanare — DIGI România

Cum activezi jurnalul detaliat, ce mesaje scrie integrarea și ce înseamnă fiecare.

---

## 1. Activează jurnalul detaliat

### Din interfață (cel mai simplu)

1. **Setări** → **Dispozitive și Servicii** → **DIGI România**
2. Meniul (⋮) → **Activează jurnalizarea de depanare**
3. Reproduce problema (ex. **⋮** → **Reîncarcă**, sau așteaptă o actualizare)
4. Meniul (⋮) → **Dezactivează jurnalizarea de depanare** — Home Assistant descarcă automat fișierul cu jurnalul

### Din `configuration.yaml`

```yaml
logger:
  default: warning
  logs:
    custom_components.digi: debug
```

Repornește Home Assistant (**Setări** → **Sistem** → **Repornire**).

După ce ai rezolvat problema, șterge blocul sau pune `custom_components.digi: info` — jurnalul detaliat e mare.

---

## 2. Unde găsești jurnalul

- **Interfață**: **Setări** → **Sistem** → **Jurnale** → **Afișează jurnalele complete**, apoi caută `[Digi]`
- **Fișier**: `config/home-assistant.log`

```bash
grep "\[Digi\]" config/home-assistant.log | tail -100
```

- **Home Assistant OS** (add-on-ul SSH / Terminal):

```bash
ha core logs | grep "\[Digi\]"
```

Toate mesajele integrării încep cu **`[Digi]`**. Mesajele despre licență încep cu `[Digi:License]`.

---

## 3. Cum arată o actualizare normală

La fiecare actualizare (implicit la 6 ore), integrarea verifică sesiunea, citește facturile și detaliile facturilor neplătite. O dată pe zi citește și serviciile și datele clientului. Fiecare cerere apare cu pagina, codul HTTP, durata și mărimea răspunsului:

```
[Digi] /app-user-info-bulk-mobile-xhr → HTTP 200 /app-user-info-bulk-mobile-xhr (0.2 s, 9924 caractere)
[Digi] /my-account/invoices → HTTP 200 /my-account/invoices (0.6 s, 115629 caractere)
[Digi] /my-account/invoices/details → HTTP 200 /my-account/invoices/details (0.2 s, 6462 caractere)
[Digi] /my-account/invoices/details → HTTP 200 /my-account/invoices/details (0.2 s, 7579 caractere)
[Digi] /my-account/my-services → HTTP 200 /my-account/my-services (0.5 s, 87988 caractere)
[Digi] /my-account/my-services/overview → HTTP 200 /my-account/my-services/overview (0.2 s, 4300 caractere)
[Digi] /my-account/my-services/fiberlink → HTTP 200 /my-account/my-services/fiberlink (0.2 s, 11231 caractere)
[Digi] /my-account/my-services/digi-tv → HTTP 200 /my-account/my-services/digi-tv (0.3 s, 23129 caractere)
[Digi] Servicii citite pentru 2 adrese: *****123: Internet (FiberLink Popular); *****456: Internet (FiberLink 1000), Televiziune (Digital)
[Digi] /my-account/account-details → HTTP 200 /my-account/account-details (0.4 s, 94353 caractere)
[Digi] Actualizare în 3.1 s: 2 adrese, 36 facturi (2 neplătite, 97.29 lei), 2 detalii în cache; adresa *****123: 18 facturi, servicii Internet; adresa *****456: 18 facturi, servicii Internet, Televiziune
```

Ultima linie e rezumatul actualizării: câte adrese, câte facturi (și câte neplătite, cu suma) și ce servicii are fiecare adresă. Adresele apar mascate (ultimele 3 cifre ale ID-ului DIGI).

În afara zilei în care se citesc serviciile, liniile `my-services` și `account-details` lipsesc — e normal.

---

## 4. Cum arată configurarea (login + cod SMS)

```
[Digi] /auth/login → HTTP 200 /auth/login (0.2 s, 26036 caractere)
[Digi] Login pentru c***@exemplu.ro
[Digi] /auth/login → HTTP 200 /auth/2fa (0.4 s, 24609 caractere)
[Digi] Login acceptat — urmează codul prin SMS (telefon *******123)
[Digi] /api-post-2fa-send-code → HTTP 200 /api-post-2fa-send-code (1.1 s, 1649 caractere)
[Digi] Cod trimis prin SMS (telefon *******123)
[Digi] /api-post-2fa-validate-code → HTTP 200 /api-post-2fa-validate-code (0.1 s, 67 caractere)
[Digi] /auth/address-select → HTTP 200 /auth/address-select (0.3 s, 39981 caractere)
[Digi] Cod acceptat — sesiune activă
[Digi] Cont autentificat: client ***678
```

- `/auth/login → … /auth/2fa` — parola a fost acceptată, DIGI cere codul SMS.
- `Cod trimis prin SMS` — DIGI a trimis codul; formularul din Home Assistant așteaptă cele 6 cifre.
- `Cod acceptat — sesiune activă` — autentificarea s-a încheiat; sesiunea se salvează în configurație.

---

## 5. Mesaje și ce înseamnă

### Normale

| Mesaj | Ce înseamnă |
|-------|-------------|
| `Actualizare în … s: N adrese, M facturi …` | Actualizare reușită |
| `Servicii citite pentru N adrese: …` | Citirea zilnică a serviciilor |
| `Cookie-urile sesiunii au fost salvate în configurație` | DIGI a reînnoit sesiunea; noua sesiune e păstrată pentru repornire |
| `Adrese sau servicii noi în cont — reîncarc integrarea` | A apărut o adresă sau un serviciu nou; integrarea se reîncarcă singură, ca să creeze entitățile lui |

### Sesiune și autentificare

| Mesaj | Cauză | Ce faci |
|-------|-------|---------|
| `Sesiunea a expirat — e nevoie de reautentificare cu cod SMS (…)` | DIGI a închis sesiunea | Deschide notificarea de reconectare din Home Assistant și introdu codul primit prin SMS (vezi [FAQ](FAQ.md#mi-a-apărut-o-notificare-de-reconectare)) |
| `Configurare: login respins pentru c***@… (…)` | Email / ID client sau parolă greșite; între paranteze e mesajul DIGI | Verifică datele pe digi.ro |
| `Codul nu a fost retrimis: Poți genera un cod nou peste 1 minut!` | Ai cerut un cod nou prea devreme | Așteaptă un minut și bifează din nou „Trimite din nou codul” |
| `Cod respins: …` | Codul e greșit sau a expirat (după 2 minute) | Cere un cod nou |
| `Formularul de login DIGI cere captcha (…)` | DIGI a activat o verificare anti-robot la login | Integrarea nu o ocolește — deschide un issue |
| `Verificarea codului a eșuat: codul a fost acceptat, dar sesiunea nu e activă` | DIGI a acceptat codul, dar nu a deschis sesiunea | Încearcă din nou; dacă se repetă, deschide un issue cu jurnalul |

Integrarea **nu** se autentifică niciodată singură în fundal: fiecare autentificare trimite un SMS. De aceea, la o sesiune expirată, actualizările se opresc până la reconectare.

### Rețea și site

| Mesaj | Cauză | Ce faci |
|-------|-------|---------|
| `[Digi] /… → ClientConnectorError` / `TimeoutError` | digi.ro nu răspunde sau Home Assistant nu are internet | Nimic — integrarea reîncearcă la următoarea actualizare |
| `… HTTP 500` / `502` / `503` / `429` | digi.ro are o problemă temporară | La fel — se rezolvă de obicei singur |
| `Detaliile facturii *** nu au putut fi citite: …` | Popup-ul „Vezi factura” n-a răspuns | Restul datelor se actualizează; detaliile se reiau la următoarea actualizare |
| `Serviciile nu au putut fi actualizate, rămân cele de la ultima citire: …` | Pagina „Serviciile mele” n-a răspuns | Senzorii de servicii păstrează valorile de ieri |
| `Datele clientului nu au putut fi citite: …` | Pagina „Administrare cont” n-a răspuns | „Date client” păstrează valorile anterioare |

### DIGI și-a schimbat paginile

Integrarea citește paginile digi.ro (nu există API public). Mesajele de mai jos înseamnă de obicei că DIGI a schimbat o pagină — **deschide un issue** cu jurnalul și diagnosticul:

- `formularul de login nu a fost găsit pe /auth/login`
- `acțiunea de trimitere a codului lipsește din pagina 2FA` / `formularul pentru cod nu a venit în răspuns`
- `pagina „Serviciile mele” nu conține tabul Overview`
- `login neconfirmat (pagina …)`
- `redirect în afara digi.ro (…)`

### Licență

| Mesaj | Ce înseamnă |
|-------|-------------|
| `Licență invalidă — se omit cererile către digi.ro` | Perioada de evaluare a expirat sau licența nu e validă; integrarea nu mai contactează digi.ro și afișează doar „Licență necesară” |
| `[Digi:License] ✓ Licență ACTIVĂ` / `⏳ Perioadă de evaluare: N zile rămase` | Starea licenței la pornire |

---

## 6. Diagnosticul

**Setări** → **Dispozitive și Servicii** → **DIGI România** → meniul (⋮) → **Descarcă diagnosticul**.

Conține starea actualizării, numărul de adrese și facturi, ultima factură a fiecărei adrese (sume, date, servicii facturate), serviciile din Overview și starea licenței. **Nu** conține email, parolă, nume, adrese, numere de factură, cont PPPoE, seriile echipamentelor sau valorile cookie-urilor — poate fi atașat liniștit la un issue.

---

## 7. Date personale în jurnal

Mesajele `[Digi]` maschează emailul (`c***@exemplu.ro`), telefonul (`*******123`), ID-ul de client (`***678`) și adresele (`*****456`). Unele mesaje ale Home Assistant însă afișează **titlul intrării**, care e adresa ta de email, de exemplu:

```
Config entry 'client@exemplu.ro' for digi integration could not authenticate: …
```

Înainte să publici jurnalul, înlocuiește emailul și orice altă dată personală.

---

## 8. Cum raportezi o problemă

Deschide un [issue pe GitHub](https://github.com/cnecrea/digi/issues) cu:

- **ce s-a întâmplat** și ce te așteptai să se întâmple;
- **diagnosticul** (secțiunea 6);
- **liniile `[Digi]`** din jurnal, din momentul problemei (20–50 de linii);
- versiunea Home Assistant (**Setări** → **Despre**) și versiunea integrării (din HACS);
- ce servicii DIGI ai (internet, TV, mobil, energie) și la câte adrese.

Pune jurnalul într-un bloc de cod:

````
```
2026-10-30 08:15:12 DEBUG custom_components.digi.api [Digi] /app-user-info-bulk-mobile-xhr → HTTP 200 /app-user-info-bulk-mobile-xhr (0.2 s, 9924 caractere)
2026-10-30 08:15:12 WARNING custom_components.digi.coordinator [Digi] Sesiunea a expirat — e nevoie de reautentificare cu cod SMS (sesiunea DIGI a expirat (utilizator neautentificat))
```
````
