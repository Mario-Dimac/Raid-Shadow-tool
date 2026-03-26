const state = {
  status: null,
  summary: null,
  sessions: [],
  selectedSessionSlug: new URLSearchParams(window.location.search).get("slug") || null,
  sessionDetail: null,
  selectedRunId: null,
  runDetail: null,
  selectedMemberOrder: null,
};

const summaryEl = document.getElementById("runSummary");
const statusEl = document.getElementById("runStatus");
const sessionListEl = document.getElementById("runSessionList");
const detailsEl = document.getElementById("runDetails");
const durationEl = document.getElementById("runDuration");
const intervalEl = document.getElementById("runInterval");
const startBtn = document.getElementById("runStartBtn");
const stopBtn = document.getElementById("runStopBtn");
const importBtn = document.getElementById("runImportBtn");
const importAllBtn = document.getElementById("runImportAllBtn");
const deleteBtn = document.getElementById("runDeleteBtn");
const reloadBtn = document.getElementById("runReloadBtn");

let refreshTimer = null;

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

function setStatus(message, isError = false) {
  statusEl.textContent = message || "";
  statusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
}

function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (!Number.isFinite(value) || value <= 0) return "manuale";
  if (value < 60) return `${Math.round(value)} s`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  return `${(value / 3600).toFixed(value % 3600 === 0 ? 0 : 1)} h`;
}

function kvRow(label, value) {
  return `<div class="kv-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value || "-"))}</strong></div>`;
}

function formatNumber(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric) || numeric <= 0) return "-";
  return numeric.toLocaleString("it-IT");
}

function formatPercent(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric) || numeric <= 0) return "-";
  return `${numeric.toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}%`;
}

function damageLabel(run) {
  if (run?.damage_trusted && Number(run?.total_damage || 0) > 0) {
    return formatNumber(run.total_damage);
  }
  if (Number(run?.total_damage || 0) > 0) {
    return formatNumber(run.total_damage);
  }
  return "non trusted";
}

function formatJsonBlock(value) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch (error) {
    return String(value ?? "");
  }
}

function renderDebugDetails(title, value) {
  return `
    <details class="debug-details">
      <summary>${escapeHtml(title)}</summary>
      <pre class="mono-block">${escapeHtml(formatJsonBlock(value))}</pre>
    </details>
  `;
}

function renderDebugToggle(summaryText, content) {
  return `
    <details class="debug-details" style="margin-top: 12px;">
      <summary>${escapeHtml(summaryText)}</summary>
      <div class="stack" style="margin-top: 12px;">
        ${content}
      </div>
    </details>
  `;
}

function renderEffectTimeline(effectTimeline) {
  const payload = effectTimeline || {};
  const effectTotals = payload.effect_totals || {};
  const timeline = payload.timeline || [];
  const providerByChampion = payload.provider_by_champion || {};
  const providerSummary = Object.entries(providerByChampion).map(([name, provider]) => `${name}: ${provider}`).join(" | ");

  return `
    <section class="card">
      <h3>Timeline Effetti / Turni</h3>
      ${timeline.length ? `
        <div class="kv single-column" style="margin-bottom: 12px;">
          ${kvRow("Status", payload.status_timeline_status || "candidate")}
          ${kvRow("Eventi timeline", payload.timeline_count || timeline.length)}
          ${kvRow("Cast boss/nemico", payload.enemy_skill_event_count || 0)}
          ${kvRow("Eventi con effetti", payload.status_timeline_count || 0)}
          ${kvRow("Eventi raw", payload.event_count || 0)}
          ${kvRow("Provider", providerSummary || "-")}
        </div>
        <div class="grid">
          <div class="card">
            <h3>Effetti Più Visti</h3>
            <div class="list-block">
              ${Object.entries(effectTotals).length ? Object.entries(effectTotals).map(([effectType, count]) => `
                <div class="list-row">
                  <strong>${escapeHtml(effectType)}</strong>
                  <div class="subtext">${escapeHtml(String(count))}</div>
                </div>
              `).join("") : '<div class="empty">Nessun effetto candidato trovato.</div>'}
            </div>
          </div>
          <div class="card">
            <h3>Nota</h3>
            <div class="subtext">
              Timeline candidata costruita da cast order reale + metadata skill provider. Non e' ancora un log trusted di placed, resisted, blocked o extended.
            </div>
          </div>
        </div>
        <div class="list-block scroll-card" style="margin-top: 12px;">
          ${timeline.map((row) => {
            const effects = (row.status_effects || []).map((effect) => {
              const duration = effect.duration ? ` ${effect.duration}t` : "";
              const chance = Number(effect.chance || 0) > 0 ? ` ${effect.chance}%` : "";
              const targets = (effect.candidate_targets || []).map((target) => target.champion_name || `slot ${target.slot_index ?? "-"}`).join(", ");
              return `${effect.action}:${effect.effect_type}${duration}${chance}${targets ? ` -> ${targets}` : ""}`;
            }).join(" | ");
            const rowLabel = row.timeline_kind === "enemy_skill_cast" ? "colpo/skill boss raw" : (effects || "nessun effetto candidato");
            const timingLabel = row.timeline_kind === "enemy_skill_cast"
              ? `turno boss ${row.enemy_turn_index || "?"}`
              : `finestra ${row.turn_window_index || "?"} | prossimo boss tra ${row.actions_until_upcoming_enemy_turn ?? "-"} azioni`;
            return `
              <div class="list-row">
                <strong>T${escapeHtml(String(row.timeline_index || row.event_index))} #${escapeHtml(String(row.event_index))} ${escapeHtml(row.source_name || "-")} ${escapeHtml(row.skill_slot || "-")} ${escapeHtml(row.skill_name || "-")}</strong>
                <div class="subtext">${escapeHtml(rowLabel)}</div>
                <div class="subtext">${escapeHtml(timingLabel)}</div>
                <div class="subtext mono">${escapeHtml(`${row.source_party_role || "-"} -> target party ${row.target_party_id ?? "-"} slot ${row.target_slot ?? "-"}`)}</div>
              </div>
            `;
          }).join("")}
        </div>
        ${renderDebugToggle("Mostra dettagli tecnici timeline", renderDebugDetails("Effect timeline raw", payload))}
      ` : `
        <div class="empty">Timeline buff/debuff non disponibile per questa run o raw asset non sufficiente.</div>
      `}
    </section>
  `;
}

