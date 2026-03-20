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
const scopeEl = document.getElementById("scope");
const sortEl = document.getElementById("sort");
const rebuildBtn = document.getElementById("rebuildBtn");
const recomputeStatsBtn = document.getElementById("recomputeStatsBtn");
const refreshAllBtn = document.getElementById("refreshAllBtn");
const refreshOneBtn = document.getElementById("refreshOneBtn");
const reloadBtn = document.getElementById("reloadBtn");
const SET_LABELS = {
  "Attack Speed": "Speed",
  "Accuracy And Speed": "Perception",
};

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

function setSidebarStatus(message, isError = false) {
  sidebarStatusEl.textContent = message || "";
  sidebarStatusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
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
  if (Math.abs(numeric - Math.round(numeric)) < 0.05) {
    return String(Math.round(numeric));
  }
  return numeric.toFixed(1);
}

function displaySetName(setName) {
  return SET_LABELS[setName] || setName || "n/d";
}

function statsLabel(model) {
  if (!model || !model.source) return "n/d";
  if (model.source === "raw") return "import raw";
  if (model.source === "derived" && model.completeness === "partial") return "derivato con caveat";
  if (model.source === "derived") return "derivato da gear";
  if (model.source === "missing") return "non disponibile";
  return model.source;
}

function renderStatsGrid(stats, tone = "") {
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
    <div class="summary ${tone}">
      ${entries.map(([label, value]) => metricCard(label, formatStatValue(value))).join("")}
    </div>
  `;
}

function renderSummary() {
  const summary = state.summary;
  if (!summary) {
    summaryEl.innerHTML = "";
    return;
  }
  summaryEl.innerHTML = [
    metricCard("Posseduti", summary.owned_champions || 0, "Campioni presenti nel tuo account"),
    metricCard("Target L60", summary.registry_targets || 0, "Roster gestito per Clan Boss"),
    metricCard("Enriched", summary.registry_targets_fully_enriched || 0, "Target con skill complete"),
    metricCard("Effect Rows", summary.skill_effect_rows || 0, summary.hellhades_last_enrich_utc || "Mai aggiornato"),
  ].join("");
}

function championPills(champion) {
  const pills = [];
  pills.push(`<span class="pill gold">Lv ${champion.level}</span>`);
  pills.push(`<span class="pill">R${champion.rank}</span>`);
  pills.push(`<span class="pill">${escapeHtml(champion.rarity || "n/d")}</span>`);
  if (champion.is_registry_target) pills.push('<span class="pill gold">Target</span>');
  pills.push(champion.enriched ? '<span class="pill ok">Enriched</span>' : '<span class="pill warn">Da arricchire</span>');
  return pills.join("");
}

function renderRoster() {
  if (!state.champions.length) {
    rosterEl.innerHTML = '<div class="empty">Nessun campione trovato con i filtri correnti.</div>';
    return;
  }
  rosterEl.innerHTML = state.champions.map((champion) => `
    <button class="champ-row ${state.selectedChampion === champion.champion_name ? "active" : ""}" data-name="${escapeHtml(champion.champion_name)}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(champion.champion_name)}</div>
        <div class="pill">${champion.skill_rows_with_type}/${champion.skill_rows}</div>
      </div>
      <div class="pillbar">${championPills(champion)}</div>
    </button>
  `).join("");
  rosterEl.querySelectorAll(".champ-row").forEach((button) => {
    button.addEventListener("click", () => selectChampion(button.dataset.name));
  });
}

function formatEffect(effect) {
  const bits = [effect.effect_type];
  if (effect.target) bits.push(`@${effect.target}`);
  if (effect.effect_value !== null && effect.effect_value !== undefined) bits.push(String(effect.effect_value));
  if (effect.duration !== null && effect.duration !== undefined) bits.push(`${effect.duration}t`);
  if (effect.chance !== null && effect.chance !== undefined) bits.push(`${effect.chance}%`);
  return escapeHtml(bits.join(" "));
}

function renderDetails() {
  const detail = state.championDetail;
  if (!detail) {
    detailsEl.innerHTML = '<div class="empty">Seleziona un campione dalla lista per vedere stats, skill ed effetti.</div>';
    return;
  }

  const accountMeta = [
    `<span class="pill gold">Lv ${detail.account.level}</span>`,
    `<span class="pill">Rank ${detail.account.rank}</span>`,
    `<span class="pill">${escapeHtml(detail.account.rarity || "n/d")}</span>`,
    `<span class="pill">${escapeHtml(detail.account.affinity || "n/d")}</span>`,
    `<span class="pill">${escapeHtml(detail.account.faction || "n/d")}</span>`,
    detail.account.booked ? '<span class="pill ok">Bookato</span>' : '<span class="pill">Non bookato</span>',
    detail.catalog.hellhades_post_id ? `<span class="pill ok">HH ${detail.catalog.hellhades_post_id}</span>` : '<span class="pill warn">HH mancante</span>',
  ].join("");

  const profileRows = [
    ["Campione", detail.account.champion_name],
    ["Rarita", detail.account.rarity || "n/d"],
    ["Affinity", detail.account.affinity || "n/d"],
    ["Faction", detail.account.faction || "n/d"],
    ["Livello", detail.account.level],
    ["Rank", detail.account.rank],
    ["Awakening", detail.account.awakening_level],
    ["Empowerment", detail.account.empowerment_level],
    ["Bookato", detail.account.booked ? "si" : "no"],
  ].map(([label, value]) => `
    <div class="kv-row"><span>${escapeHtml(String(label))}</span><strong>${escapeHtml(String(value))}</strong></div>
  `).join("");

  const unsupportedSets = (detail.stat_model?.unsupported_sets || []).map((setName) => displaySetName(setName)).join(", ") || "nessuno";
  const appliedSets = (detail.stat_model?.applied_sets || []).map((setRow) => (
    `${displaySetName(setRow.set_name)} x${setRow.completed_sets}`
  )).join(", ") || "nessuno";
  const enrichRows = [
    ["HellHades ID", detail.catalog.hellhades_post_id ?? "n/d"],
    ["Ultimo enrich", detail.catalog.last_enriched_at || "n/d"],
    ["Skill", `${detail.skills.length}`],
    ["Effect rows", `${detail.skills.reduce((count, skill) => count + (skill.effects || []).length, 0)}`],
    ["Ruoli", detail.roles.length ? detail.roles.join(", ") : "n/d"],
    ["Stats source", statsLabel(detail.stat_model)],
    ["Stats refresh", detail.stat_model?.computed_at || "n/d"],
    ["Set applicati", appliedSets],
    ["Set non quantificati", unsupportedSets],
  ].map(([label, value]) => `
    <div class="kv-row"><span>${escapeHtml(String(label))}</span><strong>${escapeHtml(String(value))}</strong></div>
  `).join("");

  const statsNote = detail.stat_model?.completeness === "partial"
    ? "Valori derivati da base, gear, glyph e bonus account. Alcuni set speciali equipaggiati non sono ancora quantificati."
    : "Valori account affidabili: import raw se disponibile, altrimenti derivati da base, gear, glyph, set e bonus account.";

  const skills = (detail.skills || []).map((skill) => `
    <article class="skill">
      <div class="skill-header">
        <div>
          <div class="skill-title">${escapeHtml(skill.slot)} · ${escapeHtml(skill.skill_name || "Skill")}</div>
          <div class="subtext">${escapeHtml(skill.skill_type || "n/d")}</div>
        </div>
        <div class="pillbar">
          <span class="pill">CD ${skill.cooldown ?? "-"}</span>
          <span class="pill">Booked ${skill.booked_cooldown ?? "-"}</span>
        </div>
      </div>
      <div class="skill-desc">${escapeHtml(skill.description_clean || skill.description || "Nessuna descrizione")}</div>
      ${(skill.effects || []).length ? `
        <div class="effects">
          ${skill.effects.map((effect) => `<span class="effect">${formatEffect(effect)}</span>`).join("")}
        </div>
      ` : ""}
    </article>
  `).join("");

  detailsEl.innerHTML = `
    <section class="detail-hero">
      <div>
        <div class="eyebrow">Champion Detail</div>
        <h2>${escapeHtml(detail.account.champion_name)}</h2>
        <div class="detail-meta">${accountMeta}</div>
      </div>
      <div class="pillbar">
        ${detail.roles.map((role) => `<span class="pill">${escapeHtml(role)}</span>`).join("")}
      </div>
    </section>

    <section class="grid">
      <div class="card">
        <h3>Profilo Account</h3>
        <div class="kv">${profileRows}</div>
      </div>
      <div class="card">
        <h3>Stato Dati</h3>
        <div class="kv">${enrichRows}</div>
      </div>
    </section>

    <section class="card">
      <h3>Totale Account</h3>
      <div class="subtext">${escapeHtml(statsNote)}</div>
      ${renderStatsGrid(detail.total_stats)}
    </section>

    <section class="card">
      <h3>Base Stimata</h3>
      <div class="subtext">Base convertita dal dump locale in formato utile per il controllo manuale.</div>
      ${renderStatsGrid(detail.base_totals, "muted")}
    </section>

    <section class="card">
      <h3>Skill</h3>
      ${skills || '<div class="empty">Nessuna skill disponibile.</div>'}
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
    search: searchEl.value.trim(),
    scope: scopeEl.value,
    sort: sortEl.value,
  });
  const payload = await fetchJson(`/api/champions?${query.toString()}`);
  state.champions = payload.champions || [];
  if (!state.selectedChampion && state.champions.length) {
    state.selectedChampion = state.champions[0].champion_name;
  }
  if (state.selectedChampion && !state.champions.some((item) => item.champion_name === state.selectedChampion)) {
    state.selectedChampion = state.champions[0] ? state.champions[0].champion_name : null;
  }
  renderRoster();
  setSidebarStatus(`${state.champions.length} campioni caricati.`);
  if (state.selectedChampion) {
    await loadChampionDetail(state.selectedChampion);
  } else {
    state.championDetail = null;
    renderDetails();
  }
}

