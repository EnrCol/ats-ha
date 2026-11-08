# Alto Trevigiano Servizi (ATS) for Home Assistant

[Italiano](README.md) · English · [Stable v0.4.0](https://github.com/EnrCol/ats-ha/releases/tag/v0.4.0)

**Unofficial integration** that brings water supplies, invoices, payments and meter readings from the [Alto Trevigiano Servizi customer portal](https://sgc.altotrevigianoservizi.it/) into Home Assistant. This project is **not** affiliated with, approved by, or supported by ATS. Portal changes can affect the integration.

**v0.4.0 is the first stable release of the [EnrCol/ats-ha fork](https://github.com/EnrCol/ats-ha)**, based on the original work by [Manu-Nat](https://github.com/Manu-Nat/ats-ha). It was functionally tested on Home Assistant TEST Core **2026.11.0**, with real ATS login, 19 sensors, 22 invoices, private PDF downloads, and the built-in Lovelace viewer. “Stable” indicates this project's release status, **not** official Home Assistant/ATS certification.

## Features

- **Minimal first-time configuration:** enter only your **ATS portal username**, **password**, and **polling interval** (default **60 minutes**, range 5–1440). ATS URL, session, customer code, supply IDs and API paths are discovered automatically. SPID/CIE login is not supported.
- **Session handling:** automatically logs in and renews expired sessions; Home Assistant can request reauthentication after invalid credentials without recreating the sensors. Network/portal errors are distinguished from password errors.
- **Water supplies:** active and total supply counts, meter number, address, status, balance and other available supply details, including discontinued supplies.
- **Invoice overview:** total/unpaid counts, total billed/paid/outstanding amounts, current-year total, billed water volume, most recent invoice status and next due date when applicable.
- **Yearly invoice history:** groups invoices by **issue year**, with yearly invoice count, billed and paid totals; chronological details with date, status, amount, payment and PDF availability. Missing financial data is represented as unknown/null instead of silently calculating misleading subtotals.
- **Meter readings:** most recent reading, reading-related consumption and date, plus history. The displayed date uses `DD-MM-YYYY`; `data_iso` contains a machine-readable date for templates.
- **Estimated yearly water usage (m³/year):** computes annualized usage from the two latest **effective, positively validated readings** for each active meter. The projection stays `unknown` if readings are insufficient; the portal's separate annual estimate may still be available in sensor attributes.
- **Private on-demand invoice PDFs:** call the `ats.download_invoices` service to download missing documents. Existing PDFs are skipped without overwrite. No recurring download on every sensor refresh.
- **Bundled Lovelace invoice history card:** expandable yearly sections, **Apri PDF / Open PDF** and **Scarica PDF / Download PDF** controls, a PDF.js in-app dialog with page navigation and zoom. Tested in the Android Home Assistant Companion App.
- **Portable dashboards:** the card automatically finds ATS invoice history with no `entity:` setting; all 19 sensors expose a stable `ats_metric` attribute, and sample YAML uses `integration_entities('ats')` instead of fixed entity IDs.
- **Automatic frontend resource:** registers/updates the JavaScript module in Lovelace storage mode. **Browser Mod is not required**; no copying JS into `/config/www`.

### All 19 ATS sensor metrics

Home Assistant may prefix or rename actual `entity_id` values based on the device, area or an existing entity registry. The stable `ats_metric` attribute is intended for dynamic lookups. Existing unique IDs remain unchanged.

| `ats_metric` | Sensor data |
|---|---|
| `active_supplies` | Active water supplies |
| `total_supplies` | All water supplies |
| `supply_details` | Supply details, including retired connections |
| `invoice_count` | Invoice count plus `storico_fatture` and `riepilogo_annuale` attributes |
| `unpaid_count` | Unpaid invoice count |
| `remaining_total` | Total outstanding amount (€) |
| `total_amount` | Total billed (€) |
| `invoices_current_year` | Total invoices issued in the current year (€) |
| `paid_total` | Total paid (€) |
| `next_expiry_amount` | Amount of the next invoice due (€) |
| `next_expiry_date` | Next due date |
| `consumption` | Total invoiced volume (m³), not the meter's cumulative reading |
| `last_status` | Latest invoice status |
| `invoice_details` | Individual invoice metadata |
| `last_reading_value` | Last meter reading (m³) |
| `last_reading_consumption` | Consumption associated with the last reading (m³) |
| `annual_consumption_forecast` | Annualized usage from validated readings; ATS estimate in attributes |
| `last_reading_date` | Reading date as `DD-MM-YYYY`, plus ISO attribute |
| `reading_details` | Meter reading history/details |

Invoice-year calculations use **issue date**, not billing-period dates. Paid invoices take precedence over potentially inconsistent raw `ToPay` flags. No data is invented for fields the portal does not provide. Forecasts are historical projections, not real-time usage measurements; the supplied m³ precision is retained even when HA suggests a no-decimal display.

## Install v0.4.0

### Marketplace / HACS (recommended)

1. In the Home Assistant **Marketplace** or HACS, add the custom repository `EnrCol/ats-ha`, category **Integration**.
2. Install **Alto Trevigiano Servizi (ATS)** version **v0.4.0** (the stable release, not an older beta).
3. **Restart Home Assistant** to activate the custom integration.
4. Open **Settings → Devices & services → Add integration → Alto Trevigiano Servizi**.
5. Enter your **ATS portal username and password**; optionally change the **polling interval** (60 minutes by default).
6. Check that the **ATS** device and its 19 sensors appear. You need credentials for the ATS customer portal, not SPID/CIE credentials.

### Manual installation

Download the [v0.4.0 source archive](https://github.com/EnrCol/ats-ha/archive/refs/tags/v0.4.0.zip), copy the complete `custom_components/ats/` directory (including `www/`) into `/config/custom_components/ats/`, restart HA, and complete the integration flow. Keep `/config` persistent. Do **not** copy config entries, passwords or invoice files from another installation.

Existing legacy setups retain advanced options for cookie, HTTPS origin and API paths. Those fields are not shown in the first-run wizard.

## Sample card and dashboard

The repository includes:

- **[Complete ATS card](examples/ats-card.yaml):** a `vertical-stack` showing a summary of supplies/invoices/consumption, a button to download missing PDFs, and the yearly invoice browser.
- **[Complete ATS dashboard](examples/ats-dashboard.yaml):** a full Lovelace dashboard with the same functionality.
- **[Bundled card JavaScript](custom_components/ats/www/invoice-history-card.js):** distributed with the integration and automatically registered.

To use the card, open a dashboard → **Edit dashboard → Add card → Manual**, then paste `examples/ats-card.yaml`. To add only the yearly PDF history:

```yaml
type: custom:ats-invoice-history-card
title: Storico fatture ATS
```

No `entity:` is required; the card finds the unique sensor with `ats_metric: invoice_count`, regardless of its area/device prefix. If the card finds several possible invoice sensors, an explicit `entity: sensor.YOUR_ACTUAL_ID` override remains available. The Markdown summary in both examples also identifies each metric dynamically using `integration_entities('ats')`.

On first installation or update, hard-refresh the browser or restart the Companion App. In Lovelace **storage mode**, `/ats_static/invoice-history-card.js?v=0.4.0` is automatically registered/updated as a JavaScript module. In Lovelace **YAML resource mode**, manual module registration may be required if the automatic frontend fallback does not load it.

**Browser Mod or any separate third-party card is not required.**

### PDF downloads and in-app viewer

1. Use the **Scarica fatture ATS mancanti** button in the complete card, or call `ats.download_invoices`.
2. With no arguments, it downloads missing available invoices; optionally pass `invoice_number` for a specific document.
3. Files are saved under `/media/ats/fatture/YEAR/INVOICE_NUMBER.pdf`. Existing files are not overwritten. PDFs are downloaded **on demand**, not during ordinary sensor polling.
4. In the invoice history select **Apri PDF** to display a document in HA, or **Scarica PDF** to save it on the device.

PDF.js loads from `cdnjs.cloudflare.com` when opening a PDF. The browser/WebView needs network access to that CDN; the invoice contents themselves **are not sent to the CDN**. If PDF.js cannot load, the **Scarica PDF** button still provides a download.

The `GET /api/ats/invoice/{year}/{number}` endpoint requires HA authentication and validates that an invoice is known and locally archived. The files are **not** served from public `/local` or `/config/www` paths. The `pdf_disponibile` attribute indicates availability at the **ATS portal**, not guaranteed prior local download.

For Home Assistant Container, persist `/media` if you need PDFs to survive redeployment and include it in an appropriately protected backup.

## Privacy: Recorder, documents and backups

The integration declares `_unrecorded_attributes = frozenset({MATCH_ALL})` for all **19 ATS sensors**. All current live attributes remain readable by dashboards and the invoice card, including `ats_metric`, yearly invoice histories, invoice/supply details, addresses and meter identifiers. **New Recorder history rows exclude integration-specific attributes** while retaining sensor state values and core metadata needed for statistics (such as unit and `state_class`). The integration does not add a global `recorder: exclude` rule.

**This is not retroactive.** Sensitive attributes recorded by earlier betas may still be present in the Recorder database and existing backups until normal retention or deliberate cleanup. Current attributes are still exposed to any HA user who has permission to read those sensors; Recorder minimization is not an access-control mechanism.

The private local PDF directory `/media/ats/fatture/` may contain **full personal data** present in an invoice, such as names, postal addresses, tax identifiers, dates and amounts. These PDFs are not published through `/local`, but users with authorized Home Assistant, filesystem, Media browser (where supported), snapshot or backup access may be able to read them. Protect your HA installation, storage and backups appropriately.

## Security and known limitations

- ATS portal credentials are held in the Home Assistant config entry, **not encrypted as in a password manager**. Protect your config and backup copies. Do not publish credentials, signed URLs, cookies, account/customer codes or session tokens in bug reports.
- PDF downloads validate the ATS signed HTTPS endpoint, expected host/path/query, content type and PDF signature; streaming size is limited and saved files are not overwritten. The local API also validates invoice identity/path and requires HA authentication.
- The integration relies on ATS WebForms and portal APIs. Portal changes can break login, data discovery or PDF download.
- **One ATS config entry per HA instance** is supported. Multiple supplies for the same customer are aggregated, but multiple distinct customer accounts under a single login are not currently supported.
- No SPID/CIE login. ATS has indicated that HMAC-signed API requests may be required in future; this integration does not implement that future protocol.
- Values remain `unknown` when there is no future unpaid invoice or too few validated readings. An unknown value should not be silently converted to zero.
- The primary functional verification was on HA Core **2026.11.0** in TEST. Not every HA version/account type was tested. Repeated removal/reinstallation on the same TEST database may cause Recorder history-migration warnings unrelated to ATS data retrieval.

## Verification and support

The beta.8 foundation passed **133 Python tests, 3 subtests and 6 JavaScript tests**, plus syntax, Hassfest and HACS checks. The live-account TEST run verified the login, 19 ATS metrics, 22 invoices, portable sample YAML and the authenticated PDF viewer **without Browser Mod**. These counts describe the test account, **not content bundled in the repository**.

- [v0.4.0 release notes](docs/releases/v0.4.0.md)
- [Clean-install verification checklist](docs/test-ha-clean.md)
- [Energy dashboard date/consumption migration](docs/dashboard-energia-ats-beta5.md)
- [Report issues](https://github.com/EnrCol/ats-ha/issues)

When reporting an issue, include HA version, ATS version, symptoms and redacted diagnostics; never include personal account or invoice details.