function recorderStatusText() {
  const status = state.status || {};
  if (status.running) {
    return `Recorder attivo su ${status.session_slug} | intervallo ${status.interval_seconds}s | durata ${formatDuration(status.duration_seconds)}`;
  }
  if (status.session_slug) {
    return `Recorder fermo | ultima sessione ${status.session_slug}`;
  }
  return "Recorder fermo.";
}

function renderSummary() {
  const sessions = state.sessions || [];
  const status = state.status || {};
  const summary = state.summary || {};
  const latest = sessions[0] || null;
  summaryEl.innerHTML = [
    metricCard("Recorder", status.running ? "ON" : "OFF", status.running ? `PID ${status.pid || "-"}` : "Inattivo"),
    metricCard("Sessioni", summary.sessions || sessions.length, "Catture salvate in input/client_probe"),
    metricCard("Run", summary.runs || sessions.reduce((sum, item) => sum + Number(item.run_count || 0), 0), "Battle ricostruite"),
    metricCard("Run Nel DB", summary.db_runs || 0, `${summary.db_sessions || 0} sessioni importate`),
    metricCard("Eventi", summary.events || sessions.reduce((sum, item) => sum + Number(item.event_count || 0), 0), "Righe registrate"),
    metricCard("Snapshot", summary.snapshots || sessions.reduce((sum, item) => sum + Number(item.snapshot_count || 0), 0), "File salvati"),
    metricCard(
      "Ultima Run",
      latest?.latest_run?.battle_id?.slice(0, 8) || "-",
      latest?.latest_run?.stage_id ? `Stage ${latest.latest_run.stage_id}` : "Nessuna battle rilevata"
    ),
  ].join("");
}

function renderSessionList() {
  const sessions = state.sessions || [];
  if (!sessions.length) {
    sessionListEl.innerHTML = '<div class="empty">Nessuna sessione catturata finora.</div>';
    return;
  }
  sessionListEl.innerHTML = sessions.map((session) => `
    <button class="champ-row ${state.selectedSessionSlug === session.session_slug ? "active" : ""}" data-session="${escapeHtml(session.session_slug)}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(session.session_slug)}</div>
        <div class="pill">${escapeHtml(String(session.run_count || 0))} run</div>
      </div>
      <div class="subtext">${escapeHtml(session.latest_run?.stage_id ? `Stage ${session.latest_run.stage_id}` : "Nessuna battle strutturata")}</div>
      <div class="pillbar">
        ${session.running ? '<span class="pill ok">Recorder live</span>' : '<span class="pill">Storico</span>'}
        ${session.db_import?.imported ? `<span class="pill ok">DB ${escapeHtml(String(session.db_import.imported_runs || 0))}</span>` : '<span class="pill">Non importata</span>'}
        ${session.latest_run?.boss_name ? `<span class="pill">${escapeHtml(session.latest_run.boss_name)}</span>` : ""}
        ${session.latest_run?.boss_affinity ? `<span class="pill">${escapeHtml(session.latest_run.boss_affinity)}</span>` : ""}
        <span class="pill">${escapeHtml(String(session.event_count || 0))} eventi</span>
        <span class="pill">${escapeHtml(String(session.snapshot_count || 0))} snapshot</span>
        ${session.latest_run?.battle_id ? `<span class="pill gold">${escapeHtml(session.latest_run.battle_id.slice(0, 8))}</span>` : ""}
      </div>
    </button>
  `).join("");
  sessionListEl.querySelectorAll("[data-session]").forEach((button) => {
    button.addEventListener("click", () => selectSession(button.dataset.session));
  });
}

