const state = {
  registry: null,
  selectedSetName: "",
};

const setListEl = document.getElementById("setList");
const setDetailsEl = document.getElementById("setDetails");
const setSummaryEl = document.getElementById("setSummary");
const setStatusEl = document.getElementById("setStatus");
const setSearchEl = document.getElementById("setSearch");
const setKindFilterEl = document.getElementById("setKindFilter");
const setObservedFilterEl = document.getElementById("setObservedFilter");
const setReloadBtn = document.getElementById("setReloadBtn");

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
  "Unkillable And SPD And CR Damage": "Swift Parry",
  "Attack And Crit Rate": "Fatal",
  "Block Debuff": "Immunity",
  "Crit Rate And Ignore DEF Multiplier": "Lethal",
  "Damage Increase On HP Decrease": "Fury",
  "Get Extra Turn": "Relentless",
  "HP": "Life",
  "Stun Chance": "Stun",
  "Crit Damage And Transform Week Into Crit Hit": "Affinitybreaker",
  "Crit Rate And Life Drain": "Bloodthirst",
  "Change Hit Type": "Reaction Accessory",
  "Counterattack Accessory": "Revenge Accessory",
  "Shield Accessory": "Bloodshield Accessory",
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
  setStatusEl.textContent = message || "";
  setStatusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
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

function displaySetName(setName) {
  return SET_LABELS[setName] || setName || "Set";
}

function formatStatValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value || "");
  if (Math.abs(numeric - Math.round(numeric)) < 0.05) return String(Math.round(numeric));
  return numeric.toFixed(1);
}

function formatStatLabel(statType, statValue) {
  const text = String(statType || "").toLowerCase();
  const labels = {
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
    spd_pct: "SPD%",
  };
  const suffix = text.endsWith("_pct") ? "%" : "";
  if (text === "spd" || text === "acc" || text === "res" || text === "crit_rate" || text === "crit_dmg") {
    return `${labels[text] || statType} +${formatStatValue(statValue)}`;
  }
  if (suffix) return `${labels[text] || statType} +${formatStatValue(statValue)}%`;
  return `${labels[text] || statType} +${formatStatValue(statValue)}`;
}

function summarizeThreshold(threshold) {
  const bits = [];
  (threshold.stats || []).forEach((stat) => bits.push(formatStatLabel(stat.stat_type, stat.stat_value)));
  (threshold.effects || []).forEach((effect) => bits.push(effect));
  return bits.join(" | ") || "Nessun bonus visibile";
}

function getVisibleSets() {
  const registrySets = state.registry?.sets || [];
  const search = (setSearchEl.value || "").trim().toLowerCase();
  const selectedKind = (setKindFilterEl.value || "").trim().toLowerCase();
  const observedFilter = setObservedFilterEl.value || "all";
  return registrySets.filter((setRow) => {
    const setName = String(setRow.set_name || "");
    const displayName = displaySetName(setName);
    const haystack = `${setName} ${displayName} ${setRow.summary || ""}`.toLowerCase();
    if (search && !haystack.includes(search)) return false;
    if (selectedKind && String(setRow.set_kind || "").toLowerCase() !== selectedKind) return false;
    const observed = Number(setRow.inventory?.total_items || 0) > 0;
    if (observedFilter === "observed" && !observed) return false;
    if (observedFilter === "missing" && observed) return false;
    return true;
  });
}

function ensureSelection(visibleSets) {
  if (!visibleSets.length) {
    state.selectedSetName = "";
    return;
  }
  if (!visibleSets.some((setRow) => setRow.set_name === state.selectedSetName)) {
    state.selectedSetName = visibleSets[0].set_name;
  }
}

function renderSummary() {
  const summary = state.registry?.summary || {};
  setSummaryEl.innerHTML = [
    metricCard("Set Totali", summary.total_sets || 0, "registry locale"),
    metricCard("Set Osservati", summary.observed_sets || 0, "presenti nell'inventario"),
    metricCard("Chiudibili", summary.completable_fixed_sets || 0, "fixed set con pezzi gia' posseduti"),
    metricCard("Liberi Ora", summary.inventory_ready_fixed_sets || 0, "fixed set chiudibili da magazzino"),
  ].join("");
}

