import { UI, CHECK_NAMES } from "./i18n.js";

const API = "/api/v1";
const LANES = ["ON_HOLD", "PROCESSED", "REJECTED"];
const LANE_LABEL = { ON_HOLD: "onHold", PROCESSED: "processed", REJECTED: "rejected" };
const STAGES = ["stageUpload", "stageRead", "stageCheck", "stageRate"];
const MAX_BYTES = 10 * 1024 * 1024;

const store = {
  get(key, fallback = null) { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* private mode */ } },
};

const state = {
  key: store.get("ph.key"),
  lang: store.get("ph.lang", "en"),
  workspace: null,
  docs: [],
  pending: [],
  selected: null,
  details: new Map(),
  tab: "details",
  readLang: null,
  translations: new Map(),
  pdfUrls: new Map(),
  samples: null,
};

const $ = (selector) => document.querySelector(selector);
const t = (key) => (UI[state.lang] && UI[state.lang][key]) || UI.en[key] || key;

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (name === "class") node.className = value;
    else if (name === "style") node.style.cssText = value;
    else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (name === "dataset") Object.assign(node.dataset, value);
    else node.setAttribute(name, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const inr = (value, currency = "INR") => (value == null ? "–"
  : new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value)));
const dateFmt = (iso) => {
  if (!iso) return "–";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return new Intl.DateTimeFormat(`${state.lang}-IN`, { day: "numeric", month: "short", year: "numeric" }).format(d);
};
const timeFmt = (iso) => new Intl.DateTimeFormat(`${state.lang}-IN`, {
  day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
}).format(new Date(iso));
const vendorName = (doc) => doc.invoice.trade_name || doc.invoice.vendor_name || doc.filename;
const isNarrow = () => matchMedia("(max-width: 860px)").matches;

/* ---------- API ---------- */
class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}

async function api(path, { method = "GET", json, body, raw = false } = {}) {
  const headers = { Authorization: `Bearer ${state.key}` };
  if (json !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(API + path, { method, headers, body: json !== undefined ? JSON.stringify(json) : body });
  } catch {
    throw new ApiError(0, "NETWORK", t("gone"));
  }
  if (!response.ok) {
    let error = {};
    try { error = (await response.json()).error || {}; } catch { /* not json */ }
    if (response.status === 401 && path !== "/workspace") disconnect(true);
    throw new ApiError(response.status, error.code || "HTTP_ERROR", error.message || response.statusText);
  }
  return raw ? response : response.json();
}

function toast(message, tone = "") {
  const node = h("div", { class: `toast ${tone}` }, message);
  $("#toasts").append(node);
  setTimeout(() => node.remove(), 4200);
}

/* ---------- Language and theme ---------- */
function applyLanguage() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-t]").forEach((node) => { node.textContent = t(node.dataset.t); });
  $("#ui-lang").value = state.lang;
  document.querySelectorAll("[data-lang]").forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.lang === state.lang)));
}

function setLanguage(lang) {
  state.lang = lang;
  store.set("ph.lang", lang);
  applyLanguage();
  if (state.workspace) renderAll();
}

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme; else delete document.documentElement.dataset.theme;
}
applyTheme(store.get("ph.theme"));

/* ---------- Connect ---------- */
async function connect(key) {
  state.key = key;
  try {
    state.workspace = await api("/workspace");
  } catch (error) {
    state.key = null;
    throw error;
  }
  store.set("ph.key", key);
  $("#connect").hidden = true;
  $("#shell").hidden = false;
  $("#brand-name").textContent = state.workspace.business_name;
  $("#cash").textContent = inr(state.workspace.cash_available, state.workspace.currency);
  state.docs = await api("/documents");
  renderAll();
}