function renderRunList(runs) {
  if (!runs.length) {
    return '<div class="empty">Nessuna run ricostruita dagli eventi della sessione.</div>';
  }
  return runs.map((run) => `
    <div class="list-row">
      <strong>${escapeHtml(run.battle_id || "run")}</strong>
      <div class="subtext">${escapeHtml(run.stage_id ? `Stage ${run.stage_id}` : "Stage n/d")}</div>
      <div class="subtext">${escapeHtml([run.boss_name || run.encounter_name || "", run.boss_affinity || ""].filter(Boolean).join(" | ") || "Boss n/d")}</div>
      <div class="subtext">${escapeHtml((run.team_members || []).join(", ") || "Team n/d")}</div>
      <div class="pillbar" style="margin-top: 8px;">
        <span class="pill gold">${escapeHtml(damageLabel(run))}</span>
        <span class="pill">${escapeHtml(run.started_at || run.first_seen_at || "-")}</span>
        <span class="pill">${escapeHtml(run.finished_at || "-")}</span>
        <span class="pill">${escapeHtml(String(run.event_count || 0))} eventi</span>
        <span class="pill">${escapeHtml(String(run.battle_results_snapshot_count || 0))} result snapshot</span>
        <span class="pill ${run.has_rich_battle_results ? "ok" : ""}">${run.has_rich_battle_results ? "rich result" : "no rich result"}</span>
      </div>
    </div>
  `).join("");
}

function renderDbRunList(runs) {
  if (!runs.length) {
    return '<div class="empty">Nessuna run importata nel DB per questa sessione.</div>';
  }
  return runs.map((run) => `
    <button class="champ-row ${Number(state.selectedRunId) === Number(run.run_id) ? "active" : ""}" data-run-id="${escapeHtml(String(run.run_id))}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(run.battle_id || `Run ${run.run_id}`)}</div>
        <div class="pill">${escapeHtml(String(run.run_id))}</div>
      </div>
      <div class="subtext">${escapeHtml(run.stage_label || run.stage_id || run.encounter_name || "Run DB")}</div>
      <div class="pillbar">
        <span class="pill ${run.success ? "ok" : "warn"}">${run.success ? "Success" : "Fail"}</span>
        <span class="pill gold">${escapeHtml(damageLabel(run))}</span>
        <span class="pill">${escapeHtml(String(run.members || 0))} membri</span>
        <span class="pill">${escapeHtml(String(run.skill_usages || 0))} skill</span>
        <span class="pill">${escapeHtml(run.saved_at || "-")}</span>
      </div>
    </button>
  `).join("");
}

function renderRunMemberList(members) {
  if (!members.length) {
    return '<div class="empty">Nessun membro salvato per questa run.</div>';
  }
  return members.map((member) => `
    <button class="champ-row ${Number(state.selectedMemberOrder) === Number(member.member_order) ? "active" : ""}" data-member-order="${escapeHtml(String(member.member_order))}">
      <div class="champ-topline">
        <div class="champ-name">${escapeHtml(member.champion_name || `Slot ${member.member_order}`)}</div>
        <div class="pill">${escapeHtml(String(member.member_order))}</div>
      </div>
      <div class="subtext">${escapeHtml(`Type ${member.champion_type_id || "-"}`)}</div>
      <div class="pillbar">
        <span class="pill gold">${escapeHtml(formatNumber(member.metrics?.damage_done || 0))}</span>
        <span class="pill">${escapeHtml(`subito ${formatPercent(member.derived?.damage_taken_share_pct || 0)}`)}</span>
        <span class="pill">${escapeHtml(`aggro ${formatPercent(member.derived?.incoming_target_share_pct || 0)}`)}</span>
        <span class="pill">${escapeHtml(String((member.skill_usage || []).reduce((sum, row) => sum + Number(row.usage_count || 0), 0)))} cast</span>
        <span class="pill">${escapeHtml(`boss ${formatPercent(member.derived?.incoming_boss_target_share_pct || 0)}`)}</span>
      </div>
    </button>
  `).join("");
}

