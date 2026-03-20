const state = {
  summary: null,
  sellAssist: null,
  items: [],
  selectedItemId: null,
  itemDetail: null,
  pendingSoldIds: new Set(),
  filters: { slots: [], sets: [], owners: [] },
};

const gearSummaryEl = document.getElementById("gearSummary");
const sellAssistEl = document.getElementById("sellAssist");
const gearListEl = document.getElementById("gearList");
const gearDetailsEl = document.getElementById("gearDetails");
const gearStatusEl = document.getElementById("gearStatus");
const gearSearchEl = document.getElementById("gearSearch");
const ownershipEl = document.getElementById("ownership");
const itemClassFilterEl = document.getElementById("itemClassFilter");
const slotFilterEl = document.getElementById("slotFilter");
const setFilterEl = document.getElementById("setFilter");
const adviceFilterEl = document.getElementById("adviceFilter");
const gearSortEl = document.getElementById("gearSort");
const gearRefreshGameBtn = document.getElementById("gearRefreshGameBtn");
const gearReloadBtn = document.getElementById("gearReloadBtn");
const initialParams = new URLSearchParams(window.location.search);
const SET_LABELS = {
  "Attack Speed": "Speed",
  "Accuracy And Speed": "Perception",
};

if (initialParams.get("search")) gearSearchEl.value = initialParams.get("search");
if (initialParams.get("ownership")) ownershipEl.value = initialParams.get("ownership");
if (initialParams.get("item_class")) itemClassFilterEl.value = initialParams.get("item_class");
if (initialParams.get("advice")) adviceFilterEl.value = initialParams.get("advice");
state.selectedItemId = initialParams.get("id") || null;

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (error) {
    throw new Error(text || "Risposta non valida");
  }
  if (!response.ok) {
    throw new Error(payload.error || response.statusText || "Richiesta fallita");
  }
  return payload;
}