function disconnect(expired = false) {
  store.set("ph.key", null);
  Object.assign(state, { key: null, workspace: null, docs: [], selected: null });
  state.details.clear();
  for (const url of state.pdfUrls.values()) URL.revokeObjectURL(url);
  state.pdfUrls.clear();
  closeDrawer();
  $("#shell").hidden = true;
  $("#connect").hidden = false;
  const error = $("#connect-error");
  error.hidden = !expired;
  error.textContent = expired ? t("badKey") : "";
  $("#key-input").value = "";
  $("#key-input").focus();
}

/* ---------- Board ---------- */
function renderAll() {
  renderPending();
  renderBoard();
  if (state.selected) renderDetail();
}

function scoreBadge(doc) {
  const score = doc.rating.score;
  if (score == null) return null;
  const high = score >= doc.rating.threshold;
  return h("span", { class: `score ${high ? "high" : ""}`, title: t("rating") },
    h("span", { class: "bar", "aria-hidden": "true" }, h("i", { style: `width:${score}%` })), `${score}/100`);
}

function card(doc) {
  const inv = doc.invoice;
  const reason = doc.lane !== "PROCESSED" ? doc.reasons[0] : null;
  return h("li", {}, h("button", {
    class: "card", type: "button", dataset: { id: doc.document_id },
    "aria-current": String(state.selected === doc.document_id),
    onclick: () => openDrawer(doc.document_id),
  },
  h("span", { class: "card-top" },
    h("span", { class: "card-name" }, vendorName(doc)),
    h("span", { class: "card-amount" }, inv.grand_total ? inr(inv.grand_total, inv.currency || "INR") : "–")),
  reason ? h("span", { class: `card-reason ${reason.severity === "block" ? "block" : ""}` }, reason.text) : null,
  h("span", { class: "card-meta" },
    h("span", { class: "card-ids" }, inv.invoice_number ? h("span", {}, inv.invoice_number) : null,
      inv.payment_deadline ? h("span", {}, `${t("payBy")} ${dateFmt(inv.payment_deadline)}`) : null),
    scoreBadge(doc))));
}

function renderBoard() {
  for (const lane of LANES) {
    const docs = state.docs.filter((doc) => doc.lane === lane);
    const sum = docs.reduce((acc, doc) => acc + Number(doc.invoice.grand_total || 0), 0);
    $(`#count-${lane}`).textContent = docs.length;
    const total = $(`#sum-${lane}`);
    if (total) total.textContent = docs.length ? inr(sum) : "";
    const list = $(`#cards-${lane}`);
    list.replaceChildren(...(docs.length ? docs.map(card)
      : [h("li", { class: "empty" }, t(lane === "ON_HOLD" ? "emptyHold" : lane === "PROCESSED" ? "emptyProcessed" : "emptyRejected"))]));
  }
  $("#rejected").hidden = !state.docs.some((doc) => doc.lane === "REJECTED");
}

function renderPending() {
  $("#pending").replaceChildren(...state.pending.map((item) => h("li", {},
    h("span", { class: "name" }, item.name),
    item.failed ? h("span", { class: "failed" }, item.failed)
      : h("span", { class: "stages" }, STAGES.map((stage, index) => h("span", {
        class: `stage ${index < item.stage ? "done" : index === item.stage ? "on" : ""}`,
      }, t(stage)))))));
}

/* ---------- Drawer ---------- */
async function openDrawer(id) {
  const fresh = state.selected !== id;
  state.selected = id;
  if (fresh) state.tab = "details";
  $("#scrim").hidden = false;
  const drawer = $("#detail");
  drawer.hidden = false;
  renderBoard();
  renderDetail(true);
  drawer.focus({ preventScroll: true });
  try {
    const full = await api(`/documents/${id}`);
    replaceDoc(full);
    if (state.selected === id) { renderBoard(); renderDetail(); }
  } catch (error) { toast(error.message, "stop"); }
}

function closeDrawer() {
  const id = state.selected;
  state.selected = null;
  $("#scrim").hidden = true;
  $("#detail").hidden = true;
  if (state.workspace) renderBoard();
  if (id) document.querySelector(`.card[data-id="${id}"]`)?.focus();
}

