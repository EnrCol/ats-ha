# Alto Trevigiano Servizi (ATS) per Home Assistant

🇮🇹 Italiano · [🇬🇧 English](README.en.md)

Integrazione **non ufficiale** per Home Assistant che legge dall'area utente di [Alto Trevigiano Servizi](https://sgc.altotrevigianoservizi.it/) le tue forniture idriche, le fatture e le letture del contatore.

> Non è affiliata né approvata da Alto Trevigiano Servizi. Usa le stesse richieste che il portale esegue nel tuo browser, quindi può smettere di funzionare se il portale cambia.

> **Ramo sperimentale `feat/public-ats-onboarding`.** Non è ancora una release pubblica.
> La modalità automatica usa **solo username e password dello Sportello Online ATS**: identifica il cliente e le forniture senza chiedere cookie o percorsi API.
> Non sostituire una installazione live funzionante con questo ramo.
>
> È supportata **una sola configurazione ATS per istanza Home Assistant**. Più forniture appartenenti allo stesso cliente vengono aggregate; più clienti distinti sotto lo stesso login non sono ancora supportati.

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

Con login automatico le fatture vengono richieste senza data iniziale fissa e le letture su una finestra mobile di 365 giorni; con cookie manuale il percorso API delle letture è facoltativo.

## Installazione

### Con HACS (consigliata)

1. In HACS apri il menu ⋮ → **Repository personalizzati**.
2. Incolla l'URL di questo repository, scegli la categoria **Integrazione** e premi **Aggiungi**.
3. Cerca **Alto Trevigiano Servizi (ATS)**, scaricala e **riavvia Home Assistant**.

### Manuale

Copia la cartella `custom_components/ats` in `/config/custom_components/ats` e riavvia Home Assistant.

### Aggiunta dell'integrazione

**Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Alto Trevigiano Servizi (ATS)**. Per la modalità automatica inserisci username e password dello Sportello Online ATS, lascia vuoti i percorsi API e il cookie, quindi conferma. Non usare SPID/CIE.

## Configurazione automatica (consigliata)

1. Accedi a Home Assistant e apri la procedura di aggiunta dell'integrazione ATS.
2. Lascia l'**URL base** precompilato (`https://sgc.altotrevigianoservizi.it`).
3. Inserisci **username e password** dello Sportello Online ATS.
4. Lascia **vuoti** `Percorso API utenze`, `Percorso API fatture`, `Percorso API letture` e `Cookie`.
5. Conferma: l'integrazione verifica il login, recupera dall'HTML autenticato il token di sessione e il codice cliente, quindi interroga le API delle forniture, delle fatture e delle letture.

L'elenco delle forniture include anche quelle cessate; le fatture e le letture vengono aggregate per le forniture del cliente selezionato. Non è necessario copiare dati dagli strumenti sviluppatore. È previsto il rinnovo del login quando il portale rifiuta la sessione.

## Configurazione manuale (legacy)

Usala solo per mantenere un'installazione precedente o se la configurazione automatica non è applicabile. Senza username/password servono un **cookie HTTP manuale** e i **percorsi API utenze e fatture**; il percorso letture è facoltativo. Con credenziali e percorsi manuali resta disponibile una modalità di compatibilità che rinnova il token di sessione.

Per individuare i percorsi:

1. Accedi al portale ATS nel browser e apri **Strumenti sviluppatore → Rete → Fetch/XHR**.
2. Visita le pagine **Forniture**, **Fatture** e, se necessario, **Letture**.
3. Copia solo la parte dell'URL che parte da `/webapi/` per le rispettive richieste `supply-light`, `invoice`, `reading-base`; non includere il dominio. Gli URL possono contenere token di sessione: trattali come credenziali.
4. Nella sola modalità cookie, inserisci anche il valore dell'intestazione `Cookie` nel campo dedicato. I cookie scadono e vanno sostituiti manualmente.

L'intervallo di aggiornamento è in minuti (da 5 a 1440, predefinito 60).

> **Privacy:** password, cookie, token AT negli URL e codici cliente sono dati riservati. Non pubblicarli in issue, log o screenshot. Oscurali prima di condividere diagnostiche.

## Durata della sessione

Con **username e password ATS** l'integrazione esegue il login al portale e riprova dopo un rifiuto della sessione. Questo meccanismo non implementa il login SPID/CIE né la firma HMAC. La durata della sessione non è documentata e il comportamento su altri account richiede ulteriori test.

Se ATS rifiuta esplicitamente username o password, Home Assistant avvia la procedura di **riautenticazione**: inserisci soltanto la nuova password e l'integrazione ricarica i dati conservando le entità. Errori di rete e modifiche al portale non avviano una richiesta di password. In modalità cookie manuale, un cookie revocato o scaduto deve essere sostituito nelle opzioni.

## Sicurezza

- Usa esclusivamente le credenziali di accesso **allo Sportello Online ATS**; non inserire credenziali SPID/CIE.
- Password ATS e cookie sono memorizzati nella configurazione Home Assistant; non sono cifrati come in un password manager. Proteggi backup, file e accesso all'istanza.
- L'integrazione evita di scrivere cookie, password e token AT nei messaggi di log ed errore. Il token AT presente nell'URL API è una credenziale di accesso: non condividere URL completi.
- Il portale segnala con un header `deprecated` che in futuro le richieste senza firma HMAC non saranno più accettate. Questa versione **non** implementa HMAC.

## Limiti

- I campi sono letti dai JSON osservati nel portale; l'integrazione non inventa altri endpoint e non scarica i PDF delle fatture.
- La modalità automatica dipende dall'oggetto `sol.conf` nell'HTML autenticato di ATS: se il portale cambia, la scoperta può smettere di funzionare.
- La configurazione resta limitata a un cliente per istanza Home Assistant; la selezione di più clienti sotto un solo login non è supportata.
- I valori assenti restano `unknown`, non vengono sostituiti con zero.
- Il consumo fatturato totale somma il campo `Consumption` delle fatture ricevute: può coprire più periodi e non è una lettura cumulativa del contatore.

## Risoluzione problemi

- **Errore nella configurazione automatica:** verifica le credenziali dello Sportello Online ATS e la disponibilità del portale. Se compare `discovery_failed`, ATS potrebbe aver modificato l'HTML o i dati della sessione.
- **Modalità manuale:** controlla cookie e percorsi API; se la sessione scade, aggiorna il cookie.
- **Sensori delle letture `unknown`:** controlla la risposta API; con cookie manuale configura anche il percorso delle letture.
- **Gli ID non sono `sensor.ats_…`:** se avevi installato una versione precedente, gli ID già registrati restano quelli vecchi. Dalla pagina del dispositivo, menu ⋮, usa **Ricrea ID entità**.
- Per i log, attiva il livello debug per `custom_components.ats` e non condividere righe che contengono cookie o codici.

## Segnalare problemi

Apri una issue su GitHub descrivendo versione di Home Assistant, versione dell'integrazione e l'errore del log, **senza** cookie né codici dell'account.
