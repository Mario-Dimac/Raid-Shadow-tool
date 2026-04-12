const state = {
  targets: [],
  selectedBoss: "demon_lord",
  selectedAffinity: "void",
  selectedLevel: "ultra_nightmare",
  selectedSource: "optimizer",
  report: null,
  teamLoadout: null,
  teamLoadoutError: "",
  selectedChampion: null,
  equipInGameLoading: false,
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
      throw new Error("Richiesta scaduta.");
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
  } catch (_error) {
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

function currentBossConfig() {
  const targets = state.targets || [];
  return targets.find((target) => target.key === state.selectedBoss) || targets[0] || null;
}

function renderBossSelect() {
  const targets = state.targets || [];
  if (!targets.length) {
    bossEl.innerHTML = '<option value="demon_lord">Demon Lord</option>';
    bossEl.value = "demon_lord";
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

function isTeamLeader(member, index = 0) {
  if (member?.is_team_leader === true) return true;
  if (Number(member?.team_slot || 0) === 1) return true;
  return index === 0;
}

function getTeamLoadoutMember(championName) {
  return (state.teamLoadout?.team || []).find((member) => member.champion_name === championName) || null;
}

function getMemberStatus(candidate) {
  const member = getTeamLoadoutMember(candidate?.champion_name);
  if (!member) {
    return {
      label: state.teamLoadoutError ? "loadout non disponibile" : "piano in arrivo",
      note: state.teamLoadoutError || "Sto preparando il piano equip.",
      tone: "warn",
      hasChanges: false,
      hasConflicts: false,
      champId: String(candidate?.champ_id || ""),
    };
  }
  const changedItems = (member.items || []).filter((item) => String(item?.source_kind || "").toLowerCase() !== "current");
  const hasChanges = changedItems.length > 0;
  const conflictCount = Number(member.conflict_item_ids?.length || 0);
  const hasConflicts = conflictCount > 0;
  const label = hasConflicts
    ? `${formatNumber(conflictCount, 0)} conflitti`
    : (hasChanges ? `${formatNumber(changedItems.length, 0)} cambi` : "gia pronto");
  const note = hasConflicts
    ? "Controlla i pezzi condivisi prima di inviare."
    : (hasChanges ? "Invio diretto disponibile per questo campione." : "Nessun cambio richiesto.");
  return {
    label,
    note,
    tone: hasConflicts ? "warn" : (hasChanges ? "ok" : ""),
    hasChanges,
    hasConflicts,
    champId: String(member.champ_id || candidate?.champ_id || ""),
  };
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
        <div class="champ-name">${escapeHtml(`${candidate.team_slot || (index + 1)}. ${candidate.champion_name}`)}</div>
        <div class="pill ${getMemberStatus(candidate).tone}">${escapeHtml(getMemberStatus(candidate).label)}</div>
      </div>
      <div class="pillbar">
        ${isTeamLeader(candidate, index) ? '<span class="pill gold">Capo</span>' : ""}
        <span class="pill">${escapeHtml(candidate.default_build || "n/d")}</span>
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
      metricCard("Boss", "-", "In attesa del report"),
      metricCard("Team", "-", "Nessuna proposta"),
      metricCard("Fonte", "-", "Ranking non disponibile"),
      metricCard("Equip", "-", "Piano non disponibile"),
    ].join("");
    return;
  }
  const team = state.report.selected_team || [];
  const loadoutSummary = state.teamLoadout?.summary || {};
  summaryEl.innerHTML = [
    metricCard("Boss", state.report.target?.boss_label || "-", `${state.report.target?.level_label || "-"} / ${state.report.target?.affinity_label || "-"}`),
    metricCard("Team", `${team.length}/${state.report.target?.team_size || 5}`, "Campioni selezionati"),
    metricCard("Fonte", state.report.target?.recommendation_label || "Optimizer", state.selectedSource || "optimizer"),
    metricCard("Equip", formatNumber(loadoutSummary.total_swap_count || 0, 0), `${formatNumber(loadoutSummary.conflict_count || 0, 0)} conflitti`),
  ].join("");
}

function renderMemberCard(candidate, index) {
  const memberStatus = getMemberStatus(candidate);
  const isFocused = state.selectedChampion === candidate?.champion_name;
  return `
    <div class="card optimizer-member-workspace ${isFocused ? "optimizer-member-workspace-active" : ""}">
      <div class="detail-hero">
        <div>
          <h3>${escapeHtml(`${candidate?.team_slot || (index + 1)}. ${candidate?.champion_name || "-"}`)}</h3>
          <div class="detail-meta">
            ${isTeamLeader(candidate, index) ? '<span class="pill gold">Capo</span>' : ""}
            <span class="pill">${escapeHtml(candidate?.default_build || "n/d")}</span>
            <span class="pill ${memberStatus.tone}">${escapeHtml(memberStatus.label)}</span>
          </div>
        </div>
        <div class="action-row">
          <button class="primary optimizer-member-equip-btn" data-name="${escapeHtml(candidate?.champion_name || "")}" data-champ-id="${escapeHtml(memberStatus.champId)}" ${state.equipInGameLoading || !memberStatus.hasChanges || memberStatus.hasConflicts ? "disabled" : ""}>${state.equipInGameLoading && isFocused ? "Invio In Corso..." : "Equipaggia"}</button>
        </div>
      </div>
      <div class="subtext">${escapeHtml(memberStatus.note)}</div>
    </div>
  `;
}

function renderDetails() {
  if (!state.report) {
    detailsEl.innerHTML = '<div class="empty">Optimizer non disponibile.</div>';
    return;
  }
  const team = state.report?.selected_team || [];
  detailsEl.innerHTML = `
    <div class="card">
      <h3>Team Proposto</h3>
      <div class="subtext">Solo i 5 campioni selezionati. Se il pulsante e attivo, il piano equip e pronto per l'invio.</div>
      ${state.teamLoadoutError ? `<div class="list-row warn" style="margin-top: 12px;">${escapeHtml(state.teamLoadoutError)}</div>` : ""}
      <div class="stack optimizer-team-workspace" style="margin-top: 14px;">
        ${team.length ? team.map((candidate, index) => renderMemberCard(candidate, index)).join("") : '<div class="empty">Nessun team selezionato.</div>'}
      </div>
    </div>
  `;
  detailsEl.querySelectorAll(".optimizer-member-equip-btn").forEach((button) => {
    if (button.disabled) return;
    button.addEventListener("click", async () => {
      state.selectedChampion = button.dataset.name || null;
      renderRoster();
      renderDetails();
      await equipTeamMemberInGame(button.dataset.name || "", button.dataset.champId || "");
    });
  });
}

async function equipTeamMemberInGame(championName, champId) {
  if (!championName) return;
  state.equipInGameLoading = true;
  renderDetails();
  setStatus(`Invio equip a RAID per ${championName}...`);
  try {
    const payload = await fetchJson("/api/team-optimizer-equip-member", {
      method: "POST",
      timeoutMs: 180000,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        champion_name: championName,
        champ_id: champId,
        boss: state.selectedBoss,
        level: state.selectedLevel,
        affinity: state.selectedAffinity,
        source: state.selectedSource,
      }),
    });
    const summary = payload?.summary || {};
    setStatus(`Richiesta equip inviata per ${championName}: ${formatNumber(summary.members_succeeded || 0, 0)}/${formatNumber(summary.members_requested || 0, 0)} campioni.`);
  } catch (error) {
    setStatus(error.message || "Impossibile equipaggiare il campione selezionato.", true);
  } finally {
    state.equipInGameLoading = false;
    renderDetails();
  }
}