function setStatus(message, isError = false) {
  gearStatusEl.textContent = message || "";
  gearStatusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function metricCard(label, value, note = "") {
  return `
    <div class="metric">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${escapeHtml(String(value))}</div>
      ${note ? `<div class="subtext">${escapeHtml(note)}</div>` : ""}
    </div>
  `;
}

function formatStatValue(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  if (Math.abs(numeric - Math.round(numeric)) < 0.05) return String(Math.round(numeric));
  return numeric.toFixed(1);
}

function adviceLabel(verdict) {
  const labels = {
    push_12: "Da portare a +12",
    push_16: "Da portare a +16",
    keep_after_12: "Tenere a +12",
    review_pre12: "Rivedere +8/+11",
    sell_now: "Vendere subito",
    sell_after_12: "Vendere dopo +12",
    review_equipped: "Rivedere equipaggiato",
    keep_16: "Tenere +16",
    review_16: "Rivedere +16",
  };
  return labels[verdict] || verdict || "n/d";
}

function adviceClass(verdict) {
  if (verdict === "push_16" || verdict === "keep_16") return "ok";
  if (verdict === "push_12" || verdict === "keep_after_12") return "gold";
  if (verdict === "sell_now" || verdict === "sell_after_12") return "warn";
  return "";
}

function itemClassLabel(itemClass) {
  if (itemClass === "artifact") return "Artifact";
  if (itemClass === "accessory") return "Accessori";
  return itemClass || "n/d";
}

function displaySetName(setName) {
  return SET_LABELS[setName] || setName || "No Set";
}

function renderSummary() {
  const summary = state.summary;
  if (!summary) {
    gearSummaryEl.innerHTML = "";
    return;
  }
  const push12 = summary.verdict_counts?.push_12 || 0;
  const push16 = summary.verdict_counts?.push_16 || 0;
  const sell = (summary.verdict_counts?.sell_now || 0) + (summary.verdict_counts?.sell_after_12 || 0);
  gearSummaryEl.innerHTML = [
    metricCard("Totale", summary.total_items || 0, "Pezzi nel database"),
    metricCard("Equipaggiati", summary.equipped_items || 0, "Attualmente addosso"),
    metricCard("Push +12", push12, "Base promettente"),
    metricCard("Push +16", push16, "Roll buoni a +12"),
    metricCard("Da vendere", sell, "Subito o dopo +12"),
  ].join("");
}

function renderSellAssist() {
  const payload = state.sellAssist;
  if (!payload) {
    sellAssistEl.innerHTML = '<div class="empty">Coda ID vendita non ancora caricata.</div>';
    return;
  }
  const pages = payload.pages || [];
  sellAssistEl.innerHTML = `
    <section class="card">
      <div class="eyebrow">Sell Queue</div>
      <h2>ID Candidati Vendita</h2>
      <p class="subtext">Qui vedi solo i pezzi candidati a vendita dal DB, separati tra pagina Artifact e pagina Accessori. Il bottone live manda gli ID mostrati a <code>SellArtifacts</code>: vende davvero, non seleziona soltanto.</p>
    </section>
    <section class="grid">
      ${pages.map((page) => renderSellAssistPage(page)).join("")}
    </section>
  `;
  sellAssistEl.querySelectorAll("[data-sell-page]").forEach((button) => {
    button.addEventListener("click", () => applySellAssistPage(button.dataset.sellPage));
  });
  sellAssistEl.querySelectorAll("[data-sell-item]").forEach((button) => {
    button.addEventListener("click", () => selectItem(button.dataset.sellItem));
  });
  sellAssistEl.querySelectorAll("[data-live-sell-page]").forEach((button) => {
    button.addEventListener("click", () => liveSellPage(button.dataset.liveSellPage));
  });
}

function renderSellAssistPage(page) {
  const candidates = (page.visible_candidates || []).filter((item) => !state.pendingSoldIds.has(item.item_id));
  return `
    <div class="card">
      <h3>${escapeHtml(page.label || page.page || "Pagina")}</h3>
      <div class="summary compact-summary">
        ${metricCard("Candidati", page.candidate_count || 0, "Solo inventario e non locked")}
      </div>
      <div class="action-row">
        <button class="ghost" data-sell-page="${escapeHtml(page.item_class || "")}">Filtra ${escapeHtml(itemClassLabel(page.item_class || ""))}</button>
        ${candidates.length ? `<button data-live-sell-page="${escapeHtml(page.page || "")}">Vendi ID mostrati (${candidates.length})</button>` : ""}
      </div>
      <div style="margin-top: 12px;">
        ${candidates.length ? candidates.map((item) => `
          <button class="sell-candidate" data-sell-item="${escapeHtml(item.item_id)}">
            <div class="champ-topline">
              <div class="champ-name">${escapeHtml(item.slot || "slot")} - ${escapeHtml(item.main_stat_type || "stat")}</div>
              <div class="pill">${escapeHtml(item.item_id)}</div>
            </div>
            <div class="subtext">${escapeHtml(displaySetName(item.set_name))} - ${escapeHtml(item.rarity || "n/d")} - +${escapeHtml(String(item.level || 0))}</div>
            <div class="pillbar">
              <span class="pill">${escapeHtml(itemClassLabel(item.item_class || ""))}</span>
              <span class="pill ${adviceClass(item.advice_verdict)}">${escapeHtml(adviceLabel(item.advice_verdict))}</span>
              ${item.locked ? '<span class="pill">Locked</span>' : ''}
            </div>
          </button>
        `).join("") : '<div class="empty">Nessun candidato vendita per questa pagina.</div>'}
      </div>
    </div>
  `;
}

function itemPills(item) {
  const pills = [];
  pills.push(`<span class="pill gold">${escapeHtml(item.slot || "slot")}</span>`);
  pills.push(`<span class="pill">R${item.rank}</span>`);
  pills.push(`<span class="pill">+${item.level}</span>`);
  if (item.set_name) pills.push(`<span class="pill">${escapeHtml(displaySetName(item.set_name))}</span>`);
  if (item.equipped) pills.push(`<span class="pill ok">${escapeHtml(item.owner_name || "equipaggiato")}</span>`);
  else pills.push('<span class="pill warn">Magazzino</span>');
  pills.push(`<span class="pill ${adviceClass(item.advice_verdict)}">${escapeHtml(adviceLabel(item.advice_verdict))}</span>`);
  if (item.locked) pills.push('<span class="pill">Locked</span>');
  return pills.join("");
}

function renderList() {
  if (!state.items.length) {
    gearListEl.innerHTML = '<div class="empty">Nessun pezzo trovato con i filtri correnti.</div>';
    return;
  }
  gearListEl.innerHTML = state.items.map((item) => `
    <button class="champ-row ${state.selectedItemId === item.item_id ? "active" : ""}" data-id="${escapeHtml(item.item_id)}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(item.slot)} - ${escapeHtml(item.main_stat_type || "stat")}</div>
        <div class="pill">${escapeHtml(item.item_id)}</div>
      </div>
      <div class="subtext">${escapeHtml(formatStatValue(item.main_stat_value))} - ${escapeHtml(item.rarity || "n/d")} - pre12 ${formatStatValue(item.pre12_score)} - score ${formatStatValue(item.realized_score)}</div>
      <div class="subtext">${escapeHtml((item.advice_reasons || []).slice(0, 2).join(" | "))}</div>
      <div class="pillbar">${itemPills(item)}</div>
    </button>
  `).join("");

  gearListEl.querySelectorAll(".champ-row").forEach((button) => {
    button.addEventListener("click", () => selectItem(button.dataset.id));
  });
}

function renderDetail() {
  const detail = state.itemDetail;
  if (!detail) {
    gearDetailsEl.innerHTML = '<div class="empty">Seleziona un pezzo dalla lista per vedere owner, stat principale e substat.</div>';
    return;
  }
  const item = detail.item;
  const infoRows = [
    ["ID", item.item_id],
    ["Tipo", item.item_class || "n/d"],
    ["Slot", item.slot || "n/d"],
    ["Set", displaySetName(item.set_name || "")],
    ["Rarita", item.rarity || "n/d"],
    ["Rank", item.rank],
    ["Livello", item.level],
    ["Ascension", item.ascension_level],
    ["Owner", item.owner_name || "Magazzino"],
    ["Locked", item.locked ? "si" : "no"],
    ["Verdetto", adviceLabel(detail.advice?.verdict)],
  ].map(([label, value]) => `
    <div class="kv-row"><span>${escapeHtml(String(label))}</span><strong>${escapeHtml(String(value))}</strong></div>
  `).join("");

  const substats = (detail.substats || []).map((substat) => `
    <div class="kv-row">
      <span>${escapeHtml(substat.stat_type || "stat")}</span>
      <strong>${escapeHtml(formatStatValue(substat.stat_value))} | rolls ${substat.rolls} | glyph ${escapeHtml(formatStatValue(substat.glyph_value))}</strong>
    </div>
  `).join("");

  gearDetailsEl.innerHTML = `
    <section class="detail-hero">
      <div>
        <div class="eyebrow">Gear Detail</div>
        <h2>${escapeHtml(item.slot)} - ${escapeHtml(item.main_stat_type || "stat")}</h2>
        <div class="detail-meta">${itemPills(item)}</div>
      </div>
    </section>

    <section class="grid">
      <div class="card">
        <h3>Pezzo</h3>
        <div class="kv">${infoRows}</div>
      </div>
      <div class="card">
        <h3>Valutazione</h3>
        <div class="summary compact-summary">
          ${metricCard("Verdetto", adviceLabel(detail.advice?.verdict), item.owner_name || "Magazzino")}
          ${metricCard("Pre +12", formatStatValue(detail.advice?.pre12_score), "Qualita base")}
          ${metricCard("Score", formatStatValue(detail.advice?.realized_score), "Valore attuale")}
          ${metricCard("Roll premium", detail.advice?.premium_rolls || 0, `Roll utili: ${detail.advice?.good_rolls || 0}`)}
        </div>
      </div>
    </section>

    <section class="card">
      <h3>Motivi</h3>
      <div class="kv single-column">
        ${(detail.advice?.reasons || []).map((reason) => `<div class="kv-row"><span>note</span><strong>${escapeHtml(reason)}</strong></div>`).join("") || '<div class="empty">Nessuna nota.</div>'}
      </div>
    </section>

    <section class="card">
      <h3>Substat</h3>
      <div class="kv single-column">${substats || '<div class="empty">Nessuna substat disponibile.</div>'}</div>
    </section>
  `;
}

async function loadSummary() {
  state.summary = await fetchJson("/api/gear-summary");
  renderSummary();
}

async function loadSellAssist() {
  const query = new URLSearchParams();
  Array.from(state.pendingSoldIds).forEach((itemId) => query.append("exclude_id", itemId));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  state.sellAssist = await fetchJson(`/api/sell-queue${suffix}`);
  renderSellAssist();
}

function refillSelect(selectEl, values, placeholder) {
  const current = selectEl.value;
  selectEl.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` + values.map((value) => (
    `<option value="${escapeHtml(value)}">${escapeHtml(selectEl === setFilterEl ? displaySetName(value) : value)}</option>`
  )).join("");
  if (values.includes(current)) selectEl.value = current;
}

async function loadItems() {
  setStatus("Caricamento inventario...");
  const query = new URLSearchParams({
    search: gearSearchEl.value.trim(),
    ownership: ownershipEl.value,
    item_class: itemClassFilterEl.value,
    slot: slotFilterEl.value,
    set: setFilterEl.value,
    advice: adviceFilterEl.value,
    sort: gearSortEl.value,
  });
  const payload = await fetchJson(`/api/gear-items?${query.toString()}`);
  state.items = payload.items || [];
  state.filters = payload.filters || { slots: [], sets: [], owners: [] };
  refillSelect(slotFilterEl, state.filters.slots || [], "Tutti gli slot");
  refillSelect(setFilterEl, state.filters.sets || [], "Tutti i set");
  if (!state.selectedItemId && state.items.length) state.selectedItemId = state.items[0].item_id;
  if (state.selectedItemId && !state.items.some((item) => item.item_id === state.selectedItemId)) {
    state.selectedItemId = state.items[0] ? state.items[0].item_id : null;
  }
  renderList();
  setStatus(`${state.items.length} pezzi caricati.`);
  if (state.selectedItemId) {
    await loadDetail(state.selectedItemId);
  } else {
    state.itemDetail = null;
    renderDetail();
  }
}

async function loadDetail(itemId) {
  state.itemDetail = await fetchJson(`/api/gear-item?id=${encodeURIComponent(itemId)}`);
  renderDetail();
}

async function selectItem(itemId) {
  state.selectedItemId = itemId;
  renderList();
  await loadDetail(itemId);
}

async function liveSellPage(pageName) {
  const page = (state.sellAssist?.pages || []).find((entry) => entry.page === pageName);
  const artifactIds = (page?.visible_candidates || [])
    .map((item) => item.item_id)
    .filter((itemId) => itemId && !state.pendingSoldIds.has(itemId));
  if (!artifactIds.length) {
    setStatus("Nessun ID mostrato da vendere in questa pagina.", true);
    return;
  }

  const confirmed = window.confirm(
    `Conferma vendita live di ${artifactIds.length} pezzi nella pagina ${page?.label || pageName}.\n\n` +
    `IDs: ${artifactIds.join(", ")}\n\n` +
    "Questa chiamata usa SellArtifacts e vende davvero gli item."
  );
  if (!confirmed) return;

  setStatus(`Invio vendita live per ${artifactIds.length} pezzi...`);
  const payload = await fetchJson("/api/live-sell-artifacts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ artifact_ids: artifactIds }),
  });
  const approvedIds = payload.result?.approved_ids || [];
  approvedIds.forEach((itemId) => state.pendingSoldIds.add(itemId));
  await loadSellAssist();
  setStatus(`${payload.result?.message || "Richiesta inviata."} Il DB locale non si aggiorna da solo finché non reimporti.`);
}

async function refreshGearFromGame() {
  setStatus("Aggiornamento equip dal gioco in corso...");
  const payload = await fetchJson("/api/refresh-gear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  state.pendingSoldIds = new Set();
  await Promise.all([loadSummary(), loadSellAssist(), loadItems()]);
  const imported = payload.summary?.gear_items ?? payload.summary?.gear_count ?? payload.summary?.gear ?? "?";
  setStatus(`Equip aggiornato dal gioco. Pezzi importati: ${imported}.`);
}

function applySellAssistPage(itemClass) {
  ownershipEl.value = "inventory";
  itemClassFilterEl.value = itemClass || "";
  gearSortEl.value = "advice";
  loadItems().catch((error) => setStatus(error.message, true));
}

gearSearchEl.addEventListener("input", () => loadItems().catch((error) => setStatus(error.message, true)));
ownershipEl.addEventListener("change", () => loadItems().catch((error) => setStatus(error.message, true)));
itemClassFilterEl.addEventListener("change", () => loadItems().catch((error) => setStatus(error.message, true)));
slotFilterEl.addEventListener("change", () => loadItems().catch((error) => setStatus(error.message, true)));
setFilterEl.addEventListener("change", () => loadItems().catch((error) => setStatus(error.message, true)));
adviceFilterEl.addEventListener("change", () => loadItems().catch((error) => setStatus(error.message, true)));
gearSortEl.addEventListener("change", () => loadItems().catch((error) => setStatus(error.message, true)));
gearRefreshGameBtn.addEventListener("click", () => refreshGearFromGame().catch((error) => setStatus(error.message, true)));
gearReloadBtn.addEventListener("click", () => Promise.all([loadSummary(), loadSellAssist(), loadItems()]).catch((error) => setStatus(error.message, true)));

Promise.all([loadSummary(), loadSellAssist(), loadItems()]).catch((error) => setStatus(error.message, true));
