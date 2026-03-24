const state = {
  targets: [],
  selectedBoss: "demon_lord",
  selectedAffinity: "void",
  selectedLevel: "ultra_nightmare",
  report: null,
  selectedChampion: null,
  buildPlans: {},
  buildPlanErrors: {},
  buildPlanLoading: {},
};

const rosterEl = document.getElementById("optimizerRoster");
const detailsEl = document.getElementById("optimizerDetails");
const summaryEl = document.getElementById("optimizerSummary");
const statusEl = document.getElementById("optimizerStatus");
const bossEl = document.getElementById("optimizerBoss");
const affinityEl = document.getElementById("optimizerAffinity");
const levelEl = document.getElementById("optimizerLevel");
const reloadBtn = document.getElementById("optimizerReloadBtn");
const SET_LABELS = {
  "Attack Speed": "Speed",
  "Accuracy And Speed": "Perception",
  "HP And Heal": "Immortal",
  "HP And Defence": "Resilience",
  "Shield And HP": "Divine Life",
  "Shield And Speed": "Divine Speed",
  "Shield And Attack Power": "Divine Offense",
  "Shield And Critical Chance": "Divine Crit Rate",
  "Attack Power And Ignore Defense": "Cruel",
  "Life Drain": "Lifesteal",
  "Counterattack On Crit": "Avenging",
  "Dot Rate": "Toxic",
  "Freeze Rate On Damage Received": "Frost",
  "AoE Damage Decrease": "Stalwart",
  "Ignore Defense": "Savage",
  "Sleep Chance": "Daze",
  "Decrease Max HP": "Destroy",
  "Attack Power": "Offense",
  "Cooldown Reduction Chance": "Reflex",
  "Critical Heal Multiplier": "Critical Damage",
  "Unkillable And Spd And Cr Dmg": "Swift Parry",
  "Unkillable And SPD And CR Damage": "Swift Parry",
  "Attack And Crit Rate": "Fatal",
  "Block Debuff": "Immunity",
  "Crit Rate And Ignore DEF Multiplier": "Lethal",
  "Crit Rate And Ignore Def Multiplier": "Lethal",
  "Damage Increase On HP Decrease": "Fury",
  "Get Extra Turn": "Relentless",
  "HP": "Life",
  "Stun Chance": "Stun",
  "Crit Damage And Transform Week Into Crit Hit": "Affinitybreaker",
  "Crit Dmg And Transform Week Into Crit Hit": "Affinitybreaker",
  "Crit Rate And Life Drain": "Bloodthirst",
  "Change Hit Type": "Reaction Accessory",
  "Shield Accessory": "Bloodshield Accessory",
};
const STAT_LABELS = {
  hp: "HP",
  atk: "ATK",
  def: "DEF",
  spd: "SPD",
  acc: "ACC",
  res: "RES",
  crit_rate: "C.RATE",
  crit_dmg: "C.DMG",
  hp_pct: "HP%",
  atk_pct: "ATK%",
  def_pct: "DEF%",
  ignore_def: "Ignore DEF",
};
const SLOT_LABELS = {
  weapon: "Arma",
  helmet: "Elmo",
  shield: "Scudo",
  gloves: "Guanti",
  chest: "Corazza",
  boots: "Stivali",
  ring: "Anello",
  amulet: "Amuleto",
  banner: "Stendardo",
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(message, isError = false) {
  statusEl.textContent = message || "";
  statusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
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

function formatNumber(value, digits = 0) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toLocaleString("it-IT", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function displaySetName(setName) {
  return SET_LABELS[setName] || setName || "No Set";
}

function displaySlotName(slotName) {
  return SLOT_LABELS[slotName] || slotName || "Slot";
}

function displayItemSourceLabel(item) {
  if (item?.source_kind === "inventory") return "In inventario";
  if (item?.source_kind === "current") return `Gia equipaggiato su ${item.owner_name || state.selectedChampion || "questo campione"}`;
  if (item?.source_kind === "borrowed") return `Equipaggiato su ${item.owner_name || item.equipped_by || "altro campione"}`;
  return item?.source_label || item?.source_kind || "";
}

function displayStatName(statName) {
  return STAT_LABELS[statName] || statName || "Stat";
}

function renderItemSubstats(item) {
  const substats = item?.substats || [];
  if (!substats.length) {
    return '<div class="subtext">Substat: nessuna</div>';
  }
  const ordered = [...substats]
    .sort((left, right) => Number(right.stat_value || 0) - Number(left.stat_value || 0))
    .map((substat) => {
      const rolls = Number(substat.rolls || 0);
      const glyph = Number(substat.glyph_value || 0);
      const suffix = [];
      if (rolls > 0) suffix.push(`roll ${rolls}`);
      if (glyph > 0) suffix.push(`glyph ${formatBuildStat(glyph)}`);
      const extra = suffix.length ? ` (${suffix.join(", ")})` : "";
      return `${displayStatName(substat.stat_type)} ${formatBuildStat(substat.stat_value)}${extra}`;
    });
  return `<div class="subtext">Substat: ${escapeHtml(ordered.join(" | "))}</div>`;
}

function buildPlanCacheKey(name, profile) {
  return `${name}::${profile}`;
}

function currentBossConfig() {
  const targets = state.targets || [];
  return targets.find((target) => target.key === state.selectedBoss) || targets[0] || null;
}

function renderBossSelect() {
  const targets = state.targets || [];
  if (!targets.length) {
    bossEl.innerHTML = '<option value="demon_lord">Demon Lord</option>';
    return;
  }
  bossEl.innerHTML = targets.map((target) => (
    `<option value="${escapeHtml(target.key)}">${escapeHtml(target.label)}</option>`
  )).join("");
  const current = targets.some((target) => target.key === state.selectedBoss)
    ? state.selectedBoss
    : targets[0].key;
  state.selectedBoss = current;
  bossEl.value = current;
}

function renderAffinitySelect() {
  const boss = currentBossConfig();
  const affinities = boss?.affinities || [];
  if (!affinities.length) {
    affinityEl.innerHTML = '<option value="void">Void</option>';
    state.selectedAffinity = "void";
    affinityEl.value = "void";
    return;
  }
  affinityEl.innerHTML = affinities.map((item) => (
    `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`
  )).join("");
  const current = affinities.some((item) => item.key === state.selectedAffinity)
    ? state.selectedAffinity
    : (boss?.default_affinity || affinities[0].key);
  state.selectedAffinity = current;
  affinityEl.value = current;
}

function renderLevelSelect() {
  const boss = currentBossConfig();
  const levels = boss?.levels || [];
  if (!levels.length) {
    levelEl.innerHTML = '<option value="ultra_nightmare">Ultra-Nightmare</option>';
    state.selectedLevel = "ultra_nightmare";
    levelEl.value = "ultra_nightmare";
    return;
  }
  levelEl.innerHTML = levels.map((item) => (
    `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`
  )).join("");
  const current = levels.some((item) => item.key === state.selectedLevel)
    ? state.selectedLevel
    : (boss?.default_level || levels[0].key);
  state.selectedLevel = current;
  levelEl.value = current;
}

function buildCandidatePills(candidate) {
  const pills = [];
  if (candidate.default_build) pills.push(`<span class="pill gold">${escapeHtml(candidate.default_build)}</span>`);
  (candidate.roles || []).slice(0, 3).forEach((role) => {
    pills.push(`<span class="pill">${escapeHtml(role)}</span>`);
  });
  (candidate.risks || []).slice(0, 1).forEach(() => {
    pills.push('<span class="pill warn">Rischio</span>');
  });
  return pills.join("");
}

function isSelectedTeamChampion(name) {
  return (state.report?.selected_team || []).some((member) => member.champion_name === name);
}

function renderRoster() {
  const candidates = state.report?.candidates || [];
  if (!candidates.length) {
    rosterEl.innerHTML = '<div class="empty">Nessun candidato disponibile nel roster corrente.</div>';
    return;
  }
  rosterEl.innerHTML = candidates.map((candidate) => `
    <button class="champ-row ${state.selectedChampion === candidate.champion_name ? "active" : ""}" data-name="${escapeHtml(candidate.champion_name)}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(candidate.champion_name)}</div>
        <div class="pill ${isSelectedTeamChampion(candidate.champion_name) ? "ok" : ""}">${formatNumber(candidate.score, 1)}</div>
      </div>
      <div class="pillbar">
        ${isSelectedTeamChampion(candidate.champion_name) ? '<span class="pill ok">Team Proposto</span>' : ""}
        ${buildCandidatePills(candidate)}
      </div>
    </button>
  `).join("");
  rosterEl.querySelectorAll(".champ-row").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedChampion = button.dataset.name || null;
      renderRoster();
      renderDetails();
    });
  });
}

