# Întrebări frecvente — DIGI România

- [Autentificare și cod SMS](#autentificare-și-cod-sms)
- [Facturi](#facturi)
- [Adrese și servicii](#adrese-și-servicii)
- [Actualizare](#actualizare)
- [Licență](#licență)
- [Altele](#altele)

---

## Autentificare și cod SMS

### De ce îmi cere un cod prin SMS?

Pentru că așa se autentifică DIGI: după email și parolă, digi.ro (și aplicația MyDigi) trimite un cod de 6 cifre pe telefonul contului. Integrarea face exact același lucru. Codul se cere **doar** la adăugarea integrării și când expiră sesiunea DIGI — nu la fiecare actualizare și nici după o repornire a Home Assistant.

### Pot folosi ID-ul de client în loc de email?

Da. Câmpul acceptă ce acceptă și digi.ro: adresa de email a contului sau ID-ul de client.

### Nu primesc SMS-ul

- Verifică numărul afișat în formular (ex. `*******123`) — e numărul pe care DIGI trimite codul. Dacă nu mai ai acel număr, contactează DIGI ca să-l schimbe.
- Bifează **Trimite din nou codul** și apasă **Trimite**. DIGI permite un cod nou abia după un minut; dacă ceri mai devreme, formularul îți spune să mai aștepți. Codul trimis anterior rămâne valabil până expiră.

### Codul e respins

Codul expiră după **2 minute**. Dacă a trecut mai mult, cere unul nou. Verifică și să nu fi introdus cifrele din a doua parte a SMS-ului (șirul de litere și cifre de la final e pentru aplicația MyDigi, nu face parte din cod).

### Mi-a apărut o notificare de reconectare

DIGI a închis sesiunea, iar actualizările s-au oprit. Integrarea nu se reconectează singură, pentru că fiecare autentificare trimite un SMS — așa că îți cere ție:

1. Deschide notificarea (sau **Setări** → **Dispozitive și Servicii** → **DIGI România** → **Reconfigurare**)
2. Apasă **Trimite** — completează parola doar dacă ai schimbat-o între timp
3. Introdu codul primit prin SMS

Entitățile, istoricul și automatizările rămân neschimbate.

### Cât timp ține o sesiune?

Decide DIGI. Integrarea păstrează sesiunea (cookie-ul) în configurație și o folosește până când DIGI o închide; atunci primești notificarea de reconectare de mai sus.

### Mi-am schimbat parola sau emailul DIGI

**Setări** → **Dispozitive și Servicii** → **DIGI România** → meniul (⋮) → **Reconfigurare** → datele noi + codul SMS.

### Configurarea spune că DIGI cere captcha

DIGI a activat o verificare anti-robot la login. Integrarea nu o ocolește, deci nu poate adăuga contul. Deschide un [issue](https://github.com/cnecrea/digi/issues) — conturile deja adăugate funcționează în continuare, până la expirarea sesiunii.

---

## Facturi

### De ce „Factură restantă” e „Da”, deși scadența n-a trecut?

„Factură restantă” e **Da** cât timp ai o factură neplătită, ca la celelalte integrări (E·ON, Nova). Dacă scadența a trecut sau nu vezi în atribute: textul facturii spune „scadentă pe … (peste N zile)” sau „termen depășit cu N zile”, iar **Zile până la scadență** devine negativ după scadență.

Pentru o automatizare doar pe scadența depășită, verifică atributul:

```yaml
{{ state_attr('binary_sensor.digi_strada_exemplu_nr_1_factura_restanta', 'Zile până la scadență') | int(0) < 0 }}
```

### Am plătit factura, dar încă apare de plată

Integrarea vede plata când DIGI o înregistrează în cont, adică atunci când factura apare „achitată” pe digi.ro. După aceea, factura dispare la următoarea actualizare (cel mult 6 ore) sau imediat, dacă reîncarci integrarea (**⋮** → **Reîncarcă**).

### Ce e „Rest de plată”?

Cât mai ai de plătit din factură, după plățile parțiale — exact „Rest” din „Vezi factura” de pe digi.ro. „Total de plată” adună restul tuturor facturilor neplătite.

### De ce abonamentul e în EUR și factura în lei?

Prețurile pachetelor DIGI sunt în EUR (ex. „Ab. Internet … (8,25 EUR)”), iar factura se emite în lei, la cursul zilei. „Abonament” arată prețul din contract, luat din ultima factură; sumele facturilor sunt în lei.

### Câte luni are arhiva facturilor?

Ultimele **12 luni**, inclusiv luna curentă — câte un atribut pe lună, plus totalul și media lunară.

### Pot descărca PDF-ul facturii din Home Assistant?

Nu. Integrarea doar citește datele facturilor; PDF-ul îl descarci de pe digi.ro.

### Pot plăti factura din Home Assistant?

Nu. Integrarea doar citește contul — nu plătește și nu modifică nimic.

---

## Adrese și servicii

### Am servicii la mai multe adrese

Fiecare adresă devine un dispozitiv separat („DIGI — {adresă}”), cu facturile și serviciile ei. Dispozitivul contului („DIGI — Cont {ID client}”) are totalul de plată pe toate adresele.

### Am o adresă nouă / un serviciu nou

Apare singur: când integrarea vede o adresă sau un serviciu nou (ex. TV instalat), se reîncarcă și creează entitățile lui. Serviciile se citesc o dată pe zi, deci poate dura până la 24 de ore — sau imediat, cu **⋮** → **Reîncarcă**.

### Nu am senzorul „Televiziune” (sau „Internet”)

Senzorii de pachet apar doar pentru serviciile instalate la adresa respectivă. Verifică atributele senzorului **Servicii active**: dacă serviciul apare „neinstalat”, DIGI nu îl are înregistrat la acea adresă.

### Am DIGI Mobil, DIGI Energy sau DIGI Tel — de ce nu am senzori pentru ele?

Apar în **Servicii active**, dar nu au încă senzori dedicați: au fost dezvoltate pe un cont fără aceste servicii. Dacă le ai și vrei să fie adăugate, deschide un [issue](https://github.com/cnecrea/digi/issues) și atașează diagnosticul.

### Ce înseamnă „Telefon autentificare” și „Aplicații cu acces la date” (Date client)?

- **Telefon autentificare** — numărul pe care DIGI trimite codul SMS, mascat de DIGI.
- **Aplicații cu acces la date** — aplicațiile partenere pe care le-ai autorizat în contul DIGI (ex. Pago), din „Administrare cont” → „Setări plată”.

---

## Actualizare

### Cât de des se actualizează datele?

- **Facturile**: la fiecare 6 ore.
- **Serviciile și datele clientului**: o dată pe zi.

### Pot forța o actualizare?

Da: **Setări** → **Dispozitive și Servicii** → **DIGI România** → **⋮** → **Reîncarcă**. Reîncărcarea citește tot, inclusiv serviciile.

### Integrarea a făcut prea multe cereri către DIGI?

Nu: o actualizare înseamnă de obicei 2–6 cereri (datele utilizatorului, pagina de facturi și detaliile facturilor neplătite), plus, o dată pe zi, câte 1–3 cereri pe adresă pentru servicii și una pentru datele clientului. Între cereri e o pauză scurtă.

---

## Licență

### Cât durează perioada de evaluare?

**30 de zile**, cu toate funcțiile. După aceea e nevoie de o licență `DIGI-XXXX-XXXX-XXXX-XXXX` de la [hubinteligent.org/donate?ref=digi](https://hubinteligent.org/donate?ref=digi).

### Unde introduc licența?

**Setări** → **Dispozitive și Servicii** → **DIGI România** → **Configurare** (⚙️) → **Cheie de licență**. Tot acolo vezi starea licenței.

### Ce se întâmplă fără licență?

Integrarea nu mai contactează digi.ro și afișează doar senzorul „Licență necesară”. După activarea licenței, entitățile revin, cu tot istoricul.

---

## Altele

### Unde se păstrează parola?

Local, în configurația Home Assistant. E folosită doar la reconectarea contului, când expiră sesiunea DIGI. Diagnosticul nu o include.

### Pot adăuga două conturi DIGI?

Da — adaugă integrarea de două ori, câte o dată pentru fiecare cont. Același cont nu poate fi adăugat de două ori.

### Entity ID-urile sunt în engleză

Home Assistant generează ID-urile din numele entităților, în limba instalației la momentul creării. Pe o instalare în română ID-urile sunt românești (ex. `sensor.digi_cont_12345678_total_de_plata`), pe una în engleză sunt englezești (ex. `…_total_due`). Le poți redenumi din setările fiecărei entități.

### Ceva nu merge

Vezi [DEBUG.md](DEBUG.md): cum activezi jurnalul detaliat, ce înseamnă mesajele și cum raportezi o problemă.
