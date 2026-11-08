# ATS beta.5 — migrazione della dashboard Energia

**Nota operativa:** questo file prepara la modifica, non la applica a Home Assistant.
La dashboard live `energia-monitoraggio` resta invariata finché non viene autorizzato esplicitamente il suo aggiornamento dopo l'installazione di beta.5.

## Sensore ATS

- Entità esistente: `sensor.ats_data_ultima_lettura` (stessi `entity_id` e `unique_id`).
- Nuovo stato testuale: `05-05-2026` (`GG-MM-AAAA`).
- Attributo ISO: `data_iso: "2026-05-05"` (`AAAA-MM-GG`).
- Icona: `mdi:calendar`.
- Non è più un sensore nativo di classe `date`. Le automazioni che eseguono confronti temporali devono usare `state_attr('sensor.ats_data_ultima_lettura', 'data_iso')`.

## Aggiornamento dashboard

Dashboard: **Energia** (`energia-monitoraggio`) → vista **Utenze** (`utenze`) → sezione **Acqua • ATS** → scheda Markdown di riepilogo.

Solo **dopo** l'installazione della beta.5 e la verifica che l'entità mostri il formato testuale, sostituire la riga:

```jinja2
**Ultima lettura:** {% set ultima_data = states('sensor.ats_data_ultima_lettura') %}{% if ultima_data not in ['unknown', 'unavailable', 'none', ''] %}{{ as_datetime(ultima_data).strftime('%d-%m-%Y') }}{% else %}Non disponibile{% endif %}
```

con:

```jinja2
**Ultima lettura:** {% set ultima_data = states('sensor.ats_data_ultima_lettura') %}{% if ultima_data not in ['unknown', 'unavailable', 'none', ''] %}{{ ultima_data }}{% else %}Non disponibile{% endif %}
```

Il valore è già formattato dall'integrazione, quindi non bisogna più chiamare `as_datetime()` sullo stato.
Lo storico di 22 fatture nella seconda scheda Markdown non necessita modifiche.

Per calcoli e confronti in altri template, usare l'attributo ISO:

```jinja2
{{ as_datetime(state_attr('sensor.ats_data_ultima_lettura', 'data_iso')) if state_attr('sensor.ats_data_ultima_lettura', 'data_iso') else none }}
```

## Verifiche e rollback

1. Prima della scrittura rileggere la configurazione dashboard e conservarne un backup puntuale.
2. Controllare il formato `GG-MM-AAAA` nel dispositivo ATS e `data_iso` negli attributi.
3. Applicare la sostituzione usando gli strumenti Home Assistant MCP, con controllo dell'hash della dashboard.
4. Verificare il rendering di `Ultima lettura` e lo storico di 22 fatture.
5. Rollback dashboard: ripristinare la riga precedente; rollback integrazione: reinstallare beta.4 e riavviare HA, dopo specifica autorizzazione.
