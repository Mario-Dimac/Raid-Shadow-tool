const state = {
  overview: null,
  selectedEncounter: "",
  trainingResult: null,
};

const encounterEl = document.getElementById("aiEncounter");
const outputPathEl = document.getElementById("aiOutputPath");
const rosterEl = document.getElementById("aiRoster");
const summaryEl = document.getElementById("aiSummary");
const detailsEl = document.getElementById("aiDetails");
const statusEl = document.getElementById("aiStatus");
const refreshBtn = document.getElementById("aiRefreshBtn");
const datasetBtn = document.getElementById("aiDatasetBtn");
const cleanupBtn = document.getElementById("aiCleanupBtn");
const trainBtn = document.getElementById("aiTrainBtn");

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

function selectedEncounterRow() {
  return (state.overview?.encounters || []).find((row) => row.encounter_key === state.selectedEncounter) || null;
}

function firstTrainReadyEncounter() {
  return (state.overview?.encounters || []).find((row) => row.train_ready) || null;
}

function renderSummary() {
  const summary = state.overview?.summary || {};
  const skillDataset = state.overview?.skill_dataset || {};
  const selected = selectedEncounterRow();
  summaryEl.innerHTML = [
    metricCard("Encounter", summary.encounters || 0, "Contenuti con run storiche"),
    metricCard("Runs", summary.runs || 0, "Run totali importate"),
    metricCard("Con Danno", summary.runs_with_damage || 0, "Run utili al baseline"),
    metricCard("Dataset Skill", skillDataset.sample_count || 0, "Righe AI normalizzate nel DB"),
    metricCard("Modelli", summary.models_present || 0, selected?.model_exists ? "Il selezionato esiste gia'" : "Non tutti allenati"),
  ].join("");
}

function renderRoster() {
  const encounters = state.overview?.encounters || [];
  rosterEl.innerHTML = encounters.map((item) => `
    <button class="champ-row ${item.encounter_key === state.selectedEncounter ? "active" : ""}" data-encounter-key="${escapeHtml(item.encounter_key)}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(item.encounter_name || item.encounter_key)}</div>
        <div class="pillbar">
          <span class="pill gold">${escapeHtml(item.difficulty || "-")}</span>
          <span class="pill">${escapeHtml(`${item.run_count} run`)}</span>
          <span class="pill ${item.train_ready ? "ok" : "warn"}">${item.train_ready ? "train ready" : "pochi dati"}</span>
        </div>
      </div>
      <div class="subtext">${escapeHtml(item.encounter_key)}${item.boss_affinity ? ` | aff ${item.boss_affinity}` : ""}</div>
    </button>
  `).join("");

  rosterEl.querySelectorAll("[data-encounter-key]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedEncounter = button.dataset.encounterKey || "";
      syncSelectedEncounter();
      renderAll();
    });
  });
}

