# Alto Trevigiano Servizi (ATS) per Home Assistant

🇮🇹 Italiano · [🇬🇧 English](README.en.md)

Integrazione **non ufficiale** per Home Assistant che legge dall'area utente di [Alto Trevigiano Servizi](https://sgc.altotrevigianoservizi.it/) le tue forniture idriche, le fatture e le letture del contatore.

> Non è affiliata né approvata da Alto Trevigiano Servizi. Usa le stesse richieste che il portale esegue nel tuo browser, quindi può smettere di funzionare se il portale cambia.

> **Ramo sperimentale `feat/public-ats-onboarding`.** Non è ancora una release pubblica.
> Il login con username/password dello Sportello Online ATS è ora previsto dalla UI,
> ma **l'individuazione automatica delle forniture non è ancora implementata**:
> occorre ancora configurare i percorsi API di utenze e fatture.
> Non sostituire una installazione live funzionante con questo ramo.
>
> Anche con username e password, questa beta supporta **una sola configurazione ATS per istanza Home Assistant**, finché non sarà verificata l'identificazione automatica dell'account.

## Cosa fa

- Utenze (`supply-light`): stato, contatore e dati della fornitura.
- Fatture (`invoice`): importi, residui, pagamenti, scadenze e consumi fatturati.
- Letture del contatore (`reading-base`): ultima lettura, consumo e storico. È facoltativa.

Tutto viene esposto come sensori sotto un unico dispositivo chiamato **ATS**.

### Sensori

| Entità | Contenuto |
|---|---|
| `sensor.ats_utenze_attive` / `sensor.ats_utenze_totali` | Numero di utenze attive e totali |
| `sensor.ats_dettagli_utenze_attive` | Attributi `utenza_1`, `utenza_2`… (stato, servizio, indirizzo, contatore, saldo, consumo annuo stimato) |
| `sensor.ats_fatture_presenti` / `sensor.ats_fatture_non_pagate` | Numero di fatture e di quelle non pagate |
| `sensor.ats_totale_fatture` / `sensor.ats_totale_pagato` / `sensor.ats_totale_residuo_da_pagare` | Totali in € |
| `sensor.ats_prossima_scadenza_fattura` / `sensor.ats_importo_prossima_scadenza` | Scadenza e importo residuo della prossima fattura aperta |
| `sensor.ats_stato_ultima_fattura` | Stato dell'ultima fattura, con numero, periodo, importo e residuo negli attributi |
| `sensor.ats_consumo_fatturato_totale` | Somma dei consumi presenti sulle fatture |
| `sensor.ats_dettagli_fatture` | Attributi `fattura_1`, `fattura_2`… con tutti i campi di ogni fattura |
| `sensor.ats_ultima_lettura_contatore` | Ultima lettura in m³ |
| `sensor.ats_consumo_ultima_lettura` / `sensor.ats_data_ultima_lettura` | Consumo e data dell'ultima lettura |
| `sensor.ats_dettagli_letture_contatore` | Attributi `lettura_1`, `lettura_2`… con lo storico delle letture |

Con login automatico le letture vengono richieste su un intervallo mobile di 365 giorni; con cookie manuale serve configurare il relativo percorso API.

## Installazione

### Con HACS (consigliata)

1. In HACS apri il menu ⋮ → **Repository personalizzati**.
2. Incolla l'URL di questo repository, scegli la categoria **Integrazione** e premi **Aggiungi**.
3. Cerca **Alto Trevigiano Servizi (ATS)**, scaricala e **riavvia Home Assistant**.

### Manuale

Copia la cartella `custom_components/ats` in `/config/custom_components/ats` e riavvia Home Assistant.

### Aggiunta dell'integrazione

**Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Alto Trevigiano Servizi (ATS)**, poi compila il modulo con i dati della sezione seguente.

## Come trovare i dati di configurazione

Nel ramo sperimentale puoi scegliere: **username e password ATS** con sessione aggiornata automaticamente, oppure **cookie HTTP manuale** come nella versione originale. In entrambi i casi i percorsi delle richieste API di utenze e fatture vanno ancora ricavati dal portale. I dati si trovano negli strumenti sviluppatore del browser.

