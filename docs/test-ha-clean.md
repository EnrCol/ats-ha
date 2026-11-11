# Test ATS v0.4.1 su Home Assistant pulito

## Perimetro
- Target: HA Core **2026.11.0** o compatibile, HAOS oppure Container.
- Nessuna migrazione da produzione: non trasferire file `.storage`, cookie,
  password, backup, archivi di fatture o token.
- Verificare che `/config` e `/media` siano persistenti sul Container.
- Il collaudo completo dei dati personali richiede un **account ATS valido
  inserito direttamente nell'istanza di test**.

## Installazione
1. Prima del test salvare uno snapshot o backup della configurazione di test.
2. Installare la release `v0.4.1` dal fork `EnrCol/ats-ha`
   attraverso Marketplace (repository personalizzato, categoria *Integrazione*).
   In alternativa copiare **tutta** `custom_components/ats`.
3. Riavviare Home Assistant una volta sola per caricare il codice Python.
4. Da *Impostazioni → Dispositivi e servizi* aggiungere ATS e inserire
   username/password dello Sportello Online ATS; non usare SPID/CIE.
5. Verificare che la config entry sia `loaded` e il dispositivo ATS sia presente.
6. Verificare l'azione `ats.download_invoices` e i sensori ATS.
7. Incollare `examples/ats-card.yaml` come scheda manuale in una nuova dashboard.
   Il componente `ats-invoice-history-card` deve caricarsi senza
   aggiungere alcuna risorsa JS manuale.
8. Aggiornare la pagina; su Android chiudere e riaprire la Companion App.

## Collaudo funzionale
- [ ] Login corretto con credenziali valide e individuazione delle forniture.
- [ ] Login errato: errore chiaro e nessuna config entry funzionante.
- [ ] Sensori di conteggio, importi, letture, previsione e dati disponibili.
- [ ] Fatture pagate: `da_pagare = false` anche quando `ToPay` grezzo è incongruente.
- [ ] `storico_fatture`: numeri, date e `pdf_disponibile`, nessun totale inventato.
- [ ] Primo avvio: PDF non ancora presente in `/media` → apertura non riuscita
      in modo sicuro, senza creare URL pubblici.
- [ ] Eseguire `ats.download_invoices` e verificare salvataggio in
      `/media/ats/fatture/YYYY/Numero.pdf`.
- [ ] Ripetere il download: PDF esistenti saltati (no duplicati).
- [ ] `Apri PDF`: viewer interno PDF.js, zoom e cambio pagina.
- [ ] `Scarica PDF`: funziona anche su Samsung Companion App.
- [ ] Endpoint `/api/ats/invoice/{year}/{number}`: senza token → 401;
      numero non presente / anno errato / file assente → 404.
- [ ] Nessun PDF in `/config/www` e nessuna credenziale nei log.
- [ ] Dashboard renderizzata da utente normale autenticato.
- [ ] Dopo riavvio e logout/login, dati e viewer tornano disponibili.
- [ ] Backup Container include la persistenza del volume `/media`.

## Risultati e limiti
Distingui **CI verde**, **installazione completata**, **account ATS verificato**
e **test Android del viewer**: sono prove diverse. Non dichiarare testate le
ultime due senza credenziali valide e una verifica sul dispositivo.

## Rollback
Ripristinare backup della dashboard; rimuovere la card e l'integrazione ATS
dalla test instance e reinstallare la versione precedente se necessaria.
Il file archivio `/media/ats/fatture` non va eliminato automaticamente.
Il live non deve essere modificato dal collaudo.

## Verifiche v0.4.1 — installazione davvero pulita

- [ ] Solo **username, password, intervallo** nel form iniziale; nessun cookie o percorso API.
- [ ] Nessuna entry ATS, entità ATS, dashboard ATS, risorsa card ATS e installazione Marketplace residua prima di installare.
- [ ] Cancellare i PDF TEST preesistenti *solo se la capacità di rimozione è disponibile via HA MCP*; non modificare altri volumi o il live.
- [ ] La release sul TEST installa la card in Lovelace Resources, con URL `/ats_static/invoice-history-card.js?v=0.4.1`.
- [ ] La dashboard di esempio mostra sensori `sensor.ats_*` e nessun errore *Custom element doesn't exist*.
- [ ] Download fatture e apertura PDF funzionanti, con le credenziali inserite **solo** sul TEST.
- [ ] Il riavvio con frontend ricostruito non crea un doppione della risorsa JS.

## v0.4.1 — portabilità completa
- [ ] Il riepilogo mostra i valori corretti con entity_id automaticamente prefissati dall'area o dal dispositivo.
- [ ] La card dello storico funziona senza `entity:` e apre i PDF con PDF.js, anche senza Browser Mod.
- [ ] Modificare l'entity_id del sensore ATS sul TEST: il riepilogo e la card devono continuare a funzionare.
- [ ] Passare dalla beta.7 alla v0.4.1: la risorsa Lovelace viene aggiornata all'URL `?v=0.4.1`, senza duplicati.
- [ ] Installazione precedente: `unique_id` e identificativi già registrati non vengono modificati.
- [ ] Sensore temporaneamente non disponibile: la card mostra un messaggio leggibile, non un errore rosa.

## Privacy e Recorder v0.4.1
- [ ] Dopo l'aggiornamento il sensore `invoice_count` continua a esporre `storico_fatture`, `riepilogo_annuale` e `ats_metric` **nello stato corrente**.
- [ ] I nuovi record Recorder dei sensori ATS non includono gli attributi personalizzati (indirizzi, POD, dettagli fatture, letture).
- [ ] Stati numerici e statistiche (se il sensore ha una `state_class` valida) rimangono disponibili.
- [ ] La privacy è **non retroattiva**: i backup e lo storico esistenti possono contenere gli attributi delle versioni beta.
- [ ] I PDF completi restano protetti nell'archivio `/media` e non vengono esposti in `/local`.
- [ ] Il visualizzatore funziona anche senza Browser Mod.
- [ ] Su un'istanza che ha installato molte beta, eventuali conflitti Recorder su vecchi entity_id non vengono confusi con problemi di login o lettura ATS.