function renderTrainingResult() {
  if (!state.trainingResult?.training) return "";
  const training = state.trainingResult.training || {};
  const metrics = training.metrics || {};
  const importances = training.feature_importances || [];
  return `
    <div class="details-grid">
      <div class="list-card">
        <h3>Ultimo Training</h3>
        <div class="list-row">
          <strong>${escapeHtml(state.trainingResult.encounter_key || "-")}</strong>
          <span class="subtext">Output: ${escapeHtml(training.output_path || "-")}</span>
        </div>
        ${Object.entries(metrics).map(([key, value]) => `
          <div class="list-row">
            <strong>${escapeHtml(key)}</strong>
            <span class="subtext">${escapeHtml(String(value))}</span>
          </div>
        `).join("")}
      </div>
      <div class="list-card">
        <h3>Feature Importanti</h3>
        ${importances.map((row) => `
          <div class="list-row">
            <strong>${escapeHtml(row.feature || "-")}</strong>
            <span class="subtext">importance ${escapeHtml(formatNumber(row.importance, 6))}</span>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderAdvisor() {
  const advisor = state.overview?.advisor || null;
  if (!advisor) return "";
  const health = advisor.health || {};
  const actions = advisor.next_actions || [];
  const contentFocus = advisor.content_focus || [];
  const targets = advisor.recommended_targets || [];
  return `
    <div class="details-grid">
      <div class="list-card">
        <h3>Consigliere Dataset</h3>
        <div class="list-row">
          <strong>Stato</strong>
          <span class="subtext">${escapeHtml(advisor.headline || "-")}</span>
        </div>
        <div class="list-row">
          <strong>Run con danno distinte</strong>
          <span class="subtext">${escapeHtml(formatNumber(health.distinct_damage_runs || 0, 0))}</span>
        </div>
        <div class="list-row">
          <strong>Clan Boss / team distinti</strong>
          <span class="subtext">${escapeHtml(`${formatNumber(health.clan_boss_damage_runs || 0, 0)} run | ${formatNumber(health.clan_boss_unique_teams || 0, 0)} team`)}</span>
        </div>
        <div class="list-row">
          <strong>Run skill fuori CB</strong>
          <span class="subtext">${escapeHtml(formatNumber(health.skill_capture_runs || 0, 0))}</span>
        </div>
        <div class="list-row ${Number(health.duplicate_groups || 0) > 0 ? "warn" : ""}">
          <strong>Duplicati</strong>
          <span class="subtext">${escapeHtml(`${formatNumber(health.duplicate_groups || 0, 0)} gruppi | ${formatNumber(health.duplicate_rows || 0, 0)} righe extra`)}</span>
        </div>
      </div>
      <div class="list-card">
        <h3>Prossime Mosse</h3>
        ${actions.length ? actions.map((item) => `
          <div class="list-row">
            <strong>${escapeHtml(item.title || "-")}</strong>
            <span class="subtext">[${escapeHtml(item.priority || "-")}] ${escapeHtml(item.detail || "")}</span>
          </div>
        `).join("") : '<div class="empty">Nessun consiglio disponibile.</div>'}
      </div>
    </div>
    <div class="details-grid">
      <div class="list-card">
        <h3>Focus Contenuti</h3>
        ${contentFocus.map((item) => `
          <div class="list-row">
            <strong>${escapeHtml(item.category_label || item.category_key || "-")}</strong>
            <span class="subtext">${escapeHtml(`${formatNumber(item.run_count || 0, 0)} run | ${item.why_now || ""}`)}</span>
          </div>
        `).join("")}
      </div>
      <div class="list-card">
        <h3>Target Da Spingere</h3>
        ${targets.length ? targets.map((item) => `
          <div class="list-row">
            <strong>${escapeHtml(item.encounter_name || item.encounter_key || "-")}</strong>
            <span class="subtext">${escapeHtml(`${formatNumber(item.runs_with_damage || 0, 0)} con danno / ${formatNumber(item.run_count || 0, 0)} totali${item.boss_affinity ? ` | aff ${item.boss_affinity}` : ""}${item.train_ready ? " | train ready" : ""}`)}</span>
          </div>
        `).join("") : '<div class="empty">Importa prima qualche run utile.</div>'}
      </div>
    </div>
  `;
}

function renderDetails() {
  const selected = selectedEncounterRow();
  const skillDataset = state.overview?.skill_dataset || {};
  const runtime = state.overview?.dependency_runtime || {};
  const runtimeBits = [
    runtime.python_executable ? `Python server: ${runtime.python_executable}` : "",
    runtime.python_version ? `Python ${runtime.python_version}` : "",
    runtime.sklearn_version ? `scikit-learn ${runtime.sklearn_version}` : "",
    runtime.numpy_version ? `numpy ${runtime.numpy_version}` : "",
    runtime.pandas_version ? `pandas ${runtime.pandas_version}` : "",
  ].filter(Boolean);
  const dependencyRows = state.overview?.error ? `
    <div class="list-row warn">
      <strong>Training disabilitato</strong>
      <span class="subtext">${escapeHtml(state.overview.error)}</span>
    </div>
    ${state.overview?.dependency_detail ? `
      <div class="list-row warn">
        <strong>Dettaglio errore</strong>
        <span class="subtext">${escapeHtml(state.overview.dependency_detail)}</span>
      </div>
    ` : ""}
    ${runtimeBits.length ? `
      <div class="list-row">
        <strong>Runtime server</strong>
        <span class="subtext">${escapeHtml(runtimeBits.join(" | "))}</span>
      </div>
    ` : ""}
  ` : runtimeBits.length ? `
    <div class="list-row">
      <strong>Runtime server</strong>
      <span class="subtext">${escapeHtml(runtimeBits.join(" | "))}</span>
    </div>
  ` : "";
  if (!selected) {
    const errorNote = state.overview?.error
      ? `<div class="list-card"><h3>Stato AI</h3>${dependencyRows}</div>`
      : "";
    detailsEl.innerHTML = `${errorNote}${renderAdvisor()}<div class="empty">Nessun encounter disponibile. Importa prima qualche run reale.</div>`;
    return;
  }
  detailsEl.innerHTML = `
    <div class="details-grid">
      <div class="list-card">
        <h3>Dataset Skill AI</h3>
        <div class="list-row">
          <strong>Righe materializzate</strong>
          <span class="subtext">${escapeHtml(`${formatNumber(skillDataset.sample_count || 0, 0)} sample | ${formatNumber(skillDataset.normalized_sample_count || 0, 0)} normalizzati`)}</span>
        </div>
        <div class="list-row">
          <strong>Copertura</strong>
          <span class="subtext">${escapeHtml(`${formatNumber(skillDataset.run_count || 0, 0)} run | ${formatNumber(skillDataset.encounter_count || 0, 0)} encounter`)}</span>
        </div>
        <div class="list-row">
          <strong>Ultimo refresh</strong>
          <span class="subtext">${escapeHtml(skillDataset.last_built_at || "Mai costruito da questa UI")}</span>
        </div>
        <div class="list-row">
          <strong>Uso pratico</strong>
          <span class="subtext">Questo dataset vive nel database ed evita di dover rileggere i file raw o ricordare comandi manuali.</span>
        </div>
      </div>
      <div class="list-card">
        <h3>Encounter Selezionato</h3>
        <div class="list-row">
          <strong>${escapeHtml(selected.encounter_name || selected.encounter_key)}</strong>
          <span class="subtext">${escapeHtml(selected.encounter_key)}</span>
        </div>
        <div class="list-row">
          <strong>Dataset</strong>
          <span class="subtext">${escapeHtml(`${selected.run_count} run totali | ${selected.runs_with_damage} con total_damage`)}</span>
        </div>
        <div class="list-row">
          <strong>Stato training</strong>
          <span class="subtext">${selected.train_ready ? "Hai abbastanza dati per allenare il baseline." : "Servono almeno 3 run con total_damage."}</span>
        </div>
      </div>
      <div class="list-card">
        <h3>Modello</h3>
        <div class="list-row">
          <strong>${selected.model_exists ? "Modello presente" : "Modello non presente"}</strong>
          <span class="subtext">${escapeHtml(selected.model_path || "-")}</span>
        </div>
        <div class="list-row">
          <strong>Aggiornato</strong>
          <span class="subtext">${escapeHtml(selected.model_updated_at || "Mai allenato da questa UI")}</span>
        </div>
        <div class="list-row">
          <strong>Uso pratico</strong>
          <span class="subtext">Dopo il training, il consiglio AI compare nel simulatore Clan Boss e puo' essere confrontato col consiglio CB Forge.</span>
        </div>
        ${dependencyRows}
      </div>
    </div>
    ${renderAdvisor()}
    ${renderTrainingResult()}
  `;
}

function syncSelectedEncounter() {
  const current = selectedEncounterRow();
  if ((!state.selectedEncounter || !current) && state.overview?.encounters?.length) {
    state.selectedEncounter = (firstTrainReadyEncounter() || state.overview.encounters[0]).encounter_key;
  }
  encounterEl.innerHTML = (state.overview?.encounters || []).map((item) => `
    <option value="${escapeHtml(item.encounter_key)}" ${item.encounter_key === state.selectedEncounter ? "selected" : ""}>
      ${escapeHtml(item.encounter_name || item.encounter_key)} (${escapeHtml(String(item.run_count))} run)
    </option>
  `).join("");
  encounterEl.value = state.selectedEncounter || "";
  const selected = selectedEncounterRow();
  outputPathEl.value = selected?.model_path || "";
}

function renderAll() {
  renderSummary();
  renderRoster();
  renderDetails();
}

async function loadOverview() {
  setStatus("Caricamento AI Lab...");
  state.overview = await fetchJson("/api/ai-training-overview");
  state.trainingResult = null;
  syncSelectedEncounter();
  trainBtn.disabled = state.overview?.training_available === false;
  datasetBtn.disabled = false;
  cleanupBtn.disabled = false;
  renderAll();
  if (state.overview?.training_available === false) {
    setStatus(state.overview.error || "AI Lab caricato, ma il training non e' disponibile in questo ambiente Python.", true);
  } else {
    setStatus("AI Lab pronto.");
  }
}

async function trainModel() {
  if (!state.selectedEncounter) {
    setStatus("Seleziona prima un encounter.", true);
    return;
  }
  const selected = selectedEncounterRow();
  if (!selected?.train_ready) {
    setStatus("Questo encounter non ha ancora abbastanza run con total_damage. Scegline uno marcato come train ready.", true);
    return;
  }
  trainBtn.disabled = true;
  setStatus("Training AI in corso. Sto usando le run storiche gia' importate...");
  try {
    state.trainingResult = await fetchJson("/api/ai-train-baseline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        encounter_key: state.selectedEncounter,
        output_path: outputPathEl.value || "",
      }),
    });
    state.overview = state.trainingResult.overview || state.overview;
    syncSelectedEncounter();
    renderAll();
    setStatus("Training completato. Il modello ora e' disponibile anche per il flusso AI nel simulatore.");
  } catch (error) {
    setStatus(error.message || "Training non riuscito.", true);
  } finally {
    trainBtn.disabled = false;
  }
}