function renderSummary() {
  if (!state.report) {
    summaryEl.innerHTML = [
      metricCard("Target", "-", "In attesa del report"),
      metricCard("Team", "-", "Proposta non disponibile"),
      metricCard("Coverage", "-", "Ruoli chiave"),
      metricCard("Rischi", "-", "Alert principali"),
    ].join("");
    return;
  }
  const team = state.report.selected_team || [];
  const covered = (state.report.coverage || []).filter((item) => item.covered).length;
  const total = (state.report.coverage || []).length;
  summaryEl.innerHTML = [
    metricCard("Boss", state.report.target?.boss_label || "-", `${state.report.target?.level_label || "-"} / ${state.report.target?.affinity_label || "-"}`),
    metricCard("Team", `${team.length}/${state.report.target?.team_size || 5}`, team.map((item) => item.champion_name).join(", ")),
    metricCard("Coverage", `${covered}/${total}`, (state.report.missing_required_roles || []).length ? `Manca: ${(state.report.missing_required_roles || []).join(", ")}` : "Ruoli chiave coperti"),
    metricCard("Soglie", `${formatNumber(state.report.target?.thresholds?.required_speed, 0)} SPD / ${formatNumber(state.report.target?.thresholds?.required_accuracy, 0)} ACC`, state.report.target?.description || ""),
  ].join("");
}

