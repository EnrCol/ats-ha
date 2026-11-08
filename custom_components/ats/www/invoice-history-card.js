class ATSInvoiceHistoryCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity || typeof config.entity !== "string") {
      throw new Error("ATS: indicare l'entità dello storico fatture");
    }
    this._config = config;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config.entity];
    const attrs = state && state.attributes ? state.attributes : {};
    const signature = JSON.stringify([attrs.riepilogo_annuale, attrs.storico_fatture]);
    if (signature === this._lastSignature) return;
    this._lastSignature = signature;
    this._render(attrs);
  }

  _e(tag, cls, value) {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (value !== undefined && value !== null) element.textContent = String(value);
    return element;
  }

  _money(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      return "non disponibile";
    }
    return new Intl.NumberFormat("it-IT", {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    }).format(Number(value)) + " €";
  }

  _render(attrs) {
    const previous = new Set();
    this.shadowRoot.querySelectorAll("details[data-year]").forEach((el) => {
      if (el.open) previous.add(el.dataset.year);
    });

    const years = attrs.riepilogo_annuale || {};
    const invoices = Array.isArray(attrs.storico_fatture) ? attrs.storico_fatture : [];
    const sortedYears = Object.keys(years).sort((a, b) => Number(b) - Number(a));
    this.shadowRoot.replaceChildren();

    const style = this._e("style");
    style.textContent = [
      ".container{padding:0 16px 16px}",
      "details{border-top:1px solid var(--divider-color);padding:10px 0}",
      "summary{font-weight:600;cursor:pointer;line-height:1.6}",
      ".invoice{display:flex;gap:12px;justify-content:space-between;align-items:center;",
      "border-top:1px solid var(--divider-color);padding:12px 0;flex-wrap:wrap}",
      ".details{min-width:180px;flex:1;line-height:1.55}",
      ".secondary{font-size:.88em;color:var(--secondary-text-color)}",
      "button{cursor:pointer;padding:9px 12px;border-radius:8px;",
      "background:var(--primary-color);color:white;border:0;min-height:38px}",
      ".pdf-actions{display:flex;gap:8px;flex-wrap:wrap}",
      "button:disabled{opacity:.6;cursor:wait}",
      ".notice{font-size:.88em;color:var(--secondary-text-color);padding:6px 0}",
      ".error{color:var(--error-color)}"
    ].join("");
    this.shadowRoot.appendChild(style);

    const card = this._e("ha-card");
    card.setAttribute("header", this._config.title || "Storico fatture ATS");
    const container = this._e("div", "container");
    this._message = this._e("div", "notice");
    this._message.setAttribute("role", "status");
    container.appendChild(this._message);

    if (!invoices.length) {
      container.appendChild(this._e("p", "", "Nessuna fattura disponibile."));
    } else {
      sortedYears.forEach((year, index) => {
        const details = this._e("details");
        details.dataset.year = year;
        details.open = previous.size ? previous.has(year) : index === 0;
        const summaryData = years[year] || {};
        const label = year + " · " + (summaryData.numero_fatture || 0) +
          " fatture · " + this._money(summaryData.totale_fatturato);
        details.appendChild(this._e("summary", "", label));

        invoices.filter((invoice) => String(invoice.anno) === year).forEach((invoice) => {
          const row = this._e("div", "invoice");
          const lines = this._e("div", "details");
          lines.appendChild(this._e("div", "", (invoice.emissione || "Data sconosciuta") +
            " · " + this._money(invoice.importo_totale)));
          lines.appendChild(this._e("div", "secondary", "Scadenza: " +
            (invoice.scadenza || "—") + " · Stato: " +
            (invoice.stato || "Non disponibile")));
          lines.appendChild(this._e("div", "secondary", "Pagato: " +
            this._money(invoice.importo_pagato)));
          row.appendChild(lines);

          if (invoice.pdf_disponibile === true &&
              typeof invoice.numero === "string" && invoice.numero.length) {
            const buttons = this._e("div", "pdf-actions");
            const button = this._e("button", "", "Apri PDF");
            button.type = "button";
            button.addEventListener("click", () => this._openPdf(year, invoice.numero, button, false));
            const download = this._e("button", "", "Scarica PDF");
            download.type = "button";
            download.addEventListener("click", () => this._openPdf(year, invoice.numero, download, true));
            buttons.appendChild(button);
            buttons.appendChild(download);
            row.appendChild(buttons);
          } else {
            row.appendChild(this._e("span", "secondary",
              invoice.pdf_disponibile === true ? "PDF in attesa di aggiornamento ATS" :
                "PDF non disponibile"));
          }
          details.appendChild(row);
        });
        container.appendChild(details);
      });
    }
    card.appendChild(container);
    this.shadowRoot.appendChild(card);
  }

  async _openPdf(year, number, button, download) {
    const yearText = String(year);
    if (!/^[0-9]{4}$/.test(yearText) ||
        !/^[A-Za-z0-9_-]{1,128}$/.test(number)) {
      this._message.textContent = "Identificativo fattura non valido.";
      this._message.classList.add("error");
      return;
    }

    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = download ? "Download..." : "Caricamento...";
    this._message.textContent = "";
    this._message.classList.remove("error");

    let blobUrl;
    try {
      if (!this._hass || typeof this._hass.fetchWithAuth !== "function") {
        throw new Error("Frontend HA senza fetchWithAuth");
      }
      const response = await this._hass.fetchWithAuth(
        "/api/ats/invoice/" + yearText + "/" + encodeURIComponent(number),
        { method: "GET", cache: "no-store" }
      );
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      const type = (response.headers.get("content-type") || "")
        .split(";")[0].trim().toLowerCase();
      if (type !== "application/pdf") {
        throw new Error("Risposta non PDF");
      }
      const pdf = await response.blob();
      if (pdf.size < 5 ||
          new TextDecoder("ascii").decode(await pdf.slice(0, 5).arrayBuffer()) !== "%PDF-") {
        throw new Error("Contenuto PDF non valido");
      }

      if (download) {
        // Existing Android-tested download path remains unchanged.
        blobUrl = URL.createObjectURL(pdf);
        const anchor = document.createElement("a");
        anchor.href = blobUrl;
        anchor.download = number + ".pdf";
        anchor.style.display = "none";
        this.shadowRoot.appendChild(anchor);
        anchor.click();
        anchor.remove();
        const later = blobUrl;
        setTimeout(() => URL.revokeObjectURL(later), 120000);
        blobUrl = null;
      } else {
        await this._viewPdfWithPdfJs(pdf, number);
      }
    } catch (_error) {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      this._message.textContent = download
        ? "Download PDF non riuscito. Riprova."
        : "Visualizzazione PDF non riuscita. Usa Scarica PDF oppure riprova.";
      this._message.classList.add("error");
    } finally {
      button.disabled = false;
      button.textContent = originalLabel;
    }
  }

  async _loadPdfJs() {
    // Fixed release: load code only when the user explicitly opens a PDF.
    // The PDF bytes stay in the WebView and are NOT sent to the CDN.
    if (!ATSInvoiceHistoryCard._pdfJsPromise) {
      ATSInvoiceHistoryCard._pdfJsPromise = import(
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs"
      ).then((pdfjs) => {
        pdfjs.GlobalWorkerOptions.workerSrc =
          "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";
        return pdfjs;
      }).catch((error) => {
        ATSInvoiceHistoryCard._pdfJsPromise = null;
        throw error;
      });
    }
    return ATSInvoiceHistoryCard._pdfJsPromise;
  }

  async _viewPdfWithPdfJs(pdfBlob, invoiceNumber) {
    // Native dialog stays in the same Android WebView; no external browser,
    // no blob: navigation and no publicly accessible file URL.
    if (this._pdfViewerDialog && this._pdfViewerDialog.open) {
      this._pdfViewerDialog.close();
    }
    const host = document.createElement("div");
    const root = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = [
      "dialog{box-sizing:border-box;width:min(96vw,950px);height:min(94dvh,1050px);",
      "max-width:96vw;max-height:94vh;padding:0;border:1px solid var(--divider-color);",
      "border-radius:12px;background:var(--card-background-color,#fff);",
      "color:var(--primary-text-color,#222);box-shadow:0 12px 42px #0005}",
      "dialog::backdrop{background:#0009}",
      ".panel{height:100%;display:flex;flex-direction:column;min-height:0}",
      ".top{display:flex;align-items:center;justify-content:space-between;",
      "gap:12px;padding:11px 14px;border-bottom:1px solid var(--divider-color)}",
      ".heading{font-weight:600;font-size:1em;overflow-wrap:anywhere}",
      ".controls{display:flex;align-items:center;justify-content:center;gap:8px;",
      "padding:9px;border-bottom:1px solid var(--divider-color);flex-wrap:wrap}",
      "button{border:1px solid var(--divider-color);border-radius:8px;",
      "background:var(--secondary-background-color,#f5f5f5);",
      "color:var(--primary-text-color,#222);font:inherit;min-width:38px;",
      "min-height:40px;padding:6px 12px;cursor:pointer}",
      "button:disabled{opacity:.45;cursor:wait}",
      ".scroll{flex:1;min-height:0;overflow:auto;background:#7773;text-align:center;",
      "padding:10px;box-sizing:border-box}",
      "canvas{display:block;margin:0 auto;max-width:none;background:white;box-shadow:0 2px 8px #0003}",
      ".status{padding:7px 12px;font-size:.85em;color:var(--secondary-text-color)}",
      "@media(max-width:480px){.top{padding:7px 10px}.controls{gap:5px;padding:6px}",
      "button{padding:5px 9px;min-width:35px}.scroll{padding:4px}}"
    ].join("");
    const dialog = document.createElement("dialog");
    const panel = document.createElement("div");
    panel.className = "panel";
    const top = document.createElement("div");
    top.className = "top";
    const heading = document.createElement("div");
    heading.className = "heading";
    heading.textContent = "Fattura ATS " + invoiceNumber;
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "Chiudi";
    close.addEventListener("click", () => dialog.close());
    top.append(heading, close);

    const controls = document.createElement("div");
    controls.className = "controls";
    const makeButton = (text, handler) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.addEventListener("click", handler);
      return button;
    };
    const prev = makeButton("‹", () => { if (pageNumber > 1 && !busy) { pageNumber--; void render(); } });
    const indicator = document.createElement("span");
    indicator.textContent = "—";
    const next = makeButton("›", () => {
      if (pdfDocument && pageNumber < pdfDocument.numPages && !busy) {
        pageNumber++;
        void render();
      }
    });
    const minus = makeButton("−", () => {
      if (!busy && zoom > 0.6) { zoom = Math.max(0.6, zoom - 0.2); void render(); }
    });
    const plus = makeButton("+", () => {
      if (!busy && zoom < 2.4) { zoom = Math.min(2.4, zoom + 0.2); void render(); }
    });
    controls.append(prev, indicator, next, minus, plus);

    const scroll = document.createElement("div");
    scroll.className = "scroll";
    const canvas = document.createElement("canvas");
    scroll.appendChild(canvas);
    const status = document.createElement("div");
    status.className = "status";
    status.setAttribute("role", "status");
    status.textContent = "Caricamento visualizzatore PDF…";
    panel.append(top, controls, scroll, status);
    dialog.appendChild(panel);
    root.append(style, dialog);
    document.body.appendChild(host);
    this._pdfViewerDialog = dialog;

    let pdfDocument = null;
    let loadingTask = null;
    let pageNumber = 1;
    let zoom = 1;
    let busy = false;
    let closed = false;
    let renderTask = null;

    const render = async () => {
      if (closed || busy || !pdfDocument) return;
      busy = true;
      prev.disabled = next.disabled = minus.disabled = plus.disabled = true;
      status.textContent = "Rendering pagina…";
      try {
        const page = await pdfDocument.getPage(pageNumber);
        if (closed) return;
        const base = page.getViewport({ scale: 1 });
        const fit = Math.min(1.8, Math.max(0.4, (scroll.clientWidth - 18) / base.width));
        const viewport = page.getViewport({ scale: fit * zoom });
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.ceil(viewport.width * ratio);
        canvas.height = Math.ceil(viewport.height * ratio);
        canvas.style.width = viewport.width + "px";
        canvas.style.height = viewport.height + "px";
        const context = canvas.getContext("2d", { alpha: false });
        if (!context) throw new Error("Canvas non disponibile");
        renderTask = page.render({
          canvasContext: context,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0]
        });
        await renderTask.promise;
        if (!closed) {
          indicator.textContent = pageNumber + " / " + pdfDocument.numPages;
          status.textContent = "Zoom " + Math.round(zoom * 100) + "%";
          scroll.scrollTop = 0;
        }
      } catch (error) {
        if (!closed) status.textContent = "Errore di rendering. Usa Scarica PDF.";
      } finally {
        busy = false;
        if (!closed) {
          prev.disabled = pageNumber <= 1;
          next.disabled = !pdfDocument || pageNumber >= pdfDocument.numPages;
          minus.disabled = zoom <= 0.6;
          plus.disabled = zoom >= 2.4;
        }
      }
    };

    dialog.addEventListener("close", () => {
      closed = true;
      if (renderTask) renderTask.cancel();
      if (loadingTask) void loadingTask.destroy();
      host.remove();
      if (this._pdfViewerDialog === dialog) this._pdfViewerDialog = null;
    }, { once: true });
    dialog.showModal();

    try {
      const pdfjs = await this._loadPdfJs();
      if (closed) return;
      status.textContent = "Caricamento fattura…";
      loadingTask = pdfjs.getDocument({ data: new Uint8Array(await pdfBlob.arrayBuffer()) });
      pdfDocument = await loadingTask.promise;
      if (closed) return;
      await render();
    } catch (_error) {
      if (!closed) {
        status.textContent =
          "PDF.js non disponibile o documento non leggibile. Chiudi e usa Scarica PDF.";
        status.style.color = "var(--error-color,#c33)";
      }
    }
  }

  getCardSize() {
    return 6;
  }
}

if (!customElements.get("ats-invoice-history-card")) {
  customElements.define("ats-invoice-history-card", ATSInvoiceHistoryCard);
}