function replaceDoc(doc) {
  const index = state.docs.findIndex((d) => d.document_id === doc.document_id);
  if (index >= 0) state.docs[index] = doc; else state.docs.unshift(doc);
  state.details.set(doc.document_id, doc);
}

function meter(doc, animate) {
  const score = doc.rating.score ?? 0;
  const threshold = doc.rating.threshold;
  const fill = h("div", { class: "meter-fill" });
  const track = h("div", {
    class: "meter-track", role: "meter", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": score, "aria-label": t("rating"),
  }, fill, h("div", { class: "meter-mark", style: `left:${threshold}%` }, h("span", {}, threshold)));
  if (animate) {
    track.style.setProperty("--score", "0%");
    requestAnimationFrame(() => requestAnimationFrame(() => track.style.setProperty("--score", `${score}%`)));
  } else track.style.setProperty("--score", `${score}%`);
  return h("div", { class: `meter ${score >= threshold ? "pass" : ""}` },
    h("div", { class: "meter-score" }, doc.rating.score == null ? "–" : score, h("small", {}, " /100")),
    h("div", { class: "meter-label" }, h("span", {}, t("rating")), h("span", {}, t("threshold"))),
    track);
}

function decisionPanel(doc) {
  if (doc.lane === "PROCESSED") {
    return h("section", { class: "decision PROCESSED" },
      h("h3", {}, t("readyTitle")),
      h("p", {}, t("readyBody")),
      doc.review.status === "VERIFIED" && doc.review.note ? h("p", { class: "note" }, `${t("reviewedBy")}: ${doc.review.note}`) : null,
      h("div", { class: "decision-actions" },
        h("button", { class: "btn btn-go", type: "button", onclick: () => handOff(doc) }, t("pay"))));
  }
  const panel = h("section", { class: `decision ${doc.lane}` },
    h("h3", {}, doc.lane === "REJECTED" ? t("rejected") : t("whyHold")),
    h("ul", { class: "reasons" }, doc.reasons.map((reason) => h("li", { class: reason.severity }, reason.text))));
  if (doc.lane === "REJECTED") {
    if (doc.review.note) panel.append(h("p", { class: "note" }, `${t("reviewedBy")}: ${doc.review.note}`));
    return panel;
  }
  const actions = h("div", { class: "decision-actions" });
  if (doc.can_verify) actions.append(h("button", { class: "btn btn-tape", type: "button", onclick: () => openReview(doc, "verify") }, t("verify")));
  if (doc.can_recheck) actions.append(h("button", { class: "btn btn-ghost", type: "button", onclick: (e) => recheck(doc, e.currentTarget) }, t("recheck")));
  if (doc.can_reject) actions.append(h("button", { class: "btn btn-stop", type: "button", onclick: () => openReview(doc, "reject") }, t("reject")));
  panel.append(actions);
  if (!doc.can_verify) panel.append(h("p", { class: "hint" }, t("ruleLocked")));
  return panel;
}