function renderList() {
  const visibleSets = getVisibleSets();
  ensureSelection(visibleSets);
  if (!visibleSets.length) {
    setListEl.innerHTML = '<div class="empty">Nessun set corrisponde ai filtri correnti.</div>';
    renderDetails(null);
    return;
  }
  setListEl.innerHTML = visibleSets.map((setRow) => {
    const active = setRow.set_name === state.selectedSetName ? " active" : "";
    const totalItems = Number(setRow.inventory?.total_items || 0);
    const progress = setRow.progress || {};
    const observedPill = totalItems > 0
      ? `<span class="pill ok">${escapeHtml(String(totalItems))} pezzi</span>`
      : '<span class="pill">non osservato</span>';
    const kindPill = `<span class="pill gold">${escapeHtml(String(setRow.set_kind || "unknown"))}</span>`;
    const accessoryPill = setRow.counts_accessories ? '<span class="pill warn">con accessori</span>' : "";
    const setKind = String(setRow.set_kind || "").toLowerCase();
    const completionPill = ["variable", "accessory"].includes(setKind)
      ? `<span class="pill">${escapeHtml(`soglia ${String(progress.highest_bonus_threshold_total || 0)}/${String(setRow.max_pieces || 0)}`)}</span>`
      : Number(progress.complete_sets_total || 0) > 0
        ? `<span class="pill ok">${escapeHtml(`chiudibile x${String(progress.complete_sets_total || 0)}`)}</span>`
        : Number(progress.missing_for_next_total || 0) > 0
          ? `<span class="pill">${escapeHtml(`manca ${String(progress.missing_for_next_total || 0)}`)}</span>`
          : "";
    const inventoryPill = Number(progress.complete_sets_inventory || 0) > 0
      ? `<span class="pill ok">${escapeHtml(`libero x${String(progress.complete_sets_inventory || 0)}`)}</span>`
      : "";
    return `
      <button class="champ-row${active}" data-set-name="${escapeHtml(setRow.set_name)}">
        <div class="champ-topline">
          <div class="champ-name">${escapeHtml(displaySetName(setRow.set_name))}</div>
          <div class="pillbar">${kindPill}${observedPill}</div>
        </div>
        <div class="subtext">${escapeHtml(setRow.set_name)}${setRow.summary ? ` · ${escapeHtml(setRow.summary)}` : ""}</div>
        <div class="pillbar">${accessoryPill}${completionPill}${inventoryPill}</div>
      </button>
    `;
  }).join("");

  setListEl.querySelectorAll("[data-set-name]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSetName = button.getAttribute("data-set-name") || "";
      renderList();
    });
  });

  const selected = visibleSets.find((setRow) => setRow.set_name === state.selectedSetName) || null;
  renderDetails(selected);
}

