from __future__ import annotations

from datetime import datetime

from homeassistant.const import MATCH_ALL
from homeassistant.util import dt as dt_util
from typing import Any

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

def _date(value):
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
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S",
                "%d/%m/%Y", "%d-%m-%Y"):
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

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ATSAggregateSensor(coordinator, entry, "supplies_active", "Utenze attive", "active_supplies"),
        ATSAggregateSensor(coordinator, entry, "supplies_total", "Utenze totali", "total_supplies"),
        ATSAggregateSensor(coordinator, entry, "invoices_total", "Fatture presenti", "invoice_count"),
        ATSAggregateSensor(coordinator, entry, "invoices_unpaid", "Fatture non pagate", "unpaid_count"),
        ATSAggregateSensor(coordinator, entry, "invoices_remaining", "Totale residuo da pagare", "remaining_total", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "invoices_amount", "Totale fatture", "total_amount", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "invoices_paid", "Totale pagato", "paid_total", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "next_expiry_amount", "Importo prossima scadenza", "next_expiry_amount", unit=CURRENCY_EURO),
        ATSAggregateSensor(coordinator, entry, "next_expiry_date", "Prossima scadenza fattura", "next_expiry_date", device_class=SensorDeviceClass.DATE),
        ATSAggregateSensor(coordinator, entry, "invoiced_consumption", "Consumo fatturato totale", "consumption"),
        ATSAggregateSensor(coordinator, entry, "last_invoice_status", "Stato ultima fattura", "last_status"),
        ATSAggregateSensor(coordinator, entry, "active_supply_details", "Dettagli utenze attive", "supply_details"),
        ATSAggregateSensor(coordinator, entry, "invoice_details", "Dettagli fatture", "invoice_details"),
        ATSAggregateSensor(coordinator, entry, "last_reading_value", "Ultima lettura contatore", "last_reading_value", unit="m³"),
        ATSAggregateSensor(coordinator, entry, "last_reading_consumption", "Consumo ultima lettura", "last_reading_consumption", unit="m³"),
        ATSAggregateSensor(coordinator, entry, "last_reading_date", "Data ultima lettura", "last_reading_date", device_class=SensorDeviceClass.DATE),
        ATSAggregateSensor(coordinator, entry, "reading_details", "Dettagli letture contatore", "reading_details"),
    ])

class ATSAggregateSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    # Keep core state and statistics in Recorder but avoid archiving supply
    # addresses, meters, invoice details and other ATS-specific attributes.
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator, entry, key, name, metric, unit=None, device_class=None):
        super().__init__(coordinator)
        self._key = key
        self._metric = metric
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(coordinator, entry.entry_id)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        if unit == CURRENCY_EURO or metric in ("active_supplies", "total_supplies", "invoice_count", "unpaid_count"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_extra_state_attributes = {}

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        supplies = data.get("supplies") or []
        invoices = data.get("invoices") or []
        readings = data.get("readings") or []
        if self._metric in ("last_reading_value", "last_reading_consumption", "last_reading_date", "reading_details"):
            if not readings:
                self._attr_extra_state_attributes = {"nota": "Configura il percorso API /webapi/api/v1/reading-base/{id} nelle opzioni dell'integrazione ATS."}
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
                return (_date(latest.get("Date")).date() if _date(latest.get("Date")) else None)
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
            return len(supplies) if self.coordinator.data is not None else None
        if self._metric == "invoice_count":
            return len(invoices) if self.coordinator.data is not None else None
        if self._metric == "unpaid_count":
            return sum(
                1 for i in invoices
                if i.get("Payed") is not True and (
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
            today = dt_util.now().date()
            upcoming = []
            for inv in invoices:
                if inv.get("Payed") is True or inv.get("ToPay") is False:
                    continue
                dt = _date(inv.get("ExpirationDate"))
                if dt is not None and dt.date() >= today:
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
            return len(supplies) if supplies else None
        if self._metric == "invoice_details":
            self._attr_extra_state_attributes = {
                f"fattura_{idx+1}": {
                    "stato": i.get("StatusText"),
                    "importo_totale": i.get("TotalAmount"),
                    "residuo": _first(i, "RemainingAmount", "RemainigAmount"),
                    "pagato": i.get("PaidAmount"),
                    "emissione": i.get("EmissionDate"),
                    "scadenza": i.get("ExpirationDate"),
                    "periodo_da": i.get("PeriodFrom"),
                    "periodo_a": i.get("PeriodTo"),
                    "consumo": i.get("Consumption"),
                    "pagata": i.get("Payed"),
                    "da_pagare": False if i.get("Payed") is True else i.get("ToPay"),
                    "da_pagare_ats": i.get("ToPay"),
                    "pdf_disponibile": i.get("PdfExist"),
                } for idx, i in enumerate(invoices)
            }
            return len(invoices) if invoices else None
        return None