function detailsPanel(doc) {
  const inv = doc.invoice;
  const cur = inv.currency || "INR";
  const facts = [
    [t("vendor"), inv.vendor_name, !inv.vendor_registered && inv.vendor_name ? t("notRegistered") : null],
    [t("gstin"), inv.gstin], [t("invoiceNo"), inv.invoice_number], [t("invoiceDate"), dateFmt(inv.invoice_date)],
    [t("payBy"), dateFmt(inv.payment_deadline)], [t("bank"), inv.bank_reference],
  ];
  if (inv.handwritten || (inv.language && inv.language !== "en")) {
    facts.push([t("origLang"), `${state.workspace.languages[inv.language] || inv.language || "–"}${inv.handwritten ? `, ${t("handwritten").toLowerCase()}` : ""}`]);
  }
  const panel = h("div", { class: "dpanel" },
    h("dl", { class: "facts" }, facts.map(([label, value, flag]) => h("div", {},
      h("dt", {}, label), h("dd", {}, value || "–", flag ? h("span", { class: "flag" }, flag) : null)))));
  if (inv.items.length || inv.grand_total) {
    panel.append(h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, t("item")), h("th", { class: "r" }, t("qty")), h("th", { class: "r" }, t("rate")), h("th", { class: "r" }, t("amount")))),
      h("tbody", {}, inv.items.map((item) => h("tr", {},
        h("td", {}, item.description), h("td", { class: "r" }, item.quantity),
        h("td", { class: "r" }, inr(item.unit_price, cur)), h("td", { class: "r" }, inr(item.amount, cur))))),
      h("tfoot", {},
        h("tr", {}, h("td", { colspan: 3 }, t("subtotal")), h("td", { class: "r" }, inr(inv.subtotal, cur))),
        inv.taxes.map((tax) => h("tr", {}, h("td", { colspan: 3 }, `${tax.name} ${tax.rate}%`), h("td", { class: "r" }, inr(tax.amount, cur)))),
        h("tr", { class: "total" }, h("td", { colspan: 3 }, t("total")), h("td", { class: "r" }, inr(inv.grand_total, cur)))))));
    if (inv.amount_in_words) panel.append(h("p", { class: "words" }, `${t("words")}: ${inv.amount_in_words}`));
  } else if (inv.extraction_error) {
    panel.append(h("p", { class: "hint" }, inv.extraction_error));
  }
  if (doc.decision) {
    const order = { BLOCK: 0, HOLD: 1, PASS: 2 };
    const checks = [...doc.decision.results].sort((a, b) => order[a.status] - order[b.status]);
    panel.append(h("h4", { class: "section-title" }, t("checks")),
      h("ul", { class: "checks" }, checks.map((check) => h("li", { class: check.status, title: check.detail },
        h("span", { class: "mark", "aria-hidden": "true" }, check.status === "PASS" ? "✓" : check.status === "HOLD" ? "!" : "✕"),
        h("span", {}, CHECK_NAMES[check.code] || check.code.replaceAll("_", " ").toLowerCase()),
        h("span", { class: "sr" }, check.status)))));
  }
  if (doc.rating.signals.length) {
    panel.append(h("h4", { class: "section-title" }, t("signals")),
      h("ul", { class: "signals" }, doc.rating.signals.map((signal) => h("li", {},
        h("span", {}, signal.detail), signal.impact ? h("span", { class: "impact" }, `−${signal.impact}`) : null))));
  }
  return panel;
}

function originalPanel(doc) {
  const panel = h("div", { class: "dpanel" });
  const url = state.pdfUrls.get(doc.document_id);
  if (url) {
    panel.append(h("iframe", { class: "pdf-frame", src: `${url}#navpanes=0&view=FitH`, title: doc.filename }));
    return panel;
  }
  panel.append(h("div", { class: "skeleton", style: "height:420px" }));
  api(`/documents/${doc.document_id}/file`, { raw: true })
    .then((response) => response.blob())
    .then((blob) => {
      state.pdfUrls.set(doc.document_id, URL.createObjectURL(new Blob([blob], { type: "application/pdf" })));
      if (state.selected === doc.document_id && state.tab === "original") renderDetail();
    })
    .catch((error) => panel.replaceChildren(h("p", { class: "hint" }, error.message)));
  return panel;
}