function renderSelectedMember(member) {
  if (!member) {
    return '<div class="empty">Seleziona un campione per vedere skill usate e payload raw.</div>';
  }
  const skillUsage = member.skill_usage || [];
  const stats = member.stats || {};
  const metrics = member.metrics || {};
  const pressure = member.pressure || {};
  const derived = member.derived || {};
  const raw = member.raw || {};
  return `
    <section class="grid">
      <div class="card">
        <h3>${escapeHtml(member.champion_name || `Membro ${member.member_order}`)}</h3>
        <div class="kv single-column">
          ${kvRow("Member order", member.member_order)}
          ${kvRow("Type ID", member.champion_type_id || "-")}
          ${kvRow("Livello", member.level || "-")}
          ${kvRow("Rank", member.rank || "-")}
          ${kvRow("Damage done", formatNumber(metrics.damage_done || 0))}
          ${kvRow("% damage done", formatPercent(derived.damage_done_share_pct || 0))}
          ${kvRow("Damage taken", formatNumber(metrics.damage_taken || 0))}
          ${kvRow("% damage taken", formatPercent(derived.damage_taken_share_pct || 0))}
          ${kvRow("Healing done", formatNumber(metrics.healing_done || 0))}
          ${kvRow("% healing", formatPercent(derived.healing_done_share_pct || 0))}
          ${kvRow("Colpi in arrivo", pressure.incoming_target_events || 0)}
          ${kvRow("% colpi in arrivo", formatPercent(derived.incoming_target_share_pct || 0))}
          ${kvRow("Colpi boss", pressure.incoming_boss_target_events || 0)}
          ${kvRow("% focus boss", formatPercent(derived.incoming_boss_target_share_pct || 0))}
          ${kvRow("Raw blue dt", formatNumber(raw.damage_taken || 0))}
          ${kvRow("Raw slot index", raw.slot_index ?? "-")}
        </div>
      </div>
      <div class="card">
        <h3>Skill Usate</h3>
        <div class="list-block">
          ${skillUsage.length ? skillUsage.map((row) => `
            <div class="list-row">
              <strong>${escapeHtml(row.skill_slot || `A${row.skill_order}`)}</strong>
              <div class="subtext">${escapeHtml(`code ${row.skill_code || "-"} | uso ${row.usage_count || 0}`)}</div>
            </div>
          `).join("") : '<div class="empty">Nessuna skill usage salvata.</div>'}
        </div>
      </div>
    </section>
    <section class="grid">
      <div class="card">
        <h3>Pressione In Arrivo</h3>
        <div class="kv single-column">
          ${kvRow("Danno preso effettivo", formatNumber(pressure.effective_damage_taken || 0))}
          ${kvRow("% danno preso", formatPercent(derived.damage_taken_share_pct || 0))}
          ${kvRow("Target event totali", pressure.incoming_target_events || 0)}
          ${kvRow("% target event", formatPercent(derived.incoming_target_share_pct || 0))}
          ${kvRow("Target event boss", pressure.incoming_boss_target_events || 0)}
          ${kvRow("% boss target", formatPercent(derived.incoming_boss_target_share_pct || 0))}
        </div>
      </div>
      <div class="card">
        <h3>Skill In Arrivo</h3>
        <div class="kv single-column">
          ${Object.entries(pressure.incoming_enemy_skill_codes || {}).length ? Object.entries(pressure.incoming_enemy_skill_codes || {}).map(([code, count]) => kvRow(`Enemy skill ${code}`, count)).join("") : '<div class="empty">Nessun codice skill in arrivo salvato.</div>'}
        </div>
      </div>
    </section>
    ${renderDebugToggle(
      "Mostra dettagli tecnici del membro",
      `
        <section class="grid">
          <div class="card">
            <h3>Stats Salvate</h3>
            <pre class="mono-block">${escapeHtml(formatJsonBlock(stats))}</pre>
          </div>
          <div class="card">
            <h3>Metriche Salvate</h3>
            <pre class="mono-block">${escapeHtml(formatJsonBlock(metrics))}</pre>
          </div>
        </section>
        <section class="card">
          <h3>Debug Raw</h3>
          <div class="stack">
            ${renderDebugDetails("Raw member payload", raw.member_payload || {})}
            ${renderDebugDetails("Raw profile payload", raw.profile_payload || {})}
            ${renderDebugDetails("Payload skill usage", skillUsage.map((row) => ({ skill_slot: row.skill_slot, skill_code: row.skill_code, payload: row.payload || {} })))}
            ${renderDebugDetails("Codici skill in arrivo", {
              enemy_skill_codes: pressure.incoming_enemy_skill_codes || {},
              boss_skill_codes: pressure.incoming_boss_skill_codes || {},
            })}
          </div>
        </section>
      `,
    )}
  `;
}