async function loadReport() {
  setStatus("Calcolo optimizer in corso...");
  state.report = null;
  state.teamLoadout = null;
  state.teamLoadoutError = "";
  renderSummary();
  renderRoster();
  renderDetails();
  try {
    const query = `boss=${encodeURIComponent(state.selectedBoss)}&level=${encodeURIComponent(state.selectedLevel)}&affinity=${encodeURIComponent(state.selectedAffinity)}&source=${encodeURIComponent(state.selectedSource)}`;
    const reportPromise = fetchJson(`/api/team-optimizer?${query}`);
    const loadoutPromise = fetchJson(`/api/team-optimizer-loadout?${query}`);
    const payload = await reportPromise;
    state.targets = payload.targets || [];
    state.selectedBoss = payload.selection?.boss_key || state.selectedBoss;
    state.selectedLevel = payload.selection?.level_key || state.selectedLevel;
    state.selectedAffinity = payload.selection?.affinity || state.selectedAffinity;
    state.selectedSource = payload.selection?.recommendation_source || state.selectedSource;
    state.report = payload.report || null;
    renderBossSelect();
    renderAffinitySelect();
    renderLevelSelect();
    renderSourceSelect();
    if (!(state.report?.selected_team || []).some((item) => item.champion_name === state.selectedChampion)) {
      state.selectedChampion = state.report?.selected_team?.[0]?.champion_name || null;
    }
    renderSummary();
    renderRoster();
    renderDetails();
    try {
      state.teamLoadout = await loadoutPromise;
      state.teamLoadoutError = "";
      setStatus(`Optimizer pronto su ${state.report?.target?.boss_label || state.selectedBoss} ${state.report?.target?.level_label || state.selectedLevel}.`);
    } catch (error) {
      state.teamLoadoutError = error.message || "Impossibile preparare il piano equip.";
      setStatus(state.teamLoadoutError, true);
    }
    renderSummary();
    renderRoster();
    renderDetails();
  } catch (error) {
    state.report = null;
    state.teamLoadout = null;
    state.teamLoadoutError = "";
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