function readPanel(doc) {
  const lang = state.readLang || state.lang;
  const cacheKey = `${doc.document_id}:${lang}:${doc.lane}`;
  const panel = h("div", { class: "dpanel" });
  const result = state.translations.get(cacheKey);
  if (!result) {
    panel.append(h("div", { class: "read" }, h("p", { class: "provider" }, t("translating")),
      h("div", { class: "skeleton" }), h("div", { class: "skeleton", style: "width:70%" })));
    api(`/documents/${doc.document_id}/translate`, { method: "POST", json: { language: lang } })
      .then((data) => {
        state.translations.set(cacheKey, data);
        if (state.selected === doc.document_id && state.tab === "read") renderDetail();
      })
      .catch((error) => panel.replaceChildren(h("p", { class: "hint" }, error.message)));
    return panel;
  }
  const provider = { sarvam: "providerSarvam", "built-in": "providerBuiltIn", original: "providerOriginal", unavailable: "providerNone" }[result.provider];
  const read = h("div", { class: "read", lang: result.provider === "unavailable" ? "en" : lang },
    h("p", { class: `provider ${result.provider === "unavailable" ? "warn" : ""}` }, t(provider)),
    h("div", { class: "lead" }, result.summary.map((line) => h("p", {}, line))));
  if (result.reasons.length) read.append(h("div", {}, h("h4", {}, t("reasons")), h("ul", {}, result.reasons.map((r) => h("li", {}, r)))));
  if (result.items.length) read.append(h("div", {}, h("h4", {}, t("items")), h("ul", {}, result.items.map((i) => h("li", {}, i)))));
  panel.append(read);
  return panel;
}

function historyPanel(doc) {
  return h("div", { class: "dpanel" }, h("ol", { class: "timeline" }, (doc.events || []).map((event) => h("li", {},
    h("strong", {}, t(`ev_${event.action}`)),
    h("time", { datetime: event.at }, timeFmt(event.at)),
    event.details.note ? h("p", {}, event.details.note) : null,
    event.details.rating != null ? h("p", { class: "hint" }, `${t("rating")}: ${event.details.rating}/100`) : null))));
}

function renderDetail(animate = false) {
  const drawer = $("#detail");
  const doc = state.details.get(state.selected) || state.docs.find((d) => d.document_id === state.selected);
  if (!doc) { closeDrawer(); return; }
  const inv = doc.invoice;
  const readSelect = h("select", {
    "aria-label": t("language"),
    onchange: (e) => { state.readLang = e.target.value; state.tab = "read"; renderDetail(); },
  }, Object.entries(state.workspace.languages).map(([code, name]) => h("option", { value: code, selected: code === (state.readLang || state.lang) }, name)));
  const tabs = [["details", t("tabDetails")], ["original", t("tabOriginal")], ["read", t("tabRead"), readSelect], ["history", t("tabHistory")]];
  const body = { details: detailsPanel, original: originalPanel, read: readPanel, history: historyPanel }[state.tab](doc);
  const scroll = drawer.scrollTop;
  drawer.replaceChildren(
    h("div", { class: "drawer-bar" },
      h("span", { class: `status ${doc.lane}` }, t(LANE_LABEL[doc.lane])),
      h("button", { class: "btn btn-quiet", type: "button", onclick: closeDrawer }, `${t("close")} ✕`)),
    h("header", { class: "detail-head" },
      h("h2", {}, vendorName(doc)),
      h("p", { class: "head-sub" },
        inv.vendor_name && inv.trade_name ? h("span", {}, inv.vendor_name) : null,
        inv.invoice_number ? h("span", {}, inv.invoice_number) : null,
        h("span", {}, `${t("uploadedAt")} ${timeFmt(doc.uploaded_at)}`)),
      h("p", { class: "head-amount" }, inv.grand_total ? inr(inv.grand_total, inv.currency || "INR") : "–")),
    meter(doc, animate),
    decisionPanel(doc),
    h("nav", { class: "dtabs", "aria-label": t("tabDetails") }, tabs.map(([key, label, extra]) => [h("button", {
      class: "dtab", type: "button", "aria-pressed": String(state.tab === key),
      onclick: () => { state.tab = key; renderDetail(); },
    }, label), extra ? h("span", { class: "dtab-extra" }, extra) : null])),
    body);
  if (!animate) drawer.scrollTop = scroll;
}

function move(step) {
  const order = ["ON_HOLD", "PROCESSED", "REJECTED"].flatMap((lane) => state.docs.filter((d) => d.lane === lane));
  if (!order.length) return;
  const index = order.findIndex((d) => d.document_id === state.selected);
  const next = order[Math.max(0, Math.min(order.length - 1, index + step))];
  if (next) openDrawer(next.document_id);
}