function renderDetails() {
  const detail = state.sessionDetail;
  const status = state.status || {};
  if (!detail) {
    detailsEl.innerHTML = `
      <section class="card">
        <h3>Recorder</h3>
        <div class="subtext">${escapeHtml(recorderStatusText())}</div>
      </section>
      <div class="empty">Seleziona una sessione dalla lista per vedere run, eventi e snapshot.</div>
    `;
    return;
  }

  const metadata = detail.metadata || {};
  const paths = detail.paths || {};
  const recentLogLines = detail.recent_log_lines || [];
  const recentEvents = detail.recent_events || [];
  const snapshots = detail.snapshots || [];
  const runs = detail.runs || [];
  const latestRun = detail.latest_run || runs[0] || {};
  const eventTypeCounts = detail.event_type_counts || {};
  const memberDamage = latestRun.member_damage || [];
  const dbImport = detail.db_import || {};
  const dbRuns = detail.db_runs || [];
  const runDetail = state.runDetail || null;
  const derivedTotals = runDetail?.derived_totals || {};
  const effectTimeline = runDetail?.effect_timeline || {};
  const selectedMember = runDetail?.members?.find((member) => Number(member.member_order) === Number(state.selectedMemberOrder)) || runDetail?.members?.[0] || null;

  detailsEl.innerHTML = `
    <section class="detail-hero">
      <div>
        <div class="eyebrow">Run Recorder</div>
        <h2>${escapeHtml(detail.session_slug)}</h2>
        <div class="detail-meta">
          ${detail.running ? '<span class="pill ok">Recorder attivo</span>' : '<span class="pill">Sessione salvata</span>'}
          <span class="pill">Run ${escapeHtml(String(detail.run_count || 0))}</span>
          <span class="pill">Eventi ${escapeHtml(String(detail.event_count || 0))}</span>
          <span class="pill">Snapshot ${escapeHtml(String(detail.snapshot_count || 0))}</span>
          ${status.pid && detail.running ? `<span class="pill gold">PID ${escapeHtml(String(status.pid))}</span>` : ""}
        </div>
      </div>
      <div class="pillbar">
        <span class="pill">${escapeHtml(metadata.created_at || detail.created_at || "-")}</span>
        <span class="pill">${escapeHtml(detail.last_event_at || "-")}</span>
      </div>
    </section>

    <section class="grid">
      <div class="card">
        <h3>Sessione</h3>
        <div class="kv single-column">
          ${kvRow("Slug", detail.session_slug)}
          ${kvRow("Creata", metadata.created_at || detail.created_at)}
          ${kvRow("Ultimo evento", detail.last_event_at)}
          ${kvRow("Importata nel DB", dbImport.imported ? "si" : "no")}
          ${kvRow("Run importate", dbImport.imported_runs ?? 0)}
          ${kvRow("Pending stimate", dbImport.pending_runs_estimate ?? 0)}
          ${kvRow("Ultimo salvataggio DB", dbImport.latest_saved_at || "-")}
          ${kvRow("Intervallo", metadata.interval || status.interval_seconds || "-")}
          ${kvRow("Durata target", formatDuration(metadata.duration || status.duration_seconds || 0))}
          ${kvRow("Session dir", detail.session_dir)}
        </div>
      </div>
      <div class="card">
        <h3>Dati Salienti Run</h3>
        <div class="kv single-column">
          ${kvRow("Battle ID", latestRun.battle_id || "-")}
          ${kvRow("Boss", latestRun.boss_name || latestRun.encounter_name || "-")}
          ${kvRow("Affinity", latestRun.boss_affinity || "-")}
          ${kvRow("Stage", latestRun.stage_id || "-")}
          ${kvRow("Formation", latestRun.formation_index ?? "-")}
          ${kvRow("Team", (latestRun.team_members || []).join(", ") || "-")}
          ${kvRow("Start", latestRun.started_at || latestRun.first_seen_at || "-")}
          ${kvRow("Result detect", latestRun.result_detected_at || "-")}
          ${kvRow("Finish", latestRun.finished_at || "-")}
          ${kvRow("Total damage", damageLabel(latestRun))}
          ${kvRow("Rich battleResults", latestRun.has_rich_battle_results ? "si" : "no")}
          ${kvRow("Best result size", latestRun.best_battle_results_size || "-")}
        </div>
      </div>
    </section>

    <section class="card">
      <h3>Danno Per Campione</h3>
      <div class="list-block">
        ${latestRun.damage_trusted && memberDamage.length ? memberDamage.map((row, index) => `
          <div class="list-row">
            <strong>${escapeHtml((latestRun.team_members || [])[index] || `Slot ${row.member_order || index + 1}`)}</strong>
            <div class="subtext">Type ID ${escapeHtml(String(row.champion_type_id || "-"))}</div>
            <div class="pillbar" style="margin-top: 8px;">
              <span class="pill gold">${escapeHtml(formatNumber(row.damage_done))}</span>
            </div>
          </div>
        `).join("") : `<div class="empty">${escapeHtml(latestRun.damage_note || "Danno non disponibile: decoder non ancora trusted.")}</div>`}
      </div>
    </section>

    <section class="card">
      <h3>Run Nel DB</h3>
      <div class="list-block">
        ${renderDbRunList(dbRuns)}
      </div>
    </section>

    <section class="card">
      <h3>Run Catturate</h3>
      <div class="list-block">
        ${renderRunList(runs)}
      </div>
    </section>

    <section class="card">
      <h3>Dettaglio Run DB</h3>
      ${runDetail ? `
        <div class="kv single-column" style="margin-bottom: 12px;">
          ${kvRow("Run ID", runDetail.run?.run_id || "-")}
          ${kvRow("Battle ID", runDetail.run?.battle_id || "-")}
          ${kvRow("Stage", runDetail.run?.stage_label || runDetail.run?.stage_id || "-")}
          ${kvRow("Encounter", runDetail.run?.encounter_name || runDetail.run?.encounter_key || "-")}
          ${kvRow("Saved at", runDetail.run?.saved_at || "-")}
          ${kvRow("Tot danno team", formatNumber(derivedTotals.damage_done || 0))}
          ${kvRow("Tot cure team", formatNumber(derivedTotals.healing_done || 0))}
          ${kvRow("Tot danno preso", formatNumber(derivedTotals.damage_taken || 0))}
          ${kvRow("Colpi in arrivo", derivedTotals.incoming_target_events || 0)}
          ${kvRow("Colpi boss", derivedTotals.incoming_boss_target_events || 0)}
          ${kvRow("Raw asset", runDetail.raw_asset_path || "-")}
        </div>
        <div class="grid">
          <div class="card">
            <h3>Membri</h3>
            <div class="list-block">
              ${renderRunMemberList(runDetail.members || [])}
            </div>
          </div>
          <div class="card">
            <h3>Riepilogo Run</h3>
            <div class="kv single-column">
              ${kvRow("Membri salvati", (runDetail.members || []).length)}
              ${kvRow("Asset salvati", (runDetail.assets || []).length)}
              ${kvRow("Tot cast skill", derivedTotals.skill_casts || 0)}
              ${kvRow("Tot danno team", formatNumber(derivedTotals.damage_done || 0))}
              ${kvRow("Tot cure team", formatNumber(derivedTotals.healing_done || 0))}
              ${kvRow("Tot danno preso", formatNumber(derivedTotals.damage_taken || 0))}
              ${kvRow("Tot colpi in arrivo", derivedTotals.incoming_target_events || 0)}
              ${kvRow("Tot colpi boss", derivedTotals.incoming_boss_target_events || 0)}
            </div>
          </div>
        </div>
        ${renderSelectedMember(selectedMember)}
        ${renderEffectTimeline(effectTimeline)}
        ${renderDebugToggle(
          "Mostra dettagli tecnici della run",
          `
            ${renderDebugDetails("Run / context", { run: runDetail.run || {}, derived_totals: derivedTotals || {}, effect_timeline_status: effectTimeline.status_timeline_status || "" })}
            ${renderDebugDetails("Assets", runDetail.assets || [])}
          `,
        )}
      ` : '<div class="empty">Seleziona una battaglia importata nel DB per vedere skill usage e raw per campione.</div>'}
    </section>

    <section class="grid">
      <div class="card">
        <h3>Paths</h3>
        <div class="stack">
          <pre class="mono-block">${escapeHtml([paths.session_json, paths.events_jsonl, paths.log_capture].filter(Boolean).join("\n"))}</pre>
        </div>
      </div>
      <div class="card">
        <h3>Conteggio Eventi</h3>
        <div class="list-block scroll-card">
          ${Object.entries(eventTypeCounts).length ? Object.entries(eventTypeCounts).map(([key, value]) => `
            <div class="list-row">
              <strong>${escapeHtml(key)}</strong>
              <div class="subtext">${escapeHtml(String(value))}</div>
            </div>
          `).join("") : '<div class="empty">Nessun evento salvato.</div>'}
        </div>
      </div>
    </section>

    <section class="grid">
      <div class="card">
        <h3>Recent Log Lines</h3>
        <div class="stack scroll-card">
          ${recentLogLines.length ? `<pre class="mono-block">${escapeHtml(recentLogLines.join("\n"))}</pre>` : '<div class="empty">Nessuna log line interessante.</div>'}
        </div>
      </div>
      <div class="card">
        <h3>Recent Events</h3>
        <div class="list-block scroll-card">
          ${recentEvents.length ? recentEvents.map((event) => `
            <div class="list-row">
              <strong>${escapeHtml(String(event.event_type || "event"))}</strong>
              <div class="subtext mono">${escapeHtml(String(event.captured_at || "-"))}</div>
              <div class="subtext">${escapeHtml(event.line || event.source_name || event.reason || "")}</div>
            </div>
          `).join("") : '<div class="empty">Nessun evento recente.</div>'}
        </div>
      </div>
    </section>

    <section class="card">
      <h3>Snapshots</h3>
      <div class="list-block scroll-card">
        ${snapshots.length ? snapshots.map((row) => `
          <div class="list-row">
            <strong>${escapeHtml(row.relative_path || row.file_name || "snapshot")}</strong>
            <div class="subtext">${escapeHtml(`${row.root_name || "snapshots"} | ${row.size_bytes || 0} byte | ${row.modified_at || "-"}`)}</div>
            <div class="subtext mono">${escapeHtml(row.path || "")}</div>
          </div>
        `).join("") : '<div class="empty">Nessun file snapshot salvato.</div>'}
      </div>
    </section>
  `;

  detailsEl.querySelectorAll("[data-run-id]").forEach((button) => {
    button.addEventListener("click", () => selectRun(button.dataset.runId));
  });
  detailsEl.querySelectorAll("[data-member-order]").forEach((button) => {
    button.addEventListener("click", () => selectMember(button.dataset.memberOrder));
  });
}