function renderCoverageCard() {
  const rows = (state.report?.coverage || []).map((item) => `
    <div class="kv-row">
      <span>${escapeHtml(item.label)}</span>
      <span>${item.covered ? escapeHtml((item.covered_by || []).join(", ") || "Coperto") : "Assente"}</span>
    </div>
  `).join("");
  return `
    <div class="card">
      <h3>Coverage</h3>
      <div class="kv single-column">${rows || '<div class="empty">Nessuna copertura disponibile.</div>'}</div>
    </div>
  `;
}

function renderWarningsCard() {
  const warnings = state.report?.warnings || [];
  const notes = state.report?.notes || [];
  return `
    <div class="card">
      <h3>Rischi E Note</h3>
      <div class="list-block">
        ${(warnings.length ? warnings : ["Nessun rischio rilevato da questa euristica."]).map((item) => `
          <div class="list-row">${escapeHtml(item)}</div>
        `).join("")}
        ${notes.map((item) => `<div class="list-row">${escapeHtml(item)}</div>`).join("")}
      </div>
    </div>
  `;
}

function renderTeamCard() {
  const team = state.report?.selected_team || [];
  if (!team.length) {
    return '<div class="card"><h3>Team Proposto</h3><div class="empty">Nessun team selezionato.</div></div>';
  }
  return `
    <div class="card">
      <h3>Team Proposto</h3>
      <div class="list-block">
        ${team.map((member, index) => `
          <button class="sell-candidate optimizer-member-btn" data-name="${escapeHtml(member.champion_name)}">
            <strong>${index + 1}. ${escapeHtml(member.champion_name)}</strong>
            <div class="pillbar">
              <span class="pill gold">Score ${formatNumber(member.score, 1)}</span>
              <span class="pill">${escapeHtml(member.default_build || "n/d")}</span>
              ${(member.roles || []).slice(0, 4).map((role) => `<span class="pill">${escapeHtml(role)}</span>`).join("")}
            </div>
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function renderBenchCard() {
  const bench = state.report?.bench || [];
  return `
    <div class="card">
      <h3>Panchina Utile</h3>
      <div class="list-block">
        ${(bench.length ? bench : []).map((member) => `
          <button class="sell-candidate optimizer-member-btn" data-name="${escapeHtml(member.champion_name)}">
            <strong>${escapeHtml(member.champion_name)}</strong>
            <div class="pillbar">
              <span class="pill gold">Score ${formatNumber(member.score, 1)}</span>
              ${(member.roles || []).slice(0, 4).map((role) => `<span class="pill">${escapeHtml(role)}</span>`).join("")}
            </div>
          </button>
        `).join("") || '<div class="empty">Nessuna panchina disponibile.</div>'}
      </div>
    </div>
  `;
}

function renderRoleSourceCard(candidate) {
  const roleSources = candidate?.role_sources || {};
  return `
    <div class="card">
      <h3>Ruoli Riconosciuti</h3>
      <div class="kv single-column">
        <div class="kv-row"><span>Hint statici</span><span>${escapeHtml((roleSources.hint_roles || []).join(", ") || "-")}</span></div>
        <div class="kv-row"><span>Role tag account</span><span>${escapeHtml((roleSources.account_roles || []).join(", ") || "-")}</span></div>
        <div class="kv-row"><span>Inferiti da skill</span><span>${escapeHtml((roleSources.inferred_roles || []).join(", ") || "-")}</span></div>
      </div>
    </div>
  `;
}

function formatBuildStat(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return Math.abs(numeric - Math.round(numeric)) < 0.05 ? String(Math.round(numeric)) : numeric.toFixed(1);
}

function formatBuildDelta(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return "-";
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${formatBuildStat(numeric)}`;
}

function renderStatReliabilityPill(candidate) {
  const reliability = candidate?.stat_reliability || {};
  const source = reliability.source || "missing";
  const confidence = formatNumber(reliability.confidence || 0, 2);
  if (source === "raw") {
    return `<span class="pill ok">stats raw ${escapeHtml(confidence)}</span>`;
  }
  return `<span class="pill warn">stats derivate ${escapeHtml(confidence)}</span>`;
}

function renderBuildSetPills(build) {
  const bits = [];
  (build.applied_sets || []).forEach((row) => {
    const setName = displaySetName(row.set_name || "Set");
    const count = row.completed_sets ? ` x${row.completed_sets}` : "";
    bits.push(`<span class="pill ok">${escapeHtml(`${setName}${count}`)}</span>`);
  });
  (build.unsupported_sets || []).forEach((setName) => {
    bits.push(`<span class="pill warn">${escapeHtml(displaySetName(setName))}</span>`);
  });
  return bits.join("") || '<span class="pill">Nessun set chiave</span>';
}

function renderBuildPieces(build) {
  const items = build?.items || [];
  if (!items.length) {
    return '<div class="empty">Nessun pezzo disponibile per questa proposta.</div>';
  }
  return `
    <div class="stack">
      ${items.map((item) => `
        <div class="build-piece">
          <div class="champ-topline">
            <div class="champ-name">${escapeHtml(displaySlotName(item.slot || "slot"))} | ${escapeHtml(displaySetName(item.set_name || "No Set"))}</div>
            <div class="pill mono">${escapeHtml(item.item_id || "")}</div>
          </div>
          <div class="subtext">Main: ${escapeHtml(displayStatName(item.main_stat_type || "stat"))} ${escapeHtml(formatBuildStat(item.main_stat_value))}</div>
          ${renderItemSubstats(item)}
          <div class="subtext">${escapeHtml(displayItemSourceLabel(item))}</div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderExcludedBuildPieces(build) {
  const items = build?.excluded_items || [];
  if (!items.length) {
    return "";
  }
  return `
    <div class="build-section">
      <h3>Equip Escluso</h3>
      <div class="subtext">Pezzi presenti nei dati ma esclusi dal planner per decode sospetto.</div>
      <div class="stack">
        ${items.map((item) => `
          <div class="build-piece">
            <div class="champ-topline">
              <div class="champ-name">${escapeHtml(displaySlotName(item.slot || "slot"))} | ${escapeHtml(displaySetName(item.set_name || "No Set"))}</div>
              <div class="pill warn">${escapeHtml(item.item_id || "")}</div>
            </div>
            <div class="subtext">Main: ${escapeHtml(displayStatName(item.main_stat_type || "stat"))} ${escapeHtml(formatBuildStat(item.main_stat_value))}</div>
            ${renderItemSubstats(item)}
            <div class="subtext">${escapeHtml(displayItemSourceLabel(item))}</div>
            <div class="subtext">Motivo esclusione: ${escapeHtml((item.validation_issues || []).join(", ") || "decode sospetto")}</div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderBuildPlanCard(candidate) {
  const cacheKey = buildPlanCacheKey(candidate.champion_name, candidate.default_build || "support_general");
  const loading = state.buildPlanLoading[cacheKey];
  const error = state.buildPlanErrors[cacheKey];
  const plan = state.buildPlans[cacheKey];
  if (loading) {
    return `
      <div class="card">
        <h3>Build Proposta</h3>
        <div class="empty">Calcolo build planner in corso...</div>
      </div>
    `;
  }
  if (error) {
    return `
      <div class="card">
        <h3>Build Proposta</h3>
        <div class="empty">${escapeHtml(error)}</div>
      </div>
    `;
  }
  if (!plan) {
    return `
      <div class="card">
        <h3>Build Proposta</h3>
        <div class="empty">Build planner non ancora caricato.</div>
      </div>
    `;
  }
  const current = plan.current_build || {};
  const best = (plan.proposals || [])[0] || current;
  const highlights = plan.profile?.highlights || ["spd", "hp", "def", "acc"];
  return `
    <div class="card">
      <h3>Build Proposta</h3>
      <div class="pillbar">
        <span class="pill gold">${escapeHtml(plan.profile?.label || candidate.default_build || "Profilo")}</span>
        <span class="pill">${escapeHtml(best.label || "Best Proposal")}</span>
        <span class="pill">${escapeHtml(best.scope_label || "")}</span>
      </div>
      <div class="summary compact-summary">
        ${highlights.map((stat) => metricCard(
          stat.toUpperCase(),
          formatBuildStat(best.stats?.[stat]),
          `${formatBuildDelta(best.deltas?.[stat] || 0)} vs attuale`
        )).join("")}
      </div>
      <div class="build-section">
        <h3>Set</h3>
        <div class="pillbar">${renderBuildSetPills(best)}</div>
      </div>
      <div class="build-section">
        <h3>Pezzi</h3>
        ${renderBuildPieces(best)}
      </div>
      ${renderExcludedBuildPieces(current)}
      <div class="subtext">Build attuale: score ${formatBuildStat(current.score)} | proposta: score ${formatBuildStat(best.score)}</div>
    </div>
  `;
}

function renderCandidateDetail() {
  const candidate = (state.report?.candidates || []).find((item) => item.champion_name === state.selectedChampion)
    || (state.report?.selected_team || [])[0]
    || null;
  if (!candidate) {
    return '<div class="empty">Seleziona un campione per vedere motivi, rischi e segnali build.</div>';
  }
  state.selectedChampion = candidate.champion_name;
  const evidence = candidate.evidence || {};
  const stats = candidate.stats || {};
  const statSignals = candidate.stat_signals || {};
  return `
    <div class="stack">
      <div class="detail-hero">
        <div>
          <h2>${escapeHtml(candidate.champion_name)}</h2>
          <div class="detail-meta">
            <span class="pill gold">Score ${formatNumber(candidate.score, 1)}</span>
            <span class="pill">${escapeHtml(candidate.default_build || "n/d")}</span>
            ${renderStatReliabilityPill(candidate)}
            <span class="pill ${candidate.affinity_matchup === "weak" ? "warn" : candidate.affinity_matchup === "strong" ? "ok" : ""}">${escapeHtml(candidate.affinity || "n/d")} vs ${escapeHtml(state.report?.target?.affinity_label || "n/d")}</span>
            ${(candidate.roles || []).map((role) => `<span class="pill">${escapeHtml(role)}</span>`).join("")}
          </div>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <h3>Perche Dentro</h3>
          <div class="list-block">
            ${(candidate.reasons || []).map((reason) => `<div class="list-row">${escapeHtml(reason)}</div>`).join("") || '<div class="empty">Nessuna spiegazione disponibile.</div>'}
          </div>
        </div>
        <div class="card">
          <h3>Cosa Sistemare</h3>
          <div class="list-block">
            ${(candidate.risks || []).map((risk) => `<div class="list-row">${escapeHtml(risk)}</div>`).join("") || '<div class="list-row">Nessun alert forte per questo scheletro.</div>'}
          </div>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <h3>${candidate.stat_reliability?.source === "raw" ? "Stats Chiave" : "Stats Chiave Stimate"}</h3>
          <div class="subtext">${candidate.stat_reliability?.source === "raw" ? "Lette da total stats importate." : "Valori derivati: utili per lo scheletro, ma non ancora trusted come il pannello in-game."}</div>
          <div class="kv single-column">
            <div class="kv-row"><span>SPD</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.spd, 0)}</span></div>
            <div class="kv-row"><span>ACC</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.acc, 0)}</span></div>
            <div class="kv-row"><span>HP</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.hp, 0)}</span></div>
            <div class="kv-row"><span>DEF</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.def, 0)}</span></div>
            <div class="kv-row"><span>C.RATE</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.crit_rate, 0)}</span></div>
            <div class="kv-row"><span>C.DMG</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.crit_dmg, 0)}</span></div>
          </div>
        </div>
        <div class="card">
          <h3>Segnali Build</h3>
          <div class="subtext">${candidate.stat_reliability?.source === "raw" ? "Pesi pieni." : "Speed pesa quasi piena, le altre colonne sono ridotte se il dato non e trusted."}</div>
          <div class="kv single-column">
            <div class="kv-row"><span>Speed fit</span><span>${formatNumber((candidate.weighted_stat_signals || {}).speed ?? statSignals.speed, 2)}</span></div>
            <div class="kv-row"><span>Accuracy fit</span><span>${formatNumber((candidate.weighted_stat_signals || {}).accuracy ?? statSignals.accuracy, 2)}</span></div>
            <div class="kv-row"><span>Survival fit</span><span>${formatNumber((candidate.weighted_stat_signals || {}).survival ?? statSignals.survival, 2)}</span></div>
            <div class="kv-row"><span>Damage fit</span><span>${formatNumber((candidate.weighted_stat_signals || {}).damage ?? statSignals.damage, 2)}</span></div>
          </div>
        </div>
      </div>

      <div class="card">
        <h3>Affidabilita Stats</h3>
        <div class="kv single-column">
          <div class="kv-row"><span>Source</span><span>${escapeHtml(candidate.stat_reliability?.source || "n/d")}</span></div>
          <div class="kv-row"><span>Completeness</span><span>${escapeHtml(candidate.stat_reliability?.completeness || "n/d")}</span></div>
          <div class="kv-row"><span>Confidence</span><span>${formatNumber(candidate.stat_reliability?.confidence || 0, 2)}</span></div>
          <div class="kv-row"><span>Sorgenti mancanti</span><span>${escapeHtml((candidate.stat_reliability?.missing_sources || []).join(", ") || "nessuna")}</span></div>
        </div>
        <div class="list-block">
          ${(candidate.stat_reliability?.warnings || []).map((warning) => `<div class="list-row">${escapeHtml(warning)}</div>`).join("") || '<div class="list-row">Nessun warning specifico.</div>'}
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <h3>Run Evidence</h3>
          <div class="kv single-column">
            <div class="kv-row"><span>Run viste</span><span>${formatNumber(evidence.run_count, 0)}</span></div>
            <div class="kv-row"><span>Avg damage</span><span>${formatNumber(evidence.avg_damage_done, 0)}</span></div>
            <div class="kv-row"><span>Avg damage taken</span><span>${formatNumber(evidence.avg_damage_taken, 0)}</span></div>
            <div class="kv-row"><span>Avg healing</span><span>${formatNumber(evidence.avg_healing_done, 0)}</span></div>
          </div>
        </div>
        ${renderRoleSourceCard(candidate)}
      </div>

      ${renderBuildPlanCard(candidate)}
    </div>
  `;
}

function renderDetails() {
  if (!state.report) {
    detailsEl.innerHTML = '<div class="empty">Optimizer non disponibile.</div>';
    return;
  }
  detailsEl.innerHTML = `
    <div class="grid">
      ${renderTeamCard()}
      ${renderCoverageCard()}
    </div>
    <div class="grid">
      ${renderWarningsCard()}
      ${renderBenchCard()}
    </div>
    ${renderCandidateDetail()}
  `;
  detailsEl.querySelectorAll(".optimizer-member-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedChampion = button.dataset.name || null;
      renderRoster();
      renderDetails();
    });
  });
  const selectedCandidate = (state.report?.candidates || []).find((item) => item.champion_name === state.selectedChampion);
  if (selectedCandidate) {
    ensureBuildPlan(selectedCandidate);
  }
}

async function ensureBuildPlan(candidate) {
  const profile = candidate.default_build || "support_general";
  const cacheKey = buildPlanCacheKey(candidate.champion_name, profile);
  if (state.buildPlans[cacheKey] || state.buildPlanLoading[cacheKey]) return;
  state.buildPlanLoading[cacheKey] = true;
  delete state.buildPlanErrors[cacheKey];
  renderDetails();
  try {
    const query = new URLSearchParams({
      name: candidate.champion_name,
      profile,
      region: "clan_boss",
    });
    state.buildPlans[cacheKey] = await fetchJson(`/api/build-plan?${query.toString()}`);
  } catch (error) {
    state.buildPlanErrors[cacheKey] = error.message || "Impossibile calcolare la build.";
  } finally {
    delete state.buildPlanLoading[cacheKey];
    if (state.selectedChampion === candidate.champion_name) {
      renderDetails();
    }
  }
}

async function loadReport() {
  setStatus("Calcolo optimizer in corso...");
  try {
    const payload = await fetchJson(
      `/api/team-optimizer?boss=${encodeURIComponent(state.selectedBoss)}&level=${encodeURIComponent(state.selectedLevel)}&affinity=${encodeURIComponent(state.selectedAffinity)}`
    );
    state.targets = payload.targets || [];
    state.selectedBoss = payload.selection?.boss_key || state.selectedBoss;
    state.selectedLevel = payload.selection?.level_key || state.selectedLevel;
    state.selectedAffinity = payload.selection?.affinity || state.selectedAffinity;
    state.report = payload.report || null;
    renderBossSelect();
    renderAffinitySelect();
    renderLevelSelect();
    if (!state.selectedChampion && state.report?.selected_team?.length) {
      state.selectedChampion = state.report.selected_team[0].champion_name;
    }
    renderSummary();
    renderRoster();
    renderDetails();
    setStatus(`Optimizer pronto su ${state.report?.target?.boss_label || state.selectedBoss} ${state.report?.target?.level_label || state.selectedLevel}.`);
  } catch (error) {
    state.report = null;
    renderSummary();
    renderRoster();
    renderDetails();
    setStatus(error.message || "Impossibile caricare l'optimizer.", true);
  }
}

bossEl.addEventListener("change", async () => {
  state.selectedBoss = bossEl.value || "demon_lord";
  renderAffinitySelect();
  renderLevelSelect();
  await loadReport();
});

affinityEl.addEventListener("change", async () => {
  state.selectedAffinity = affinityEl.value || "void";
  await loadReport();
});

levelEl.addEventListener("change", async () => {
  state.selectedLevel = levelEl.value || "ultra_nightmare";
  await loadReport();
});

reloadBtn.addEventListener("click", async () => {
  await loadReport();
});

loadReport();