async function cleanupDuplicates() {
  cleanupBtn.disabled = true;
  setStatus("Pulizia duplicati run in corso...");
  try {
    const payload = await fetchJson("/api/ai-cleanup-duplicates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "probe_import" }),
    });
    state.overview = payload.overview || state.overview;
    state.trainingResult = null;
    syncSelectedEncounter();
    renderAll();
    const cleanup = payload.cleanup || {};
    setStatus(`Pulizia completata: ${formatNumber(cleanup.removed_runs || 0, 0)} run duplicate rimosse in ${formatNumber(cleanup.duplicate_groups || 0, 0)} gruppi.`);
  } catch (error) {
    setStatus(error.message || "Pulizia duplicati non riuscita.", true);
  } finally {
    cleanupBtn.disabled = false;
  }
}

async function refreshSkillDataset() {
  datasetBtn.disabled = true;
  setStatus("Sto importando le novita' nel DB e preparando il dataset AI normalizzato...");
  try {
    const payload = await fetchJson("/api/ai-refresh-training-dataset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    state.overview = payload.overview || state.overview;
    state.trainingResult = null;
    syncSelectedEncounter();
    renderAll();
    const refresh = payload.refresh || {};
    const overview = refresh.overview || {};
    setStatus(`Dataset AI aggiornato: ${formatNumber(overview.sample_count || 0, 0)} righe da ${formatNumber(overview.run_count || 0, 0)} run. Ultimo refresh ${overview.last_built_at || "-"}.`);
  } catch (error) {
    setStatus(error.message || "Aggiornamento dataset AI non riuscito.", true);
  } finally {
    datasetBtn.disabled = false;
  }
}

encounterEl.addEventListener("change", () => {
  state.selectedEncounter = encounterEl.value || "";
  syncSelectedEncounter();
  renderAll();
});

refreshBtn.addEventListener("click", loadOverview);
datasetBtn.addEventListener("click", refreshSkillDataset);
cleanupBtn.addEventListener("click", cleanupDuplicates);
trainBtn.addEventListener("click", trainModel);

loadOverview();
