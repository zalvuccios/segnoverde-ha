# Segnoverde per Home Assistant

Integrazione non ufficiale per [Segnoverde S.p.A.](https://www.segnoverde.it/) che espone in Home Assistant le **fatture** e i **consumi kWh** del tuo contratto luce (e gas, in futuro) letti dall'area clienti [`segnoverde-webcli.serviceict.it`](https://segnoverde-webcli.serviceict.it/PortaleClienti/Home/Login).

> ⚠️ **Disclaimer**: integrazione non ufficiale, non affiliata a Segnoverde S.p.A. Utilizza tecniche di scraping del portale clienti accessibile con Codice Cliente + Password. Le credenziali restano salvate nella tua istanza di Home Assistant (in `config_entries` crittografate) e non escono dal tuo sistema.

## Funzionalità

- 🔐 **Config flow UI** con validazione del login (Codice Cliente + Password)
- 🧾 **Storico fatture** completo (numero, importo, scadenza, stato pagamento)
- ⚡ **Dettaglio ultima bolletta** dal PDF: kWh totali, fasce F1/F2/F3, prezzo medio, potenza max
- 📊 **Consumo annuo** per fascia e **spesa annua** aggiornata (letti dal PDF)
- 📚 **Storico kWh mensili** (popolato progressivamente dal servizio `scarica_storico`)
- ✅ **Binary sensor** "fatture non pagate" (ON quando c'è almeno una fattura da saldare)
- 💾 **Download PDF bollette** in cartella configurabile (`/config/segnoverde_pdfs/`)

## Entità create

| Entità | Classe | Stato | Note |
|---|---|---|---|
| `sensor.segnoverde_ultima_fattura_importo` | Monetario | Importo (€) | attributi: numero, scadenza, stato, kWh, F1/F2/F3, prezzo medio, periodo, ecc. |
| `sensor.segnoverde_ultimo_consumo_kwh` | Energia | kWh ultima bolletta | attributi: storico kWh per mese/anno |
| `sensor.segnoverde_spesa_annua` | Monetario | Spesa annua (€) | periodo da/al |
| `sensor.segnoverde_consumo_annuo_f1` | Energia | kWh F1 (anno mobile) | |
| `sensor.segnoverde_consumo_annuo_f2` | Energia | kWh F2 (anno mobile) | |
| `sensor.segnoverde_consumo_annuo_f3` | Energia | kWh F3 (anno mobile) | |
| `binary_sensor.segnoverde_fatture_non_pagate` | Binary | ON se fatture INSOLUTE | elenco in attributi |

## Installazione

### HACS (consigliato)

1. In HACS → **Integrazioni** → ⋮ → **Repository personalizzati**
2. Aggiungi: `https://github.com/zalvuccios/segnoverde-ha`
3. Categoria: **Integrazione**
4. Cerca "Segnoverde" e installa.
5. Riavvia Home Assistant.
6. **Impostazioni** → **Dispositivi e servizi** → **Aggiungi integrazione** → "Segnoverde".

### Manuale

Copia la cartella `custom_components/segnoverde/` in `<config>/custom_components/segnoverde/` e riavvia Home Assistant.

## Configurazione

Nel flow di configurazione inserisci:

- **Codice cliente** (es. `00085232`)
- **Password** dell'area clienti
- **Intervallo aggiornamento** (ore, predefinito 12, min 1)
- **Cartella download PDF** (relativa a `/config`, predefinita `segnoverde_pdfs`)

## Servizi disponibili

| Servizio | Descrizione |
|---|---|
| `segnoverde.scarica_pdf` | Scarica il PDF di una fattura (`numero_fattura`) o dell'ultima se omesso |
| `segnoverde.forza_aggiornamento` | Forza refresh immediato |
| `segnoverde.scarica_storico` | Scarica tutti i PDF non ancora in cache e popola lo storico kWh completo |

## Esempi di automazione

```yaml
# Notifica al telefono quando arriva una nuova fattura non pagata
- alias: "Segnoverde - Nuova fattura da pagare"
  trigger:
    platform: state
    entity_id: binary_sensor.segnoverde_fatture_non_pagate
    to: "on"
  action:
    service: notify.mobile_app_iphone_di_xxx
    data:
      title: "Nuova bolletta Segnoverde"
      message: >-
        Importo {{ states('sensor.segnoverde_ultima_fattura_importo') }} € -
        scadenza {{ state_attr('sensor.segnoverde_ultima_fattura_importo','scadenza') }}
```

## Limiti note

- I dati kWh dettagliati provengono dal **PDF della singola bolletta**, quindi solo l'ultima viene scaricata automaticamente a ogni refresh. Per lo storico completo usa il servizio `segnoverde.scarica_storico` (una tantum, impiega qualche minuto).
- L'autenticazione avviene di nuovo a ogni refresh (HTTP stateless via cookie di sessione). Segnoverde non espone API ufficiale quindi questo componente esegue scraping: se il portale cambia markup, l'integrazione potrebbe rompersi. Apri una issue se succede.
- Per lo stesso motivo: se Segnoverde abilita CAPTCHA o 2FA, l'integrazione smetterà di funzionare finché non venga aggiornata.

## Problemi noti

Se il login fallisce con `auth`:
- Verifica che Codice Cliente e Password siano corretti collegandoti al portale via browser.
- Verifica che la password non sia scaduta (`pwd_expired`): accedi via browser, completail cambio password e reinstanzia l'integrazione.

## Sviluppo

```
custom_components/segnoverde/
├── __init__.py         # setup + servizi
├── api.py              # client HTTP + parsing HTML elenco fatture
├── parser.py           # parsing PDF bollette (pdfplumber)
├── coordinator.py      # DataUpdateCoordinator + cache storico
├── config_flow.py      # flow UI
├── entity.py           # classe base
├── sensor.py           # sensori
├── binary_sensor.py    # binary sensor fatture insolute
├── const.py
├── services.yaml
├── strings.json
├── translations/{en,it}.json
└── manifest.json
```

## Licenza

MIT — vedi [LICENSE](LICENSE).