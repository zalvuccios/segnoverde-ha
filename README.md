# <img src="images/logo.png" width="64" align="top"> Segnoverde per Home Assistant

Integrazione non ufficiale per [Segnoverde S.p.A.](https://www.segnoverde.it/) che espone in Home Assistant le **fatture** e i **consumi kWh** del tuo contratto luce (e gas, in futuro) letti dall'area clienti [`segnoverde-webcli.serviceict.it`](https://segnoverde-webcli.serviceict.it/PortaleClienti/Home/Login).

![banner](images/banner.png)

> ⚠️ **Disclaimer**: integrazione non ufficiale, non affiliata a Segnoverde S.p.A. Utilizza tecniche di scraping del portale clienti accessibile con Codice Cliente + Password. Le credenziali restano nella configurazione locale di Home Assistant; proteggi l'accesso alla cartella `/config` e ai backup.

## Funzionalità

- 🔐 **Config flow UI** con validazione del login (Codice Cliente + Password)
- 🧾 **Storico fatture** completo (numero, importo, scadenza, stato pagamento)
- ⚡ **Dettaglio ultima bolletta** dal PDF: kWh totali, fasce F1/F2/F3, prezzo medio, potenza max
- 📊 **Consumo annuo** per fascia e **spesa annua** aggiornata (letti dal PDF)
- 📚 **Storico kWh mensili** (popolato automaticamente in background; comportamento disattivabile da **Configura**)
- ✅ **Binary sensor** "fatture non pagate" (ON quando c'è almeno una fattura da saldare)
- 💾 **Download PDF bollette** in cartella configurabile (`/config/segnoverde_pdfs/`)

## Entità create

| Entità | Classe | Stato | Note |
|---|---|---|---|
| `sensor.segnoverde_ultima_fattura_importo` | Monetario | Importo (€) | attributi: numero, scadenza, stato, kWh, F1/F2/F3, prezzo medio, periodo, **storico_mensile** (importo + kWh + stato per ogni mese) |
| `sensor.segnoverde_ultimo_consumo_kwh` | Energia | kWh ultima bolletta | attributi: storico kWh per mese/anno |
| `sensor.segnoverde_spesa_annua` | Monetario | Spesa annua (€) | periodo da/al |
| `sensor.segnoverde_consumo_annuo_totale` | Energia | **F1+F2+F3 (anno mobile)** | attributi: f1, f2, f3, periodo da/al |
| `sensor.segnoverde_consumo_annuo_f1` | Energia | kWh F1 (anno mobile) | |
| `sensor.segnoverde_consumo_annuo_f2` | Energia | kWh F2 (anno mobile) | |
| `sensor.segnoverde_consumo_annuo_f3` | Energia | kWh F3 (anno mobile) | |
| `sensor.segnoverde_stato_integrazione` | Diagnostico | `online`/`offline` | attributi: login_ok, codice cliente, ultimo aggiornamento, n.fatture |
| `binary_sensor.segnoverde_fatture_non_pagate` | Binary | ON se fatture INSOLUTE | elenco in attributi |
| `button.segnoverde_scarica_storico` | Button | — | Cliccabile: scarica tutti i PDF + popola storico kWh completo |
| `button.segnoverde_forza_aggiornamento` | Button | — | Cliccabile: forza refresh immediato |
| `button.segnoverde_scarica_pdf_ultima` | Button | — | Cliccabile: scarica il PDF dell'ultima fattura |

### Attributo `storico_mensile`

Il sensore `sensor.segnoverde_ultima_fattura_importo` espone l'attributo `storico_mensile`: un dizionario con chiave `MM_AAAA` e per ogni mese `{importo, kwh, stato, numero_fattura, scadenza}`. Esempio:

```json
{
  "05_2026": {"importo": 50.00, "kwh": 120.00, "stato": "PAGATA", "numero_fattura": "EE00000001/2026", "scadenza": "2026-07-01"},
  "04_2026": {"importo": 45.00, "kwh": 100.00, "stato": "PAGATA", "numero_fattura": "EE00000002/2026", "scadenza": "2026-06-01"}
}
```

Gli **importi** sono disponibili per **tutti i mesi** fin dal primo avvio. I **kWh** vengono popolati automaticamente in background scaricando esclusivamente i PDF ancora mancanti; il button `scarica_storico` permette di rilanciare manualmente la sincronizzazione.

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

- **Codice cliente** (es. `00000000`)
- **Password** dell'area clienti
- **Intervallo aggiornamento** (ore, predefinito 12, min 1)
- **Cartella download PDF** (relativa a `/config`, predefinita `segnoverde_pdfs`)
- **Scarica automaticamente lo storico mancante** (attivo per impostazione predefinita)

### Modificare le impostazioni in un secondo momento

Non è necessario reinstallare l'integrazione per cambiare parametri:

1. **Impostazioni → Dispositivi e servizi** → clicca sull'integrazione **Segnoverde**
2. Pulsante **Configura** (ingranaggio)
3. Modifica **Intervallo di aggiornamento** e/o **Cartella download PDF** → **Salva**

L'integrazione si ricarica automaticamente con i nuovi valori. Puoi inoltre attivare/disattivare il popolamento automatico dello storico mancante.

## Azioni rapide (button) e servizi

Non serve aprire Strumenti Sviluppatore: you puoi cliccare direttamente i **button** dalla card dell'integrazione (vedi sezione esempi Lovelace):

| Entità button | Azione |
|---|---|
| `button.segnoverde_scarica_storico` | Scarica tutti i PDF e popola lo storico kWh completo (~1 fattura/sec) |
| `button.segnoverde_forza_aggiornamento` | Forza refresh immediato |
| `button.segnoverde_scarica_pdf_ultima` | Scarica solo il PDF dell'ultima fattura |

Servizi equivalenti (per uso in automazioni):

| Servizio | Descrizione |
|---|---|
| `segnoverde.scarica_pdf` | Scarica il PDF di una fattura (`numero_fattura`) o dell'ultima se omesso |
| `segnoverde.forza_aggiornamento` | Forza refresh immediato |
| `segnoverde.scarica_storico` | Scarica tutti i PDF non ancora in cache e popola lo storico kWh completo |

## Esempi Lovelace

### Card con i 3 button rapidi

```yaml
- type: entities
  title: Segnoverde - Azioni
  entities:
    - button.segnoverde_forza_aggiornamento
    - button.segnoverde_scarica_pdf_ultima
    - button.segnoverde_scarica_storico
```

### Card overview fatture

```yaml
- type: entities
  title: Segnoverde - Bollette
  entities:
    - sensor.segnoverde_ultima_fattura_importo
    - sensor.segnoverde_ultimo_consumo_kwh
    - sensor.segnoverde_consumo_annuo_totale
    - sensor.segnoverde_spesa_annua
    - binary_sensor.segnoverde_fatture_non_pagate
```

### Card completa con tutti i dettagli

Nella cartella [`docs/`](docs/) trovi due YAML pronti da incollare nella dashboard (modalità RAW → Modifica):

- [`docs/lovelace-card.yaml`](docs/lovelace-card.yaml) — card `vertical-stack` con stato, azioni rapide, ultima bolletta, dettaglio fasce F1/F2/F3, consumo annuo e storico.
- [`docs/lovelace-tabella-storico.yaml`](docs/lovelace-tabella-storico.yaml) — tabella markdown con tutti i mesi (importo + kWh + stato + scadenza) estratta dall'attributo `storico_mensile`.

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

- I dati kWh dettagliati provengono dal **PDF della singola bolletta**. Al primo avvio l'integrazione popola automaticamente in background solo i mesi mancanti (circa una richiesta al secondo); l'opzione può essere disattivata da **Configura**.
- L'autenticazione avviene di nuovo a ogni refresh (HTTP stateless via cookie di sessione). Segnoverde non espone API ufficiale quindi questo componente esegue scraping: se il portale cambia markup, l'integrazione potrebbe rompersi. Apri una issue se succede.
- Per lo stesso motivo: se Segnoverde abilita CAPTCHA o 2FA, l'integrazione smetterà di funzionare finché non venga aggiornata.

## Diagnostica

Da **Impostazioni → Dispositivi e servizi → Segnoverde → menu ⋮ → Scarica diagnostica** puoi ottenere un file utile per le issue. Password, codice cliente, token di download e numeri fattura vengono oscurati automaticamente.

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
├── config_flow.py      # flow UI + **options flow (Configura)**
├── entity.py           # classe base
├── sensor.py           # sensori
├── binary_sensor.py    # binary sensor fatture insolute
├── button.py           # button rapidi (scarica_storico, forza, pdf)
├── const.py
├── services.yaml
├── strings.json
├── translations/{en,it}.json
└── manifest.json
```

## Licenza

MIT — vedi [LICENSE](LICENSE).