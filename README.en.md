# Alto Trevigiano Servizi (ATS) for Home Assistant

[🇮🇹 Italiano](README.md) · 🇬🇧 English

**Unofficial** Home Assistant integration that reads your water supplies, invoices and meter readings from the [Alto Trevigiano Servizi](https://sgc.altotrevigianoservizi.it/) customer area.

> Not affiliated with or endorsed by Alto Trevigiano Servizi. It uses the same requests the portal makes in your browser, so it may stop working if the portal changes.

> **Beta.8 candidate in the `EnrCol/ats-ha` fork.** Check that the prerelease has actually been published before upgrading production.
> Automatic mode uses **only your ATS online portal username and password** and discovers the customer and supplies without manual cookies or API paths.
> Do not replace a working production installation with this branch.
>
> This beta supports **one ATS config entry per Home Assistant instance**. Multiple supplies belonging to the same customer are aggregated; multiple separate customers under one login are not yet supported.

## What it does

- Supplies (`supply-light`): status, meter and supply data.
- Invoices (`invoice`): amounts, remaining balance, payments, due dates and billed consumption.
- Meter readings (`reading-base`): latest reading, consumption and history. Optional.

Everything is exposed as sensors under a single device named **ATS**.

### Sensors

The `entity_id` values in this table are **examples**, not guaranteed IDs: Home Assistant may add area/device prefixes or retain user-defined names. Every ATS sensor exposes a stable `ats_metric` attribute; the example dashboards discover the right entity dynamically.

| Entity | Content |
|---|---|
| `sensor.ats_utenze_attive` / `sensor.ats_utenze_totali` | Active and total supplies |
| `sensor.ats_dettagli_utenze_attive` | Display name **Dettagli utenze**: includes both active and ceased supplies in `utenza_1`, `utenza_2`… attributes |
| `sensor.ats_fatture_presenti` / `sensor.ats_fatture_non_pagate` | Invoice counts; `fatture_presenti` also exposes `riepilogo_annuale` and `storico_fatture` attributes |
| `sensor.ats_totale_fatture` / `sensor.ats_totale_pagato` / `sensor.ats_totale_residuo_da_pagare` | Totals in € |
| `sensor.ats_totale_fatture_anno_corrente` | Sum of invoices issued in the current calendar year (€), with year and invoice count as attributes |
| `sensor.ats_prossima_scadenza_fattura` / `sensor.ats_importo_prossima_scadenza` | Due date and remaining amount of the next open invoice |
| `sensor.ats_stato_ultima_fattura` | Latest invoice status, with number, period, amount and remaining balance as attributes |
| `sensor.ats_consumo_fatturato_totale` | Sum of consumption values on invoices, with **m³** unit (not a cumulative meter reading) |
| `sensor.ats_dettagli_fatture` | Existing `fattura_1`, `fattura_2`… ISO-date attributes retained; new `emissione_formattata` / `scadenza_formattata` dates use `DD-MM-YYYY` |
| `sensor.ats_ultima_lettura_contatore` | Latest reading in m³ |
| `sensor.ats_consumo_ultima_lettura` / `sensor.ats_data_ultima_lettura` | Latest reading consumption and date; the date state is `DD-MM-YYYY`, and the `data_iso` attribute preserves `YYYY-MM-DD` |
| `sensor.ats_dettagli_letture_contatore` | Attributes `lettura_1`, `lettura_2`… with the readings history |
| `sensor.ats_previsione_consumo_annuo` | Annualized consumption in m³/year from the latest two valid effective readings per active meter; ATS's own estimate is available in attributes |

With automatic login, invoices use an open-ended historical start date and readings use a rolling 365-day API window. In manual cookie mode, the readings path is optional.

Sensors measuring m³ or m³/year **suggest zero display decimals** without rounding their underlying values. Users can override display precision in Home Assistant entity settings. The `Data ultima lettura` sensor is now text-based: its state is `DD-MM-YYYY`, while `data_iso` preserves the machine-readable `YYYY-MM-DD`. It no longer exposes `device_class: date`; consumers requiring a native date should read the `data_iso` attribute. The [beta.5 Energia dashboard migration](docs/dashboard-energia-ats-beta5.md) documents the necessary template change.

### Financial history and annual calculations

- **Invoice count:** the state remains the total number of invoices returned by ATS. The `riepilogo_annuale` attribute groups invoices by **issue year**, with `numero_fatture`, `totale_fatturato` and `totale_pagato`; `storico_fatture` lists each invoice in descending date order with year, amount, issue/due dates, status and paid amount when available. New display dates are `DD-MM-YYYY`. `fatture_senza_data_emissione` counts invoices without a usable issue date.
- **Missing values:** when an invoice lacks a total or paid amount, the respective annual total is `null`, rather than a misleading partial sum. Invoices without an issue date remain in the detailed history but are not included in annual totals. The existing `Dettagli fatture` attributes and ISO dates remain unchanged, with additional `anno`, `emissione_formattata` and `scadenza_formattata` fields.
- **Current-year invoice total:** filtered by `EmissionDate` (issue date), not due date or billing period. Returns `€0` when invoices exist but none were issued this year. Returns `unknown` when the invoice list is empty or a current-year invoice amount is invalid.
- **Annual consumption forecast:** for each active supply meter, select the two latest distinct-date effective (`Effective=true`), positively validated readings. Formula: `(new reading - old reading) × 365 / elapsed days`. When multiple meters are active, sum **only if every active meter has a valid pair**. Exclude ceased supplies; insufficient or decreasing readings give `unknown`.
- The result is a **historical projection**, not live consumption. Attributes include source reading dates, sample period, and the supplier's own annual estimate `EstimatedAnnualConsumptyion`. Older readings may make the projection unrepresentative of current consumption.

## Installation

### With HACS (after publication to `main`)

> **Important:** HACS normally installs the repository's default branch (`main`), which does **not** contain this experimental version yet. Adding this repository to HACS will **not** install `feat/public-ats-onboarding` automatically.

1. In HACS open the ⋮ menu → **Custom repositories**.
2. Paste this repository's URL, choose the **Integration** category and click **Add**.
3. Search for **Alto Trevigiano Servizi (ATS)**, download it and **restart Home Assistant**.

### Beta via Marketplace

For our fork `EnrCol/ats-ha`, enable **pre-releases** for the repository, then use **Install another version** to select the desired beta tag. The fork's `main` does not yet include automatic onboarding: **do not install the old commit `2fdb8b2`**.

### Manual (to test this branch)

Download the ZIP of [`feat/public-ats-onboarding`](https://github.com/EnrCol/ats-ha/archive/refs/heads/feat/public-ats-onboarding.zip), extract it, and copy `custom_components/ats` into `/config/custom_components/ats`. Restart Home Assistant **only on a test instance**; do not replace a working production setup before real-world validation.

### Adding the integration

**Settings → Devices & services → Add integration → Alto Trevigiano Servizi (ATS)**. In automatic mode, enter your ATS portal username and password, leave API paths and cookie blank, and submit. SPID/CIE is not supported.

## Automatic setup (recommended)

1. Start the ATS integration setup flow in Home Assistant.
2. Keep the pre-filled **base URL** (`https://sgc.altotrevigianoservizi.it`).
3. Enter the **username and password** for the ATS online portal.
4. Leave **Supplies API path**, **Invoices API path**, **Readings API path**, and **Cookie** empty.
5. Submit. The integration verifies the login, discovers the session token and customer code from the authenticated page, then loads supplies, invoices and readings.

Active and ceased supplies are included; invoices and readings are aggregated for the selected customer. No browser developer tools or copied session cookies are required. A denied session triggers a new login attempt.

## Manual setup (legacy)

Use this only for an existing installation or when automatic setup is unsuitable. Without username/password, the legacy mode requires a **manual HTTP cookie** plus **supplies and invoices API paths**; the readings path is optional. A compatibility mode with credentials and manual paths can also renew session tokens.

To find paths:

1. Sign in to ATS in your browser and open **Developer tools → Network → Fetch/XHR**.
2. Browse **Supplies**, **Invoices**, and, optionally, **Readings**.
3. Copy only the portion starting with `/webapi/` from the corresponding `supply-light`, `invoice` and `reading-base` URLs. Do not include the domain. URLs may contain session tokens and must be treated as credentials.
4. For manual cookie mode only, paste the request's `Cookie` header into the integration's cookie field. Expired cookies must be replaced manually.

The update interval is in minutes (5 to 1440, default 60).

> **Privacy:** passwords, cookies, AT tokens embedded in API URLs, and customer codes are sensitive. Do not publish them in issues, logs or screenshots. Redact them before sharing diagnostics.

## Session lifetime

With ATS portal username/password the integration signs in automatically and retries once after a session denial. It does not implement SPID/CIE or HMAC signing. Session lifetimes and compatibility with other accounts still require testing.

If ATS explicitly rejects your stored credentials, Home Assistant starts a **reauthentication** flow: enter the new password for the same username and the integration reloads without recreating entities. Network errors and portal changes do not trigger password prompts. In manual cookie mode, update a revoked or expired cookie in the options form.

## Security

- Use only **ATS online portal credentials**, not SPID/CIE credentials.
- ATS passwords and manual cookies are stored in Home Assistant's config-entry data; this is not an encrypted password manager. Protect backups and the HA installation.
- The integration avoids writing passwords, cookies and AT tokens to its log and error messages. The AT token embedded in API URLs is an access credential: do not share complete URLs.
- The portal returns a `deprecated` header saying requests without an HMAC signature will eventually stop being accepted. This version does **not** implement HMAC.

## Limitations

- Fields are read from the JSON observed in the portal; the integration does not guess other endpoints and does not download invoice PDFs.
- Automatic discovery depends on the ATS authenticated page rendering `sol.conf`; portal changes may break it.
- Only one customer per Home Assistant instance is supported; selecting multiple separate customers under one login is not implemented.
- Missing values stay `unknown`; they are not replaced with zero.
- Total billed consumption sums the `Consumption` field of the invoices received: it may span several periods and is not a cumulative meter reading.

## Troubleshooting

- **Automatic setup fails:** check ATS portal credentials and portal availability. A `discovery_failed` message may mean ATS changed its authenticated HTML or session fields.
- **Manual mode fails:** check the cookie and API paths. Replace an expired cookie.
- **Reading sensors `unknown`:** there may be no reading in the selected period. Manual mode also requires a configured readings path to fetch them.
- **Entity IDs differ from `sensor.ats_…`:** this is normal when HA prefixes area/device names. Existing IDs remain untouched; **you do not need to rename entities** to use the beta.8 example dashboard. For your own automations use the ID actually assigned by HA.
- For logs, enable debug level for `custom_components.ats` and do not share lines containing cookies or codes.

## Reporting issues

Open a GitHub issue with your Home Assistant version, the integration version and the log error, **without** cookies or account codes.

## Beta.8 — complete installation with PDF viewer and example card

This beta includes automatic ATS login, sensors, yearly invoice history, the
`da_pagare` payment flag fix, `ats.download_invoices`, private invoice PDFs under
`/media/ats/fatture/YEAR/` and a PDF.js Lovelace card that opens PDFs **inside
Home Assistant**, including the Android Companion App.

1. In Home Assistant **Marketplace**, add **`EnrCol/ats-ha`** as a custom
   *Integration* repository and install prerelease **`v0.4.0-beta.8`** when
   published. Alternatively copy the entire **`custom_components/ats/`**
   directory (including its **`www/`** directory) into Home Assistant and
   restart Core.
2. Configure **Alto Trevigiano Servizi (ATS)** in Settings → Devices & services
   with **your own ATS portal username and password** (not SPID/CIE).
   Customer and supply discovery runs automatically.
3. Paste [`examples/ats-card.yaml`](examples/ats-card.yaml) into a new
   manual YAML dashboard card, or install the complete
   [`examples/ats-dashboard.yaml`](examples/ats-dashboard.yaml) view.
   The integration automatically registers the
   `custom:ats-invoice-history-card` frontend module. **No separate resource
   registration or /config/www file copy is needed.** Refresh the frontend
   after the initial install.
4. Click **Scarica fatture ATS mancanti** to download missing PDFs, then
   **Apri PDF** to view a document in place or **Scarica PDF** to download
   a local copy.

**Security:** PDFs are served through the authenticated
`/api/ats/invoice/{year}/{number}` endpoint, never through public
`/local` paths. The PDF.js viewer lazy-loads from **cdnjs.cloudflare.com**;
PDF bytes are processed in the browser and are not uploaded to the CDN.
The download button still works if PDF.js cannot load.

**Backup:** on HA Container, persist the `/media` directory and include it
in backups. `PdfExist` reflects availability on the **ATS portal**, not whether
the file has already been downloaded locally. See the
[clean-instance test checklist](docs/test-ha-clean.md) for setup and
verification. No personal invoice or credentials are distributed.


### Beta.8 — simplified first-run and native Lovelace registration

- **New setup:** only ATS portal **username**, **password**, and **polling interval** (60 minutes by default) are shown. HTTPS origin, invoice/supply paths and cookies are discovered and stored automatically. Already-configured legacy entries retain advanced options.
- **Lovelace card:** in storage resource mode ATS automatically registers `/ats_static/invoice-history-card.js?v=0.4.0b8` as a **module** resource, without duplicates on restart. Hard-refresh the frontend or reopen the Companion App after installation; in YAML resource mode the frontend module fallback is used and manual YAML registration may be needed.
- **Portable discovery:** all ATS sensors expose a stable `ats_metric` attribute. Example YAML finds the correct entities using `integration_entities('ats')` plus `ats_metric`, and the invoice card automatically discovers its sensor without requiring `entity:`. An optional explicit `entity:` override remains available. **No registered entity ID or unique ID is changed.**
- **Security:** invoices remain private under `/media/ats/fatture/` and are fetched using `fetchWithAuth()`; no public `/local` links.

### Beta.8 card — requirements and behavior

**Browser Mod is not required.** The card uses an HTML-native `dialog` with PDF.js loaded on first use. Once ATS is installed and configured, paste `examples/ats-card.yaml`; no entity renaming or manual resource installation is needed. The Lovelace module resource is also updated automatically on upgrades. If ATS is not yet available a message is displayed; if several candidate invoice sensors exist, set the optional `entity: sensor.actual_entity_id` override.
