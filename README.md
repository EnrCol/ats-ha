# Alto Trevigiano Servizi (ATS) per Home Assistant

[Italiano](README.md) · [English](README.en.md) · [Release v0.4.0](https://github.com/EnrCol/ats-ha/releases/tag/v0.4.0)

**Integrazione non ufficiale** per leggere forniture idriche, fatture e letture dallo [Sportello Online Alto Trevigiano Servizi](https://sgc.altotrevigianoservizi.it/) direttamente in Home Assistant. Non è affiliata, approvata o supportata da ATS. Il portale può modificare le proprie API in qualsiasi momento.

La **v0.4.0 è la prima release stabile del fork [EnrCol/ats-ha](https://github.com/EnrCol/ats-ha)**, sviluppata a partire dal progetto di [Manu-Nat](https://github.com/Manu-Nat/ats-ha). È stata collaudata su Home Assistant TEST Core **2026.11.0** con login reale, 19 sensori, 22 fatture, download e visualizzazione dei PDF, anche senza Browser Mod. È una release stabile del progetto, **non una certificazione ufficiale Home Assistant/ATS**.

## Funzionalità

- **Primo accesso semplificato:** soltanto username ATS, password ATS e intervallo di aggiornamento. URL HTTPS del portale, cliente, token, forniture ed endpoint API sono individuati automaticamente.
- **Sessione e riautenticazione:** rinnovo del login quando ATS rifiuta la sessione; se la password non è più valida, Home Assistant richiede quella aggiornata senza ricreare le entità.
- **Forniture idriche:** conteggio utenze totali e attive, dettagli di forniture anche cessate, contatore, stato, indirizzo e informazioni rese disponibili dal portale.
- **Fatture e pagamenti:** numero totale, fatture non pagate, importi fatturati/pagati/residui, stato dell'ultima fattura, prossima scadenza quando esiste, consumo fatturato e totale dell'anno corrente.
- **Storico economico per anno:** gruppi per anno di **emissione** con numero di fatture, somma fatturata e pagata; elenco cronologico con importo, scadenza, stato e disponibilità del PDF. Dati incompleti rimangono `unknown`/`null`, senza totali parziali ingannevoli.
- **Letture contatore:** ultima lettura, data, consumo dell'ultima lettura e storico. La data visualizzata è `GG-MM-AAAA`, con `data_iso` utilizzabile nei template.
- **Previsione annua (m³/anno):** calcolo dalle ultime due letture **effettive e validate** di ogni contatore attivo; evita di combinare forniture cessate o contatori diversi. Se mancano dati sufficienti il risultato è `unknown`, ma resta consultabile negli attributi l'eventuale stima annua comunicata da ATS.
- **PDF fatture su richiesta:** azione `ats.download_invoices`, archivio locale privato per anno, salto dei file già presenti, recupero di singola fattura opzionale.
- **Card Lovelace inclusa:** storico espandibile per anno, pulsanti **Apri PDF** e **Scarica PDF**, visualizzatore interno PDF.js con navigazione delle pagine e zoom; compatibile anche con la Companion App Android.
- **Card portabile:** nessun `entity_id` obbligatorio. I sensori hanno l'attributo tecnico `ats_metric` e la card individua automaticamente il sensore dello storico; gli esempi YAML non richiedono di rinominare entità.
- **Risorsa JavaScript automatica:** registrazione e aggiornamento della card nelle risorse Lovelace in modalità storage, senza copiare file in `/config/www`. **Browser Mod non è richiesto**.

### Tutti i 19 sensori

Gli `entity_id` sono assegnati da Home Assistant: possono avere prefissi di area/dispositivo o nomi personalizzati. La colonna `ats_metric` è il riferimento stabile da usare per una dashboard portabile; i `unique_id` delle installazioni precedenti sono preservati.

| `ats_metric` | Sensore / dato |
|---|---|
| `active_supplies` | Utenze attive |
| `total_supplies` | Utenze totali |
| `supply_details` | Dettagli utenze (anche cessate) |
| `invoice_count` | Fatture presenti; attributi `storico_fatture` e `riepilogo_annuale` |
| `unpaid_count` | Fatture non pagate |
| `remaining_total` | Totale residuo da pagare (€) |
| `total_amount` | Totale fatture (€) |
| `invoices_current_year` | Totale fatture emesse nell'anno corrente (€) |
| `paid_total` | Totale pagato (€) |
| `next_expiry_amount` | Importo della prossima fattura da pagare (€) |
| `next_expiry_date` | Data della prossima scadenza |
| `consumption` | Consumo fatturato complessivo (m³), non lettura cumulativa |
| `last_status` | Stato dell'ultima fattura |
| `invoice_details` | Dettagli individuali delle fatture |
| `last_reading_value` | Ultima lettura contatore (m³) |
| `last_reading_consumption` | Consumo dell'ultima lettura (m³) |
| `annual_consumption_forecast` | Previsione annua da letture validate (m³/anno) e stima ATS negli attributi |
| `last_reading_date` | Data ultima lettura (`GG-MM-AAAA` + attributo `data_iso`) |
| `reading_details` | Storico e dettagli letture contatore |

#### Precisazioni sui calcoli

Lo storico `riepilogo_annuale` e il totale dell'anno corrente usano la **data di emissione** della fattura, non il periodo fatturato. Se un importo è assente, il totale annuale corrispondente è `null` anziché una somma incompleta. Per le fatture saldate, il flag `Payed=true` prevale su eventuali incongruenze del campo ATS `ToPay`.

La previsione dei consumi usa la differenza delle ultime due letture validate per contatore, divisa per i giorni trascorsi e moltiplicata per 365. Non è una misura in tempo reale. Per contatori attivi senza due letture valide, restituisce `unknown`. I valori in m³ sono suggeriti senza decimali solo a livello di visualizzazione: la precisione numerica viene conservata.

## Installazione v0.4.0

### Marketplace / HACS (consigliato)

1. Apri il **Marketplace** di Home Assistant (o HACS, se presente). Aggiungi `EnrCol/ats-ha` fra i repository personalizzati, categoria **Integrazione**.
2. Installa **Alto Trevigiano Servizi (ATS)** nella versione **v0.4.0**, non una vecchia beta.
3. **Riavvia Home Assistant** per caricare il codice dell'integrazione.
4. Apri **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Alto Trevigiano Servizi**.
5. Inserisci **Username ATS**, **Password ATS** e, se desiderato, **Intervallo aggiornamento** (default **60 minuti**, consentiti **5–1440**). Non servono URL, cookie o percorsi API.
6. Attendi la creazione del dispositivo **ATS** e dei sensori. Le credenziali sono quelle dello **Sportello Online ATS**, non SPID/CIE.

### Installazione manuale

Scarica il [pacchetto della release v0.4.0](https://github.com/EnrCol/ats-ha/archive/refs/tags/v0.4.0.zip). Copia **l'intera cartella** `custom_components/ats/` in `/config/custom_components/ats/`, **compresa `www/`**. Riavvia Home Assistant e completa la configurazione tramite l'interfaccia. Non copiare credenziali o file `.storage` da altre installazioni.

Le impostazioni manuali legacy di una configurazione già presente (cookie, URL e percorsi API) restano disponibili nelle **opzioni dell'integrazione** per compatibilità. Non vengono richieste durante un primo avvio nuovo.

## Dashboard e card di esempio

Sono inclusi due esempi pronti da incollare:

- **[Card completa ATS](examples/ats-card.yaml):** un blocco `vertical-stack` con riepilogo utenze/fatture/consumi, pulsante di download e storico interattivo.
- **[Dashboard completa ATS](examples/ats-dashboard.yaml):** una vista Lovelace con le medesime funzioni.
- **[File JavaScript della card](custom_components/ats/www/invoice-history-card.js):** già distribuito con l'integrazione e registrato automaticamente; non copiarlo in `www` manualmente.

Per usare la card completa: apri una dashboard → **Modifica dashboard → Aggiungi scheda → Manuale**, poi incolla il contenuto di `examples/ats-card.yaml`. Per lo storico da solo basta:

```yaml
type: custom:ats-invoice-history-card
title: Storico fatture ATS
```

**Non occorre impostare `entity:`:** la card trova il sensore con `ats_metric: invoice_count` anche se Home Assistant gli assegna un ID come `sensor.locale_tecnico_ats_ats_fatture_presenti`. Se eccezionalmente ci sono più sensori di storico possibili, puoi specificare `entity: sensor.ID_REALE`. Il riepilogo Markdown degli esempi usa `integration_entities('ats')` e `ats_metric`, senza ID fissi.

Dopo la prima installazione o un aggiornamento, esegui un refresh completo della pagina oppure chiudi e riapri la Companion App. Su Lovelace in modalità **storage**, il modulo `/ats_static/invoice-history-card.js?v=0.4.0` viene aggiunto/aggiornato automaticamente fra le risorse. In modalità **YAML**, se il caricamento frontend automatico non è disponibile, potrebbe essere necessario dichiarare quella risorsa come `module` nella configurazione Lovelace.

**Non serve Browser Mod**, né un'altra card di terze parti.

### PDF: download, archivio e visualizzazione

1. Premi **Scarica fatture ATS mancanti** nella card completa oppure esegui l'azione `ats.download_invoices`.
2. L'azione, senza parametri, scarica i PDF disponibili sul portale che non sono ancora nell'archivio locale; con `invoice_number` permette di richiedere una singola fattura.
3. I documenti sono salvati in `/media/ats/fatture/ANNO/NUMERO.pdf`. I file già esistenti non vengono sovrascritti. **Non è previsto il download automatico a ogni aggiornamento dei sensori.**
4. Nello storico apri un documento con **Apri PDF** oppure usa **Scarica PDF** per salvarlo sul dispositivo.

Il viewer usa PDF.js caricato dalla CDN `cdnjs.cloudflare.com` alla prima apertura (serve accesso Internet a tale host). **I dati PDF non sono inviati alla CDN**. Se la CDN non è disponibile, la funzione **Scarica PDF** continua a funzionare.

L'API `GET /api/ats/invoice/{year}/{number}` richiede autenticazione Home Assistant, convalida anno/numero e serve solo fatture conosciute, presenti nell'archivio. I PDF **non** sono pubblicati in `/local` o `/config/www`. La presenza del flag `pdf_disponibile` nel sensore indica disponibilità sul **portale ATS**, non prova che il file sia stato già scaricato localmente.

**Home Assistant Container:** rendi persistente `/media` e includila nei backup se vuoi conservare i PDF locali. La cartella `/config` deve essere persistente per conservare configurazione e integrazione.

## Privacy: sensori, Recorder, PDF e backup

Questa release applica `_unrecorded_attributes = frozenset({MATCH_ALL})` ai **19 sensori ATS**: Home Assistant continua a leggere tutti gli attributi correnti (inclusi `ats_metric`, `storico_fatture`, `riepilogo_annuale`, `indirizzo`, `pod` e dettagli economici) per dashboard e card, ma **Recorder non registra questi attributi specifici dell'integrazione nelle nuove righe di storico**. Gli **stati dei sensori** e i metadati nativi necessari alle statistiche (unità, `state_class` e simili) rimangono registrabili. L'installazione non aggiunge alcuna regola globale `recorder: exclude` e non altera lo storico delle altre integrazioni.

**Attenzione:** la modifica è **non retroattiva**. Gli attributi salvati dalle beta precedenti possono rimanere nel database Recorder e nei vecchi backup fino alla loro naturale eliminazione o a una pulizia dedicata. Il sensore mostra comunque i dettagli **in tempo reale** a qualunque utente HA che abbia accesso a quelle entità; escludere dal Recorder non è una misura di controllo degli accessi.

I file `/media/ats/fatture/ANNO/NUMERO.pdf` contengono potenzialmente **nome, indirizzo, codice fiscale, importi e altri dati personali** presenti nella bolletta completa. Sono conservati in locale e non sono resi pubblici in `/local`, ma possono essere letti da utenti autorizzati di Home Assistant, da chi accede al filesystem, al Media browser (ove supportato), agli snapshot o ai backup. Proteggi questi accessi, includi `/media` nel backup solo quando necessario e applica una conservazione adeguata.

## Sicurezza e limiti

- Proteggi le credenziali ATS conservate nella configurazione Home Assistant e i relativi backup. Non condividere password, cookie, codici cliente, token o URL di richieste firmate.
- L'integrazione usa richieste WebForms e API osservate nel portale; se ATS modifica il portale, il login, la scoperta o il recupero dei PDF possono smettere di funzionare.
- È supportata **una sola configurazione ATS per istanza**: vengono aggregate più forniture dello stesso cliente, non più clienti distinti associati allo stesso login.
- Non sono supportati login SPID/CIE. Il portale ha segnalato una futura necessità di firma **HMAC**, non ancora implementata.
- `unknown` è corretto se non ci sono fatture aperte oppure mancano due letture validate per costruire la previsione; non sostituirlo con 0 nei calcoli.
- La release è stata verificata su **Home Assistant Core 2026.11.0** in TEST; non sono state collaudate automaticamente tutte le versioni o tutti i tipi di account ATS. Storici Recorder delle vecchie installazioni possono mostrare avvisi in caso di ripetute rimozioni/reinstallazioni.

## Verifiche, aggiornamenti e assistenza

Sulla beta.8 alla base della release sono passati **133 test Python, 3 subtest, 6 test JavaScript**, più le verifiche di sintassi, Hassfest e HACS. Il collaudo su TEST ha confermato login, 19 sensori con `ats_metric`, 22 fatture, dashboard senza `entity_id` fissi, download PDF e visualizzazione nella card senza Browser Mod. I dati sono esempi del **collaudo**, non fatture o credenziali incluse nel repository.

- [Note di rilascio v0.4.0](docs/releases/v0.4.0.md)
- [Checklist di installazione e test](docs/test-ha-clean.md)
- [Migrazione template data/consumi](docs/dashboard-energia-ats-beta5.md)
- [Problemi e richieste](https://github.com/EnrCol/ats-ha/issues)

Per un problema indica versione di Home Assistant, release ATS, sintomo ed eventuali log **ripuliti dai dati sensibili**.
