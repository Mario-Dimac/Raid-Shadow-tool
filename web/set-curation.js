const state = {
  payload: null,
  selectedSetName: "",
};

const curationListEl = document.getElementById("curationList");
const curationDetailsEl = document.getElementById("curationDetails");
const curationSummaryEl = document.getElementById("curationSummary");
const curationStatusTextEl = document.getElementById("curationStatusText");
const curationSearchEl = document.getElementById("curationSearch");
const curationStatusEl = document.getElementById("curationStatus");
const curationReloadBtn = document.getElementById("curationReloadBtn");

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
  curationStatusTextEl.textContent = message || "";
  curationStatusTextEl.style.color = isError ? "var(--danger)" : "var(--muted)";
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

function formatMainStat(sample) {
  const statType = String(sample?.main_stat_type || "").trim();
  const statValue = sample?.main_stat_value;
  if (!statType) return "main stat n/d";
  if (statValue === null || statValue === undefined || statValue === "") return statType;
  return `${statType} ${statValue}`;
}

function renderObservedSamples(item) {
  const observed = item?.observed_samples || {};
  const sampleItems = observed.sample_items || [];
  const slotCounts = observed.slot_counts || [];
  const ownerCounts = observed.owner_counts || [];
  const gearLink = `/gear?set=${encodeURIComponent(item.set_name || "")}&sort=owner`;

  return `
    <section class="card">
      <h3>Pezzi Osservati</h3>
      <div class="kv single-column">
        <div class="kv-row"><span>Totale set</span><strong>${escapeHtml(String(item.inventory?.total_items || 0))} pezzi</strong></div>
        <div class="kv-row"><span>Artifact</span><strong>${escapeHtml(String(item.inventory?.artifact_items || 0))}</strong></div>
        <div class="kv-row"><span>Accessori</span><strong>${escapeHtml(String(item.inventory?.accessory_items || 0))}</strong></div>
        <div class="kv-row"><span>Equipaggiati</span><strong>${escapeHtml(String(item.inventory?.equipped_items || 0))}</strong></div>
        <div class="kv-row"><span>Magazzino</span><strong>${escapeHtml(String(item.inventory?.inventory_items || 0))}</strong></div>
      </div>

      <div class="stack">
        <div class="subtext">Distribuzione slot: ${slotCounts.length ? slotCounts.map((entry) => `${escapeHtml(entry.slot)} ${escapeHtml(String(entry.count))}`).join(", ") : "n/d"}</div>
        <div class="subtext">Owner principali: ${ownerCounts.length ? ownerCounts.map((entry) => `${escapeHtml(entry.owner_name)} ${escapeHtml(String(entry.count))}`).join(", ") : "nessun owner"}</div>
        <div><a class="nav-link" href="${gearLink}">Apri questi pezzi in Equip</a></div>
      </div>

      <div class="stack">
        ${sampleItems.length ? sampleItems.map((sample) => `
          <div class="kv-row">
            <span>${escapeHtml(sample.slot || sample.item_class || "pezzo")} | ${escapeHtml(sample.rarity || "rarity n/d")} r${escapeHtml(String(sample.rank || 0))} +${escapeHtml(String(sample.level || 0))}</span>
            <strong>${escapeHtml(formatMainStat(sample))}${sample.equipped ? ` | su ${escapeHtml(sample.owner_name || "owner sconosciuto")}` : " | in magazzino"}</strong>
          </div>
        `).join("") : '<div class="empty">Nessun pezzo osservato per questo set.</div>'}
      </div>
    </section>
  `;
}

function getVisibleItems() {
  const items = state.payload?.items || [];
  const search = (curationSearchEl.value || "").trim().toLowerCase();
  const statusFilter = curationStatusEl.value || "all";
  return items.filter((item) => {
    const haystack = `${item.set_name || ""} ${item.display_name || ""} ${item.curation?.canonical_name || ""}`.toLowerCase();
    if (search && !haystack.includes(search)) return false;
    if (statusFilter === "missing" && item.curated) return false;
    if (statusFilter === "curated" && !item.curated) return false;
    return true;
  });
}

function ensureSelection(items) {
  if (!items.length) {
    state.selectedSetName = "";
    return;
  }
  if (!items.some((item) => item.set_name === state.selectedSetName)) {
    state.selectedSetName = items[0].set_name;
  }
}

