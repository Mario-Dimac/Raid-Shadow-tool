const state = {
  bootstrap: null,
  recommendations: null,
  comparison: null,
  team: [],
  result: null,
  loading: false,
  championCache: {},
};

const rosterEl = document.getElementById("cbRoster");
const detailsEl = document.getElementById("cbDetails");
const summaryEl = document.getElementById("cbSummary");
const statusEl = document.getElementById("cbStatus");
const difficultyEl = document.getElementById("cbDifficulty");
const affinityEl = document.getElementById("cbAffinity");
const bossTurnsEl = document.getElementById("cbBossTurns");
const auraEl = document.getElementById("cbAuraSpeed");
const stunTargetEl = document.getElementById("cbStunTarget");
const useOptimizerBtn = document.getElementById("cbUseOptimizerBtn");
const useAiBtn = document.getElementById("cbUseAiBtn");
const compareBtn = document.getElementById("cbCompareBtn");
const resetBtn = document.getElementById("cbResetBtn");
const simulateBtn = document.getElementById("cbSimulateBtn");

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

function formatNumber(value, digits = 0) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toLocaleString("it-IT", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
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

function makeBlankEffect() {
  return {
    effect_type: "",
    target: "boss",
    duration: 0,
    value: 0,
    stacks: 1,
  };
}

function makeBlankSkill(slot, priority) {
  return {
    slot,
    skill_name: slot,
    cooldown: slot === "A1" ? 0 : 3,
    priority,
    use_as_opener: slot !== "A1",
    enabled: true,
    effects: [makeBlankEffect(), makeBlankEffect()],
  };
}

function normalizeSkill(rawSkill, fallbackSlot, fallbackPriority) {
  const effects = [...(rawSkill?.effects || [])];
  while (effects.length < 2) effects.push(makeBlankEffect());
  return {
    slot: rawSkill?.slot || fallbackSlot,
    skill_name: rawSkill?.skill_name || fallbackSlot,
    cooldown: Number(rawSkill?.cooldown ?? (fallbackSlot === "A1" ? 0 : 3)),
    priority: Number(rawSkill?.priority ?? fallbackPriority),
    use_as_opener: Boolean(rawSkill?.use_as_opener ?? (fallbackSlot !== "A1")),
    enabled: rawSkill?.enabled !== false,
    effects: effects.slice(0, 2).map((effect) => ({
      effect_type: effect?.effect_type || "",
      target: effect?.target || "boss",
      duration: Number(effect?.duration ?? 0),
      value: Number(effect?.value ?? 0),
      stacks: Number(effect?.stacks ?? 1),
    })),
  };
}

function normalizeMember(rawMember, slotIndex) {
  const rawSkills = rawMember?.skills || [];
  return {
    slot_index: slotIndex,
    champ_id: rawMember?.champ_id || "",
    champion_name: rawMember?.champion_name || "",
    speed: Number(rawMember?.speed ?? 170),
    notes: rawMember?.notes || "",
    preset_key: rawMember?.preset_key || "blank",
    skills: [
      normalizeSkill(rawSkills[0], "A1", 100),
      normalizeSkill(rawSkills[1], "A2", 240),
      normalizeSkill(rawSkills[2], "A3", 320),
      normalizeSkill(rawSkills[3], "A4", 160),
    ],
  };
}

function effectOptionsHtml(selectedValue) {
  const library = state.bootstrap?.effect_library || [];
  return [
    '<option value="">Nessun effetto</option>',
    ...library.map((item) => `<option value="${escapeHtml(item.key)}" ${item.key === selectedValue ? "selected" : ""}>${escapeHtml(item.label)}</option>`),
  ].join("");
}

function targetOptionsHtml(selectedValue) {
  const options = [
    { key: "boss", label: "Boss" },
    { key: "all_allies", label: "Team" },
    { key: "self", label: "Self" },
  ];
  return options.map((item) => `<option value="${escapeHtml(item.key)}" ${item.key === selectedValue ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("");
}

function rosterOptionsHtml(selectedName) {
  const champions = state.bootstrap?.champions || [];
  return [
    '<option value="">Seleziona campione</option>',
    ...champions.map((champion) => `<option value="${escapeHtml(champion.champion_name)}" ${champion.champion_name === selectedName ? "selected" : ""}>${escapeHtml(champion.champion_name)}</option>`),
  ].join("");
}

function presetOptionsHtml(selectedKey = "blank") {
  const presets = state.bootstrap?.team_presets || [];
  return presets.map((preset) => `<option value="${escapeHtml(preset.key)}" ${preset.key === selectedKey ? "selected" : ""}>${escapeHtml(preset.label)}</option>`).join("");
}

function renderSummary() {
  const result = state.result;
  if (!result?.ok) {
    summaryEl.innerHTML = [
      metricCard("Boss", difficultyEl.options[difficultyEl.selectedIndex]?.text || "Clan Boss", affinityEl.options[affinityEl.selectedIndex]?.text || ""),
      metricCard("Turni Boss", bossTurnsEl.value || "12", "Finestra simulata"),
      metricCard("SPD Aura", `${formatNumber(auraEl.value || 0, 1)}%`, "Bonus globale opzionale"),
      metricCard("Stun Target", stunTargetEl.options[stunTargetEl.selectedIndex]?.text || "Slot 5", "Target euristico del boss"),
    ].join("");
    return;
  }
  const summary = result.summary || {};
  summaryEl.innerHTML = [
    metricCard("Boss Turni", summary.boss_turns || 0, `${formatNumber(summary.elapsed_seconds || 0, 1)}s simulati`),
    metricCard("Dec ATK", `${formatNumber(summary.decrease_attack_uptime_pct || 0, 1)}%`, "Uptime sui colpi boss"),
    metricCard("Increase DEF", `${formatNumber(summary.increase_def_uptime_pct || 0, 1)}%`, "Copertura media team"),
    metricCard("Stun Bloccati", `${formatNumber(summary.blocked_stuns_pct || 0, 1)}%`, `${summary.stun_turns || 0} stun simulati`),
  ].join("");
}

function renderRoster() {
  rosterEl.innerHTML = state.team.map((member, memberIndex) => `
    <div class="champ-row sim-editor-card">
      <div class="champ-topline">
        <div class="champ-name">Slot ${member.slot_index}</div>
        <div class="pillbar">
          <span class="pill gold">${escapeHtml(member.champion_name || "Vuoto")}</span>
          <span class="pill">${escapeHtml(`SPD ${formatNumber(member.speed, 0)}`)}</span>
        </div>
      </div>
      <div class="grid-2">
        <label class="field">
          <span class="subtext">Campione</span>
          <select data-member-index="${memberIndex}" data-field="champion_name">${rosterOptionsHtml(member.champion_name)}</select>
        </label>
        <label class="field">
          <span class="subtext">Speed</span>
          <input type="number" min="1" step="0.1" value="${escapeHtml(member.speed)}" data-member-index="${memberIndex}" data-field="speed">
        </label>
      </div>
      <div class="grid-2">
        <label class="field">
          <span class="subtext">Template rapido</span>
          <select data-member-index="${memberIndex}" data-template-select="1">${presetOptionsHtml(member.preset_key || "blank")}</select>
        </label>
        <button class="ghost" data-member-index="${memberIndex}" data-apply-template="1">Applica Template</button>
      </div>
      <label class="field">
        <span class="subtext">Note</span>
        <input type="text" value="${escapeHtml(member.notes || "")}" placeholder="Esempio: deve coprire lo stun, o va in 4:3" data-member-index="${memberIndex}" data-field="notes">
      </label>
      <div class="sim-skill-list">
        ${member.skills.map((skill, skillIndex) => `
          <div class="sim-skill-card">
            <div class="pillbar">
              <span class="pill gold">${escapeHtml(skill.slot)}</span>
              <span class="pill">${escapeHtml(`prio ${skill.priority}`)}</span>
            </div>
            <div class="grid-4">
              <label class="field">
                <span class="subtext">Nome skill</span>
                <input type="text" value="${escapeHtml(skill.skill_name)}" data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-skill-field="skill_name">
              </label>
              <label class="field">
                <span class="subtext">Cooldown</span>
                <input type="number" min="0" step="1" value="${escapeHtml(skill.cooldown)}" data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-skill-field="cooldown">
              </label>
              <label class="field">
                <span class="subtext">Priorita</span>
                <input type="number" min="0" step="10" value="${escapeHtml(skill.priority)}" data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-skill-field="priority">
              </label>
              <label class="field checkbox-line">
                <span class="subtext">Opener</span>
                <input type="checkbox" ${skill.use_as_opener ? "checked" : ""} data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-skill-field="use_as_opener">
              </label>
            </div>
            ${skill.effects.map((effect, effectIndex) => `
              <div class="grid-5 sim-effect-row">
                <label class="field">
                  <span class="subtext">Effetto</span>
                  <select data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-effect-index="${effectIndex}" data-effect-field="effect_type">${effectOptionsHtml(effect.effect_type)}</select>
                </label>
                <label class="field">
                  <span class="subtext">Target</span>
                  <select data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-effect-index="${effectIndex}" data-effect-field="target">${targetOptionsHtml(effect.target)}</select>
                </label>
                <label class="field">
                  <span class="subtext">Durata</span>
                  <input type="number" min="0" step="1" value="${escapeHtml(effect.duration)}" data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-effect-index="${effectIndex}" data-effect-field="duration">
                </label>
                <label class="field">
                  <span class="subtext">Valore %</span>
                  <input type="number" min="0" step="1" value="${escapeHtml(effect.value)}" data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-effect-index="${effectIndex}" data-effect-field="value">
                </label>
                <label class="field">
                  <span class="subtext">Stack</span>
                  <input type="number" min="1" step="1" value="${escapeHtml(effect.stacks)}" data-member-index="${memberIndex}" data-skill-index="${skillIndex}" data-effect-index="${effectIndex}" data-effect-field="stacks">
                </label>
              </div>
            `).join("")}
          </div>
        `).join("")}
      </div>
    </div>
  `).join("");

  rosterEl.querySelectorAll("[data-field]").forEach((input) => {
    input.addEventListener("change", async () => {
      const member = state.team[Number(input.dataset.memberIndex)];
      const field = input.dataset.field;
      if (field === "champion_name") {
        member.champion_name = input.value || "";
        const rosterRow = (state.bootstrap?.champions || []).find((item) => item.champion_name === member.champion_name);
        member.champ_id = rosterRow?.champ_id || "";
        if (member.champion_name) {
          await hydrateChampion(member);
        }
        renderRoster();
        return;
      }
      member[field] = field === "speed" ? Number(input.value || 0) : input.value || "";
      renderSummary();
    });
  });

  rosterEl.querySelectorAll("[data-skill-field]").forEach((input) => {
    input.addEventListener("change", () => {
      const skill = state.team[Number(input.dataset.memberIndex)].skills[Number(input.dataset.skillIndex)];
      const field = input.dataset.skillField;
      skill[field] = input.type === "checkbox" ? input.checked : (field === "cooldown" || field === "priority" ? Number(input.value || 0) : input.value || "");
    });
  });

  rosterEl.querySelectorAll("[data-effect-field]").forEach((input) => {
    input.addEventListener("change", () => {
      const effect = state.team[Number(input.dataset.memberIndex)].skills[Number(input.dataset.skillIndex)].effects[Number(input.dataset.effectIndex)];
      const field = input.dataset.effectField;
      effect[field] = ["duration", "value", "stacks"].includes(field) ? Number(input.value || 0) : (input.value || "");
    });
  });

  rosterEl.querySelectorAll("[data-template-select]").forEach((select) => {
    select.addEventListener("change", () => {
      const member = state.team[Number(select.dataset.memberIndex)];
      member.preset_key = select.value || "blank";
    });
  });

  rosterEl.querySelectorAll("[data-apply-template]").forEach((button) => {
    button.addEventListener("click", () => {
      const memberIndex = Number(button.dataset.memberIndex);
      const select = rosterEl.querySelector(`[data-member-index="${memberIndex}"][data-template-select="1"]`);
      applyPreset(memberIndex, select?.value || "blank");
      renderRoster();
    });
  });
}

function renderResults() {
  if (!state.result && !state.comparison) {
    detailsEl.innerHTML = `
      <div class="details-grid">
        <div class="list-card">
          <h3>Come si Usa</h3>
          <div class="list-row">
            <strong>1. Imposta il team</strong>
            <span class="subtext">Scegli i 5 campioni, correggi la SPD reale e applica un template rapido solo come punto di partenza.</span>
          </div>
          <div class="list-row">
            <strong>2. Descrivi la rotazione</strong>
            <span class="subtext">Per ogni skill indica cooldown, priorita e gli effetti che contano davvero in Clan Boss: Block Debuffs, Increase DEF, Ally Protect, Counterattack, poison, HP Burn.</span>
          </div>
          <div class="list-row">
            <strong>3. Leggi il risultato</strong>
            <span class="subtext">La pagina ti dice chi prende lo stun, dove manca Decrease ATK, dove cade la copertura difensiva e quando un campione salta il turno.</span>
          </div>
        </div>
        <div class="list-card">
          <h3>Cosa Modella</h3>
          <div class="list-row">
            <strong>Gia incluso</strong>
            <span class="subtext">Ordine turni, boss cycle AoE1/AoE2/Stun, speed aura, Increase SPD, Block Debuffs, Increase DEF, Ally Protect, Counterattack, Unkillable, poison, HP Burn e stun target scelto da te.</span>
          </div>
          <div class="list-row">
            <strong>Non ancora completo</strong>
            <span class="subtext">Damage reale, AI avanzata, affinity targeting, set e mastery. Questa versione serve per trovare una tune leggibile e capire se la finestra buff/debuff regge.</span>
          </div>
        </div>
      </div>
    `;
    return;
  }
  if (state.comparison) {
    const heuristic = state.comparison.heuristic || {};
    const ai = state.comparison.ai || {};
    detailsEl.innerHTML = `
      <div class="comparison-grid">
        ${renderComparisonCard("Consiglio CB Forge", heuristic)}
        ${renderComparisonCard("Consiglio AI", ai)}
      </div>
      ${state.result ? renderSingleResultBlock(state.result) : ""}
    `;
    return;
  }
  detailsEl.innerHTML = renderSingleResultBlock(state.result);
}

function renderComparisonCard(label, payload) {
  if (!payload?.available) {
    return `
      <div class="list-card">
        <h3>${escapeHtml(label)}</h3>
        ${(payload?.warnings || ["Non disponibile."]).map((warning) => `<div class="list-row warn">${escapeHtml(warning)}</div>`).join("")}
      </div>
    `;
  }
  const summary = payload?.simulation?.summary || {};
  const names = (payload?.team_names || []).filter(Boolean).join(" / ");
  const notes = [...(payload?.notes || []), ...(payload?.warnings || [])];
  return `
    <div class="list-card">
      <h3>${escapeHtml(label)}</h3>
      <div class="list-row">
        <strong>${escapeHtml(names || "-")}</strong>
        <span class="subtext">Dec ATK ${escapeHtml(formatNumber(summary.decrease_attack_uptime_pct || 0, 1))}% | Increase DEF ${escapeHtml(formatNumber(summary.increase_def_uptime_pct || 0, 1))}% | Stun bloccati ${escapeHtml(formatNumber(summary.blocked_stuns_pct || 0, 1))}%</span>
        ${payload?.predicted_total_damage ? `<span class="subtext">AI predicted damage: ${escapeHtml(formatNumber(payload.predicted_total_damage, 0))}</span>` : ""}
      </div>
      ${notes.map((note) => `<div class="list-row">${escapeHtml(note)}</div>`).join("")}
    </div>
  `;
}

function renderSingleResultBlock(result) {
  if (!result) return "";
  if (!result.ok) {
    return `
      <div class="list-card">
        <h3>Errori di Configurazione</h3>
        ${(result.errors || []).map((error) => `<div class="list-row warn">${escapeHtml(error)}</div>`).join("")}
      </div>
    `;
  }
  const summary = result.summary || {};
  const bossTurns = result.boss_turns || [];
  const timeline = result.timeline || [];
  const teamState = result.team_state || [];
  return `
    <div class="details-grid">
      <div class="list-card">
        <h3>Lettura Rapida</h3>
        ${(summary.warnings || []).map((warning) => `<div class="list-row">${escapeHtml(warning)}</div>`).join("")}
      </div>
      <div class="list-card">
        <h3>Stato Team</h3>
        ${teamState.map((member) => `
          <div class="list-row">
            <strong>${escapeHtml(member.champion_name || `Slot ${member.slot_index}`)}</strong>
            <span class="subtext">SPD ${escapeHtml(formatNumber(member.speed, 0))} | turni ${escapeHtml(String(member.turns_taken || 0))} | persi ${escapeHtml(String(member.skipped_turns || 0))}</span>
          </div>
        `).join("")}
      </div>
      <div class="list-card">
        <h3>Turni Boss</h3>
        ${bossTurns.map((row) => `
          <div class="list-row">
            <strong>T${escapeHtml(String(row.boss_turn))} ${escapeHtml(row.skill_label || "-")}</strong>
            <span class="subtext">Dec ATK ${row.decrease_attack_active ? "ok" : "manca"} | Increase DEF ${escapeHtml(formatNumber((row.increase_def_coverage / Math.max(1, row.coverage_team_size)) * 100, 0))}% | Ally Protect ${escapeHtml(formatNumber((row.ally_protect_coverage / Math.max(1, row.coverage_team_size)) * 100, 0))}% | Poison ${escapeHtml(String(row.poison_stacks || 0))}</span>
            ${row.notes?.length ? `<span class="subtext">${escapeHtml(row.notes.join(" | "))}</span>` : ""}
          </div>
        `).join("")}
      </div>
      <div class="list-card">
        <h3>Timeline</h3>
        ${timeline.map((row) => `
          <div class="list-row">
            <strong>${escapeHtml(`${row.event_index}. ${row.actor_name} ${row.skill_name || ""}`)}</strong>
            <span class="subtext">${escapeHtml(`t=${formatNumber(row.time_seconds, 2)}s | ${row.skill_slot || "-"} | ${row.summary || ""}`)}</span>
            ${row.boss_debuffs ? `<span class="subtext">Boss: ${escapeHtml(row.boss_debuffs)}</span>` : ""}
            ${row.active_buffs ? `<span class="subtext">Self: ${escapeHtml(row.active_buffs)}</span>` : ""}
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

async function hydrateChampion(member) {
  if (!member?.champion_name) return;
  if (!state.championCache[member.champion_name]) {
    try {
      state.championCache[member.champion_name] = await fetchJson(`/api/champion?name=${encodeURIComponent(member.champion_name)}`);
    } catch (error) {
      setStatus(error.message || "Impossibile leggere il campione.", true);
      return;
    }
  }
  const detail = state.championCache[member.champion_name];
  const speed = Number(detail?.total_stats?.spd || detail?.base_totals?.spd || detail?.base_stats?.spd || 0);
  if (speed > 0) {
    member.speed = speed;
  }
}

function applyPreset(memberIndex, presetKey) {
  const member = state.team[memberIndex];
  const preset = (state.bootstrap?.team_presets || []).find((item) => item.key === presetKey);
  member.preset_key = presetKey || "blank";
  member.skills = [
    makeBlankSkill("A1", 100),
    makeBlankSkill("A2", 240),
    makeBlankSkill("A3", 320),
    makeBlankSkill("A4", 160),
  ];
  if (!preset) return;
  for (const presetSkill of preset.skills || []) {
    const targetIndex = ["A1", "A2", "A3", "A4"].indexOf(presetSkill.slot || "A1");
    if (targetIndex < 0) continue;
    member.skills[targetIndex] = normalizeSkill(presetSkill, presetSkill.slot, presetSkill.priority || 200);
  }
}

function applyOptimizerDefaults() {
  const team = state.recommendations?.heuristic?.team || state.bootstrap?.default_team || [];
  state.team = team.map((member, index) => normalizeMember(member, index + 1));
  state.comparison = null;
  renderRoster();
  renderSummary();
  renderResults();
}

function applyAiDefaults() {
  const team = state.recommendations?.ai?.team || [];
  if (!team.length) {
    setStatus("Nessun team AI disponibile. Allena prima un modello baseline oppure verifica il file in models/.", true);
    return;
  }
  state.team = team.map((member, index) => normalizeMember(member, index + 1));
  state.comparison = null;
  renderRoster();
  renderSummary();
  renderResults();
}

function applyBlankDefaults() {
  state.team = Array.from({ length: 5 }, (_, index) => normalizeMember({}, index + 1));
  state.comparison = null;
  renderRoster();
  renderSummary();
  renderResults();
}

function collectPayload() {
  return {
    settings: {
      difficulty: difficultyEl.value || "ultra_nightmare",
      affinity: affinityEl.value || "void",
      max_boss_turns: Number(bossTurnsEl.value || 12),
      speed_aura_pct: Number(auraEl.value || 0),
      stun_target_slot: Number(stunTargetEl.value || 5),
    },
    team: state.team.map((member) => ({
      ...member,
      preset_key: member.preset_key || "blank",
    })),
  };
}

async function runSimulation() {
  state.loading = true;
  simulateBtn.disabled = true;
  setStatus("Simulazione turno per turno in corso...");
  try {
    const payload = await fetchJson("/api/clan-boss-simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectPayload()),
    });
    state.result = payload;
    state.comparison = null;
    renderSummary();
    renderResults();
    setStatus(payload.ok ? "Simulazione pronta." : "Simulazione completata con errori di configurazione.", !payload.ok);
  } catch (error) {
    state.result = null;
    renderSummary();
    renderResults();
    setStatus(error.message || "Impossibile eseguire la simulazione.", true);
  } finally {
    state.loading = false;
    simulateBtn.disabled = false;
  }
}

async function loadRecommendations() {
  state.recommendations = await fetchJson(`/api/clan-boss-recommendations?difficulty=${encodeURIComponent(difficultyEl.value || "ultra_nightmare")}&affinity=${encodeURIComponent(affinityEl.value || "void")}`);
}

async function runComparison() {
  compareBtn.disabled = true;
  setStatus("Confronto tra consiglio euristico e AI in corso...");
  try {
    await loadRecommendations();
    const settings = collectPayload().settings;
    const heuristicPayload = state.recommendations?.heuristic?.team?.length
      ? await fetchJson("/api/clan-boss-simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ settings, team: state.recommendations.heuristic.team }),
        })
      : null;
    const aiPayload = state.recommendations?.ai?.team?.length
      ? await fetchJson("/api/clan-boss-simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ settings, team: state.recommendations.ai.team }),
        })
      : null;
    state.comparison = {
      heuristic: {
        ...(state.recommendations?.heuristic || {}),
        simulation: heuristicPayload,
      },
      ai: {
        ...(state.recommendations?.ai || {}),
        simulation: aiPayload,
      },
    };
    state.result = null;
    renderSummary();
    renderResults();
    setStatus("Confronto pronto. Ora vedi le due proposte sulla stessa finestra boss.", false);
  } catch (error) {
    setStatus(error.message || "Impossibile confrontare i due flussi.", true);
  } finally {
    compareBtn.disabled = false;
  }
}

function renderSelectors() {
  const difficulties = state.bootstrap?.difficulty_options || [];
  difficultyEl.innerHTML = difficulties.map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)} (${formatNumber(item.boss_speed, 0)} SPD)</option>`).join("");
  difficultyEl.value = "ultra_nightmare";
  affinityEl.innerHTML = (state.bootstrap?.affinity_options || []).map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`).join("");
  affinityEl.value = "void";
  stunTargetEl.innerHTML = Array.from({ length: 5 }, (_, index) => `<option value="${index + 1}">Slot ${index + 1}</option>`).join("");
  stunTargetEl.value = "5";
}

async function loadBootstrap() {
  setStatus("Caricamento simulator Clan Boss...");
  try {
    state.bootstrap = await fetchJson("/api/clan-boss-simulator-bootstrap");
    state.recommendations = state.bootstrap?.recommendations || null;
    renderSelectors();
    applyOptimizerDefaults();
    setStatus("Simulator pronto. Puoi partire dal team optimizer o costruire la tune a mano.");
  } catch (error) {
    setStatus(error.message || "Impossibile caricare il simulator.", true);
    detailsEl.innerHTML = '<div class="empty">Errore nel caricamento del simulator.</div>';
  }
}

useOptimizerBtn.addEventListener("click", () => {
  applyOptimizerDefaults();
  setStatus("Consiglio CB Forge caricato nel simulatore.");
});

useAiBtn.addEventListener("click", async () => {
  try {
    await loadRecommendations();
    applyAiDefaults();
    if (state.recommendations?.ai?.available) {
      setStatus("Consiglio AI caricato nel simulatore.");
    }
  } catch (error) {
    setStatus(error.message || "Impossibile caricare il consiglio AI.", true);
  }
});

compareBtn.addEventListener("click", runComparison);

resetBtn.addEventListener("click", () => {
  applyBlankDefaults();
  setStatus("Simulator resettato su cinque slot vuoti.");
});

simulateBtn.addEventListener("click", runSimulation);

loadBootstrap();
