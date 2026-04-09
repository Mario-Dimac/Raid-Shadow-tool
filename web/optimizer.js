const state = {
  targets: [],
  selectedBoss: "demon_lord",
  selectedAffinity: "void",
  selectedLevel: "ultra_nightmare",
  selectedSource: "optimizer",
  report: null,
  bossIntel: null,
  trainingOverview: null,
  selectedChampion: null,
  buildPlans: {},
  buildPlanErrors: {},
  buildPlanLoading: {},
  teamLoadout: null,
  teamLoadoutError: "",
  localBridgePlan: null,
  localBridgePlanError: "",
  equipInGameLoading: false,
  equipInGameResult: null,
  equipQueueIndex: 0,
  refreshGameLoading: false,
  optimizerSimulation: null,
  optimizerSimulationLoading: false,
  memberOpenerPrefs: {},
  snapshotStatus: null,
  saveSnapshotLoading: false,
  saveSnapshotResult: null,
  restoreLoading: false,
  restoreResult: null,
};

const rosterEl = document.getElementById("optimizerRoster");
const detailsEl = document.getElementById("optimizerDetails");
const summaryEl = document.getElementById("optimizerSummary");
const statusEl = document.getElementById("optimizerStatus");
const bossEl = document.getElementById("optimizerBoss");
const affinityEl = document.getElementById("optimizerAffinity");
const levelEl = document.getElementById("optimizerLevel");
const sourceEl = document.getElementById("optimizerSource");
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