function renderSummary() {
  const summary = state.payload?.summary || {};
  const items = state.payload?.items || [];
  const curatedCount = items.filter((item) => item.curated).length;
  const missingCount = items.filter((item) => !item.curated && Number(item.inventory?.total_items || 0) > 0).length;
  curationSummaryEl.innerHTML = [
    metricCard("Set Osservati", summary.observed_sets || 0, "presenti nel DB"),
    metricCard("Curati", curatedCount, "con regola locale"),
    metricCard("Da Fare", missingCount, "osservati ma non curati"),
    metricCard("Chiudibili", summary.completable_fixed_sets || 0, "dato inventario"),
  ].join("");
}

function renderList() {
  const items = getVisibleItems();
  ensureSelection(items);
  if (!items.length) {
    curationListEl.innerHTML = '<div class="empty">Nessun set corrisponde ai filtri correnti.</div>';
    curationDetailsEl.innerHTML = '<div class="empty">Nessun set selezionato.</div>';
    return;
  }
  curationListEl.innerHTML = items.map((item) => {
    const active = item.set_name === state.selectedSetName ? " active" : "";
    const curatedPill = item.curated ? '<span class="pill ok">curato</span>' : '<span class="pill warn">da curare</span>';
    const countPill = `<span class="pill">${escapeHtml(String(item.inventory?.total_items || 0))} pezzi</span>`;
    const canonicalSuffix = item.curation?.canonical_name ? ` -> ${escapeHtml(item.curation.canonical_name)}` : "";
    return `
      <button class="champ-row${active}" data-set-name="${escapeHtml(item.set_name)}">
        <div class="champ-topline">
          <div class="champ-name">${escapeHtml(item.display_name || item.set_name)}</div>
          <div class="pillbar">${curatedPill}${countPill}</div>
        </div>
        <div class="subtext">${escapeHtml(item.set_name)}${canonicalSuffix}</div>
      </button>
    `;
  }).join("");

  curationListEl.querySelectorAll("[data-set-name]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSetName = button.getAttribute("data-set-name") || "";
      renderList();
    });
  });

  const selected = items.find((item) => item.set_name === state.selectedSetName) || null;
  renderDetails(selected);
}