1. Accedi all'area utente del portale ATS dal browser, come fai di solito.
2. Premi **F12** (o tasto destro → **Ispeziona**) e apri la scheda **Rete**.
3. Nel filtro scegli **Fetch/XHR**, così vedi solo le chiamate API.
4. Con gli strumenti aperti, naviga tra le sezioni del portale: **utenze/forniture**, **fatture** e **letture del contatore**. Ognuna lancia la sua richiesta. Se la lista è vuota, ricarica la pagina con la scheda Rete già aperta.
5. Per ogni richiesta, cliccala e nella scheda **Intestazioni** guarda **URL di richiesta**. Ti servono queste tre:

   | Richiesta | Come la riconosci | Campo nel modulo |
   |---|---|---|
   | Utenze | l'URL contiene `supply-light` | Percorso API utenze |
   | Fatture | l'URL contiene `invoice` | Percorso API fatture |
   | Letture | `…/webapi/api/v1/reading-base/<codice>` | Percorso API letture (facoltativo) |

6. Dall'URL copia **solo la parte che inizia con `/webapi/`**, parametri compresi (per esempio `/webapi/api/v1/reading-base/<codice>`). L'indirizzo base `https://sgc.altotrevigianoservizi.it` è già precompilato.
7. Se utilizzi **username e password ATS**, non devi copiare cookie. Solo se preferisci la modalità manuale, nella sezione **Intestazioni** copia il valore del cookie della richiesta e inseriscilo nel relativo campo. Non condividerlo mai.
8. Controlla che la richiesta sia `GET` con codice `200 OK` e che nella scheda **Risposta** o **Anteprima** compaia un JSON con i tuoi dati.

L'intervallo di aggiornamento è in minuti (da 5 a 1440, predefinito 60).

> I percorsi contengono codici legati al tuo account e il cookie equivale a una password. Non incollarli in issue, forum, log o screenshot. Se devi mostrare qualcosa, oscura i codici.

## Durata della sessione

Con **username e password ATS** l'integrazione esegue il login al portale e riprova dopo un rifiuto della sessione. Questo meccanismo non implementa il login SPID/CIE né la firma HMAC. La durata della sessione non è documentata e il comportamento su altri account richiede ulteriori test.

Se ATS rifiuta esplicitamente username o password, Home Assistant avvia la procedura di **riautenticazione**: inserisci soltanto la nuova password e l'integrazione ricarica i dati conservando le entità. Errori di rete e modifiche al portale non avviano una richiesta di password. In modalità cookie manuale, un cookie revocato o scaduto deve essere sostituito nelle opzioni.

## Sicurezza

- Usa esclusivamente le credenziali di accesso **allo Sportello Online ATS**; non inserire credenziali SPID/CIE.
- Password ATS e cookie sono memorizzati nella configurazione Home Assistant; non sono cifrati come in un password manager. Proteggi backup, file e accesso all'istanza.
- L'integrazione non scrive il cookie nei log.
- Il portale segnala con un header `deprecated` che in futuro le richieste senza firma HMAC non saranno più accettate. Questa versione **non** implementa HMAC.

## Limiti

- I campi sono letti dai JSON osservati nel portale; l'integrazione non inventa altri endpoint e non scarica i PDF delle fatture.
- Che una richiesta funzioni nel browser non garantisce da sola che la sessione sia riutilizzabile da Home Assistant.
- I valori assenti restano `unknown`, non vengono sostituiti con zero.
- Il consumo fatturato totale somma il campo `Consumption` delle fatture ricevute: può coprire più periodi e non è una lettura cumulativa del contatore.

## Risoluzione problemi

- **Errore all'aggiunta o entità non disponibili:** controlla percorsi API completi, credenziali ATS oppure cookie manuale, e stato del portale.
- **Sensori delle letture `unknown`:** controlla la risposta API; con cookie manuale configura anche il percorso delle letture.
- **Gli ID non sono `sensor.ats_…`:** se avevi installato una versione precedente, gli ID già registrati restano quelli vecchi. Dalla pagina del dispositivo, menu ⋮, usa **Ricrea ID entità**.
- Per i log, attiva il livello debug per `custom_components.ats` e non condividere righe che contengono cookie o codici.

## Segnalare problemi

Apri una issue su GitHub descrivendo versione di Home Assistant, versione dell'integrazione e l'errore del log, **senza** cookie né codici dell'account.
