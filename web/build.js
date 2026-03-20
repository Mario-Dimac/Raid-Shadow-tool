const state = {
  champions: [],
  selectedChampion: null,
  profiles: [],
  selectedProfile: "arena_speed_lead",
  plan: null,
};

const buildRosterEl = document.getElementById("buildRoster");
const buildDetailsEl = document.getElementById("buildDetails");
const buildSummaryEl = document.getElementById("buildSummary");
const buildStatusEl = document.getElementById("buildStatus");
const buildSearchEl = document.getElementById("buildSearch");
const buildSortEl = document.getElementById("buildSort");
const profileSelectEl = document.getElementById("profileSelect");
const buildCalcBtn = document.getElementById("buildCalcBtn");
const buildReloadBtn = document.getElementById("buildReloadBtn");

const STAT_LABELS = {
  hp: "HP",
  atk: "ATK",
  def: "DEF",
  spd: "SPD",
  acc: "ACC",
  res: "RES",
  crit_rate: "C.RATE",
  crit_dmg: "C.DMG",
};
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

function setStatus(message, isError = false) {
  buildStatusEl.textContent = message || "";
  buildStatusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
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

function formatDelta(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return String(value || "");
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${formatStatValue(numeric)}`;
}

function displaySetName(setName) {
  return SET_LABELS[setName] || setName || "No Set";
}

function championPills(champion) {
  const pills = [];
  pills.push(`<span class="pill gold">Lv ${champion.level}</span>`);
  pills.push(`<span class="pill">R${champion.rank}</span>`);
  pills.push(`<span class="pill">${escapeHtml(champion.rarity || "n/d")}</span>`);
  if (champion.affinity) pills.push(`<span class="pill">${escapeHtml(champion.affinity)}</span>`);
  return pills.join("");
}

function renderRoster() {
  if (!state.champions.length) {
    buildRosterEl.innerHTML = '<div class="empty">Nessun campione trovato con i filtri correnti.</div>';
    return;
  }
  buildRosterEl.innerHTML = state.champions.map((champion) => `
    <button class="champ-row ${state.selectedChampion === champion.champion_name ? "active" : ""}" data-name="${escapeHtml(champion.champion_name)}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(champion.champion_name)}</div>
        <div class="pill">${champion.skill_rows_with_type}/${champion.skill_rows}</div>
      </div>
      <div class="pillbar">${championPills(champion)}</div>
    </button>
  `).join("");
  buildRosterEl.querySelectorAll(".champ-row").forEach((button) => {
    button.addEventListener("click", () => selectChampion(button.dataset.name));
  });
}

function renderProfileSelect() {
  if (!state.profiles.length) {
    profileSelectEl.innerHTML = '<option value="arena_speed_lead">Arena Speed Lead</option>';
    return;
  }
  const current = state.selectedProfile;
  profileSelectEl.innerHTML = state.profiles.map((profile) => (
    `<option value="${escapeHtml(profile.key)}">${escapeHtml(profile.label)}</option>`
  )).join("");
  profileSelectEl.value = state.profiles.some((profile) => profile.key === current)
    ? current
    : state.profiles[0].key;
  state.selectedProfile = profileSelectEl.value;
}

function renderSummary() {
  if (!state.plan) {
    buildSummaryEl.innerHTML = [
      metricCard("Campione", "-", "Seleziona un campione"),
      metricCard("Profilo", "-", "Scegli l'obiettivo build"),
      metricCard("Build", "-", "Attuale vs proposte"),
      metricCard("Delta", "-", "Qui compariranno le differenze"),
    ].join("");
    return;
  }
  const highlights = state.plan.profile?.highlights || ["spd", "hp", "def", "res"];
  const topStat = highlights[0] || "spd";
  const current = state.plan.current_build || {};
  const best = (state.plan.proposals || [])[0] || current;
  const delta = best.deltas?.[topStat] || 0;
  buildSummaryEl.innerHTML = [
    metricCard("Campione", state.plan.champion?.champion_name || "-", state.plan.champion?.faction || "n/d"),
    metricCard("Profilo", state.plan.profile?.label || "-", state.plan.profile?.description || ""),
    metricCard(`Attuale ${STAT_LABELS[topStat] || topStat}`, formatStatValue(current.stats?.[topStat]), current.label || "Build attuale"),
    metricCard(`Best ${STAT_LABELS[topStat] || topStat}`, formatStatValue(best.stats?.[topStat]), `${formatDelta(delta)} vs attuale`),
    metricCard("Swap", best.swap_count || 0, `${best.borrowed_items || 0} da altri, ${best.inventory_items || 0} da magazzino`),
  ].join("");
}

function renderBuildMetrics(build, highlights) {
  const stats = highlights.map((statName) => metricCard(
    STAT_LABELS[statName] || statName,
    formatStatValue(build.stats?.[statName]),
    build.key === "current" ? "attuale" : `${formatDelta(build.deltas?.[statName] || 0)} vs attuale`,
  ));
  stats.push(metricCard("Score", formatStatValue(build.score), build.key === "current" ? "base confronto" : "ranking profilo"));
  return `<div class="summary compact-summary">${stats.join("")}</div>`;
}

function renderSetPills(build) {
  const bits = [];
  (build.applied_sets || []).forEach((row) => {
    bits.push(`<span class="pill ok">${escapeHtml(displaySetName(row.set_name))} x${escapeHtml(String(row.completed_sets || 0))}</span>`);
  });
  (build.unsupported_sets || []).forEach((setName) => {
    bits.push(`<span class="pill warn">${escapeHtml(displaySetName(setName))}</span>`);
  });
  if (!bits.length) bits.push('<span class="pill">Nessun set attivo rilevante</span>');
  return bits.join("");
}

function buildItemLink(item) {
  const query = new URLSearchParams({
    search: item.item_id || "",
    id: item.item_id || "",
  });
  if (item.source_kind === "inventory") query.set("ownership", "inventory");
  if (item.source_kind === "borrowed" || item.source_kind === "current") query.set("ownership", "equipped");
  return `/gear?${query.toString()}`;
}

function renderItemSubstats(item) {
  const substats = (item.substats || []).map((substat) => (
    `${substat.stat_type || "stat"} ${formatStatValue(substat.stat_value)}`
  ));
  return substats.length ? substats.join(" | ") : "Nessuna substat";
}

function renderItems(build) {
  if (!(build.items || []).length) {
    return '<div class="empty">Nessun pezzo disponibile per questa proposta.</div>';
  }
  return `
    <div class="stack">
      ${(build.items || []).map((item) => `
        <article class="build-piece">
          <div class="champ-topline">
            <div class="champ-name">${escapeHtml(item.slot || "slot")} | ${escapeHtml(displaySetName(item.set_name))}</div>
            <div class="pill mono">${escapeHtml(item.item_id || "")}</div>
          </div>
          <div class="subtext">${escapeHtml(item.rarity || "n/d")} | R${escapeHtml(String(item.rank || 0))} | +${escapeHtml(String(item.level || 0))} | main ${escapeHtml(item.main_stat_type || "stat")} ${escapeHtml(formatStatValue(item.main_stat_value))}</div>
          <div class="subtext">${escapeHtml(renderItemSubstats(item))}</div>
          <div class="action-row">
            <span class="pill ${item.source_kind === "inventory" ? "warn" : item.source_kind === "borrowed" ? "gold" : "ok"}">${escapeHtml(item.source_label || "n/d")}</span>
            ${item.locked ? '<span class="pill">Locked</span>' : ""}
            <a class="nav-link" href="${escapeHtml(buildItemLink(item))}">Apri in Equip</a>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderNotes(build) {
  if (!(build.notes || []).length) {
    return '<div class="subtext">Nessuna nota sintetica.</div>';
  }
  return `
    <div class="pillbar">
      ${(build.notes || []).map((note) => `<span class="pill">${escapeHtml(note)}</span>`).join("")}
    </div>
  `;
}

function renderBuildCard(build, highlights) {
  return `
    <section class="card build-card">
      <div class="detail-hero build-card-hero">
        <div>
          <div class="eyebrow">${escapeHtml(build.key === "current" ? "Current Build" : "Build Proposal")}</div>
          <h3>${escapeHtml(build.label || "Build")}</h3>
          <div class="subtext">${escapeHtml(build.description || "")}</div>
        </div>
        <div class="pillbar">
          <span class="pill gold">Swap ${escapeHtml(String(build.swap_count || 0))}</span>
          <span class="pill">${escapeHtml(build.source || "derived")}</span>
          <span class="pill">${escapeHtml(build.completeness || "n/d")}</span>
        </div>
      </div>
      ${renderBuildMetrics(build, highlights)}
      <div class="build-section">
        <h3>Set</h3>
        <div class="pillbar">${renderSetPills(build)}</div>
      </div>
      <div class="build-section">
        <h3>Note</h3>
        ${renderNotes(build)}
      </div>
      <div class="build-section">
        <h3>Pezzi</h3>
        ${renderItems(build)}
      </div>
    </section>
  `;
}

function renderDetails() {
  if (!state.plan) {
    buildDetailsEl.innerHTML = '<div class="empty">Seleziona un campione dalla lista per vedere build attuale e proposte.</div>';
    return;
  }
  const plan = state.plan;
  const highlights = plan.profile?.highlights || ["spd", "hp", "def", "res"];
  const champion = plan.champion || {};
  const currentBuild = plan.current_build || {};
  const proposals = plan.proposals || [];
  buildDetailsEl.innerHTML = `
    <section class="detail-hero">
      <div>
        <div class="eyebrow">Build Planner</div>
        <h2>${escapeHtml(champion.champion_name || "-")}</h2>
        <div class="detail-meta">
          <span class="pill gold">Profilo ${escapeHtml(plan.profile?.label || "-")}</span>
          <span class="pill">${escapeHtml(champion.faction || "n/d")}</span>
          <span class="pill">${escapeHtml(champion.affinity || "n/d")}</span>
          <span class="pill">${escapeHtml(champion.rarity || "n/d")}</span>
        </div>
      </div>
      <div class="pillbar">
        ${(state.profiles || []).map((profile) => `
          <span class="pill ${profile.key === state.selectedProfile ? "gold" : ""}">${escapeHtml(profile.label)}</span>
        `).join("")}
      </div>
    </section>

    ${renderBuildCard(currentBuild, highlights)}

    <section class="grid build-grid">
      ${proposals.map((proposal) => renderBuildCard(proposal, highlights)).join("")}
    </section>
  `;
}

async function loadProfiles() {
  const payload = await fetchJson("/api/build-profiles");
  state.profiles = payload.profiles || [];
  renderProfileSelect();
}

async function loadChampions() {
  setStatus("Caricamento campioni...");
  const query = new URLSearchParams({
    search: buildSearchEl.value.trim(),
    scope: "all",
    sort: buildSortEl.value,
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
  setStatus(`${state.champions.length} campioni caricati.`);
}

async function loadPlan() {
  if (!state.selectedChampion) {
    state.plan = null;
    renderSummary();
    renderDetails();
    return;
  }
  setStatus(`Calcolo build per ${state.selectedChampion}...`);
  const query = new URLSearchParams({
    name: state.selectedChampion,
    profile: state.selectedProfile,
  });
  state.plan = await fetchJson(`/api/build-plan?${query.toString()}`);
  state.profiles = state.plan.profiles || state.profiles;
  renderProfileSelect();
  renderSummary();
  renderDetails();
  setStatus(`Build pronta per ${state.selectedChampion}.`);
}

async function selectChampion(name) {
  state.selectedChampion = name;
  renderRoster();
  await loadPlan();
}

async function reloadPageState() {
  await loadProfiles();
  await loadChampions();
  await loadPlan();
}

buildSearchEl.addEventListener("input", async () => {
  try {
    await loadChampions();
    await loadPlan();
  } catch (error) {
    setStatus(error.message || "Errore caricamento build.", true);
  }
});

buildSortEl.addEventListener("change", async () => {
  try {
    await loadChampions();
    await loadPlan();
  } catch (error) {
    setStatus(error.message || "Errore caricamento build.", true);
  }
});

profileSelectEl.addEventListener("change", () => {
  state.selectedProfile = profileSelectEl.value || "arena_speed_lead";
});

buildCalcBtn.addEventListener("click", async () => {
  try {
    state.selectedProfile = profileSelectEl.value || "arena_speed_lead";
    await loadPlan();
  } catch (error) {
    setStatus(error.message || "Errore calcolo build.", true);
  }
});

buildReloadBtn.addEventListener("click", async () => {
  try {
    await reloadPageState();
  } catch (error) {
    setStatus(error.message || "Errore ricarica build.", true);
  }
});

async function init() {
  try {
    renderSummary();
    renderDetails();
    await reloadPageState();
  } catch (error) {
    setStatus(error.message || "Errore inizializzazione build.", true);
  }
}

init();
