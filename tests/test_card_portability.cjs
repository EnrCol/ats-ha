"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const classes = new Map();
const sandbox = {
  HTMLElement: class {
    attachShadow() {
      this.shadowRoot = {};
      return this.shadowRoot;
    }
  },
  customElements: {
    define: (tag, cls) => classes.set(tag, cls),
    get: (tag) => classes.get(tag)
  }
};

const source = fs.readFileSync(
  path.join(__dirname, "../custom_components/ats/www/invoice-history-card.js"),
  "utf8"
);
vm.runInNewContext(source, sandbox, { filename: "invoice-history-card.js" });
const Card = classes.get("ats-invoice-history-card");

function state(marker = "invoice_count") {
  return {
    state: "22",
    attributes: {
      ats_metric: marker,
      storico_fatture: [{ anno: 2026, numero: "INV_1" }],
      riepilogo_annuale: { 2026: { numero_fatture: 1 } }
    }
  };
}

function card(config = {}) {
  const instance = new Card();
  instance.setConfig(config);
  instance._render = (attrs) => {
    instance.rendered = attrs;
    instance._message = { textContent: "" };
  };
  return instance;
}

test("automatically resolves prefixed ATS invoice entity via ats_metric", () => {
  const c = card({ title: "ATS" });
  c.hass = {
    states: {
      "sensor.unrelated": { state: "1", attributes: {} },
      "sensor.locale_tecnico_ats_ats_fatture_presenti": state(),
      "sensor.ats_fatture_non_pagate": state("unpaid_count")
    }
  };
  assert.equal(c.rendered.storico_fatture.length, 1);
  assert.equal(c._message.textContent, "");
});

test("still resolves legacy sensors by the invoice-history attributes", () => {
  const legacy = state();
  delete legacy.attributes.ats_metric;
  const c = card();
  c.hass = { states: { "sensor.custom_renamed_invoice": legacy } };
  assert.equal(c.rendered.storico_fatture.length, 1);
});

test("explicit entity override works when multiple candidates exist", () => {
  const c = card({ entity: "sensor.ats_b" });
  c.hass = { states: { "sensor.ats_a": state(), "sensor.ats_b": state() } };
  assert.equal(c.rendered.storico_fatture.length, 1);
  assert.equal(c._message.textContent, "");
});

test("multiple ATS invoice sensors are never silently confused", () => {
  const c = card();
  c.hass = { states: { "sensor.ats_a": state(), "sensor.ats_b": state() } };
  assert.equal(c.rendered.storico_fatture, undefined);
  assert.match(c._message.textContent, /più storici ATS/);
});

test("missing ATS integration produces an actionable message", () => {
  const c = card();
  c.hass = { states: {} };
  assert.match(c._message.textContent, /configura l'integrazione/);
});

test("bad explicit entity is rejected", () => {
  assert.throws(() => card({ entity: "" }), /entity/);
  assert.throws(() => card({ entity: 4 }), /entity/);
});