function renderDetails(item) {
  if (!item) {
    curationDetailsEl.innerHTML = '<div class="empty">Nessun set selezionato.</div>';
    return;
  }
  const curation = item.curation || {};
  const canonicalSuffix = curation.canonical_name ? ` | Nome corretto: ${escapeHtml(curation.canonical_name)}` : "";
  curationDetailsEl.innerHTML = `
    <section class="detail-hero">
      <div>
        <h2>${escapeHtml(item.display_name || item.set_name)}</h2>
        <p class="subtext">Nome grezzo: ${escapeHtml(item.set_name)}${canonicalSuffix}</p>
      </div>
      <div class="detail-meta">
        <span class="pill">${escapeHtml(String(item.inventory?.total_items || 0))} pezzi</span>
        <span class="pill gold">${escapeHtml(curation.set_kind || item.set_kind || "fixed")}</span>
        ${item.curated ? '<span class="pill ok">regola locale attiva</span>' : '<span class="pill warn">non ancora curato</span>'}
      </div>
    </section>

    ${renderObservedSamples(item)}

    <section class="card">
      <h3>Compilazione</h3>
      <div class="kv single-column">
        <div class="kv-row"><span>Come usarla</span><strong>Puoi copiare il testo quasi com&#39;e. Usa <code>effect:</code> per i bonus non-stat.</strong></div>
        <div class="kv-row"><span>Esempio fixed</span><strong>Base bonus: <code>SPD +12</code> oppure <code>HP% +15; heal_each_turn 3</code></strong></div>
        <div class="kv-row"><span>Esempio variable</span><strong>Soglie: <code>1 | HP% +8</code>, <code>4 | effect: Grants Stone Skin for 1 turn</code></strong></div>
      </div>
      <form id="curationForm" class="stack">
        <div class="grid">
          <div class="card">
            <h3>Identita'</h3>
            <div class="stack">
              <label class="subtext">Nome grezzo osservato
                <input id="setName" name="set_name" value="${escapeHtml(item.set_name)}" readonly>
              </label>
              <label class="subtext">Nome corretto/canonico
                <input id="canonicalName" name="canonical_name" value="${escapeHtml(curation.canonical_name || "")}" placeholder="Es. Bloodshield Accessory">
              </label>
              <label class="subtext">Nome display opzionale
                <input id="displayName" name="display_name" value="${escapeHtml(curation.display_name || "")}" placeholder="Es. Bloodshield">
              </label>
            </div>
          </div>

          <div class="card">
            <h3>Tipo Regola</h3>
            <div class="stack">
              <label class="subtext">Set kind
                <select id="setKind" name="set_kind">
                  <option value="fixed"${(curation.set_kind || "") === "fixed" ? " selected" : ""}>fixed</option>
                  <option value="variable"${(curation.set_kind || "") === "variable" ? " selected" : ""}>variable 1-9</option>
                  <option value="accessory"${(curation.set_kind || "") === "accessory" ? " selected" : ""}>accessory 1-3</option>
                </select>
              </label>
              <label class="subtext">Pezzi richiesti base
                <input id="piecesRequired" name="pieces_required" type="number" min="1" value="${escapeHtml(String(curation.pieces_required || 1))}">
              </label>
              <label class="subtext">Max pezzi
                <input id="maxPieces" name="max_pieces" type="number" min="1" value="${escapeHtml(String(curation.max_pieces || 6))}">
              </label>
              <label class="subtext">Conta accessori
                <select id="countsAccessories" name="counts_accessories">
                  <option value="false"${curation.counts_accessories ? "" : " selected"}>no</option>
                  <option value="true"${curation.counts_accessories ? " selected" : ""}>si</option>
                </select>
              </label>
            </div>
          </div>
        </div>

        <div class="grid">
          <div class="card">
            <h3>Bonus Base</h3>
            <label class="subtext">Usa una riga per bonus. Le stat diventano calcolabili, gli <code>effect:</code> restano effetti speciali.
              <textarea id="baseBonusText" name="base_bonus_text" rows="10" class="mono">${escapeHtml(curation.base_bonus_text || "")}</textarea>
            </label>
          </div>

          <div class="card">
            <h3>Soglie</h3>
            <label class="subtext">Una riga per soglia: <code>pezzi | bonus</code>. Esempio: <code>4 | effect: Grants Stone Skin for 1 turn</code>
              <textarea id="thresholdsText" name="thresholds_text" rows="10" class="mono">${escapeHtml(curation.thresholds_text || "")}</textarea>
            </label>
          </div>
        </div>

        <div class="action-row">
          <button id="saveCurationBtn" type="submit" class="primary">Salva Regola</button>
          <button id="resetCurationBtn" type="button" class="ghost">Ricarica Dati Set</button>
        </div>
      </form>
    </section>
  `;

  const form = document.getElementById("curationForm");
  const setKindEl = document.getElementById("setKind");
  const piecesRequiredEl = document.getElementById("piecesRequired");
  const maxPiecesEl = document.getElementById("maxPieces");
  const countsAccessoriesEl = document.getElementById("countsAccessories");
  const resetBtn = document.getElementById("resetCurationBtn");

  function syncKindDefaults() {
    const kind = setKindEl.value;
    if (kind === "variable") {
      piecesRequiredEl.value = "1";
      if (Number(maxPiecesEl.value || 0) < 9) maxPiecesEl.value = "9";
      countsAccessoriesEl.value = "true";
    } else if (kind === "accessory") {
      piecesRequiredEl.value = "1";
      maxPiecesEl.value = "3";
      countsAccessoriesEl.value = "true";
    } else if (Number(maxPiecesEl.value || 0) <= 0) {
      maxPiecesEl.value = "6";
    }
  }

  setKindEl.addEventListener("change", syncKindDefaults);
  resetBtn.addEventListener("click", () => renderDetails(item));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      set_name: document.getElementById("setName").value,
      canonical_name: document.getElementById("canonicalName").value,
      display_name: document.getElementById("displayName").value,
      set_kind: setKindEl.value,
      pieces_required: Number(piecesRequiredEl.value || 0),
      max_pieces: Number(maxPiecesEl.value || 0),
      counts_accessories: countsAccessoriesEl.value === "true",
      base_bonus_text: document.getElementById("baseBonusText").value,
      thresholds_text: document.getElementById("thresholdsText").value,
    };
    try {
      setStatus(`Salvo ${payload.set_name} e ricostruisco il DB...`);
      await fetchJson("/api/set-curation-save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await loadPayload(payload.set_name);
      setStatus(`Regola salvata per ${payload.set_name}`);
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

async function loadPayload(preferredSetName = "") {
  state.payload = await fetchJson("/api/set-curation");
  if (preferredSetName) state.selectedSetName = preferredSetName;
  renderSummary();
  renderList();
}

curationSearchEl.addEventListener("input", renderList);
curationStatusEl.addEventListener("change", renderList);
curationReloadBtn.addEventListener("click", () => {
  loadPayload(state.selectedSetName).catch((error) => setStatus(error.message, true));
});

loadPayload().catch((error) => setStatus(error.message, true));