function syncButtons() {
  const running = Boolean(state.status?.running);
  startBtn.disabled = running;
  stopBtn.disabled = !running;
  const selectedSession = state.selectedSessionSlug || "";
  const deletingRunningSession = running && selectedSession && state.status?.session_slug === selectedSession;
  const importingRunningSession = running && selectedSession && state.status?.session_slug === selectedSession;
  importBtn.disabled = !selectedSession || importingRunningSession;
  importAllBtn.disabled = false;
  deleteBtn.disabled = !selectedSession || deletingRunningSession;
}

async function loadSessions() {
  const payload = await fetchJson("/api/run-recorder-sessions");
  state.status = payload.status || {};
  state.summary = payload.summary || {};
  state.sessions = payload.sessions || [];
  if (!state.selectedSessionSlug) {
    state.selectedSessionSlug = state.status.session_slug || state.sessions[0]?.session_slug || null;
  } else if (!state.sessions.some((session) => session.session_slug === state.selectedSessionSlug)) {
    state.selectedSessionSlug = state.status.session_slug || state.sessions[0]?.session_slug || null;
  }
}

async function loadSessionDetail() {
  if (!state.selectedSessionSlug) {
    state.sessionDetail = null;
    return;
  }
  state.sessionDetail = await fetchJson(`/api/run-recorder-session?slug=${encodeURIComponent(state.selectedSessionSlug)}`);
}

