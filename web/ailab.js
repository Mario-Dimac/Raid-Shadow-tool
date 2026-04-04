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
  const selected = selectedEncounterRow();
  summaryEl.innerHTML = [
    metricCard("Encounter", summary.encounters || 0, "Contenuti con run storiche"),
    metricCard("Runs", summary.runs || 0, "Run totali importate"),
    metricCard("Con Danno", summary.runs_with_damage || 0, "Run utili al baseline"),
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

function renderDetails() {
  const selected = selectedEncounterRow();
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
    detailsEl.innerHTML = `${errorNote}<div class="empty">Nessun encounter disponibile. Importa prima qualche run reale.</div>`;
    return;
  }
  detailsEl.innerHTML = `
    <div class="details-grid">
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

encounterEl.addEventListener("change", () => {
  state.selectedEncounter = encounterEl.value || "";
  syncSelectedEncounter();
  renderAll();
});

refreshBtn.addEventListener("click", loadOverview);
trainBtn.addEventListener("click", trainModel);

loadOverview();
