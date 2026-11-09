# Alto Trevigiano Servizi (ATS) per Home Assistant

🇮🇹 Italiano · [🇬🇧 English](README.en.md)

Integrazione **non ufficiale** per Home Assistant che legge dall'area utente di [Alto Trevigiano Servizi](https://sgc.altotrevigianoservizi.it/) le tue forniture idriche, le fatture e le letture del contatore.

> Non è affiliata né approvata da Alto Trevigiano Servizi. Usa le stesse richieste che il portale esegue nel tuo browser, quindi può smettere di funzionare se il portale cambia.

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

I sensori delle letture restano `unknown` finché non configuri il percorso delle letture.

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

L'integrazione non chiede username e password: usa i percorsi delle richieste API e il cookie di sessione che il portale usa quando sei collegato. Li prendi dagli strumenti per sviluppatori del browser (qui i nomi delle voci sono quelli di Chrome in italiano; in Edge e Firefox sono molto simili).

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
7. Sempre in **Intestazioni**, scorri fino a **Intestazioni della richiesta** e copia il valore della riga **cookie** (per esempio `ASP.NET_SessionId=…`), tutto, compreso il nome prima del segno `=`. Va nel campo **Cookie HTTP della sessione**.
8. Controlla che la richiesta sia `GET` con codice `200 OK` e che nella scheda **Risposta** o **Anteprima** compaia un JSON con i tuoi dati.

L'intervallo di aggiornamento è in minuti (da 5 a 1440, predefinito 60).

> I percorsi contengono codici legati al tuo account e il cookie equivale a una password. Non incollarli in issue, forum, log o screenshot. Se devi mostrare qualcosa, oscura i codici.

## Durata della sessione

L'integrazione usa il cookie di sessione del portale e non implementa né il rinnovo automatico dell'accesso SPID né la firma HMAC. Finora, nell'uso reale, il cookie è rimasto valido nel tempo senza bisogno di essere rinnovato, ma la durata **non è documentata dal portale** e non è garantita: la sessione potrebbe terminare, per esempio dopo un logout dal portale, una revoca o una scadenza lato server.

Se smette di funzionare, l'aggiornamento fallisce e Home Assistant mostra l'errore di aggiornamento dell'integrazione. Rifai i passi 1–7 per prendere un cookie nuovo e aggiornalo in **Impostazioni → Dispositivi e servizi → ATS → Configura**: l'integrazione si ricarica da sola. Per non invalidare il cookie in uso, evita di fare logout dal portale nel browser da cui l'hai copiato.

## Sicurezza

- Non inserire credenziali SPID o password del portale.
- Il cookie viene salvato nella configurazione di Home Assistant, che non è un archivio cifrato per segreti.
- L'integrazione non scrive il cookie nei log.
- Il portale segnala con un header `deprecated` che in futuro le richieste senza firma HMAC non saranno più accettate. Questa versione **non** implementa HMAC.

## Limiti

- I campi sono letti dai JSON osservati nel portale; l'integrazione non inventa altri endpoint e non scarica i PDF delle fatture.
- Che una richiesta funzioni nel browser non garantisce da sola che la sessione sia riutilizzabile da Home Assistant.
- I valori assenti restano `unknown`, non vengono sostituiti con zero.
- Il consumo fatturato totale somma il campo `Consumption` delle fatture ricevute: può coprire più periodi e non è una lettura cumulativa del contatore.

## Correzioni e privacy dei sensori

- Se il portale riporta `Payed=true`, la fattura è considerata **pagata** anche se il campo `ToPay` è incongruente. I dettagli mantengono `da_pagare_ats` come valore originale per la diagnosi.
- La "prossima scadenza" esclude le date passate e le fatture già pagate.
- Sono riconosciute le date ISO e le date italiane `GG/MM/AAAA` e `GG-MM-AAAA`.
- Se la risposta API contiene un elenco valido ma vuoto, i conteggi mostrano **0**.
- Per minimizzare i dati nel database, gli **attributi aggiuntivi** ATS (indirizzi, contatori e dettagli fatture) sono omessi dalle nuove registrazioni di Recorder. Rimangono disponibili in tempo reale nel frontend e continuano a essere registrabili gli stati/statistiche. **I vecchi record e i backup non vengono ripuliti retroattivamente.**

## Risoluzione problemi

- **Errore all'aggiunta o entità non disponibili:** controlla che i percorsi comincino con `/`, che siano completi di codici e che il cookie sia ancora valido (vedi *Durata della sessione*).
- **Sensori delle letture `unknown`:** manca il percorso delle letture; aggiungilo da **Configura**.
- **Gli ID non sono `sensor.ats_…`:** se avevi installato una versione precedente, gli ID già registrati restano quelli vecchi. Dalla pagina del dispositivo, menu ⋮, usa **Ricrea ID entità**.
- Per i log, attiva il livello debug per `custom_components.ats` e non condividere righe che contengono cookie o codici.

## Segnalare problemi

Apri una issue su GitHub descrivendo versione di Home Assistant, versione dell'integrazione e l'errore del log, **senza** cookie né codici dell'account.