async function loadRunDetail() {
  if (!state.selectedRunId) {
    state.runDetail = null;
    return;
  }
  state.runDetail = await fetchJson(`/api/run-history-run?run_id=${encodeURIComponent(state.selectedRunId)}`);
  const members = state.runDetail?.members || [];
  if (!members.some((member) => Number(member.member_order) === Number(state.selectedMemberOrder))) {
    state.selectedMemberOrder = members[0]?.member_order || null;
  }
}

async function reloadAll() {
  await loadSessions();
  await loadSessionDetail();
  const dbRuns = state.sessionDetail?.db_runs || [];
  if (!state.selectedRunId || !dbRuns.some((run) => Number(run.run_id) === Number(state.selectedRunId))) {
    state.selectedRunId = dbRuns[0]?.run_id || null;
  }
  await loadRunDetail();
  setStatus(recorderStatusText());
  renderSummary();
  renderSessionList();
  renderDetails();
  syncButtons();
  updateUrl();
  refreshAutoPoll();
}

function updateUrl() {
  const url = new URL(window.location.href);
  if (state.selectedSessionSlug) url.searchParams.set("slug", state.selectedSessionSlug);
  else url.searchParams.delete("slug");
  window.history.replaceState({}, "", url);
}

async function selectSession(sessionSlug) {
  state.selectedSessionSlug = sessionSlug || null;
  state.selectedRunId = null;
  state.selectedMemberOrder = null;
  await loadSessionDetail();
  const dbRuns = state.sessionDetail?.db_runs || [];
  state.selectedRunId = dbRuns[0]?.run_id || null;
  await loadRunDetail();
  renderSessionList();
  renderDetails();
  updateUrl();
}