function renderDetails(setRow) {
  if (!setRow) {
    setDetailsEl.innerHTML = '<div class="empty">Nessun set selezionato.</div>';
    return;
  }
  const kindLabel = String(setRow.set_kind || "unknown");
  const inventory = setRow.inventory || {};
  const progress = setRow.progress || {};
  const thresholds = (setRow.piece_bonuses || []).length
    ? (setRow.piece_bonuses || [])
    : [{
        pieces_required: setRow.pieces_required || 0,
        stats: setRow.stats || [],
        effects: setRow.heal_each_turn_pct ? [`Heal ${formatStatValue(setRow.heal_each_turn_pct)}% ogni turno`] : [],
      }];

  const thresholdHtml = thresholds.map((threshold) => `
    <div class="build-piece">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(String(threshold.pieces_required || 0))} pezzi</div>
        <div class="pillbar"><span class="pill">${escapeHtml(summarizeThreshold(threshold))}</span></div>
      </div>
    </div>
  `).join("");

  const baseBonusText = (setRow.stats || []).length
    ? (setRow.stats || []).map((stat) => formatStatLabel(stat.stat_type, stat.stat_value)).join(" | ")
    : "Nessun bonus base statico";

  setDetailsEl.innerHTML = `
    <section class="detail-hero">
      <div>
        <h2>${escapeHtml(displaySetName(setRow.set_name))}</h2>
        <p class="subtext">${escapeHtml(setRow.set_name)} · ${escapeHtml(setRow.summary || "")}</p>
      </div>
      <div class="detail-meta">
        <span class="pill gold">${escapeHtml(kindLabel)}</span>
        <span class="pill">${setRow.counts_accessories ? "artifact + accessori" : "solo artifact"}</span>
        <span class="pill">${escapeHtml(String(setRow.source || "unknown"))}</span>
      </div>
    </section>

    <section class="grid">
      <div class="card">
        <h3>Registry</h3>
        <div class="kv">
          <div class="kv-row"><span>Tipo</span><strong>${escapeHtml(kindLabel)}</strong></div>
          <div class="kv-row"><span>Soglia base</span><strong>${escapeHtml(String(setRow.pieces_required || 0))}</strong></div>
          <div class="kv-row"><span>Max pezzi</span><strong>${escapeHtml(String(setRow.max_pieces || 0))}</strong></div>
          <div class="kv-row"><span>Accessori</span><strong>${setRow.counts_accessories ? "si" : "no"}</strong></div>
          <div class="kv-row"><span>Bonus base</span><strong>${escapeHtml(baseBonusText)}</strong></div>
          <div class="kv-row"><span>Heal turno</span><strong>${setRow.heal_each_turn_pct ? `${formatStatValue(setRow.heal_each_turn_pct)}%` : "n/d"}</strong></div>
        </div>
      </div>

      <div class="card">
        <h3>Inventario</h3>
        <div class="kv">
          <div class="kv-row"><span>Pezzi totali</span><strong>${escapeHtml(String(inventory.total_items || 0))}</strong></div>
          <div class="kv-row"><span>Artifact</span><strong>${escapeHtml(String(inventory.artifact_items || 0))}</strong></div>
          <div class="kv-row"><span>Accessori</span><strong>${escapeHtml(String(inventory.accessory_items || 0))}</strong></div>
          <div class="kv-row"><span>Equipaggiati</span><strong>${escapeHtml(String(inventory.equipped_items || 0))}</strong></div>
          <div class="kv-row"><span>Magazzino</span><strong>${escapeHtml(String(inventory.inventory_items || 0))}</strong></div>
          <div class="kv-row"><span>Owner distinti</span><strong>${escapeHtml(String(inventory.equipped_owners || 0))}</strong></div>
        </div>
      </div>
    </section>

    <section class="card">
      <h3>Operativita'</h3>
      <div class="kv">
        <div class="kv-row"><span>Pezzi rilevanti totali</span><strong>${escapeHtml(String(progress.relevant_total_items || 0))}</strong></div>
        <div class="kv-row"><span>Pezzi rilevanti liberi</span><strong>${escapeHtml(String(progress.relevant_inventory_items || 0))}</strong></div>
        <div class="kv-row"><span>Pezzi rilevanti equip</span><strong>${escapeHtml(String(progress.relevant_equipped_items || 0))}</strong></div>
        <div class="kv-row"><span>Set chiudibili</span><strong>${escapeHtml(String(progress.complete_sets_total || 0))}</strong></div>
        <div class="kv-row"><span>Set chiudibili liberi</span><strong>${escapeHtml(String(progress.complete_sets_inventory || 0))}</strong></div>
        <div class="kv-row"><span>Soglia attiva</span><strong>${escapeHtml(`${String(progress.highest_bonus_threshold_total || 0)}/${String(setRow.max_pieces || 0)}`)}</strong></div>
        <div class="kv-row"><span>Prossima soglia</span><strong>${progress.next_threshold_total ? escapeHtml(String(progress.next_threshold_total)) : "nessuna"}</strong></div>
        <div class="kv-row"><span>Pezzi mancanti</span><strong>${escapeHtml(String(progress.missing_for_next_total || 0))}</strong></div>
      </div>
    </section>

    <section class="card">
      <h3>Bonus Per Soglia</h3>
      <div class="stack">
        ${thresholdHtml || '<div class="empty">Nessuna soglia disponibile.</div>'}
      </div>
    </section>
  `;
}

async function loadRegistry() {
  setStatus("Carico il registry dei set...");
  state.registry = await fetchJson("/api/set-registry");
  renderSummary();
  renderList();
  setStatus(`Set caricati: ${state.registry?.summary?.total_sets || 0}`);
}

setSearchEl.addEventListener("input", renderList);
setKindFilterEl.addEventListener("change", renderList);
setObservedFilterEl.addEventListener("change", renderList);
setReloadBtn.addEventListener("click", () => {
  loadRegistry().catch((error) => setStatus(error.message, true));
});

loadRegistry().catch((error) => setStatus(error.message, true));