async function loadChampionDetail(name) {
  state.championDetail = await fetchJson(`/api/champion?name=${encodeURIComponent(name)}`);
  renderDetails();
}

async function selectChampion(name) {
  state.selectedChampion = name;
  renderRoster();
  await loadChampionDetail(name);
}

async function postAction(url, body = {}) {
  return fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function rebuildDb() {
  setSidebarStatus("Ricostruzione DB in corso...");
  const payload = await postAction("/api/rebuild-db");
  setSidebarStatus(`DB ricostruito. Catalogo: ${payload.summary.champion_catalog}, target: ${payload.summary.registry_targets}.`);
  await loadSummary();
  await loadChampions();
}

async function recomputeStats() {
  setSidebarStatus("Ricalcolo stats in corso...");
  const payload = await postAction("/api/recompute-stats");
  setSidebarStatus(`Stats ricalcolate per ${payload.summary.updated_champions} campioni.`);
  await loadSummary();
  await loadChampions();
  if (state.selectedChampion) await loadChampionDetail(state.selectedChampion);
}

async function refreshAll() {
  setSidebarStatus("Refresh HellHades di tutti i target in corso...");
  const payload = await postAction("/api/update-targets");
  setSidebarStatus(`Aggiornati ${payload.summary.updated}/${payload.summary.requested} target.`);
  await loadSummary();
  await loadChampions();
  if (state.selectedChampion) await loadChampionDetail(state.selectedChampion);
}

async function refreshSelected() {
  if (!state.selectedChampion) return;
  setSidebarStatus(`Aggiornamento ${state.selectedChampion} in corso...`);
  const payload = await postAction("/api/update-champion", { champion_name: state.selectedChampion });
  setSidebarStatus(`Aggiornato ${payload.summary.updated}/${payload.summary.requested}: ${state.selectedChampion}.`);
  await loadSummary();
  await loadChampions();
  await loadChampionDetail(state.selectedChampion);
}

searchEl.addEventListener("input", () => loadChampions().catch((error) => setSidebarStatus(error.message, true)));
scopeEl.addEventListener("change", () => loadChampions().catch((error) => setSidebarStatus(error.message, true)));
sortEl.addEventListener("change", () => loadChampions().catch((error) => setSidebarStatus(error.message, true)));
rebuildBtn.addEventListener("click", () => rebuildDb().catch((error) => setSidebarStatus(error.message, true)));
recomputeStatsBtn.addEventListener("click", () => recomputeStats().catch((error) => setSidebarStatus(error.message, true)));
refreshAllBtn.addEventListener("click", () => refreshAll().catch((error) => setSidebarStatus(error.message, true)));
refreshOneBtn.addEventListener("click", () => refreshSelected().catch((error) => setSidebarStatus(error.message, true)));
reloadBtn.addEventListener("click", () => Promise.all([loadSummary(), loadChampions()]).catch((error) => setSidebarStatus(error.message, true)));

Promise.all([loadSummary(), loadChampions()]).catch((error) => setSidebarStatus(error.message, true));