async function selectRun(runId) {
  state.selectedRunId = runId || null;
  state.selectedMemberOrder = null;
  await loadRunDetail();
  renderDetails();
}

function selectMember(memberOrder) {
  state.selectedMemberOrder = Number(memberOrder || 0) || null;
  renderDetails();
}

async function startRecorder() {
  setStatus("Avvio recorder in corso...");
  await fetchJson("/api/run-recorder-start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      duration_seconds: Number(durationEl.value || 0),
      interval_seconds: Number(intervalEl.value || 0.35),
    }),
  });
  await reloadAll();
}

async function stopRecorder() {
  setStatus("Arresto recorder in corso...");
  const payload = await fetchJson("/api/run-recorder-stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  const importedRuns = Number(payload?.import_summary?.imported_runs || 0);
  const skippedRuns = Number(payload?.import_summary?.skipped_runs || 0);
  if (payload?.import_summary?.session_slug) {
    setStatus(`Recorder fermato. Import DB: ${importedRuns} nuove run, ${skippedRuns} gia' presenti.`);
  }
  await reloadAll();
}

async function importSelectedSession() {
  const sessionSlug = state.selectedSessionSlug || "";
  if (!sessionSlug) {
    throw new Error("Nessuna sessione selezionata.");
  }
  setStatus(`Import DB della sessione ${sessionSlug} in corso...`);
  const payload = await fetchJson("/api/run-recorder-import-session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_slug: sessionSlug }),
  });
  const result = payload.result || {};
  setStatus(`Import completato per ${sessionSlug}: ${Number(result.imported_runs || 0)} nuove run, ${Number(result.skipped_runs || 0)} gia' presenti.`);
  await reloadAll();
}

async function importAllSessions() {
  setStatus("Import DB di tutte le sessioni in corso...");
  const payload = await fetchJson("/api/run-recorder-import-all", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const result = payload.result || {};
  setStatus(`Import totale completato: ${Number(result.imported_runs || 0)} nuove run, ${Number(result.skipped_runs || 0)} gia' presenti.`);
  await reloadAll();
}

async function deleteSelectedSession() {
  const sessionSlug = state.selectedSessionSlug || "";
  if (!sessionSlug) {
    throw new Error("Nessuna sessione selezionata.");
  }
  const confirmed = window.confirm(`Eliminare la sessione ${sessionSlug}? Questa operazione cancella i file salvati su disco.`);
  if (!confirmed) {
    return;
  }
  setStatus(`Eliminazione sessione ${sessionSlug} in corso...`);
  await fetchJson("/api/run-recorder-delete-session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_slug: sessionSlug }),
  });
  state.selectedSessionSlug = null;
  await reloadAll();
}

function refreshAutoPoll() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (state.status?.running) {
    refreshTimer = setInterval(() => {
      reloadAll().catch((error) => setStatus(error.message || "Errore aggiornando il recorder.", true));
    }, 4000);
  }
}

startBtn.addEventListener("click", () => {
  startRecorder().catch((error) => setStatus(error.message || "Errore avviando il recorder.", true));
});

stopBtn.addEventListener("click", () => {
  stopRecorder().catch((error) => setStatus(error.message || "Errore fermando il recorder.", true));
});

importBtn.addEventListener("click", () => {
  importSelectedSession().catch((error) => setStatus(error.message || "Errore importando la sessione nel DB.", true));
});

importAllBtn.addEventListener("click", () => {
  importAllSessions().catch((error) => setStatus(error.message || "Errore importando le sessioni nel DB.", true));
});

reloadBtn.addEventListener("click", () => {
  reloadAll().catch((error) => setStatus(error.message || "Errore ricaricando lo stato.", true));
});

deleteBtn.addEventListener("click", () => {
  deleteSelectedSession().catch((error) => setStatus(error.message || "Errore eliminando la sessione.", true));
});

reloadAll().catch((error) => {
  setStatus(error.message || "Errore caricando il recorder.", true);
});