async function fetchJson(url, options = {}) {
  const { timeoutMs = 0, ...fetchOptions } = options || {};
  const controller = timeoutMs > 0 ? new AbortController() : null;
  let timeoutHandle = null;
  if (controller) {
    timeoutHandle = window.setTimeout(() => controller.abort(), timeoutMs);
    fetchOptions.signal = controller.signal;
  }
  let response;
  try {
    response = await fetch(url, fetchOptions);
  } catch (error) {
    if (controller && error?.name === "AbortError") {
      throw new Error("Richiesta scaduta: il bridge HH sta rispondendo troppo lentamente. Controlla in game e riprova.");
    }
    throw error;
  } finally {
    if (timeoutHandle !== null) {
      window.clearTimeout(timeoutHandle);
    }
  }
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

function formatDurationMs(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "-";
  const seconds = numeric / 1000;
  if (seconds < 10) return `${seconds.toFixed(1)} s`;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

async function refreshGearAndReloadOptimizer() {
  state.refreshGameLoading = true;
  renderDetails();
  setStatus("Riallineamento equip dal game in corso...");
  try {
    const payload = await fetchJson("/api/refresh-gear", {
      method: "POST",
      timeoutMs: 180000,
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    await loadReport();
    const imported = Number(payload?.summary?.gear_items || 0);
    setStatus(`Equip riallineato dal game. Pezzi nel DB: ${formatNumber(imported, 0)}.`);
  } catch (error) {
    setStatus(error.message || "Impossibile riallineare l'equip dal game.", true);
  } finally {
    state.refreshGameLoading = false;
    renderDetails();
  }
}

function openerPreferenceStorageKey() {
  return [
    "cbforge",
    "optimizer",
    "openers",
    state.selectedBoss || "demon_lord",
    state.selectedLevel || "ultra_nightmare",
    state.selectedAffinity || "void",
    state.selectedSource || "optimizer",
  ].join("::");
}

function loadSavedOpenerPreferences() {
  try {
    const raw = window.localStorage.getItem(openerPreferenceStorageKey());
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function persistOpenerPreferences() {
  try {
    window.localStorage.setItem(openerPreferenceStorageKey(), JSON.stringify(state.memberOpenerPrefs || {}));
  } catch (_error) {
    // Ignore localStorage failures: the page should remain usable even in private mode.
  }
}

function syncMemberOpenerPreferences() {
  const stored = loadSavedOpenerPreferences();
  const allowed = new Set(["AUTO", "A1", "A2", "A3", "A4", "NONE"]);
  const next = {};
  (state.report?.selected_team || []).forEach((member) => {
    const championName = String(member?.champion_name || "").trim();
    const requested = String(stored?.[championName] || "AUTO").trim().toUpperCase();
    next[championName] = allowed.has(requested) ? requested : "AUTO";
  });
  state.memberOpenerPrefs = next;
}

function getMemberOpenerPreference(championName) {
  return String((state.memberOpenerPrefs || {})[championName] || "AUTO").toUpperCase();
}

function setMemberOpenerPreference(championName, openerSlot) {
  const normalizedName = String(championName || "").trim();
  if (!normalizedName) return;
  const normalizedSlot = String(openerSlot || "AUTO").trim().toUpperCase() || "AUTO";
  state.memberOpenerPrefs = {
    ...(state.memberOpenerPrefs || {}),
    [normalizedName]: normalizedSlot,
  };
  persistOpenerPreferences();
}

function getSelectedTeamCandidate(championName) {
  return (state.report?.selected_team || []).find((member) => member.champion_name === championName) || null;
}

function getTeamLoadoutMember(championName) {
  return (state.teamLoadout?.team || []).find((member) => member.champion_name === championName) || null;
}

async function refreshOptimizerSimulation(options = {}) {
  const { silent = false } = options || {};
  const team = state.report?.selected_team || [];
  if (state.selectedBoss !== "demon_lord" || !team.length) {
    state.optimizerSimulation = null;
    state.optimizerSimulationLoading = false;
    return;
  }
  state.optimizerSimulationLoading = true;
  renderDetails();
  if (!silent) {
    setStatus("Simulazione optimizer con opener personalizzato in corso...");
  }
  try {
    state.optimizerSimulation = await fetchJson("/api/team-optimizer-simulate", {
      method: "POST",
      timeoutMs: 30000,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        boss: state.selectedBoss,
        level: state.selectedLevel,
        affinity: state.selectedAffinity,
        source: state.selectedSource,
        max_boss_turns: 6,
        opener_preferences: state.memberOpenerPrefs || {},
      }),
    });
    if (!silent) {
      setStatus("Simulazione opener aggiornata sull'attuale team selezionato.");
    }
  } catch (error) {
    state.optimizerSimulation = null;
    setStatus(error.message || "Impossibile aggiornare la simulazione opener.", true);
  } finally {
    state.optimizerSimulationLoading = false;
    renderDetails();
  }
}

function getMemberChangeSummary(member) {
  const changedItems = (member?.items || []).filter((item) => String(item?.source_kind || "").toLowerCase() !== "current");
  const borrowedItems = changedItems.filter((item) => String(item?.source_kind || "").toLowerCase() === "borrowed");
  const inventoryItems = changedItems.filter((item) => String(item?.source_kind || "").toLowerCase() === "inventory");
  const donorNames = Array.from(new Set(
    borrowedItems
      .map((item) => String(item?.owner_name || item?.equipped_by || "").trim())
      .filter(Boolean)
  )).sort();
  return {
    changedItems,
    borrowedItems,
    inventoryItems,
    donorNames,
  };
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

function renderSourceSelect() {
  const options = state.selectedBoss === "demon_lord"
    ? [
      { key: "optimizer", label: "Optimizer stabile" },
      { key: "optimizer_push", label: "Optimizer push 70M" },
      { key: "ai", label: "AI stabile" },
      { key: "ai_push", label: "AI push 70M" },
    ]
    : [{ key: "optimizer", label: "Optimizer" }];
  sourceEl.innerHTML = options.map((item) => (
    `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`
  )).join("");
  const current = options.some((item) => item.key === state.selectedSource)
    ? state.selectedSource
    : options[0].key;
  state.selectedSource = current;
  sourceEl.value = current;
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
  const selectedTeam = state.report?.selected_team || [];
  if (!selectedTeam.length) {
    rosterEl.innerHTML = '<div class="empty">Nessun team proposto disponibile.</div>';
    return;
  }
  rosterEl.innerHTML = selectedTeam.map((candidate, index) => `
    <button class="champ-row ${state.selectedChampion === candidate.champion_name ? "active" : ""}" data-name="${escapeHtml(candidate.champion_name)}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(`${index + 1}. ${candidate.champion_name}`)}</div>
        <div class="pill ok">${formatNumber(candidate.score, 1)}</div>
      </div>
      <div class="pillbar">
        <span class="pill ok">Team Proposto</span>
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
      metricCard("Modalita", "-", "Ranking non disponibile"),
      metricCard("Storico", "-", "Nessuna shell"),
      metricCard("Alert", "-", "Warning principali"),
    ].join("");
    return;
  }
  const team = state.report.selected_team || [];
  const history = state.report.historical_team_evidence || {};
  const warningCount = (state.report.warnings || []).length;
  const historyLabel = Number(history.run_count || 0) > 0
    ? `${formatNumber(history.avg_total_damage || 0, 0)} avg`
    : "n/d";
  const historyNote = Number(history.run_count || 0) > 0
    ? `${formatNumber(history.run_count || 0, 0)} run | max ${formatNumber(history.max_total_damage || 0, 0)}`
    : "Nessuna run forte trovata";
  summaryEl.innerHTML = [
    metricCard("Boss", state.report.target?.boss_label || "-", `${state.report.target?.level_label || "-"} / ${state.report.target?.affinity_label || "-"}`),
    metricCard("Modalita", state.report.target?.recommendation_label || "Optimizer", `${team.length}/${state.report.target?.team_size || 5} campioni scelti`),
    metricCard("Storico", historyLabel, historyNote),
    metricCard("Alert", formatNumber(warningCount, 0), warningCount ? "Da leggere sotto" : "Nessun warning forte"),
  ].join("");
}

function renderDecisionCard() {
  const report = state.report || {};
  const notes = (report.notes || []).slice(0, 4);
  const history = report.historical_team_evidence || {};
  const missing = report.missing_required_roles || [];
  return `
    <div class="card">
      <h3>Perche Questo Team</h3>
      <div class="kv single-column">
        <div class="kv-row"><span>Modalita</span><span>${escapeHtml(report.target?.objective_label || report.target?.recommendation_label || "-")}</span></div>
        <div class="kv-row"><span>Storico</span><span>${Number(history.run_count || 0) > 0 ? `${formatNumber(history.run_count || 0, 0)} run` : "n/d"}</span></div>
        <div class="kv-row"><span>Media danni</span><span>${Number(history.run_count || 0) > 0 ? formatNumber(history.avg_total_damage || 0, 0) : "-"}</span></div>
        <div class="kv-row"><span>Gap target</span><span>${report.target?.target_damage ? `${formatNumber((report.target.target_damage || 0) - (history.max_total_damage || 0), 0)}` : "-"}</span></div>
        <div class="kv-row"><span>Ruoli mancanti</span><span>${escapeHtml(missing.join(", ") || "nessuno")}</span></div>
      </div>
      <div class="list-block">
        ${notes.map((item) => `<div class="list-row">${escapeHtml(item)}</div>`).join("") || '<div class="list-row">Nessuna nota disponibile.</div>'}
      </div>
    </div>
  `;
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
  const warnings = (state.report?.warnings || []).slice(0, 8);
  return `
    <div class="card">
      <h3>Warning Principali</h3>
      <div class="list-block">
        ${(warnings.length ? warnings : ["Nessun rischio rilevato da questa euristica."]).map((item) => `
          <div class="list-row">${escapeHtml(item)}</div>
        `).join("")}
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

function renderQuickBenchCard() {
  const bench = (state.report?.bench || []).slice(0, 3);
  return `
    <div class="card">
      <h3>Alternative Rapide</h3>
      <div class="list-block">
        ${bench.map((member) => `
          <div class="list-row">
            <strong>${escapeHtml(member.champion_name)}</strong>
            <div class="subtext">${escapeHtml(member.default_build || "build")} | score ${escapeHtml(formatNumber(member.score, 1))}</div>
          </div>
        `).join("") || '<div class="empty">Nessuna alternativa immediata.</div>'}
      </div>
    </div>
  `;
}

function renderCompactGearCard() {
  if (state.teamLoadoutError) {
    return `
      <div class="card">
        <h3>Cambio Equip</h3>
        <div class="empty">${escapeHtml(state.teamLoadoutError)}</div>
      </div>
    `;
  }
  const selectedName = state.selectedChampion
    || state.report?.selected_team?.[0]?.champion_name
    || "";
  const selectedMember = getTeamLoadoutMember(selectedName);
  const summary = state.teamLoadout?.summary || {};
  const snapshotStatus = state.snapshotStatus || {};
  const teamSnapshot = snapshotStatus.team_snapshot || {};
  const lastRestore = snapshotStatus.last_restore || {};
  if (!state.teamLoadout || !selectedMember) {
    return `
      <div class="card">
        <h3>Cambio Equip</h3>
        <div class="subtext">Sto preparando il piano equip del team scelto.</div>
        <div class="empty">Attendi qualche secondo dopo il calcolo optimizer.</div>
      </div>
    `;
  }
  const changeSummary = getMemberChangeSummary(selectedMember);
  const hasChanges = changeSummary.changedItems.length > 0;
  const hasConflicts = !!selectedMember.conflict_item_ids?.length;
  return `
    <div class="card">
      <h3>Cambio Equip</h3>
      <div class="summary compact-summary">
        ${metricCard("Selezionato", selectedMember.champion_name || "-", hasChanges ? `${formatNumber(changeSummary.changedItems.length, 0)} cambi` : "Gia pronto")}
        ${metricCard("Swap team", formatNumber(summary.total_swap_count || 0, 0), `${formatNumber(summary.conflict_count || 0, 0)} conflitti`)}
        ${metricCard("Snapshot", teamSnapshot.available ? "pronto" : "assente", lastRestore.available ? "restore pronto" : "restore assente")}
      </div>
      <div class="action-row">
        <button id="optimizerEquipSelectedMemberBtn" class="primary" ${state.equipInGameLoading || !hasChanges || hasConflicts ? "disabled" : ""}>${state.equipInGameLoading ? "Invio In Corso..." : "Equipaggia Campione"}</button>
        <button id="optimizerSaveSnapshotBtn" class="secondary" ${state.saveSnapshotLoading ? "disabled" : ""}>${state.saveSnapshotLoading ? "Salvataggio..." : "Salva Snapshot"}</button>
        <button id="optimizerRestoreSnapshotBtn" class="secondary" ${state.restoreLoading || !teamSnapshot.available ? "disabled" : ""}>${state.restoreLoading ? "Ripristino..." : "Ripristina Team"}</button>
        <button id="optimizerRestoreInGameBtn" class="secondary" ${state.restoreLoading || !lastRestore.available ? "disabled" : ""}>${state.restoreLoading ? "Ripristino..." : "Ripristina Ultimo Equip"}</button>
        <button id="optimizerRefreshGameBtn" class="secondary" ${state.refreshGameLoading ? "disabled" : ""}>${state.refreshGameLoading ? "Riallineamento..." : "Riallinea Dal Game"}</button>
      </div>
      <div class="list-block">
        <div class="list-row">
          <strong>${escapeHtml(selectedMember.champion_name || "-")}</strong>
          <div class="subtext">
            swap ${escapeHtml(String(selectedMember.swap_count || 0))}
            | inventario ${escapeHtml(String(selectedMember.inventory_items || 0))}
            | borrowed ${escapeHtml(String(selectedMember.borrowed_items || 0))}
            | conflitti ${escapeHtml(String(selectedMember.conflict_item_ids?.length || 0))}
          </div>
        </div>
        ${hasConflicts ? `<div class="list-row">Pezzi in conflitto: ${escapeHtml((selectedMember.conflict_item_ids || []).join(", "))}.</div>` : ""}
        ${changeSummary.donorNames.length ? `<div class="list-row">Donor toccati: ${escapeHtml(changeSummary.donorNames.join(", "))}.</div>` : ""}
        <div class="list-row">${hasChanges ? `Invio diretto pronto per ${escapeHtml(selectedMember.champion_name || "-")}.` : `${escapeHtml(selectedMember.champion_name || "-")} risulta gia allineato alla build proposta.`}</div>
      </div>
    </div>
  `;
}

function renderTrainingOverviewCard() {
  const overview = state.trainingOverview || {};
  const categories = overview.categories || [];
  const summary = overview.summary || {};
  return `
    <div class="card">
      <h3>Categorie Run</h3>
      <div class="summary compact-summary">
        ${metricCard("Run DB", formatNumber(summary.runs || 0, 0), `${formatNumber(summary.encounters || 0, 0)} encounter`)}
        ${metricCard("Con Danno", formatNumber(summary.runs_with_damage || 0, 0), "Run con total damage")}
        ${metricCard("Categorie", formatNumber(categories.length || 0, 0), "Distribuzione storica")}
      </div>
      <div class="list-block">
        ${categories.length ? categories.map((item) => `
          <div class="list-row">
            <strong>${escapeHtml(item.category_label || "Altro")}</strong>
            <div class="subtext">
              ${escapeHtml(String(item.run_count || 0))} run
              | ${escapeHtml(String(item.runs_with_damage || 0))} con danno
              | ${escapeHtml(String(item.encounter_count || 0))} encounter
            </div>
            <div class="subtext">${escapeHtml((item.examples || []).join(", ") || "Nessun esempio disponibile")}</div>
          </div>
        `).join("") : '<div class="empty">Nessuna run disponibile nel DB.</div>'}
      </div>
    </div>
  `;
}

function renderBossIntelCard() {
  const intel = state.bossIntel || {};
  const selectedTargets = intel.selected_level_targets || [];
  const selectedNotes = intel.selected_level_notes || [];
  const mechanics = intel.mechanics || [];
  const keyRoles = intel.key_roles || [];
  const watchouts = intel.watchouts || [];
  const timingNotes = intel.timing_notes || [];
  const optimizerGaps = intel.optimizer_gaps || [];
  const catalog = intel.catalog || [];
  const plannedModules = intel.planned_modules || [];
  const selectedRotation = intel.selected_rotation || null;
  const sources = intel.sources || [];
  const statusLabel = intel.implemented_in_optimizer ? "attivo" : "knowledge only";
  const statusNote = intel.implemented_in_optimizer
    ? "Le regole base di questo boss sono gia agganciate al flusso optimizer."
    : "Modulo dati pronto, ma scoring e warning boss-specifici sono ancora in costruzione.";
  return `
    <div class="card">
      <h3>Boss Intel</h3>
      <div class="summary compact-summary">
        ${metricCard("Boss", intel.label || "-", intel.category || "")}
        ${metricCard("Stato", statusLabel, statusNote)}
        ${metricCard("Team Size", formatNumber(intel.team_size || 0, 0), intel.selected_level_label || "livello n/d")}
        ${metricCard("Affinity", intel.selected_affinity_label || "-", catalog.length ? `${formatNumber(catalog.length, 0)} moduli disponibili` : "Catalogo boss vuoto")}
      </div>
      <div class="subtext">${escapeHtml(intel.overview || "Nessuna scheda boss disponibile.")}</div>
      ${selectedTargets.length ? `
        <div class="build-section">
          <h3>Target Rapidi</h3>
          <div class="kv single-column">
            ${selectedTargets.map((item) => `
              <div class="kv-row">
                <span>${escapeHtml(item.label || "-")}</span>
                <span>${escapeHtml(item.value || "-")}</span>
              </div>
            `).join("")}
          </div>
          <div class="list-block">
            ${selectedTargets.map((item) => `<div class="list-row">${escapeHtml(item.note || "")}</div>`).join("")}
          </div>
        </div>
      ` : ""}
      ${selectedNotes.length ? `
        <div class="build-section">
          <h3>Note Livello</h3>
          <div class="list-block">
            ${selectedNotes.map((item) => `<div class="list-row">${escapeHtml(item)}</div>`).join("")}
          </div>
        </div>
      ` : ""}
      ${selectedRotation ? `
        <div class="build-section">
          <h3>Rotazione Hydra</h3>
          <div class="kv single-column">
            <div class="kv-row"><span>Rotazione</span><span>${escapeHtml(selectedRotation.label || intel.selected_affinity_label || "-")}</span></div>
            <div class="kv-row"><span>Starter</span><span>${escapeHtml((selectedRotation.starter_heads || []).join(", ") || "-")}</span></div>
            <div class="kv-row"><span>Sub</span><span>${escapeHtml((selectedRotation.substitute_heads || []).join(", ") || "-")}</span></div>
          </div>
          <div class="list-block">
            ${Object.entries(selectedRotation.head_affinities || {}).map(([head, affinity]) => `
              <div class="list-row">
                <strong>${escapeHtml(head)}</strong>
                <div class="subtext">Affinity: ${escapeHtml(affinity || "n/d")}</div>
              </div>
            `).join("")}
            ${(selectedRotation.optimizer_focus || []).map((item) => `<div class="list-row">${escapeHtml(item)}</div>`).join("")}
          </div>
        </div>
      ` : ""}
      <div class="grid">
        <div class="card">
          <h3>Meccaniche Chiave</h3>
          <div class="list-block">
            ${mechanics.map((item) => `
              <div class="list-row">
                <strong>${escapeHtml(item.label || "-")}</strong>
                <div class="subtext">${escapeHtml(item.summary || "")}</div>
              </div>
            `).join("") || '<div class="empty">Nessuna meccanica disponibile.</div>'}
          </div>
        </div>
        <div class="card">
          <h3>Ruoli Da Premiare</h3>
          <div class="list-block">
            ${keyRoles.map((item) => `
              <div class="list-row">
                <strong>${escapeHtml(item.label || "-")}</strong>
                <div class="subtext">${escapeHtml(item.reason || "")}</div>
              </div>
            `).join("") || '<div class="empty">Nessun ruolo suggerito.</div>'}
          </div>
        </div>
      </div>
      <div class="build-section">
        <h3>Attenzione</h3>
        <div class="list-block">
          ${watchouts.map((item) => `<div class="list-row">${escapeHtml(item)}</div>`).join("") || '<div class="list-row">Nessun warning boss-specifico.</div>'}
        </div>
      </div>
      ${timingNotes.length ? `
        <div class="build-section">
          <h3>Timing E Tune</h3>
          <div class="list-block">
            ${timingNotes.map((item) => `<div class="list-row">${escapeHtml(item)}</div>`).join("")}
          </div>
        </div>
      ` : ""}
      ${optimizerGaps.length ? `
        <div class="build-section">
          <h3>Appunto Modulo</h3>
          <div class="list-block">
            ${optimizerGaps.map((item) => `<div class="list-row">${escapeHtml(item)}</div>`).join("")}
          </div>
        </div>
      ` : ""}
      <div class="build-section">
        <h3>Fonti</h3>
        <div class="list-block">
          ${sources.map((item) => `
            <div class="list-row">
              <strong><a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(item.label || item.url || "Fonte")}</a></strong>
              <div class="subtext">${escapeHtml([item.kind, item.confidence, item.checked_at].filter(Boolean).join(" | "))}</div>
              <div class="subtext">${escapeHtml(item.note || "")}</div>
            </div>
          `).join("") || '<div class="empty">Nessuna fonte tracciata.</div>'}
        </div>
      </div>
      <div class="build-section">
        <h3>Moduli Disponibili</h3>
        <div class="pillbar">
          ${catalog.map((item) => `<span class="pill ${item.implemented_in_optimizer ? "ok" : ""}">${escapeHtml(item.label || item.boss_key || "Boss")}</span>`).join("") || '<span class="pill">Nessun modulo</span>'}
        </div>
      </div>
      ${plannedModules.length ? `
        <div class="build-section">
          <h3>Boss In Coda</h3>
          <div class="list-block">
            ${plannedModules.map((item) => `
              <div class="list-row">
                <strong>${escapeHtml(item.label || item.boss_key || "Boss")}</strong>
                <div class="subtext">${escapeHtml(item.category || "")}</div>
                <div class="subtext">${escapeHtml(item.note || "Da implementare.")}</div>
              </div>
            `).join("")}
          </div>
        </div>
      ` : ""}
    </div>
  `;
}

function renderTeamLoadoutCard() {
  if (state.teamLoadoutError) {
    return `
      <div class="card">
        <h3>Loadout Team</h3>
        <div class="empty">${escapeHtml(state.teamLoadoutError)}</div>
      </div>
    `;
  }
  const payload = state.teamLoadout;
  if (!payload) {
    return `
      <div class="card">
        <h3>Loadout Team</h3>
        <div class="empty">Preparazione riepilogo equip in corso...</div>
      </div>
    `;
  }
  const summary = payload.summary || {};
  const conflicts = payload.conflicts || [];
  return `
    <div class="card">
      <h3>Loadout Team</h3>
      <div class="summary compact-summary">
        ${metricCard("Campioni", formatNumber(summary.champions || 0, 0), "Team proposto")}
        ${metricCard("Swap", formatNumber(summary.total_swap_count || 0, 0), `${formatNumber(summary.total_inventory_items || 0, 0)} da magazzino`)}
        ${metricCard("Borrowed", formatNumber(summary.total_borrowed_items || 0, 0), "Da altri campioni")}
        ${metricCard("Conflitti", formatNumber(summary.conflict_count || 0, 0), conflicts.length ? "Pezzi condivisi da risolvere" : "Nessun pezzo condiviso")}
      </div>
      <div class="list-block">
        ${(payload.team || []).map((member) => `
          <div class="list-row">
            <strong>${escapeHtml(member.champion_name || "-")}</strong>
            <div class="subtext">
              ${escapeHtml(member.build_label || member.default_build || "Build")}
              | swap ${escapeHtml(String(member.swap_count || 0))}
              | inventario ${escapeHtml(String(member.inventory_items || 0))}
              | borrowed ${escapeHtml(String(member.borrowed_items || 0))}
              ${member.conflict_item_ids?.length ? `| conflitti ${escapeHtml(member.conflict_item_ids.join(", "))}` : ""}
            </div>
          </div>
        `).join("") || '<div class="empty">Nessun riepilogo loadout disponibile.</div>'}
      </div>
      ${conflicts.length ? `
        <div class="build-section">
          <h3>Conflitti Pezzi</h3>
          <div class="list-block">
            ${conflicts.map((conflict) => `
              <div class="list-row">
                <strong>${escapeHtml(conflict.item_id || "")}</strong>
                <div class="subtext">${escapeHtml((conflict.usage || []).map((row) => `${row.champion_name} ${row.slot || ""}`.trim()).join(" | "))}</div>
              </div>
            `).join("")}
          </div>
        </div>
      ` : ""}
    </div>
  `;
}

function renderLocalBridgeCard() {
  if (state.localBridgePlanError) {
    return `
      <div class="card">
        <h3>Bridge Locale</h3>
        <div class="action-row">
          <button id="optimizerEquipInGameBtn" class="primary" disabled>Equipaggia In Game</button>
          <span class="pill warn">Bridge non pronto</span>
        </div>
        <div class="empty">${escapeHtml(state.localBridgePlanError)}</div>
      </div>
    `;
  }
  const payload = state.localBridgePlan;
  if (!payload) {
    return `
      <div class="card">
        <h3>Bridge Locale</h3>
        <div class="action-row">
          <button id="optimizerEquipInGameBtn" class="primary" disabled>Equipaggia In Game</button>
          <span class="pill">Preparazione...</span>
        </div>
        <div class="subtext">Il pulsante compare subito, ma resta disattivato finche il piano equip del team non e pronto.</div>
        <div class="empty">Preparazione piano cambio equip in corso...</div>
      </div>
    `;
  }
  const plan = payload.plan || {};
  const memberBlocks = plan.member_blocks || [];
  const previewSteps = (plan.steps || []).slice(0, 12);
  const teamMembers = state.teamLoadout?.team || [];
  const selectedTeamMember = teamMembers.find((member) => member.champion_name === state.selectedChampion) || null;
  const selectedMemberHasConflicts = !!selectedTeamMember && !!selectedTeamMember.conflict_item_ids?.length;
  const selectedMemberHasChanges = !!selectedTeamMember && (selectedTeamMember.items || []).some((item) => String(item?.source_kind || "").toLowerCase() !== "current");
  const selectedMemberChanges = selectedTeamMember ? getMemberChangeSummary(selectedTeamMember) : null;
  const snapshotStatus = state.snapshotStatus || {};
  const lastRestore = snapshotStatus.last_restore || {};
  const lastRestoreSummary = lastRestore.summary || {};
  const teamSnapshot = snapshotStatus.team_snapshot || {};
  const teamSnapshotSummary = teamSnapshot.summary || {};
  const equipSummary = state.equipInGameResult?.summary || {};
  const restoreRunSummary = state.restoreResult?.summary || {};
  const saveSnapshotSummary = state.saveSnapshotResult?.summary || {};
  return `
    <div class="card">
      <h3>Bridge Locale</h3>
      <div class="action-row">
        <button id="optimizerEquipInGameBtn" class="primary" ${state.equipInGameLoading || !selectedMemberHasChanges || selectedMemberHasConflicts ? "disabled" : ""}>${state.equipInGameLoading ? "Invio In Corso..." : "Equipaggia Campione Selezionato"}</button>
        <button id="optimizerSaveSnapshotBtn" class="secondary" ${state.saveSnapshotLoading ? "disabled" : ""}>${state.saveSnapshotLoading ? "Salvataggio..." : (teamSnapshot.available ? "Aggiorna Snapshot Team" : "Salva Snapshot Team")}</button>
        <button id="optimizerRestoreSnapshotBtn" class="secondary" ${state.restoreLoading || !teamSnapshot.available ? "disabled" : ""}>${state.restoreLoading ? "Ripristino In Corso..." : "Ripristina Snapshot Team"}</button>
        <button id="optimizerRestoreInGameBtn" class="secondary" ${state.restoreLoading || !lastRestore.available ? "disabled" : ""}>${state.restoreLoading ? "Ripristino In Corso..." : "Ripristina Ultimo Equip"}</button>
        <button id="optimizerRefreshGameBtn" class="secondary" ${state.refreshGameLoading ? "disabled" : ""}>${state.refreshGameLoading ? "Riallineamento..." : "Confermato In Game -> Riallinea"}</button>
        <span class="pill ok">Bridge attivo</span>
      </div>
      <div class="subtext">Il bridge locale invia al gioco solo il campione che hai selezionato nella pagina. Dopo la conferma in RAID usa il riallineamento dal game per aggiornare davvero DB e optimizer.</div>
      <div class="summary compact-summary">
        ${metricCard("Azioni", formatNumber(plan.action_count || 0, 0), "Cambio equip manuale guidato")}
        ${metricCard("Swap", formatNumber(plan.swap_count || 0, 0), "Pezzi presi da altri campioni")}
        ${metricCard("Liberi", formatNumber(plan.free_equip_count || 0, 0), "Pezzi da magazzino")}
        ${metricCard("Pronti", formatNumber(plan.ready_count || 0, 0), "Gia indossati")}
      </div>
      <div class="summary compact-summary">
        ${metricCard("Selezionato", selectedTeamMember ? selectedTeamMember.champion_name : "-", selectedTeamMember ? `champ ${selectedTeamMember.champ_id || "-"}` : "Scegli un campione del team")}
        ${metricCard("Snapshot Team", teamSnapshot.available ? "Pronto" : "Assente", teamSnapshot.available ? `${formatNumber(teamSnapshotSummary.champions || 0, 0)} campioni salvati` : "Salvalo dal bottone dedicato")}
        ${metricCard("Auto Restore", lastRestore.available ? "Pronto" : "Assente", lastRestore.available ? `${formatNumber(lastRestoreSummary.champions || 0, 0)} campioni salvati` : "Si aggiorna automaticamente")}
        ${metricCard("Ultimo Equip", state.equipInGameResult ? `${formatNumber(equipSummary.members_succeeded || 0, 0)}/${formatNumber(equipSummary.members_requested || 0, 0)}` : "-", state.equipInGameResult ? `${formatDurationMs(equipSummary.duration_ms)} | ${formatNumber(equipSummary.total_artifacts_requested || 0, 0)} pezzi` : "Nessun invio recente")}
        ${metricCard("Ultimo Restore", state.restoreResult ? `${formatNumber(restoreRunSummary.members_succeeded || 0, 0)}/${formatNumber(restoreRunSummary.members_requested || 0, 0)}` : "-", state.restoreResult ? `${formatDurationMs(restoreRunSummary.duration_ms)} | ${formatNumber(restoreRunSummary.total_artifacts_requested || 0, 0)} pezzi` : "Non ancora eseguito")}
      </div>
      <div class="list-block">
        ${(plan.notes || []).map((note) => `<div class="list-row">${escapeHtml(note)}</div>`).join("") || '<div class="list-row">Nessuna nota disponibile.</div>'}
        ${selectedTeamMember ? `<div class="list-row">Invio diretto pronto per ${escapeHtml(selectedTeamMember.champion_name || "-")} (#${escapeHtml(selectedTeamMember.champ_id || "-")}).</div>` : '<div class="list-row">Seleziona un campione del team per inviare il suo equip al gioco.</div>'}
        ${selectedTeamMember && !selectedMemberHasChanges ? `<div class="list-row">${escapeHtml(selectedTeamMember.champion_name || "-")} risulta gia allineato alla build proposta: nessun cambio da inviare.</div>` : ""}
        ${selectedTeamMember && selectedMemberHasConflicts ? `<div class="list-row">Equip singolo bloccato: ${escapeHtml(selectedTeamMember.champion_name || "-")} ha pezzi in conflitto con altri membri del team (${escapeHtml((selectedTeamMember.conflict_item_ids || []).join(", "))}).</div>` : ""}
        ${selectedMemberChanges?.donorNames?.length ? `<div class="list-row">Donor toccati per ${escapeHtml(selectedTeamMember.champion_name || "-")}: ${escapeHtml(selectedMemberChanges.donorNames.join(", "))}.</div>` : ""}
        ${teamSnapshot.available ? `<div class="list-row">Snapshot team nel DB dal ${escapeHtml(teamSnapshot.saved_at || "-")} per ${escapeHtml(String(teamSnapshotSummary.champions || 0))} campioni.</div>` : '<div class="list-row">Il bottone Snapshot Team salva nel DB la configurazione corrente dei campioni toccati dal piano.</div>'}
        ${lastRestore.available ? `<div class="list-row">Ultimo equip salvato automaticamente dal ${escapeHtml(lastRestore.saved_at || "-")}.</div>` : '<div class="list-row">Prima di ogni equip salvo automaticamente i campioni toccati per poterli ripristinare.</div>'}
        <div class="list-row">Flusso consigliato: invio da web, conferma nel gioco, poi bottone "Confermato In Game -> Riallinea".</div>
        ${state.saveSnapshotResult ? `<div class="list-row">Snapshot team aggiornato: ${escapeHtml(String(saveSnapshotSummary.champions || 0))} campioni e ${escapeHtml(String(saveSnapshotSummary.artifacts || 0))} pezzi.</div>` : ""}
      </div>
      <div class="build-section">
        <h3>Per Campione</h3>
        <div class="list-block">
          ${memberBlocks.map((block) => `
            <div class="list-row">
              <strong>${escapeHtml(block.member_name || "-")}</strong>
              <div class="subtext">
                ${escapeHtml(block.build_label || "Build")}
                | azioni ${escapeHtml(String(block.action_count || 0))}
                | swap ${escapeHtml(String(block.swap_count || 0))}
                | liberi ${escapeHtml(String(block.free_equip_count || 0))}
                | pronti ${escapeHtml(String(block.ready_count || 0))}
              </div>
            </div>
          `).join("") || '<div class="empty">Nessun blocco membro disponibile.</div>'}
        </div>
      </div>
      <div class="build-section">
        <h3>Prime Azioni</h3>
        <div class="list-block">
          ${previewSteps.map((step) => `
            <div class="list-row">
              <strong>${escapeHtml(String(step.step || 0))}. ${escapeHtml(step.action === "swap" ? "Sposta" : "Monta")}</strong>
              <div class="subtext">
                ${escapeHtml(step.member_name || "-")} | ${escapeHtml(displaySlotName(step.slot || "slot"))} | #${escapeHtml(step.item_id || "")}
                ${step.source_name ? ` | da ${escapeHtml(step.source_name)}` : " | dal magazzino"}
              </div>
            </div>
          `).join("") || '<div class="empty">Nessuna azione necessaria: team gia pronto.</div>'}
        </div>
      </div>
      ${renderBridgeExecutionCard("Ultimo Equip Eseguito", state.equipInGameResult)}
      ${renderBridgeExecutionCard("Ultimo Ripristino", state.restoreResult)}
    </div>
  `;
}

function renderBridgeExecutionCard(title, payload) {
  if (!payload) return "";
  const summary = payload.summary || {};
  const members = payload.members || [];
  return `
    <div class="build-section">
      <h3>${escapeHtml(title)}</h3>
      <div class="summary compact-summary">
        ${metricCard("Completati", `${formatNumber(summary.members_succeeded || 0, 0)}/${formatNumber(summary.members_requested || 0, 0)}`, `${formatNumber(summary.members_failed || 0, 0)} errori`)}
        ${metricCard("Pezzi", formatNumber(summary.total_artifacts_requested || 0, 0), "Richiesti al bridge")}
        ${metricCard("Tempo", formatDurationMs(summary.duration_ms), "Durata chiamata")}
      </div>
      <div class="list-block">
        ${members.map((member) => `
          <div class="list-row">
            <strong>${escapeHtml(member.champion_name || member.champ_id || "-")}</strong>
            <div class="subtext">
              ${(member.result?.ok ? "OK" : "Errore")}
              | pezzi ${escapeHtml(String(member.artifact_count || (member.artifact_ids || []).length || 0))}
              | champ ${escapeHtml(member.champ_id || "-")}
            </div>
          </div>
        `).join("") || '<div class="empty">Nessun campione coinvolto.</div>'}
      </div>
    </div>
  `;
}

async function equipTeamMemberInGame(championName) {
  const member = getTeamLoadoutMember(championName);
  if (!member) {
    setStatus("Il campione scelto non fa parte del team optimizer corrente.", true);
    return;
  }
  const hasChanges = (member.items || []).some((item) => String(item?.source_kind || "").toLowerCase() !== "current");
  if (!hasChanges) {
    setStatus(`${member.champion_name} e gia pronto: nessun pezzo da cambiare in game.`, true);
    return;
  }
  state.selectedChampion = member.champion_name;
  state.equipInGameLoading = true;
  state.equipInGameResult = null;
  renderRoster();
  renderDetails();
  setStatus(`Invio equip a RAID per ${member.champion_name}...`);
  try {
    const payload = await fetchJson("/api/team-optimizer-equip-member", {
      method: "POST",
      timeoutMs: 30000,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        boss: state.selectedBoss,
        level: state.selectedLevel,
        affinity: state.selectedAffinity,
        source: state.selectedSource,
        champion_name: member.champion_name,
        champ_id: member.champ_id,
      }),
    });
    state.equipInGameResult = payload;
    if (payload.restore_snapshot) {
      state.snapshotStatus = state.snapshotStatus || {};
      state.snapshotStatus.last_restore = {
        available: true,
        ...payload.restore_snapshot,
      };
    }
    setStatus(`Richiesta equip inviata per ${member.champion_name}. Conferma in RAID e poi usa il riallineamento dal game.`);
  } catch (error) {
    setStatus(error.message || "Impossibile equipaggiare il campione selezionato.", true);
  } finally {
    state.equipInGameLoading = false;
    renderDetails();
  }
}

function renderTeamOptimizerSimulationCard() {
  if (state.selectedBoss !== "demon_lord") return "";
  if (state.optimizerSimulationLoading) {
    return `
      <div class="card">
        <h3>Simulazione Opening</h3>
        <div class="empty">Aggiornamento simulazione in corso...</div>
      </div>
    `;
  }
  if (!state.optimizerSimulation?.simulation) {
    return `
      <div class="card">
        <h3>Simulazione Opening</h3>
        <div class="empty">Nessuna simulazione disponibile per il team corrente.</div>
      </div>
    `;
  }
  const simulation = state.optimizerSimulation.simulation || {};
  const summary = simulation.summary || {};
  const preferences = state.optimizerSimulation.preferences || {};
  const defenseUptime = Math.max(
    Number(summary.increase_def_uptime_pct || 0),
    Number(summary.ally_protect_uptime_pct || 0),
    Number(summary.counterattack_uptime_pct || 0),
  );
  return `
    <div class="card">
      <h3>Simulazione Opening</h3>
      <div class="summary compact-summary">
        ${metricCard("Dec ATK", `${formatNumber(summary.decrease_attack_uptime_pct || 0, 0)}%`, "Copertura sui primi turni boss")}
        ${metricCard("Stun Bloccati", `${formatNumber(summary.blocked_stuns_pct || 0, 0)}%`, `${formatNumber(summary.stun_turns || 0, 0)} stun letti`)}
        ${metricCard("Difesa", `${formatNumber(defenseUptime, 0)}%`, "Best di Increase DEF / Ally Protect / CA")}
        ${metricCard("Poison", formatNumber(summary.avg_poison_stacks || 0, 1), `${formatNumber(summary.boss_turns || 0, 0)} turni boss`)}
      </div>
      <div class="list-block">
        ${(state.report?.selected_team || []).map((member) => `
          <div class="list-row">
            <strong>${escapeHtml(member.champion_name || "-")}</strong>
            <div class="subtext">Opening: ${escapeHtml(preferences[member.champion_name] || "AUTO")}</div>
          </div>
        `).join("")}
        ${(summary.warnings || []).map((warning) => `<div class="list-row">${escapeHtml(warning)}</div>`).join("") || '<div class="list-row">Nessuna rottura evidente nella finestra breve simulata.</div>'}
        <div class="list-row">Nota: questa preview aiuta su opener e coverage, ma non modella ancora HP reali, cure effettive e danno completo della fight.</div>
      </div>
    </div>
  `;
}

function renderTeamMemberWorkspaceCard(candidate, index) {
  const member = getTeamLoadoutMember(candidate?.champion_name);
  const changeSummary = member ? getMemberChangeSummary(member) : { changedItems: [], borrowedItems: [], inventoryItems: [], donorNames: [] };
  const hasChanges = changeSummary.changedItems.length > 0;
  const hasConflicts = !!member?.conflict_item_ids?.length;
  const isFocused = state.selectedChampion === candidate?.champion_name;
  const openerPreference = getMemberOpenerPreference(candidate?.champion_name);
  const selectedOpenerLabel = openerPreference === "AUTO"
    ? "Auto"
    : (openerPreference === "NONE" ? "Nessun opener forzato" : openerPreference);
  return `
    <div class="card optimizer-member-workspace ${isFocused ? "optimizer-member-workspace-active" : ""}">
      <div class="detail-hero">
        <div>
          <h3>${escapeHtml(`${index + 1}. ${candidate?.champion_name || "-"}`)}</h3>
          <div class="detail-meta">
            <span class="pill gold">Score ${formatNumber(candidate?.score, 1)}</span>
            <span class="pill">${escapeHtml(candidate?.default_build || "n/d")}</span>
            <span class="pill ${hasConflicts ? "warn" : (hasChanges ? "ok" : "")}">${hasConflicts ? "Conflitti" : (hasChanges ? `${changeSummary.changedItems.length} cambi` : "Gia pronto")}</span>
            ${renderStatReliabilityPill(candidate)}
            ${(candidate?.roles || []).slice(0, 4).map((role) => `<span class="pill">${escapeHtml(role)}</span>`).join("")}
          </div>
        </div>
        <div class="action-row">
          <button class="secondary optimizer-member-focus-btn" data-name="${escapeHtml(candidate?.champion_name || "")}">${isFocused ? "Dettaglio Aperto" : "Apri Dettaglio"}</button>
          <button class="primary optimizer-member-equip-btn" data-name="${escapeHtml(candidate?.champion_name || "")}" ${state.equipInGameLoading || !hasChanges || hasConflicts ? "disabled" : ""}>${state.equipInGameLoading && isFocused ? "Invio In Corso..." : "Equipaggia"}</button>
        </div>
      </div>
      <div class="grid">
        <div class="card">
          <h3>Gear</h3>
          <div class="kv single-column">
            <div class="kv-row"><span>Swap</span><span>${formatNumber(member?.swap_count || 0, 0)}</span></div>
            <div class="kv-row"><span>Inventario</span><span>${formatNumber(member?.inventory_items || 0, 0)}</span></div>
            <div class="kv-row"><span>Borrowed</span><span>${formatNumber(member?.borrowed_items || 0, 0)}</span></div>
            <div class="kv-row"><span>Conflitti</span><span>${formatNumber(member?.conflict_item_ids?.length || 0, 0)}</span></div>
          </div>
          <div class="list-block">
            ${hasChanges ? changeSummary.changedItems.map((item) => `
              <div class="list-row">
                <strong>${escapeHtml(displaySlotName(item.slot || "slot"))}</strong>
                <div class="subtext">#${escapeHtml(item.item_id || "-")} | ${escapeHtml(displaySetName(item.set_name || "No Set"))} | ${escapeHtml(displayItemSourceLabel(item))}</div>
              </div>
            `).join("") : '<div class="list-row">Nessun pezzo da cambiare per questa proposta.</div>'}
            ${changeSummary.donorNames.length ? `<div class="list-row">Donor toccati: ${escapeHtml(changeSummary.donorNames.join(", "))}.</div>` : ""}
            ${hasConflicts ? `<div class="list-row">Pezzi in conflitto: ${escapeHtml((member?.conflict_item_ids || []).join(", "))}.</div>` : ""}
          </div>
        </div>
        <div class="card">
          <h3>Skill E Opening</h3>
          ${state.selectedBoss === "demon_lord" ? `
            <div class="field">
              <label>Opening iniziale</label>
              <select class="optimizer-opener-select" data-name="${escapeHtml(candidate?.champion_name || "")}">
                <option value="AUTO" ${openerPreference === "AUTO" ? "selected" : ""}>Auto</option>
                <option value="A1" ${openerPreference === "A1" ? "selected" : ""}>Apri con A1</option>
                <option value="A2" ${openerPreference === "A2" ? "selected" : ""}>Apri con A2</option>
                <option value="A3" ${openerPreference === "A3" ? "selected" : ""}>Apri con A3</option>
                <option value="A4" ${openerPreference === "A4" ? "selected" : ""}>Apri con A4</option>
                <option value="NONE" ${openerPreference === "NONE" ? "selected" : ""}>Non forzare opener</option>
              </select>
            </div>
            <div class="subtext">Preferenza attiva: ${escapeHtml(selectedOpenerLabel)}. Serve per sfasare la rotazione iniziale del team.</div>
          ` : `<div class="subtext">Le preferenze opener sono attive solo per Clan Boss.</div>`}
          <div class="list-block">
            ${(candidate?.skills || []).map((skill) => `
              <div class="list-row">
                <strong>${escapeHtml(skill.slot || "?")} | ${escapeHtml(skill.skill_name || skill.name || skill.slot || "Skill")}</strong>
                <div class="subtext">CD ${escapeHtml(String(skill.booked_cooldown ?? skill.cooldown ?? "-"))}${openerPreference === String(skill.slot || "").toUpperCase() ? " | opener scelto" : ""}</div>
              </div>
            `).join("") || '<div class="list-row">Nessuna skill strutturata disponibile nei dati correnti.</div>'}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderTeamWorkspaceCard() {
  const team = state.report?.selected_team || [];
  if (!team.length) {
    return '<div class="card"><h3>Workspace Team</h3><div class="empty">Nessun team selezionato.</div></div>';
  }
  return `
    <div class="card">
      <h3>Workspace Team</h3>
      <div class="subtext">Ogni campione ha il suo blocco operativo: gear da montare, donor toccati e preferenza opener per la rotazione iniziale.</div>
      <div class="stack optimizer-team-workspace">
        ${team.map((candidate, index) => renderTeamMemberWorkspaceCard(candidate, index)).join("")}
      </div>
    </div>
  `;
}

function renderSelectedMemberActionCard(candidate) {
  const member = (state.teamLoadout?.team || []).find((item) => item.champion_name === candidate?.champion_name);
  if (!member) return "";
  const changeSummary = getMemberChangeSummary(member);
  const hasChanges = changeSummary.changedItems.length > 0;
  const hasConflicts = !!member.conflict_item_ids?.length;
  return `
    <div class="card">
      <h3>Azioni In Game</h3>
      <div class="action-row">
        <button id="optimizerEquipSelectedMemberBtn" class="secondary" ${state.equipInGameLoading || !hasChanges || hasConflicts ? "disabled" : ""}>${state.equipInGameLoading ? "Invio In Corso..." : "Equipaggia Solo Questo Campione"}</button>
        <span class="pill ${hasConflicts ? "warn" : (hasChanges ? "ok" : "")}">${hasConflicts ? "Conflitto" : (hasChanges ? "Da cambiare" : "Gia pronto")}</span>
      </div>
      <div class="subtext">${hasConflicts
        ? `${escapeHtml(candidate.champion_name || "-")} condivide pezzi con altri membri del team proposto. Risolvi prima i conflitti nel loadout, altrimenti finisci per spogliare un altro campione.`
        : (hasChanges
        ? `Questo invia solo ${escapeHtml(candidate.champion_name || "-")} al bridge locale. Prima dell'invio vedi donor e pezzi coinvolti.`
        : `${escapeHtml(candidate.champion_name || "-")} risulta gia allineato alla build proposta, quindi non parte nessun cambio in game.`)}</div>
      ${hasConflicts ? `
        <div class="list-block">
          <div class="list-row">Pezzi in conflitto: ${escapeHtml((member.conflict_item_ids || []).join(", "))}.</div>
        </div>
      ` : ""}
      ${hasChanges ? `
        <div class="list-block">
          <div class="list-row">${escapeHtml(candidate.champion_name || "-")} richiede ${escapeHtml(String(changeSummary.changedItems.length))} cambi: ${escapeHtml(String(changeSummary.borrowedItems.length))} swap e ${escapeHtml(String(changeSummary.inventoryItems.length))} pezzi da magazzino.</div>
          ${changeSummary.donorNames.length ? `<div class="list-row">Donor coinvolti: ${escapeHtml(changeSummary.donorNames.join(", "))}.</div>` : '<div class="list-row">Nessun donor coinvolto: arrivano solo pezzi liberi da magazzino.</div>'}
          ${changeSummary.changedItems.map((item) => `
            <div class="list-row">
              <strong>${escapeHtml(displaySlotName(item.slot || "slot"))}</strong>
              <div class="subtext">
                #${escapeHtml(item.item_id || "-")}
                | ${escapeHtml(displayItemSourceLabel(item))}
                | ${escapeHtml(displaySetName(item.set_name || "No Set"))}
              </div>
            </div>
          `).join("")}
        </div>
      ` : ""}
    </div>
  `;
}

function buildLocalBridgePlanFromLoadout(payload) {
  const team = payload?.team || [];
  const conflicts = payload?.conflicts || [];
  const memberBlocks = [];
  const steps = [];
  const sourceOwners = new Set();
  let readyCount = 0;
  let freeEquipCount = 0;
  let swapCount = 0;
  let stepNumber = 1;

  team.forEach((member) => {
    const items = member?.items || [];
    const blockSteps = [];
    let memberReadyCount = 0;
    let memberFreeEquipCount = 0;
    let memberSwapCount = 0;

    items.forEach((item) => {
      const sourceKind = String(item?.source_kind || "").toLowerCase();
      if (sourceKind === "current") {
        readyCount += 1;
        memberReadyCount += 1;
        return;
      }

      const action = sourceKind === "borrowed" ? "swap" : "equip_free";
      const sourceName = item?.owner_name || item?.equipped_by || "";
      if (action === "swap") {
        swapCount += 1;
        memberSwapCount += 1;
        if (sourceName) sourceOwners.add(String(sourceName));
      } else {
        freeEquipCount += 1;
        memberFreeEquipCount += 1;
      }

      const step = {
        step: stepNumber,
        action,
        member_name: member?.champion_name || "",
        build_label: member?.build_label || member?.default_build || "",
        slot: item?.slot || "",
        item_id: item?.item_id || "",
        source_name: sourceName,
      };
      steps.push(step);
      blockSteps.push(step);
      stepNumber += 1;
    });

    memberBlocks.push({
      member_name: member?.champion_name || "",
      build_label: member?.build_label || member?.default_build || "",
      ready_count: memberReadyCount,
      free_equip_count: memberFreeEquipCount,
      swap_count: memberSwapCount,
      action_count: blockSteps.length,
      steps: blockSteps,
    });
  });

  const notes = [];
  if (!steps.length) {
    notes.push("Team gia pronto: i pezzi consigliati risultano gia indossati dai campioni target.");
  } else {
    notes.push(`${steps.length} azioni manuali: ${swapCount} swap da altri campioni e ${freeEquipCount} pezzi liberi da montare.`);
    if (sourceOwners.size) {
      notes.push(`Campioni toccati dagli swap: ${Array.from(sourceOwners).sort().join(", ")}.`);
    }
  }
  if (conflicts.length) {
    notes.push("Conflitti presenti nel planner: alcuni pezzi sono richiesti da piu campioni del team.");
  }

  return {
    target: payload?.target || {},
    summary: payload?.summary || {},
    plan: {
      provider: "local_manual",
      total_items: team.reduce((sum, member) => sum + ((member?.items || []).length), 0),
      ready_count: readyCount,
      action_count: steps.length,
      free_equip_count: freeEquipCount,
      swap_count: swapCount,
      source_owners: Array.from(sourceOwners).sort(),
      notes,
      member_blocks: memberBlocks,
      steps,
      conflicts,
    },
  };
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
          <h3>Stats Chiave</h3>
          <div class="kv single-column">
            <div class="kv-row"><span>SPD</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.spd, 0)}</span></div>
            <div class="kv-row"><span>ACC</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.acc, 0)}</span></div>
            <div class="kv-row"><span>HP</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.hp, 0)}</span></div>
            <div class="kv-row"><span>DEF</span><span>${candidate.stat_reliability?.source === "raw" ? "" : "~"}${formatNumber(stats.def, 0)}</span></div>
          </div>
        </div>
        <div class="card">
          <h3>Storico Campione</h3>
          <div class="kv single-column">
            <div class="kv-row"><span>Run viste</span><span>${formatNumber(evidence.run_count, 0)}</span></div>
            <div class="kv-row"><span>Avg damage</span><span>${formatNumber(evidence.avg_damage_done, 0)}</span></div>
            <div class="kv-row"><span>Avg healing</span><span>${formatNumber(evidence.avg_healing_done, 0)}</span></div>
            <div class="kv-row"><span>Stats</span><span>${escapeHtml(candidate.stat_reliability?.source === "raw" ? "raw" : "stimate")}</span></div>
          </div>
        </div>
      </div>
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
      ${renderDecisionCard()}
    </div>
    <div class="grid">
      ${renderWarningsCard()}
      ${renderQuickBenchCard()}
    </div>
    ${renderCompactGearCard()}
    ${renderCandidateDetail()}
  `;
  detailsEl.querySelectorAll(".optimizer-member-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedChampion = button.dataset.name || null;
      renderRoster();
      renderDetails();
    });
  });
  const equipBtn = detailsEl.querySelector("#optimizerEquipInGameBtn");
  if (equipBtn && !equipBtn.disabled) {
    equipBtn.addEventListener("click", async () => {
      if (!state.selectedChampion) {
        setStatus("Seleziona un campione del team prima di inviare l'equip.", true);
        return;
      }
      await equipTeamMemberInGame(state.selectedChampion);
    });
  }
  const equipSelectedBtn = detailsEl.querySelector("#optimizerEquipSelectedMemberBtn");
  if (equipSelectedBtn && !equipSelectedBtn.disabled) {
    equipSelectedBtn.addEventListener("click", async () => {
      if (!state.selectedChampion) {
        setStatus("Il campione selezionato non fa parte del team optimizer corrente.", true);
        return;
      }
      await equipTeamMemberInGame(state.selectedChampion);
    });
  }
  detailsEl.querySelectorAll(".optimizer-member-focus-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedChampion = button.dataset.name || null;
      renderRoster();
      renderDetails();
    });
  });
  detailsEl.querySelectorAll(".optimizer-member-equip-btn").forEach((button) => {
    if (button.disabled) return;
    button.addEventListener("click", async () => {
      await equipTeamMemberInGame(button.dataset.name || "");
    });
  });
  detailsEl.querySelectorAll(".optimizer-opener-select").forEach((selectEl) => {
    selectEl.addEventListener("change", async () => {
      const championName = selectEl.dataset.name || "";
      setMemberOpenerPreference(championName, selectEl.value || "AUTO");
      await refreshOptimizerSimulation();
    });
  });
  const saveSnapshotBtn = detailsEl.querySelector("#optimizerSaveSnapshotBtn");
  if (saveSnapshotBtn && !saveSnapshotBtn.disabled) {
    saveSnapshotBtn.addEventListener("click", async () => {
      state.saveSnapshotLoading = true;
      state.saveSnapshotResult = null;
      renderDetails();
      setStatus("Salvataggio snapshot team nel DB in corso...");
      try {
        const payload = await fetchJson("/api/team-optimizer-save-snapshot", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            boss: state.selectedBoss,
            level: state.selectedLevel,
            affinity: state.selectedAffinity,
            source: state.selectedSource,
          }),
        });
        state.saveSnapshotResult = payload.snapshot || null;
        state.snapshotStatus = state.snapshotStatus || {};
        state.snapshotStatus.team_snapshot = payload.snapshot || null;
        const summary = payload.snapshot?.summary || {};
        setStatus(`Snapshot team salvato nel DB: ${formatNumber(summary.champions || 0, 0)} campioni e ${formatNumber(summary.artifacts || 0, 0)} pezzi.`);
      } catch (error) {
        setStatus(error.message || "Impossibile salvare lo snapshot team.", true);
      } finally {
        state.saveSnapshotLoading = false;
        renderDetails();
      }
    });
  }
  const refreshGameBtn = detailsEl.querySelector("#optimizerRefreshGameBtn");
  if (refreshGameBtn && !refreshGameBtn.disabled) {
    refreshGameBtn.addEventListener("click", async () => {
      await refreshGearAndReloadOptimizer();
    });
  }
  const restoreSnapshotBtn = detailsEl.querySelector("#optimizerRestoreSnapshotBtn");
  if (restoreSnapshotBtn && !restoreSnapshotBtn.disabled) {
    restoreSnapshotBtn.addEventListener("click", async () => {
      state.restoreLoading = true;
      state.restoreResult = null;
      renderDetails();
      setStatus("Ripristino snapshot team in corso...");
      try {
        const payload = await fetchJson("/api/team-optimizer-restore-snapshot", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            boss: state.selectedBoss,
            level: state.selectedLevel,
            affinity: state.selectedAffinity,
            source: state.selectedSource,
          }),
        });
        state.restoreResult = payload;
        const summary = payload.summary || {};
        setStatus(`Snapshot team ripristinato: ${formatNumber(summary.members_succeeded || 0, 0)}/${formatNumber(summary.members_requested || 0, 0)} campioni in ${formatDurationMs(summary.duration_ms)}.`);
      } catch (error) {
        setStatus(error.message || "Impossibile ripristinare lo snapshot team.", true);
      } finally {
        state.restoreLoading = false;
        renderDetails();
      }
    });
  }
  const restoreBtn = detailsEl.querySelector("#optimizerRestoreInGameBtn");
  if (restoreBtn && !restoreBtn.disabled) {
    restoreBtn.addEventListener("click", async () => {
      state.restoreLoading = true;
      state.restoreResult = null;
      renderDetails();
      setStatus("Ripristino ultimo equip in corso...");
      try {
        const payload = await fetchJson("/api/team-optimizer-restore-last", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        state.restoreResult = payload;
        const summary = payload.summary || {};
        setStatus(`Ripristino completato: ${formatNumber(summary.members_succeeded || 0, 0)}/${formatNumber(summary.members_requested || 0, 0)} campioni in ${formatDurationMs(summary.duration_ms)}.`);
      } catch (error) {
        setStatus(error.message || "Impossibile ripristinare l'equip precedente.", true);
      } finally {
        state.restoreLoading = false;
        renderDetails();
      }
    });
  }
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
    const query = `boss=${encodeURIComponent(state.selectedBoss)}&level=${encodeURIComponent(state.selectedLevel)}&affinity=${encodeURIComponent(state.selectedAffinity)}&source=${encodeURIComponent(state.selectedSource)}`;
    const reportPromise = fetchJson(`/api/team-optimizer?${query}`);
    const loadoutPromise = fetchJson(`/api/team-optimizer-loadout?${query}`);
    const restorePromise = fetchJson(`/api/team-optimizer-restore-status?${query}`);
    state.bossIntel = null;
    state.trainingOverview = null;
    state.teamLoadout = null;
    state.teamLoadoutError = "";
    state.localBridgePlan = null;
    state.localBridgePlanError = "";
    state.equipInGameLoading = false;
    state.equipInGameResult = null;
    state.equipQueueIndex = 0;
    state.refreshGameLoading = false;
    state.optimizerSimulation = null;
    state.optimizerSimulationLoading = false;
    state.memberOpenerPrefs = {};
    state.snapshotStatus = null;
    state.saveSnapshotLoading = false;
    state.saveSnapshotResult = null;
    state.restoreLoading = false;
    state.restoreResult = null;
    renderDetails();
    const payload = await reportPromise;
    state.targets = payload.targets || [];
    state.selectedBoss = payload.selection?.boss_key || state.selectedBoss;
    state.selectedLevel = payload.selection?.level_key || state.selectedLevel;
    state.selectedAffinity = payload.selection?.affinity || state.selectedAffinity;
    state.selectedSource = payload.selection?.recommendation_source || state.selectedSource;
    state.bossIntel = payload.boss_intel || null;
    state.report = payload.report || null;
    state.trainingOverview = payload.training_overview || null;
    renderBossSelect();
    renderAffinitySelect();
    renderLevelSelect();
    renderSourceSelect();
    const selectedStillVisible = (state.report?.candidates || []).some((item) => item.champion_name === state.selectedChampion);
    if (!selectedStillVisible && state.report?.selected_team?.length) {
      state.selectedChampion = state.report.selected_team[0].champion_name;
    }
    syncMemberOpenerPreferences();
    renderSummary();
    renderRoster();
    renderDetails();
    setStatus(`Optimizer pronto su ${state.report?.target?.boss_label || state.selectedBoss} ${state.report?.target?.level_label || state.selectedLevel}. Preparazione piano equip...`);
    try {
      state.teamLoadout = await loadoutPromise;
      try {
        state.localBridgePlan = await fetchJson(`/api/team-optimizer-local-bridge?${query}`);
        state.localBridgePlanError = "";
      } catch (bridgeError) {
        state.localBridgePlan = buildLocalBridgePlanFromLoadout(state.teamLoadout);
        state.localBridgePlanError = "";
      }
      state.snapshotStatus = await restorePromise;
      setStatus(`Optimizer e piano equip pronti su ${state.report?.target?.boss_label || state.selectedBoss} ${state.report?.target?.level_label || state.selectedLevel}.`);
    } catch (error) {
      state.teamLoadoutError = error.message || "Impossibile preparare il loadout del team.";
      state.localBridgePlanError = state.teamLoadoutError;
      setStatus(state.teamLoadoutError, true);
    }
    renderDetails();
    if (state.selectedBoss === "demon_lord" && (state.report?.selected_team || []).length) {
      await refreshOptimizerSimulation({ silent: true });
    }
  } catch (error) {
    state.report = null;
    state.bossIntel = null;
    state.trainingOverview = null;
    state.teamLoadout = null;
    state.teamLoadoutError = "";
    state.localBridgePlan = null;
    state.localBridgePlanError = "";
    state.equipInGameLoading = false;
    state.equipInGameResult = null;
    state.equipQueueIndex = 0;
    state.refreshGameLoading = false;
    state.optimizerSimulation = null;
    state.optimizerSimulationLoading = false;
    state.memberOpenerPrefs = {};
    state.snapshotStatus = null;
    state.saveSnapshotLoading = false;
    state.saveSnapshotResult = null;
    state.restoreLoading = false;
    state.restoreResult = null;
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
  renderSourceSelect();
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

sourceEl.addEventListener("change", async () => {
  state.selectedSource = sourceEl.value || "optimizer";
  await loadReport();
});

reloadBtn.addEventListener("click", async () => {
  await loadReport();
});

loadReport();