/* ---------- Upload ---------- */
function uploadFiles(files) {
  for (const file of [...files]) {
    if (!(file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"))) { toast(`${file.name} ${t("notPdf")}`, "stop"); continue; }
    if (file.size > MAX_BYTES) { toast(`${file.name} ${t("tooBig")}`, "stop"); continue; }
    uploadOne(file);
  }
}

async function uploadOne(file) {
  const item = { name: file.name, stage: 0, failed: null };
  state.pending.unshift(item);
  renderPending();
  const timer = setInterval(() => { if (item.stage < STAGES.length - 1) { item.stage += 1; renderPending(); } }, 520);
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const started = performance.now();
    const doc = await api("/documents", { method: "POST", body: form });
    await new Promise((resolve) => setTimeout(resolve, Math.max(0, 1500 - (performance.now() - started))));
    clearInterval(timer);
    item.stage = STAGES.length;
    renderPending();
    await new Promise((resolve) => setTimeout(resolve, 250));
    state.pending = state.pending.filter((p) => p !== item);
    replaceDoc(doc);
    renderAll();
    toast(`${vendorName(doc)}: ${t(LANE_LABEL[doc.lane])}`, doc.lane === "PROCESSED" ? "go" : "");
    document.querySelector(`.card[data-id="${doc.document_id}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  } catch (error) {
    clearInterval(timer);
    item.failed = `${t("failed")}: ${error.message}`;
    renderPending();
    setTimeout(() => { state.pending = state.pending.filter((p) => p !== item); renderPending(); }, 6000);
  }
}

async function toggleSampleMenu() {
  const menu = $("#sample-menu");
  const button = $("#sample-btn");
  if (!menu.hidden) { menu.hidden = true; button.setAttribute("aria-expanded", "false"); return; }
  try {
    state.samples ??= await api("/samples");
    menu.replaceChildren(...state.samples.map((sample) => h("button", {
      type: "button", role: "menuitem",
      onclick: async () => {
        menu.hidden = true;
        button.setAttribute("aria-expanded", "false");
        const blob = await (await api(`/samples/${sample.name}`, { raw: true })).blob();
        uploadOne(new File([blob], `${sample.name}.pdf`, { type: "application/pdf" }));
      },
    }, h("strong", {}, sample.title, h("span", { class: `status ${sample.expected}` }, t(LANE_LABEL[sample.expected]))),
    h("small", {}, sample.description))));
    menu.hidden = false;
    button.setAttribute("aria-expanded", "true");
    menu.querySelector("button")?.focus();
  } catch (error) { toast(error.message, "stop"); }
}

/* ---------- Review ---------- */
let reviewing = null;

function openReview(doc, action) {
  reviewing = { doc, action };
  $("#review-title").textContent = t(action === "verify" ? "verifyTitle" : "rejectTitle");
  $("#review-body").textContent = t(action === "verify" ? "verifyBody" : "rejectBody");
  const submit = $("#review-submit");
  submit.textContent = t(action === "verify" ? "verify" : "reject");
  submit.className = `btn ${action === "verify" ? "btn-tape" : "btn-stop"}`;
  $("#review-note").value = "";
  $("#review-note").placeholder = t("notePlaceholder");
  $("#review-error").hidden = true;
  $("#review-dialog").showModal();
  $("#review-note").focus();
}

async function submitReview(event) {
  event.preventDefault();
  const note = $("#review-note").value.trim();
  const error = $("#review-error");
  if (note.length < 3) { error.textContent = t("noteShort"); error.hidden = false; return; }
  const { doc, action } = reviewing;
  $("#review-submit").disabled = true;
  try {
    const updated = await api(`/documents/${doc.document_id}/review`, { method: "POST", json: { action, note } });
    $("#review-dialog").close();
    replaceDoc(updated);
    toast(t(action === "verify" ? "verified" : "rejectedToast"), action === "verify" ? "go" : "stop");
    renderAll();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    $("#review-submit").disabled = false;
  }
}

async function recheck(doc, button) {
  button.disabled = true;
  try {
    await api(`/invoices/${doc.invoice_id}/revalidate`, { method: "POST" });
    const updated = await api(`/documents/${doc.document_id}`);
    replaceDoc(updated);
    toast(updated.lane === "ON_HOLD" ? t("stillHold") : `${t("rechecked")}: ${t(LANE_LABEL[updated.lane])}`, updated.lane === "PROCESSED" ? "go" : "");
    renderAll();
  } catch (error) {
    toast(error.message, "stop");
    button.disabled = false;
  }
}

// Payment itself happens on the host (Cashfree). Tell the embedding page which invoice is ready.
function handOff(doc) {
  const message = { type: "payables:payment-ready", document_id: doc.document_id, invoice_id: doc.invoice_id };
  if (window.parent !== window) window.parent.postMessage(message, document.referrer ? new URL(document.referrer).origin : "*");
  window.dispatchEvent(new CustomEvent("payables:payment-ready", { detail: message }));
  toast(t("payHanded"), "go");
}

/* ---------- Events ---------- */
function bind() {
  $("#connect-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const key = $("#key-input").value.trim();
    const error = $("#connect-error");
    if (!key) return;
    try { await connect(key); error.hidden = true; } catch (err) {
      error.textContent = err.status === 401 ? t("badKey") : err.message;
      error.hidden = false;
    }
  });
  document.querySelectorAll("[data-lang]").forEach((chip) => chip.addEventListener("click", () => setLanguage(chip.dataset.lang)));
  $("#ui-lang").addEventListener("change", (e) => { state.readLang = null; setLanguage(e.target.value); });
  $("#theme-btn").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme === "dark"
      || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    const next = dark ? "light" : "dark";
    store.set("ph.theme", next);
    applyTheme(next);
  });
  $("#disconnect-btn").addEventListener("click", () => disconnect());
  $("#file-input").addEventListener("change", (e) => { uploadFiles(e.target.files); e.target.value = ""; });
  $("#sample-btn").addEventListener("click", toggleSampleMenu);
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".menu-wrap")) { $("#sample-menu").hidden = true; $("#sample-btn").setAttribute("aria-expanded", "false"); }
  });
  $("#scrim").addEventListener("click", closeDrawer);
  $("#review-form").addEventListener("submit", submitReview);
  $("#review-cancel").addEventListener("click", () => $("#review-dialog").close());

  let depth = 0;
  const overlay = $("#drop-overlay");
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
  window.addEventListener("dragenter", (e) => { if (!hasFiles(e) || !state.workspace) return; depth += 1; overlay.hidden = false; });
  window.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) overlay.hidden = true; });
  window.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener("drop", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    overlay.hidden = true;
    if (state.workspace) uploadFiles(e.dataTransfer.files);
  });

  document.addEventListener("keydown", (e) => {
    if (!state.workspace || e.metaKey || e.ctrlKey || e.altKey || $("#review-dialog").open) return;
    if (e.key === "Escape" && state.selected) { closeDrawer(); return; }
    if (e.target.closest("input, textarea, select, [contenteditable]")) return;
    const doc = state.details.get(state.selected);
    if (e.key === "j") { e.preventDefault(); move(1); }
    else if (e.key === "k") { e.preventDefault(); move(-1); }
    else if (e.key === "u") { e.preventDefault(); $("#file-input").click(); }
    else if (e.key === "v" && doc?.can_verify) { e.preventDefault(); openReview(doc, "verify"); }
    else if (e.key === "x" && doc?.can_reject) { e.preventDefault(); openReview(doc, "reject"); }
  });
}

bind();
applyLanguage();
if (state.key) {
  connect(state.key).catch(() => disconnect(true));
} else {
  $("#connect").hidden = false;
  $("#key-input").focus();
}
