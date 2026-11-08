from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from typing import Any

from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

CURRENCY_EURO = "€"
from .const import DOMAIN

def _device_info(coordinator, entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="ATS",
        manufacturer="ATS (unofficial)",
        model="Area Utente",
        entry_type=DeviceEntryType.SERVICE,
    )

def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

_FALLBACK_DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y",
    "%d-%m-%Y",
)


def _date(value):
    """Parse an ATS date/datetime.

    ATS currently returns ISO 8601 (e.g. 2026-05-05T00:00:00), which stays the
    primary format. Day-first GG/MM/AAAA and GG-MM-AAAA are accepted as a
    preventive fallback so the sensors keep working if ATS ever changes format.
    ISO is tried first, so an unambiguous YYYY-MM-DD is never misread.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        pass
    for fmt in _FALLBACK_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None

def _first(d: dict, *keys):
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return None


def _display_date(value: Any) -> str | None:
    """Render a valid ATS date as GG-MM-AAAA without modifying stored ISO dates."""
    parsed = _date(value)
    return parsed.strftime("%d-%m-%Y") if parsed is not None else None


def _invoice_history(invoices: list[dict]) -> dict:
    """Build one compact chronological history and yearly financial totals.

    Only EmissionDate determines the invoice year, never the billing period.
    An unknown invoice amount or payment keeps that year's corresponding
    total unknown instead of reporting a misleading partial sum.
    """
    annual: dict[str, dict] = {}
    chronological: list[tuple[date, dict]] = []
    missing_dates = 0

    for invoice in invoices:
        issued = _date(invoice.get("EmissionDate"))
        year = issued.year if issued is not None else None
        amount = _number(invoice.get("TotalAmount"))
        if amount is not None and not isfinite(amount):
            amount = None
        paid = _number(invoice.get("PaidAmount"))
        if paid is not None and not isfinite(paid):
            paid = None

        chronological.append((
            issued.date() if issued is not None else date.min,
            {
                "anno": year,
                "numero": str(invoice.get("No") or "").strip() or None,
                "pdf_disponibile": invoice.get("PdfExist") is True,
                "importo_totale": amount,
                "emissione": _display_date(invoice.get("EmissionDate")),
                "scadenza": _display_date(invoice.get("ExpirationDate")),
                "stato": invoice.get("StatusText"),
                "importo_pagato": paid,
            },
        ))

        if year is None:
            missing_dates += 1
            continue
        bucket = annual.setdefault(str(year), {
            "numero_fatture": 0,
            "totale_fatturato": 0.0,
            "totale_pagato": 0.0,
        })
        bucket["numero_fatture"] += 1
        for field, value in (
            ("totale_fatturato", amount),
            ("totale_pagato", paid),
        ):
            if value is None:
                bucket[field] = None
            elif bucket[field] is not None:
                bucket[field] += value

    for bucket in annual.values():
        for field in ("totale_fatturato", "totale_pagato"):
            if bucket[field] is not None:
                bucket[field] = round(bucket[field], 2)

    chronological.sort(key=lambda item: item[0], reverse=True)
    return {
        "riepilogo_annuale": dict(sorted(annual.items(), reverse=True)),
        "storico_fatture": [item for _, item in chronological],
        "fatture_senza_data_emissione": missing_dates,
    }


def _invoice_total_for_year(invoices: list[dict], year: int) -> tuple[float | None, int]:
    """Reuse the same issued-year totals as the invoice-count history."""
    if not invoices:
        return None, 0
    year_data = _invoice_history(invoices)["riepilogo_annuale"].get(str(year))
    if year_data is None:
        return 0.0, 0
    return year_data["totale_fatturato"], year_data["numero_fatture"]


def _annualized_consumption(
    supplies: list[dict], readings: list[dict]
) -> tuple[float | None, dict]:
    """Annualize effective, positively validated readings for every active meter.

    All active meters must have two dated readings with valid nondecreasing
    values. Never mix a ceased meter or two different meter numbers.
    """
    active = [
        supply for supply in supplies
        if supply.get("Active") is True
        or str(supply.get("StateDescription", "")).strip().lower() == "attiva"
    ]
    estimated = [_number(s.get("EstimatedAnnualConsumptyion")) for s in active]
    estimated_total = (
        round(sum(estimated), 1)
        if active and all(v is not None and isfinite(v) for v in estimated)
        else None
    )
    details: dict = {
        "metodo": "ultime_due_letture_effettive_validate_per_contatore",
        "stima_ats_m3_anno": estimated_total,
        "contatori_attivi": len(active),
    }
    if not active:
        details["nota"] = "Nessuna fornitura attiva disponibile."
        return None, details

    meters = {
        str(s.get("MeterNo") or "").strip() for s in active
    }
    if "" in meters:
        details["nota"] = "Identificativo contatore mancante su una fornitura attiva."
        return None, details

    totals = []
    breakdown = []
    for meter in sorted(meters):
        valid = []
        for reading in readings:
            if str(reading.get("MeterNo") or "").strip() != meter:
                continue
            if reading.get("Effective") is not True:
                continue
            if str(reading.get("ValidationResult") or "").strip().lower() not in (
                "positiva", "positivo", "positive"
            ):
                continue
            read_date = _date(reading.get("Date"))
            value = _number(reading.get("Value"))
            if read_date is None or value is None or not isfinite(value) or value < 0:
                continue
            valid.append((read_date.date(), value))
        valid.sort(reverse=True, key=lambda item: item[0])
        # Duplicate readings from the same date do not form an interval.
        distinct = []
        for read_date, value in valid:
            if not distinct or read_date != distinct[-1][0]:
                distinct.append((read_date, value))
            if len(distinct) == 2:
                break
        if len(distinct) < 2:
            details["nota"] = "Servono due letture effettive validate per ogni contatore attivo."
            return None, details
        (recent_date, recent_value), (older_date, older_value) = distinct
        days = (recent_date - older_date).days
        delta = recent_value - older_value
        if days <= 0 or delta < 0:
            details["nota"] = "Letture non confrontabili: intervallo o valore del contatore non valido."
            return None, details
        projected = delta * 365 / days
        totals.append(projected)
        breakdown.append({
            "contatore": meter,
            "data_prima_lettura": older_date.isoformat(),
            "data_ultima_lettura": recent_date.isoformat(),
            "periodo_giorni": days,
            "consumo_periodo_m3": round(delta, 2),
            "previsione_m3_anno": round(projected, 1),
        })

    details["dettaglio_contatori"] = breakdown
    if len(breakdown) == 1:
        details.update({
            "data_prima_lettura": breakdown[0]["data_prima_lettura"],
            "data_ultima_lettura": breakdown[0]["data_ultima_lettura"],
            "periodo_giorni": breakdown[0]["periodo_giorni"],
            "consumo_periodo_m3": breakdown[0]["consumo_periodo_m3"],
        })
    return round(sum(totals), 1), details


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ATSAggregateSensor(coordinator, entry, "supplies_active", "Utenze attive", "active_supplies"),
        ATSAggregateSensor(coordinator, entry, "supplies_total", "Utenze totali", "total_supplies"),
        ATSAggregateSensor(coordinator, entry, "invoices_total", "Fatture presenti", "invoice_count"),
        ATSAggregateSensor(coordinator, entry, "invoices_unpaid", "Fatture non pagate", "unpaid_count"),
        ATSAggregateSensor(coordinator, entry, "invoices_remaining", "Totale residuo da pagare", "remaining_total", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "invoices_amount", "Totale fatture", "total_amount", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "invoices_current_year", "Totale fatture anno corrente", "invoices_current_year", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "invoices_paid", "Totale pagato", "paid_total", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "next_expiry_amount", "Importo prossima scadenza", "next_expiry_amount", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "next_expiry_date", "Prossima scadenza fattura", "next_expiry_date", device_class=SensorDeviceClass.DATE),
        ATSAggregateSensor(coordinator, entry, "invoiced_consumption", "Consumo fatturato totale", "consumption", unit="m³"),
        ATSAggregateSensor(coordinator, entry, "last_invoice_status", "Stato ultima fattura", "last_status"),
        ATSAggregateSensor(coordinator, entry, "active_supply_details", "Dettagli utenze", "supply_details"),
        ATSAggregateSensor(coordinator, entry, "invoice_details", "Dettagli fatture", "invoice_details"),
        ATSAggregateSensor(coordinator, entry, "last_reading_value", "Ultima lettura contatore", "last_reading_value", unit="m³"),
        ATSAggregateSensor(coordinator, entry, "last_reading_consumption", "Consumo ultima lettura", "last_reading_consumption", unit="m³"),
        ATSAggregateSensor(coordinator, entry, "annual_consumption_forecast", "Previsione consumo annuo", "annual_consumption_forecast", unit="m³/anno"),
        ATSAggregateSensor(coordinator, entry, "last_reading_date", "Data ultima lettura", "last_reading_date"),
        ATSAggregateSensor(coordinator, entry, "reading_details", "Dettagli letture contatore", "reading_details"),
    ])

class ATSAggregateSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, metric, unit=None, device_class=None):
        super().__init__(coordinator)
        self._key = key
        self._metric = metric
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(coordinator, entry.entry_id)
        self._attr_native_unit_of_measurement = unit
        # Display whole cubic metres while preserving full numeric sensor values.
        if unit in ("m³", "m³/anno"):
            self._attr_suggested_display_precision = 0
        self._attr_device_class = device_class
        if metric == "last_reading_date":
            # Text state GG-MM-AAAA; machine-readable ISO remains in data_iso.
            self._attr_icon = "mdi:calendar"
        if unit == CURRENCY_EURO or metric in ("active_supplies", "total_supplies", "invoice_count", "unpaid_count", "annual_consumption_forecast"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_extra_state_attributes = {}

    @property
    def suggested_object_id(self) -> str:
        """Stable new-install entity IDs, independent of area/device prefixes.

        Existing entity registry IDs are not renamed: unique_id is unchanged.
        """
        return f"ats_{slugify(self._attr_name)}"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        supplies = data.get("supplies") or []
        invoices = data.get("invoices") or []
        readings = data.get("readings") or []
        if self._metric == "invoices_current_year":
            year = dt_util.now().year
            total, count = _invoice_total_for_year(invoices, year)
            self._attr_extra_state_attributes = {
                "anno": year,
                "numero_fatture": count,
                "criterio": "data_emissione",
            }
            return total
        if self._metric == "annual_consumption_forecast":
            forecast, details = _annualized_consumption(supplies, readings)
            self._attr_extra_state_attributes = details
            return forecast
        if self._metric in ("last_reading_value", "last_reading_consumption", "last_reading_date", "reading_details"):
            if not readings:
                if getattr(self.coordinator, "uses_credentials", False):
                    # Automatic/credentials mode: readings are fetched on their
                    # own; an empty result just means none in the period.
                    self._attr_extra_state_attributes = {
                        "nota": "Nessuna lettura del contatore disponibile per il periodo."
                    }
                else:
                    self._attr_extra_state_attributes = {
                        "nota": "Configura il percorso API /webapi/api/v1/reading-base/{id} nelle opzioni dell'integrazione ATS."
                    }
                return None
            def reading_date(item):
                parsed = _date(item.get("Date"))
                if parsed is None:
                    return 0.0
                try:
                    return parsed.timestamp()
                except (OverflowError, OSError, ValueError):
                    return 0.0
            latest = max(readings, key=reading_date)
            if self._metric == "last_reading_value":
                self._attr_extra_state_attributes = {"data": latest.get("Date"), "tipo": latest.get("Type"), "stato": latest.get("ReadingStatus"), "fatturata": latest.get("Invoiced"), "validazione": latest.get("ValidationResult"), "contatore": latest.get("MeterNo")}
                return _number(latest.get("Value"))
            if self._metric == "last_reading_consumption":
                self._attr_extra_state_attributes = {"data": latest.get("Date"), "tipo": latest.get("Type"), "lettura_effettiva": latest.get("Effective"), "validazione": latest.get("ValidationResult"), "fatturata": latest.get("Invoiced")}
                return _number(latest.get("Consumption"))
            if self._metric == "last_reading_date":
                parsed = _date(latest.get("Date"))
                self._attr_extra_state_attributes = {
                    "data_iso": parsed.date().isoformat() if parsed is not None else None,
                }
                return parsed.strftime("%d-%m-%Y") if parsed is not None else None
            self._attr_extra_state_attributes = {
                f"lettura_{idx+1}": {
                    "data": item.get("Date"), "valore": item.get("Value"), "tipo": item.get("Type"),
                    "consumo": item.get("Consumption"), "effettiva": item.get("Effective"),
                    "validazione": item.get("ValidationResult"), "fatturata": item.get("Invoiced"),
                    "stato": item.get("ReadingStatus"), "contatore": item.get("MeterNo"),
                } for idx, item in enumerate(sorted(readings, key=reading_date, reverse=True))
            }
            return len(readings)
        if self._metric == "active_supplies":
            return sum(1 for s in supplies if s.get("Active") is True or str(s.get("StateDescription", "")).lower() == "attiva")
        if self._metric == "total_supplies":
            # 0 when the API replied with an empty list; unknown only when no
            # data is available yet (failed/first refresh).
            return len(supplies) if self.coordinator.data is not None else None
        if self._metric == "invoice_count":
            self._attr_extra_state_attributes = _invoice_history(invoices)
            return len(invoices) if self.coordinator.data is not None else None
        if self._metric == "unpaid_count":
            # ATS can report ToPay=True even for settled historical invoices.
            # An explicit Payed=True always takes precedence.
            return sum(
                1
                for i in invoices
                if i.get("Payed") is not True
                and (
                    i.get("Payed") is False
                    or i.get("ToPay") is True
                    or str(i.get("StatusText", "")).lower() in ("non pagata", "non pagato")
                )
            )
        if self._metric == "remaining_total":
            vals = [_number(_first(i, "RemainingAmount", "RemainigAmount")) for i in invoices]
            vals = [v for v in vals if v is not None]
            return round(sum(vals), 2) if vals else None
        if self._metric == "total_amount":
            vals = [_number(i.get("TotalAmount")) for i in invoices]
            vals = [v for v in vals if v is not None]
            return round(sum(vals), 2) if vals else None
        if self._metric == "paid_total":
            vals = [_number(i.get("PaidAmount")) for i in invoices]
            vals = [v for v in vals if v is not None]
            return round(sum(vals), 2) if vals else None
        if self._metric == "consumption":
            vals = [_number(i.get("Consumption")) for i in invoices]
            vals = [v for v in vals if v is not None]
            return round(sum(vals), 3) if vals else None
        if self._metric in ("next_expiry_date", "next_expiry_amount"):
            # The next expiry is the earliest FUTURE due date among unpaid
            # invoices; already-overdue invoices are not "next".
            today = dt_util.now().date()
            upcoming = []
            for inv in invoices:
                if inv.get("Payed") is True or inv.get("ToPay") is False:
                    continue
                dt = _date(inv.get("ExpirationDate"))
                if dt is None or dt.date() < today:
                    continue
                upcoming.append((dt, _number(_first(inv, "RemainingAmount", "RemainigAmount"))))
            if not upcoming:
                return None
            dt, amount = sorted(upcoming, key=lambda x: x[0])[0]
            return dt.date() if self._metric == "next_expiry_date" else amount
        if self._metric == "last_status":
            if not invoices:
                return None
            sorted_invoices = sorted(invoices, key=lambda i: _date(i.get("EmissionDate")) or datetime.min, reverse=True)
            inv = sorted_invoices[0]
            self._attr_extra_state_attributes = {
                "numero": inv.get("No"),
                "emissione": inv.get("EmissionDate"),
                "scadenza": inv.get("ExpirationDate"),
                "importo_totale": inv.get("TotalAmount"),
                "residuo": _first(inv, "RemainingAmount", "RemainigAmount"),
                "consumo_fatturato": inv.get("Consumption"),
                "periodo_da": inv.get("PeriodFrom"),
                "periodo_a": inv.get("PeriodTo"),
                "pdf_disponibile": inv.get("PdfExist"),
            }
            return inv.get("StatusText")
        if self._metric == "supply_details":
            self._attr_extra_state_attributes = {
                f"utenza_{idx+1}": {
                    "attiva": s.get("Active"),
                    "stato": s.get("StateDescription"),
                    "servizio": s.get("Service"),
                    "indirizzo": s.get("SupplyFullAddress"),
                    "contatore": s.get("MeterNo"),
                    "pod": s.get("POD"),
                    "saldo": s.get("Balance", s.get("Saldo")),
                    "consumo_annuo_stimato": s.get("EstimatedAnnualConsumptyion"),
                } for idx, s in enumerate(supplies)
            }
            return len(supplies) if self.coordinator.data is not None else None
        if self._metric == "invoice_details":
            self._attr_extra_state_attributes = {
                f"fattura_{idx+1}": {
                    "stato": i.get("StatusText"),
                    "importo_totale": i.get("TotalAmount"),
                    "residuo": _first(i, "RemainingAmount", "RemainigAmount"),
                    "pagato": i.get("PaidAmount"),
                    "anno": _date(i.get("EmissionDate")).year if _date(i.get("EmissionDate")) else None,
                    "emissione": i.get("EmissionDate"),
                    "scadenza": i.get("ExpirationDate"),
                    "emissione_formattata": _display_date(i.get("EmissionDate")),
                    "scadenza_formattata": _display_date(i.get("ExpirationDate")),
                    "periodo_da": i.get("PeriodFrom"),
                    "periodo_a": i.get("PeriodTo"),
                    "consumo": i.get("Consumption"),
                    "pagata": i.get("Payed"),
                    "da_pagare": False if i.get("Payed") is True else i.get("ToPay"),
                    "da_pagare_ats": i.get("ToPay"),
                    "pdf_disponibile": i.get("PdfExist"),
                } for idx, i in enumerate(invoices)
            }
            return len(invoices) if self.coordinator.data is not None else None
        return None