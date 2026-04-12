const state = {
  summary: null,
  champions: [],
  selectedChampion: null,
  championDetail: null,
};

const rosterEl = document.getElementById("roster");
const detailsEl = document.getElementById("details");
const summaryEl = document.getElementById("summary");
const sidebarStatusEl = document.getElementById("sidebarStatus");
const searchEl = document.getElementById("search");
const reloadBtn = document.getElementById("reloadBtn");

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (_error) {
    throw new Error(text || "Risposta non valida");
  }
  if (!response.ok) {
    throw new Error(payload.error || response.statusText || "Richiesta fallita");
  }
  return payload;
}

function setSidebarStatus(message, isError = false) {
  sidebarStatusEl.textContent = message || "";
  sidebarStatusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
}

function escapeHtml(value) {
  return String(value ?? "")
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
  if (Math.abs(numeric - Math.round(numeric)) < 0.05) {
    return String(Math.round(numeric));
  }
  return numeric.toFixed(1);
}

function renderStatsGrid(stats = {}) {
  const entries = [
    ["HP", stats.hp],
    ["ATK", stats.atk],
    ["DEF", stats.def],
    ["SPD", stats.spd],
    ["ACC", stats.acc],
    ["RES", stats.res],
    ["C.RATE", stats.crit_rate],
    ["C.DMG", stats.crit_dmg],
  ];
  return `
    <div class="summary">
      ${entries.map(([label, value]) => metricCard(label, formatStatValue(value))).join("")}
    </div>
  `;
}

function getVisibleChampions() {
  return (state.champions || []).filter((champion) => Number(champion?.rank || 0) === 6);
}

function renderSummary() {
  if (!state.summary) {
    summaryEl.innerHTML = "";
    return;
  }
  const visibleChampions = getVisibleChampions();
  const selectedChampion = state.championDetail?.account?.champion_name || state.selectedChampion || "-";
  summaryEl.innerHTML = [
    metricCard("Campioni 6*", visibleChampions.length || 0, "Lista principale"),
    metricCard("Selezionato", selectedChampion, "Stats totali sotto"),
    metricCard("Target", state.summary.registry_targets || 0, "Gestiti dal DB"),
    metricCard("Sync", state.summary.registry_targets_ready || 0, "Target con dati pronti"),
  ].join("");
}

function championPills(champion) {
  return [
    `<span class="pill gold">Lv ${escapeHtml(champion.level)}</span>`,
    `<span class="pill">${escapeHtml(champion.rarity || "n/d")}</span>`,
    `<span class="pill">${escapeHtml(champion.affinity || "n/d")}</span>`,
  ].join("");
}

function renderRoster() {
  const champions = getVisibleChampions();
  if (!champions.length) {
    rosterEl.innerHTML = '<div class="empty">Nessun 6 stelle trovato con i filtri correnti.</div>';
    return;
  }
  rosterEl.innerHTML = champions.map((champion) => `
    <button class="champ-row ${state.selectedChampion === champion.champion_name ? "active" : ""}" data-name="${escapeHtml(champion.champion_name)}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(champion.champion_name)}</div>
        <div class="pill gold">6*</div>
      </div>
      <div class="pillbar">${championPills(champion)}</div>
    </button>
  `).join("");
  rosterEl.querySelectorAll(".champ-row").forEach((button) => {
    button.addEventListener("click", () => selectChampion(button.dataset.name || ""));
  });
}

function renderDetails() {
  const detail = state.championDetail;
  if (!detail) {
    detailsEl.innerHTML = '<div class="empty">Seleziona un campione 6 stelle per vedere solo le stats totali.</div>';
    return;
  }
  const statSourceLabel = detail.stat_model?.imported_total_stats_present
    ? "Stats importate dal client"
    : "Stats derivate dal DB";
  detailsEl.innerHTML = `
    <section class="detail-hero">
      <div>
        <div class="eyebrow">Campione</div>
        <h2>${escapeHtml(detail.account?.champion_name || "-")}</h2>
        <div class="detail-meta">
          <span class="pill gold">6*</span>
          <span class="pill">${escapeHtml(detail.account?.rarity || "n/d")}</span>
          <span class="pill">${escapeHtml(detail.account?.affinity || "n/d")}</span>
          <span class="pill">${escapeHtml(detail.account?.faction || "n/d")}</span>
        </div>
      </div>
    </section>
    <section class="card">
      <h3>Stats Totali</h3>
      <div class="subtext">${escapeHtml(statSourceLabel)}</div>
      ${renderStatsGrid(detail.total_stats || {})}
    </section>
  `;
}

async function loadSummary() {
  state.summary = await fetchJson("/api/summary");
  renderSummary();
}

async function loadChampions() {
  setSidebarStatus("Caricamento roster...");
  const query = new URLSearchParams({
    search: searchEl?.value?.trim?.() || "",
    scope: "all",
    sort: "power",
  });
  const payload = await fetchJson(`/api/champions?${query.toString()}`);
  state.champions = payload.champions || [];
  const visibleChampions = getVisibleChampions();
  if (!state.selectedChampion && visibleChampions.length) {
    state.selectedChampion = visibleChampions[0].champion_name;
  }
  if (state.selectedChampion && !visibleChampions.some((item) => item.champion_name === state.selectedChampion)) {
    state.selectedChampion = visibleChampions[0]?.champion_name || null;
  }
  renderRoster();
  renderSummary();
  setSidebarStatus(`${visibleChampions.length} campioni 6 stelle caricati.`);
  if (state.selectedChampion) {
    await loadChampionDetail(state.selectedChampion);
  } else {
    state.championDetail = null;
    renderDetails();
  }
}

async function loadChampionDetail(name) {
  state.championDetail = await fetchJson(`/api/champion?name=${encodeURIComponent(name)}`);
  renderSummary();
  renderDetails();
}

async function selectChampion(name) {
  if (!name) return;
  state.selectedChampion = name;
  renderRoster();
  await loadChampionDetail(name);
}

if (searchEl) {
  searchEl.addEventListener("input", () => loadChampions().catch((error) => setSidebarStatus(error.message, true)));
}
if (reloadBtn) {
  reloadBtn.addEventListener("click", () => Promise.all([loadSummary(), loadChampions()]).catch((error) => setSidebarStatus(error.message, true)));
}

Promise.all([loadSummary(), loadChampions()]).catch((error) => setSidebarStatus(error.message, true));
