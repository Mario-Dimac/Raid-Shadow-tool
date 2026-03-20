from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from typing import Any, Dict

from cb_teams import available_bosses, recommend_for_boss
from cb_simulator import (
    available_clan_boss_affinities,
    available_clan_boss_levels,
    build_clan_boss_survival_plan,
    recommend_clan_boss_options,
    simulate_clan_boss_affinity_matrix,
    simulate_best_clan_boss_team,
)
from cb_run_history import (
    cancel_run_session,
    get_active_run_session,
    list_manual_runs,
    manual_run_summary,
    refresh_active_run_session,
    save_manual_run,
    start_run_session,
    stop_run_session,
)
from cb_sqlite_db import rebuild_registry_database, sqlite_status
from cb_live_monitor import build_initial_live_monitor_state, refresh_live_monitor
from cb_battle_results import (
    BATTLE_RESULTS_PATH,
    MIN_USEFUL_BATTLE_RESULT_SIZE,
    capture_battle_result_snapshot,
)
from hellhades_live import HellHadesEquipError, equip_artifacts_live
from loadout_snapshot import ensure_current_loadout_snapshot, save_current_loadout_snapshot, snapshot_status


BASE_DIR = Path(__file__).resolve().parent
RAW_PATH = BASE_DIR / "input" / "raw_account.json"
NORMALIZED_PATH = BASE_DIR / "input" / "normalized_account.json"
GLOBAL_LIVE_COMBAT_STATE: Dict[str, Any] = {
    "live_monitor": build_initial_live_monitor_state(),
    "live_feed": [],
    "live_summary": {},
}
GLOBAL_LIVE_COMBAT_LOCK = threading.Lock()
BATTLE_RESULT_WATCH_STATE: Dict[str, Any] = {
    "last_seen_signature": "",
    "last_captured_signature": "",
    "last_captured_sha256": "",
    "last_size": 0,
    "last_mtime_ns": 0,
    "last_change_monotonic": 0.0,
}


def empty_battle_result_watch_state() -> Dict[str, Any]:
    return {
        "last_seen_signature": "",
        "last_captured_signature": "",
        "last_captured_sha256": "",
        "last_size": 0,
        "last_mtime_ns": 0,
        "last_change_monotonic": 0.0,
    }


def reset_live_combat_runtime_state() -> None:
    global GLOBAL_LIVE_COMBAT_STATE, BATTLE_RESULT_WATCH_STATE
    with GLOBAL_LIVE_COMBAT_LOCK:
        GLOBAL_LIVE_COMBAT_STATE = {
            "live_monitor": build_initial_live_monitor_state(),
            "live_feed": [],
            "live_summary": {},
        }
    BATTLE_RESULT_WATCH_STATE = empty_battle_result_watch_state()
SERVER_RUNTIME_STATE: Dict[str, Any] = {
    "pid": os.getpid(),
    "started_at": "",
    "boot_monotonic": time.monotonic(),
    "host": "",
    "port": 0,
    "shutdown_requested": False,
}


HTML = """<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CB Forge Control</title>
  <style>
    :root {
      --bg: #0e1116;
      --panel: #171c24;
      --panel-2: #212835;
      --text: #f2ede3;
      --muted: #b2a792;
      --accent: #dc8d18;
      --accent-2: #f2b84a;
      --danger: #d65b4a;
      --ok: #5db06b;
      --border: #3a4354;
    }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top, rgba(220, 141, 24, 0.18), transparent 35%),
        linear-gradient(180deg, #0c1016, #101722 60%, #0d1219);
      color: var(--text);
      min-height: 100vh;
    }
    .wrap {
      max-width: 960px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }
    .hero {
      padding: 24px;
      border: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(23, 28, 36, 0.95), rgba(18, 23, 31, 0.95));
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 40px;
      letter-spacing: 0.03em;
    }
    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 20px;
    }
    .quick-help {
      margin-top: 16px;
      padding: 14px 16px;
      border: 1px solid var(--border);
      background: rgba(16, 22, 30, 0.72);
    }
    .quick-help strong {
      display: block;
      margin-bottom: 8px;
      color: var(--accent-2);
    }
    .quick-help .small {
      margin-top: 6px;
    }
    .boss-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
      align-items: center;
    }
    select {
      border: 1px solid var(--border);
      background: var(--panel-2);
      color: var(--text);
      padding: 12px 14px;
      min-width: 260px;
    }
    button {
      border: 1px solid var(--accent);
      background: linear-gradient(180deg, var(--accent-2), var(--accent));
      color: #22170a;
      font-weight: bold;
      padding: 12px 18px;
      cursor: pointer;
      min-width: 160px;
      transition: opacity 120ms ease, transform 120ms ease, filter 120ms ease;
    }
    button:hover:not(:disabled) {
      transform: translateY(-1px);
      filter: brightness(1.03);
    }
    button.secondary {
      border-color: var(--border);
      background: var(--panel-2);
      color: var(--text);
    }
    button:disabled {
      cursor: wait;
      opacity: 0.72;
    }
    button.busy {
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-top: 22px;
    }
    .card {
      padding: 18px;
      border: 1px solid var(--border);
      background: rgba(23, 28, 36, 0.92);
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .value {
      margin-top: 8px;
      font-size: 28px;
    }
    .log {
      margin-top: 20px;
      white-space: pre-wrap;
      border: 1px solid var(--border);
      background: rgba(12, 16, 22, 0.95);
      padding: 16px;
      min-height: 180px;
      line-height: 1.5;
    }
    .ok { color: var(--ok); }
    .err { color: var(--danger); }
    .warn { color: var(--accent-2); }
    .results {
      margin-top: 20px;
      display: grid;
      gap: 16px;
    }
    .team {
      border: 1px solid var(--border);
      background: rgba(23, 28, 36, 0.92);
      padding: 18px;
    }
    details.timeline {
      margin-top: 16px;
      border: 1px solid var(--border);
      background: rgba(12, 16, 22, 0.92);
      padding: 10px 12px;
    }
    details.timeline summary {
      cursor: pointer;
      color: var(--accent-2);
      font-weight: bold;
    }
    .team h3 {
      margin: 0 0 6px;
      font-size: 24px;
    }
    .small {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }
    .champ-list {
      margin-top: 14px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }
    .champ {
      border: 1px solid var(--border);
      background: rgba(12, 16, 22, 0.95);
      padding: 12px;
    }
    .champ strong {
      display: block;
      margin-bottom: 6px;
    }
    .manual-run {
      margin-top: 18px;
      padding: 18px;
      border: 1px solid var(--border);
      background: rgba(23, 28, 36, 0.92);
    }
    .manual-run input,
    .manual-run textarea {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--border);
      background: var(--panel-2);
      color: var(--text);
      padding: 10px 12px;
      margin-top: 8px;
    }
    .manual-run textarea {
      min-height: 84px;
      resize: vertical;
    }
    .inline-input {
      min-width: 280px;
      box-sizing: border-box;
      border: 1px solid var(--border);
      background: var(--panel-2);
      color: var(--text);
      padding: 12px 14px;
    }
    .session-status {
      margin-top: 12px;
      color: var(--muted);
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .live-feed {
      margin-top: 14px;
      white-space: pre-wrap;
      border: 1px solid var(--border);
      background: rgba(12, 16, 22, 0.95);
      padding: 14px;
      min-height: 140px;
      line-height: 1.5;
      color: var(--text);
      font-size: 14px;
    }
    .gear-lines {
      white-space: pre-wrap;
    }
    .cycle-debug {
      margin-top: 14px;
      display: grid;
      gap: 8px;
    }
    .cycle-row {
      border: 1px solid var(--border);
      background: rgba(12, 16, 22, 0.95);
      padding: 10px 12px;
    }
    .cycle-row strong {
      display: block;
      margin-bottom: 4px;
    }
    .advisory {
      margin-top: 10px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      background: rgba(12, 16, 22, 0.92);
    }
    .advisory.red {
      border-color: var(--danger);
      color: #ffd7d1;
    }
    .advisory.yellow {
      border-color: var(--accent-2);
      color: #ffe5ae;
    }
    .advisory.green {
      border-color: var(--ok);
      color: #d5f5dc;
    }
    .fallback-note {
      margin-top: 10px;
      padding: 10px 12px;
      border: 1px dashed var(--accent-2);
      background: rgba(34, 26, 8, 0.35);
      color: #ffe5ae;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>CB Forge Control</h1>
      <p>Comandi locali per leggere RAID, rigenerare i dump e controllare al volo quanti campioni e pezzi di equipaggiamento sono stati trovati.</p>
      <div class="boss-row">
        <select id="bossSelect"></select>
        <button onclick="recommendTeam(this)">Consiglia team</button>
        <button class="secondary" onclick="checkRecommendedTeam(this)">Controlla assetto team</button>
      </div>
      <div class="boss-row">
        <select id="cbDifficulty"></select>
        <select id="cbAffinity"></select>
        <input id="cbTurns" type="number" min="24" step="6" value="300" placeholder="Turni boss target" />
        <button class="secondary" onclick="simulateClanBoss(this)">Prepara team CB</button>
      </div>
      <div class="actions">
        <button onclick="runAction('/api/refresh-gear', this, 'Aggiorno equip...')">Aggiorna elenco equipaggiamento</button>
        <button class="secondary" onclick="runAction('/api/save-loadout', this, 'Salvataggio...')">Salva snapshot equip</button>
        <button class="secondary" onclick="runAction('/api/sync', this, 'Sync in corso...')">Aggiorna dati account</button>
        <button class="secondary" onclick="runAction('/api/extract', this, 'Estrazione in corso...')">Estrai dump grezzo</button>
        <button class="secondary" onclick="runAction('/api/normalize', this, 'Normalizzazione in corso...')">Normalizza dump</button>
        <button class="secondary" onclick="refreshStatus(this)">Aggiorna contatori</button>
        <button class="secondary" onclick="loadDiagnostics(this)">Diagnostica tecnica</button>
      </div>
      <div class="quick-help">
        <strong>Guida rapida</strong>
        <div class="small"><b>Aggiorna elenco equipaggiamento</b>: e il bottone giusto da usare di solito. Legge i dati da RAID, aggiorna il dump normalizzato e salva una snapshot locale dell'equip.</div>
        <div class="small"><b>Salva snapshot equip</b>: salva solo una copia locale dell'assetto che CB Forge conosce gia, senza rileggere il gioco.</div>
        <div class="small"><b>Aggiorna dati account</b>: rifa l'aggiornamento account standard da RAID. Gli altri due pulsanti <b>Estrai dump grezzo</b> e <b>Normalizza dump</b> sono piu tecnici e servono solo se vuoi fare i passaggi separati.</div>
      </div>
      <div class="manual-run">
        <div class="label">HellHades Live</div>
        <p>Token usato solo per inviare il comando live di equip a HellHades. Il bottone appare sui singoli campioni consigliati.</p>
        <div class="boss-row">
          <input id="hhToken" class="inline-input" type="password" placeholder="Token HellHades opzionale: se vuoto provo a leggerlo da Edge" oninput="persistHellHadesToken()" />
          <button class="secondary" onclick="clearHellHadesToken()">Pulisci token</button>
        </div>
      </div>
    </section>
    <section class="grid" id="stats"></section>
    <section class="manual-run">
      <div class="label">Run o Test Reale</div>
      <div class="boss-row">
        <select id="savedTeamSelect">
          <option value="">Seleziona un team salvato</option>
        </select>
        <button class="secondary" onclick="applySavedTeam(this)">Usa team salvato</button>
      </div>
      <input id="manualTeamName" placeholder="Nome team o test" />
      <div class="grid">
        <input id="manualDamage" type="number" min="1" step="0.1" placeholder="Danno finale, se disponibile" />
      </div>
      <div class="grid">
        <input id="manualMember1" placeholder="Campione 1" />
        <input id="manualMember2" placeholder="Campione 2" />
        <input id="manualMember3" placeholder="Campione 3" />
        <input id="manualMember4" placeholder="Campione 4" />
        <input id="manualMember5" placeholder="Campione 5" />
      </div>
      <details class="timeline">
        <summary>Dettagli opzionali</summary>
        <div class="grid">
          <input id="manualBossTurn" type="number" min="1" step="1" placeholder="Turno finale, se riesci a leggerlo" />
        </div>
        <textarea id="manualNotes" placeholder="Note libere: auto/manual, errori, target, fase, timing..."></textarea>
        <textarea id="manualTurnLog" placeholder="Eventi reali, uno per riga, solo se vuoi annotarli a mano"></textarea>
      </details>
      <div class="actions">
        <button onclick="startRunRecording(this)">Avvia registrazione run</button>
        <button onclick="stopRunRecording(this)">Ferma e salva run</button>
        <button class="secondary" onclick="cancelRunRecording(this)">Annulla test</button>
        <button class="secondary" onclick="saveManualRun(this)">Salva run reale</button>
        <button class="secondary" onclick="loadManualRuns(this)">Aggiorna storico</button>
      </div>
      <div class="session-status" id="runSessionStatus">Nessuna registrazione attiva.</div>
      <div class="live-feed" id="liveFeed">Feed live inattivo.</div>
    </section>
    <section class="results" id="results"></section>
    <section class="results" id="history"></section>
    <section class="log" id="log">Caricamento stato...</section>
  </div>
  <script>
    let bossOptions = [];
    let currentSimulationData = null;
    let currentRecommendations = [];
    let savedTeams = [];
    let liveFeedTimer = null;

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Richiesta fallita');
      }
      return data;
    }

    function setButtonBusy(button, busy, busyLabel) {
      if (!button) {
        return;
      }
      if (busy) {
        if (!button.dataset.idleLabel) {
          button.dataset.idleLabel = button.textContent;
        }
        button.dataset.busy = '1';
        button.disabled = true;
        button.classList.add('busy');
        button.textContent = busyLabel || 'Operazione...';
        return;
      }
      button.dataset.busy = '0';
      button.disabled = false;
      button.classList.remove('busy');
      if (button.dataset.idleLabel) {
        button.textContent = button.dataset.idleLabel;
      }
    }

    async function runWithButtonFeedback(button, busyLabel, work) {
      if (button?.dataset?.busy === '1') {
        return;
      }
      setButtonBusy(button, true, busyLabel);
      try {
        return await work();
      } finally {
        setButtonBusy(button, false);
      }
    }

    function renderStats(data) {
      const stats = [
        ['Campioni grezzi', data.raw?.champions ?? 0],
        ['Equip grezzo', data.raw?.gear ?? 0],
        ['Bonus grezzi', data.raw?.bonuses ?? 0],
        ['Campioni normalizzati', data.normalized?.champions ?? 0],
        ['Equip normalizzato', data.normalized?.gear ?? 0],
        ['Bonus normalizzati', data.normalized?.bonuses ?? 0],
        ['Backup loadout', data.loadout_snapshot?.count ?? 0],
      ];
      document.getElementById('stats').innerHTML = stats.map(([label, value]) => `
        <div class="card">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
        </div>
      `).join('');
    }

    function renderLog(lines, cssClass) {
      const log = document.getElementById('log');
      log.className = 'log ' + (cssClass || '');
      log.textContent = lines;
    }

    function renderBosses(data) {
      bossOptions = data.bosses || [];
      const select = document.getElementById('bossSelect');
      select.innerHTML = bossOptions.map(boss => `
        <option value="${boss.key}">${boss.label}</option>
      `).join('');
    }

    function renderClanBossConfig(data) {
      const difficulty = document.getElementById('cbDifficulty');
      const affinity = document.getElementById('cbAffinity');
      difficulty.innerHTML = (data.levels || []).map(level => `
        <option value="${level.key}">${level.label}</option>
      `).join('');
      affinity.innerHTML = (data.affinities || []).map(item => `
        <option value="${item.key}">${item.label}</option>
      `).join('');
      difficulty.value = 'ultra_nightmare';
      affinity.value = 'void';
    }

    function prettifyStatType(type) {
      const labels = {
        hp: 'HP',
        hp_pct: 'HP%',
        atk: 'ATK',
        atk_pct: 'ATK%',
        def: 'DEF',
        def_pct: 'DEF%',
        spd: 'SPD',
        crit_rate: 'CRate',
        crit_dmg: 'CDmg',
        acc: 'ACC',
        res: 'RES',
      };
      return labels[String(type || '')] || String(type || '').toUpperCase();
    }

    function formatStatValue(stat) {
      if (!stat || !stat.type) {
        return '';
      }
      const rawValue = Number(stat.value || 0);
      const value = Number.isFinite(rawValue) ? rawValue : 0;
      const normalized = value > 0 && value <= 1 && ['hp_pct', 'atk_pct', 'def_pct', 'acc', 'res'].includes(String(stat.type || ''))
        ? value * 100
        : value;
      const rounded = Number.isInteger(normalized) ? normalized : Number(normalized.toFixed(1));
      return `${prettifyStatType(stat.type)} ${rounded}`;
    }

    function formatSubstats(item) {
      const parts = (item?.substats || [])
        .map(formatStatValue)
        .filter(Boolean);
      return parts.length ? parts.join(', ') : 'sub n/d';
    }

    function formatItemFingerprint(item) {
      const parts = [
        item.required_faction || '',
        item.set_name || 'No Set',
        item.rarity || '',
        item.rank ? `${item.rank}*` : '',
        Number.isFinite(Number(item.level)) ? `+${item.level}` : '',
        formatStatValue(item.main_stat),
      ].filter(Boolean);
      return parts.join(' | ');
    }

    function formatGearItem(item) {
      const equippedBy = item.equipped_by_name ? ` da ${item.equipped_by_name}` : ' libero';
      const swap = item.needs_swap ? ' | swap' : '';
      const fingerprint = formatItemFingerprint(item);
      return `${item.slot}: ${fingerprint} | sub ${formatSubstats(item)} | #${item.item_id}${equippedBy}${swap} [${item.why}]`;
    }

    function getMemberArtifactIdsForEquip(member) {
      return (member?.gear_plan || [])
        .filter(item => item?.item_id && item?.equipped_by !== member?.champ_id)
        .map(item => String(item.item_id));
    }

    function getMemberConfirmedSwapIds(member) {
      return (member?.gear_plan || [])
        .filter(item => item?.item_id && item?.equipped_by && item?.equipped_by !== member?.champ_id)
        .map(item => String(item.item_id));
    }

    function getMemberUnconfirmedIds(member) {
      return (member?.gear_plan || [])
        .filter(item => item?.item_id && !item?.equipped_by)
        .map(item => String(item.item_id));
    }

    function countReadyGear(member) {
      return (member?.gear_plan || []).filter(item => item?.equipped_by === member?.champ_id).length;
    }

    function countSwapGear(member) {
      return (member?.gear_plan || []).filter(item => item?.equipped_by && item?.equipped_by !== member?.champ_id).length;
    }

    function countUnconfirmedGear(member) {
      return (member?.gear_plan || []).filter(item => !item?.equipped_by).length;
    }

    function summarizeMemberGear(member) {
      const total = (member?.gear_plan || []).length;
      const ready = countReadyGear(member);
      const swaps = countSwapGear(member);
      const unconfirmed = countUnconfirmedGear(member);
      return {
        total,
        ready,
        swaps,
        unconfirmed,
      };
    }

    function summarizeOptionGear(option) {
      const members = option?.members || [];
      const total = members.reduce((sum, member) => sum + summarizeMemberGear(member).total, 0);
      const ready = members.reduce((sum, member) => sum + summarizeMemberGear(member).ready, 0);
      const swaps = members.reduce((sum, member) => sum + summarizeMemberGear(member).swaps, 0);
      const unconfirmed = members.reduce((sum, member) => sum + summarizeMemberGear(member).unconfirmed, 0);
      return {
        total,
        ready,
        swaps,
        unconfirmed,
      };
    }

    function renderMember(member, optionIndex, memberIndex) {
      const targetStats = (member.target_stats || []).join(', ');
      const gearPlan = (member.gear_plan || []).map(formatGearItem).join('\\n') || 'n/d';
      const artifactIds = getMemberArtifactIdsForEquip(member);
      const confirmedSwapIds = getMemberConfirmedSwapIds(member);
      const unconfirmedIds = getMemberUnconfirmedIds(member);
      const gearSummary = summarizeMemberGear(member);
      const buttonLabel = confirmedSwapIds.length
        ? 'Applica Piano In-Game'
        : (unconfirmedIds.length ? 'Reinvia Piano' : 'Gia confermato');
      return `
        <div class="champ">
          <strong>${member.name}</strong>
          <div class="small">${member.build_label}</div>
          <div class="small">Target: ${targetStats}</div>
          <div class="small">${member.reason}</div>
          <div class="small">Equip confermato ${gearSummary.ready}/${gearSummary.total} | da spostare ${gearSummary.swaps} | non confermato DB ${gearSummary.unconfirmed}</div>
          <div class="actions">
            <button class="secondary" onclick="equipMemberInGame(${optionIndex}, ${memberIndex}, this)" ${artifactIds.length ? '' : 'disabled'}>${buttonLabel}</button>
          </div>
          <div class="small gear-lines">${gearPlan}</div>
        </div>
      `;
    }

    function formatAssistedSwapStep(step) {
      const source = step.source_name ? ` da ${step.source_name}` : ' dal magazzino';
      const details = [
        step.required_faction || '',
        step.set_name || 'No Set',
        step.rarity || '',
        step.rank ? `${step.rank}*` : '',
        Number.isFinite(Number(step.level)) ? `+${step.level}` : '',
        formatStatValue(step.main_stat),
      ].filter(Boolean).join(' | ');
      const reason = step.why ? ` [${step.why}]` : '';
      const verb = step.action === 'swap' ? 'Sposta' : 'Monta';
      return `${step.step}. ${verb} ${step.slot} ${details} #${step.item_id}${source} su ${step.member_name}${reason}`;
    }

    function renderAssistedSwapPlan(plan) {
      if (!plan) {
        return '';
      }
      const sourceOwners = (plan.source_owners || []).join(', ') || 'nessuno';
      const memberBlocks = (plan.member_blocks || []).filter(block => (block.action_count || 0) > 0);
      return `
        <div class="manual-run">
          <div class="label">Swap Assistito</div>
          <div class="small">Pronti ${plan.ready_count || 0}/${plan.total_items || 0} | Azioni ${plan.action_count || 0} | Swap ${plan.swap_count || 0} | Pezzi liberi ${plan.free_equip_count || 0}</div>
          <div class="small">Campioni toccati: ${sourceOwners}</div>
          <div class="small gear-lines">${(plan.notes || []).join('\\n')}</div>
          ${memberBlocks.length ? `
            <div class="champ-list">
              ${memberBlocks.map(block => `
                <div class="champ">
                  <strong>${block.member_name}</strong>
                  <div class="small">${block.build_label || 'n/d'} | azioni ${block.action_count || 0} | swap ${block.swap_count || 0}</div>
                  <div class="small">Gia pronti ${block.ready_count || 0} | pezzi liberi ${block.free_equip_count || 0}</div>
                  <div class="small gear-lines">${(block.steps || []).map(formatAssistedSwapStep).join('\\n')}</div>
                </div>
              `).join('')}
            </div>
          ` : '<div class="small">Nessuna azione richiesta: puoi entrare in run cosi.</div>'}
        </div>
      `;
    }

    function formatCycleActions(actions) {
      const rows = (actions || []).map(action => {
        const slot = action?.slot ? ` ${action.slot}` : '';
        const skill = action?.skill ? ` ${action.skill}` : '';
        return `${action?.name || 'n/d'}${slot}${skill}`.trim();
      }).filter(Boolean);
      return rows.length ? rows.join(' -> ') : 'nessuna azione registrata';
    }

    function renderCycleDebug(cycleDebug) {
      const rows = (cycleDebug || []).slice(0, 9);
      if (!rows.length) {
        return '';
      }
      return `
        <details class="timeline">
          <summary>Lettura ciclo boss</summary>
          <div class="small">Prime finestre della simulazione: chi agisce prima di AoE1, AoE2 e Stun, e se il colpo risulta coperto.</div>
          <div class="cycle-debug">
            ${rows.map(row => {
              const headline = `Turno boss ${row.boss_turn || 0} | ${row.attack || 'n/d'}`;
              const status = row.attack === 'Stun'
                ? `Target ${row.target || 'n/d'} | ${row.safe ? 'stun sicuro' : 'stun scoperto'} | unkillable ${row.target_had_unkillable ? 'si' : 'no'} | block debuffs ${row.target_had_block_debuffs ? 'si' : 'no'}`
                : `${row.all_protected ? 'coperto da unkillable' : 'non coperto da unkillable'} | vivi prima del colpo ${row.alive_before_hit || 0}`;
              return `
                <div class="cycle-row">
                  <strong>${headline}</strong>
                  <div class="small">${status}</div>
                  <div class="small">Prima del colpo: ${formatCycleActions(row.actions_before_hit)}</div>
                </div>
              `;
            }).join('')}
          </div>
        </details>
      `;
    }

    function renderAdvisory(advisory) {
      if (!advisory) {
        return '';
      }
      return `
        <div class="advisory ${advisory.level || 'yellow'}">
          <strong>Semaforo ${advisory.label || 'n/d'}</strong>
          <div class="small">${advisory.message || ''}</div>
        </div>
      `;
    }

    function renderRecommendations(data) {
      const results = document.getElementById('results');
      const options = data.options || [];
      currentRecommendations = options;
      if (!options.length) {
        results.innerHTML = '<div class="team">Nessuna raccomandazione disponibile.</div>';
        return;
      }
      const noPrimaryKey = options.every(option => option?.advisory?.primary_key_ok === false);

      results.innerHTML = `
        ${noPrimaryKey ? `
          <article class="team">
            <h3>Nessuna Prima Key Affidabile</h3>
            <div class="small">Tutte le opzioni attuali risultano rosse. Questo non significa "impossibile da giocare": significa solo che il motore non riesce ancora a certificarti una prima key pulita.</div>
            <div class="small">Il primo team in lista resta il miglior fallback attuale, cioe il meno peggio disponibile con i dati di oggi.</div>
          </article>
        ` : ''}
        ${options.map((option, optionIndex) => `
        <article class="team">
          <h3>${option.team_name}${noPrimaryKey && optionIndex === 0 ? ' <span class="small">| miglior fallback attuale</span>' : ''} <span class="small">score ${option.score}</span></h3>
          <div class="small">${option.summary}</div>
          ${renderAdvisory(option.advisory)}
          ${noPrimaryKey && optionIndex === 0 ? `
            <div class="fallback-note">
              <strong>Miglior fallback attuale</strong>
              <div class="small">Se proprio devi scegliere una sola opzione tra quelle rosse, questa e quella che il motore considera meno problematica oggi. Non e una key "certificata", ma e la candidata di ripiego.</div>
            </div>
          ` : ''}
          <div class="small">${(option.warnings || []).join(' ')}</div>
          <div class="small">Controllo equip: confermati ${summarizeOptionGear(option).ready}/${summarizeOptionGear(option).total} | da spostare ${summarizeOptionGear(option).swaps} | non confermati DB ${summarizeOptionGear(option).unconfirmed}</div>
          ${renderCycleDebug(option.simulated_summary?.cycle_debug)}
          <div class="champ-list">
            ${(option.members || []).map((member, memberIndex) => renderMember(member, optionIndex, memberIndex)).join('')}
          </div>
          ${renderAssistedSwapPlan(option.swap_plan)}
        </article>
      `).join('')}
      `;
    }

    function persistHellHadesToken() {
      const input = document.getElementById('hhToken');
      const value = normalizeHellHadesToken(input.value);
      input.value = value;
      window.localStorage.setItem('cbforge.hh_token', value);
    }

    function clearHellHadesToken() {
      document.getElementById('hhToken').value = '';
      window.localStorage.removeItem('cbforge.hh_token');
      renderLog('Token HellHades rimosso dal browser.', 'ok');
    }

    function loadHellHadesToken() {
      const saved = window.localStorage.getItem('cbforge.hh_token') || '';
      document.getElementById('hhToken').value = saved;
    }

    function normalizeHellHadesToken(value) {
      const raw = String(value || '').trim();
      if (!raw) {
        return '';
      }
      if (raw.includes('#token=')) {
        const fragment = raw.split('#', 2)[1] || '';
        const params = new URLSearchParams(fragment);
        return (params.get('token') || '').trim();
      }
      if (raw.includes('access_token=')) {
        try {
          const url = new URL(raw);
          return (url.searchParams.get('access_token') || new URLSearchParams(url.hash.replace(/^#/, '')).get('access_token') || '').trim();
        } catch (error) {
          return raw;
        }
      }
      return raw;
    }

    async function equipMemberInGame(optionIndex, memberIndex, button) {
      const member = currentRecommendations?.[optionIndex]?.members?.[memberIndex];
      if (!member) {
        renderLog('Campione consigliato non trovato.', 'err');
        return;
      }
      if (!member.champ_id) {
        renderLog(`${member.name}: champ_id mancante nella raccomandazione.`, 'err');
        return;
      }
      const artifactIds = getMemberArtifactIdsForEquip(member);
      const confirmedSwapIds = getMemberConfirmedSwapIds(member);
      const unconfirmedIds = getMemberUnconfirmedIds(member);
      if (!artifactIds.length) {
        renderLog(`${member.name}: nessun pezzo da inviare, risulta gia montato.`, 'ok');
        return;
      }
      const tokenInput = document.getElementById('hhToken');
      const token = normalizeHellHadesToken(tokenInput.value);
      tokenInput.value = token;
      window.localStorage.setItem('cbforge.hh_token', token);
      if (!token) {
        renderLog('Incolla prima il token HellHades nel box "HellHades Live". Va bene anche il link completo con #token=...', 'err');
        return;
      }
      const modeLabel = confirmedSwapIds.length
        ? `swap certi ${confirmedSwapIds.length}`
        : `pezzi non confermati DB ${unconfirmedIds.length}`;
      renderLog(`Invio piano live per ${member.name}... ${artifactIds.length} pezzi (${modeLabel})`);
      await runWithButtonFeedback(button, 'Invio...', async () => {
        try {
          const data = await fetchJson('/api/hellhades/equip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              access_token: token,
              hero_id: member.champ_id,
              artifact_ids: artifactIds,
            }),
          });
          const helperMessage = data.helper_result?.isSuccess === true
            ? 'helper OK'
            : (data.status === 'requested' ? 'richiesta inviata' : 'helper senza esito');
          renderLog(`${member.name}: ${helperMessage} | pezzi ${data.requested_count || artifactIds.length}`, 'ok');
        } catch (error) {
          renderLog(`${member.name}: ${error.message}`, 'err');
        }
      });
    }

    function renderAffinityMatrix(matrix) {
      const rows = matrix?.rows || [];
      if (!rows.length) {
        return '';
      }
      return `
        <article class="team">
          <h3>Varianti Per Affinita</h3>
          <div class="champ-list">
            ${rows.map(row => `
              <div class="champ">
                <strong>${row.label}</strong>
                <div class="small">${row.team_name}</div>
                <div class="small">Turni boss stimati: ${row.boss_turns_simulated || 0} | Vivi: ${row.alive_count || 0}/5</div>
                <div class="small">5th slot consigliato: ${row.fifth_member || 'n/d'}</div>
                <div class="small">Team: ${(row.members || []).join(', ')}</div>
                <div class="small">${(row.warnings || []).join(' ')}</div>
              </div>
            `).join('')}
          </div>
        </article>
      `;
    }

    function formatSwapItem(item) {
      return `${item.member_name}: ${item.slot} ${item.set_name || 'No Set'} #${item.item_id} da ${item.equipped_by_name || 'n/d'}`;
    }

    function renderSurvivalPlan(plan) {
      const rows = plan?.rows || [];
      if (!rows.length) {
        return '';
      }
      return `
        <article class="team">
          <h3>Piano Survival Per Affinita</h3>
          <div class="small">Target simulazione: ${plan.turns || 0} turni boss</div>
          <div class="small">Core condiviso: ${(plan.shared_core || []).join(', ') || 'n/d'}</div>
          <div class="small">Flex pick: ${(plan.flex_picks || []).join(', ') || 'n/d'}</div>
          <div class="champ-list">
            ${rows.map(row => `
              <div class="champ">
                <strong>${row.label}</strong>
                <div class="small">${row.team_name || 'n/d'}</div>
                <div class="small">Turni boss ${row.summary?.boss_turns_simulated || 0} | Vivi ${row.summary?.alive_count || 0}/5 | Swap ${row.swap_count || 0}</div>
                <div class="small">Campioni: ${(row.member_names || []).join(', ')}</div>
                <div class="small">${(row.summary?.warnings || []).join(' ') || 'Nessun warning strutturale rilevato.'}</div>
                <div class="small gear-lines">${(row.swap_items || []).map(formatSwapItem).join('\\n') || 'Nessuno swap richiesto.'}</div>
              </div>
            `).join('')}
          </div>
        </article>
      `;
    }

    function getManualMemberFieldValues() {
      return [1, 2, 3, 4, 5]
        .map(index => document.getElementById(`manualMember${index}`).value.trim());
    }

    function getManualMembers() {
      return getManualMemberFieldValues().filter(Boolean);
    }

    function setManualMembers(members) {
      [1, 2, 3, 4, 5].forEach((index, memberIndex) => {
        document.getElementById(`manualMember${index}`).value = members?.[memberIndex] || '';
      });
    }

    function getPreparedTeamName() {
      return document.getElementById('manualTeamName').value.trim() || currentSimulationData?.team_name || '';
    }

    function getPreparedMembers() {
      const manualFieldValues = getManualMemberFieldValues();
      const manualMembers = manualFieldValues.filter(Boolean);
      if (manualMembers.length === 5) {
        return manualMembers;
      }
      const simulatedMembers = currentSimulationData?.members?.map(member => member.name) || [];
      if (manualMembers.length === 0 && simulatedMembers.length === 5) {
        return simulatedMembers;
      }
      return manualMembers;
    }

    function renderRunSessionStatus(data) {
      const status = document.getElementById('runSessionStatus');
      const session = data?.session || null;
      if (!session) {
        status.textContent = 'Nessuna registrazione attiva.';
        return;
      }
      const context = `${session.difficulty || ''} ${session.affinity || ''}`.trim() || 'n/d';
      status.textContent = [
        `Registrazione attiva da ${session.started_at || 'n/d'}`,
        `Team: ${session.team_name || 'n/d'}`,
        `Contesto: ${context}`,
        `Campioni: ${(session.members || []).join(', ')}`,
        `Battle ID: ${session.live_summary?.battle_id || 'in attesa'}`,
        `Stato battle: ${session.live_summary?.battle_state || 'in attesa'}`,
        `Eventi live: ${session.live_summary?.entries || 0}`,
      ].join('\\n');
    }

    function renderLiveFeed(data) {
      const liveFeed = document.getElementById('liveFeed');
      const session = data?.session || null;
      const summary = data?.summary || session?.live_summary || {};
      const entries = data?.entries || session?.live_feed || [];
      const battleResultCapture = data?.battle_result_capture || session?.battle_result_capture || {};
      const damageSummary = battleResultCapture.damage_summary || {};
      const damageByChampion = damageSummary.damage_by_champion || [];
      const lines = [
        `Monitor: ${session ? 'sessione attiva' : 'combat globale'}`,
        `Ultimo polling: ${summary.last_poll_at || 'n/d'}`,
        `Battle ID: ${summary.battle_id || 'in attesa'}`,
        `Stato: ${summary.battle_state || 'in attesa'}`,
        `Eventi raccolti: ${summary.entries || entries.length || 0}`,
        `BattleResult: ${battleResultCapture.snapshot_path ? `catturato (${battleResultCapture.size || 0} byte)` : 'non catturato'}`,
        '',
      ];
      if (damageByChampion.length) {
        lines.push('Danno per campione (best effort):');
        damageByChampion.forEach(item => {
          lines.push(`${item.name || 'n/d'}: ${formatDamageValue(item.damage || 0)} [${item.source_field || 'n/d'}]`);
        });
        lines.push('');
      }
      if (!entries.length) {
        lines.push('In attesa di eventi live dal client RAID...');
      } else {
        lines.push(...entries);
      }
      liveFeed.textContent = lines.join('\\n');
    }

    function stopLiveFeedPolling() {
      if (liveFeedTimer) {
        clearInterval(liveFeedTimer);
        liveFeedTimer = null;
      }
    }

    async function pollLiveRunFeed() {
      try {
        const data = await fetchJson('/api/live-run-feed');
        renderRunSessionStatus({ session: data.session });
        renderLiveFeed(data);
      } catch (error) {
        renderLog(error.message, 'err');
      }
    }

    function startLiveFeedPolling() {
      stopLiveFeedPolling();
      pollLiveRunFeed();
      liveFeedTimer = setInterval(pollLiveRunFeed, 500);
    }

    function renderSavedTeams(runs) {
      const select = document.getElementById('savedTeamSelect');
      const seen = new Set();
      savedTeams = (runs || []).filter(run => {
        const key = `${run.team_name || ''}||${(run.members || []).join('|')}`;
        if (!run.team_name || !Array.isArray(run.members) || run.members.length !== 5 || seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      });
      select.innerHTML = [
        '<option value="">Seleziona un team salvato</option>',
        ...savedTeams.map((team, index) => `<option value="${index}">${team.team_name} | ${team.difficulty || 'n/d'} ${team.affinity || ''} | ${(team.members || []).join(', ')}</option>`),
      ].join('');
    }

    function applySavedTeam(button) {
      const select = document.getElementById('savedTeamSelect');
      const index = Number(select.value);
      if (!Number.isInteger(index) || index < 0 || index >= savedTeams.length) {
        renderLog('Seleziona prima un team salvato dallo storico.', 'err');
        return;
      }
      setButtonBusy(button, true, 'Carico...');
      const team = savedTeams[index];
      document.getElementById('manualTeamName').value = team.team_name || '';
      setManualMembers(team.members || []);
      if (team.difficulty) {
        document.getElementById('cbDifficulty').value = team.difficulty;
      }
      if (team.affinity) {
        document.getElementById('cbAffinity').value = team.affinity;
      }
      renderLog(`Team caricato dallo storico: ${team.team_name}`, 'ok');
      setButtonBusy(button, false);
    }

    function sameLocalDay(left, right) {
      return left.getFullYear() === right.getFullYear()
        && left.getMonth() === right.getMonth()
        && left.getDate() === right.getDate();
    }

    function formatSavedAt(value) {
      const date = new Date(value || '');
      if (Number.isNaN(date.getTime())) {
        return value || 'n/d';
      }
      return date.toLocaleString('it-IT');
    }

    function formatDamageValue(value) {
      return Number(value || 0).toLocaleString('it-IT', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 1,
      });
    }

    function formatRunDamage(run) {
      if (!run || ((run.damage_known === false) && !Number(run.damage || 0))) {
        return 'n/d';
      }
      return formatDamageValue(run.damage);
    }

    function renderTodayComparison(runs) {
      const now = new Date();
      const todayRuns = (runs || []).filter(run => {
        const savedAt = new Date(run.saved_at || '');
        return !Number.isNaN(savedAt.getTime()) && sameLocalDay(savedAt, now);
      });
      if (!todayRuns.length) {
        return '';
      }
      if (todayRuns.length === 1) {
        const run = todayRuns[0];
        return `
          <article class="team">
            <h3>Confronto Oggi</h3>
            <div class="small">Oggi hai registrato 1 run.</div>
            <div class="small">Run: turno boss ${run.boss_turn || run.turns || 0} | ${formatRunDamage(run)} | ${run.team_name || 'n/d'} | ${formatSavedAt(run.saved_at)}</div>
          </article>
        `;
      }
      const latest = todayRuns[0];
      const previous = todayRuns[1];
      const turnDelta = Number(latest.boss_turn || latest.turns || 0) - Number(previous.boss_turn || previous.turns || 0);
      const delta = Number(latest.damage || 0) - Number(previous.damage || 0);
      const sameTeam = JSON.stringify(latest.members || []) === JSON.stringify(previous.members || []);
      const best = [...todayRuns].sort((left, right) => {
        const leftTurns = Number(left.boss_turn || left.turns || 0);
        const rightTurns = Number(right.boss_turn || right.turns || 0);
        if (rightTurns !== leftTurns) {
          return rightTurns - leftTurns;
        }
        return Number(right.damage || 0) - Number(left.damage || 0);
      })[0];
      return `
        <article class="team">
          <h3>Confronto Oggi</h3>
          <div class="small">Run registrate oggi: ${todayRuns.length}</div>
          <div class="small">Ultima: turno boss ${latest.boss_turn || latest.turns || 0} | ${formatRunDamage(latest)} | ${latest.team_name || 'n/d'} | ${formatSavedAt(latest.saved_at)}</div>
          <div class="small">Precedente: turno boss ${previous.boss_turn || previous.turns || 0} | ${formatRunDamage(previous)} | ${previous.team_name || 'n/d'} | ${formatSavedAt(previous.saved_at)}</div>
          <div class="small">Delta sopravvivenza: ${turnDelta >= 0 ? '+' : ''}${turnDelta} turni boss</div>
          <div class="small">Delta danno: ${delta >= 0 ? '+' : ''}${formatDamageValue(delta)}</div>
          <div class="small">Migliore di oggi per sopravvivenza: turno boss ${best.boss_turn || best.turns || 0} | ${formatRunDamage(best)} | ${best.team_name || 'n/d'}</div>
          <div class="small">Setup ${sameTeam ? 'uguale' : 'diverso'} tra le ultime due run</div>
        </article>
      `;
    }

    function renderManualRunHistory(data) {
      const history = document.getElementById('history');
      const summary = data.summary || {};
      const runs = data.runs || [];
      const teamStats = summary.team_stats || [];
      renderSavedTeams(runs);
      if (!runs.length) {
        history.innerHTML = '<article class="team"><h3>Storico Run Reali</h3><div class="small">Nessuna run reale salvata finora.</div></article>';
        return;
      }
      history.innerHTML = `
        ${renderTodayComparison(runs)}
        <article class="team">
          <h3>Storico Run Reali</h3>
          <div class="small">Run salvate: ${summary.count ?? runs.length}</div>
          <div class="small">Best survival: ${summary.best_survival_run?.team_name || summary.best_run?.team_name || 'n/d'} | Turno boss ${summary.best_survival_run?.boss_turn || summary.best_survival_run?.turns || summary.best_run?.boss_turn || summary.best_run?.turns || 'n/d'} | ${formatRunDamage(summary.best_survival_run || summary.best_run)} | ${summary.best_survival_run?.difficulty || summary.best_run?.difficulty || ''} ${summary.best_survival_run?.affinity || summary.best_run?.affinity || ''}</div>
          <div class="small">Best damage: ${summary.best_damage_run?.team_name || 'n/d'} | ${formatRunDamage(summary.best_damage_run)} | Turno boss ${summary.best_damage_run?.boss_turn || summary.best_damage_run?.turns || 'n/d'} | ${summary.best_damage_run?.difficulty || ''} ${summary.best_damage_run?.affinity || ''}</div>
          <div class="champ-list">
            ${teamStats.map(item => `
              <div class="champ">
                <strong>${item.team_name}</strong>
                <div class="small">Best turn ${item.best_boss_turn || 0} | Avg turn ${item.avg_boss_turn || 0} | Run ${item.count}</div>
                <div class="small">Best dmg ${item.best_damage} | Avg dmg ${item.avg_damage} | Turni registrati ${item.survival_recorded_runs || 0}</div>
                <div class="small">Affinity: ${(item.affinities || []).join(', ') || 'n/d'}</div>
                <div class="small">${(item.members || []).join(', ')}</div>
              </div>
            `).join('')}
          </div>
          <details class="timeline">
            <summary>Ultime run (${runs.length})</summary>
            <div class="small gear-lines">${runs.map(run => `${run.saved_at} | ${run.team_name} | ${formatRunDamage(run)} | turno boss ${run.boss_turn || run.turns || 'n/d'} | ${run.difficulty} ${run.affinity} | ${(run.members || []).join(', ')}${run.notes ? ` | ${run.notes}` : ''}${run.loadout_snapshot_path ? ` | snapshot ${run.loadout_snapshot_path}` : ''}`).join('\\n')}</div>
          </details>
        </article>
      `;
    }

    function renderSimulation(data, plan) {
      currentSimulationData = data;
      const results = document.getElementById('results');
      const summary = data.summary || {};
      const members = data.members || [];
      results.innerHTML = `
        <article class="team">
          <h3>Team Preparato ${data.team_name || 'Clan Boss'} <span class="small">${summary.difficulty || ''} ${summary.affinity || ''}</span></h3>
          <div class="small">Questa vista serve per preparare run lunghe e registrare poi il test reale.</div>
          <div class="small">Selezione survival-first: finestra ${summary.boss_turns_simulated || 0} turni boss simulati | vivi ${summary.alive_count || 0}/5 | danno stimato ${formatDamageValue(summary.estimated_team_damage || 0)}</div>
          <div class="small">${(summary.warnings || []).join(' ') || 'Nessun warning strutturale rilevato nel setup proposto.'}</div>
          ${renderCycleDebug(data.cycle_debug || summary.cycle_debug)}
          <div class="champ-list">
            ${members.map(member => `
              <div class="champ">
                <strong>${member.name}</strong>
                <div class="small">${member.build_label || 'n/d'} | ${member.affinity} | SPD ${member.estimated_speed} | ACC ${member.estimated_accuracy}</div>
                <div class="small">HP ${member.estimated_hp} | DEF ${member.estimated_defense}</div>
                <div class="small">Target: ${(member.target_stats || []).join(', ') || 'n/d'} | swap ${member.swap_count || 0}</div>
                <div class="small">${member.reason || ''}</div>
                <div class="small gear-lines">${(member.gear_plan || []).map(formatGearItem).join('\\n') || 'n/d'}</div>
              </div>
            `).join('')}
          </div>
        </article>
        ${renderSurvivalPlan(plan)}
      `;
      document.getElementById('manualTeamName').value = data.team_name || '';
      setManualMembers(members.map(member => member.name));
    }

    async function refreshStatus(button) {
      renderLog('Aggiornamento stato in corso...');
      await runWithButtonFeedback(button, 'Aggiorno...', async () => {
        try {
          const data = await fetchJson('/api/status');
          renderStats(data);
          renderLog(JSON.stringify(data, null, 2));
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function loadDiagnostics(button) {
      renderLog('Raccolta diagnostica processo in corso...');
      await runWithButtonFeedback(button, 'Diagnostica...', async () => {
        try {
          const data = await fetchJson('/api/diagnostics');
          renderLog(JSON.stringify(data, null, 2), 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function runAction(url, button, busyLabel) {
      renderLog('Esecuzione in corso...');
      await runWithButtonFeedback(button, busyLabel, async () => {
        try {
          const data = await fetchJson(url, { method: 'POST' });
          renderStats(data.status || data);
          renderLog(data.output || JSON.stringify(data, null, 2), 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function loadBosses() {
      try {
        const data = await fetchJson('/api/bosses');
        renderBosses(data);
      } catch (error) {
        renderLog(error.message, 'err');
      }
    }

    async function loadClanBossConfig() {
      try {
        const data = await fetchJson('/api/clan-boss-config');
        renderClanBossConfig(data);
      } catch (error) {
        renderLog(error.message, 'err');
      }
    }

    async function loadManualRuns(button) {
      renderLog('Caricamento storico run...');
      await runWithButtonFeedback(button, 'Carico...', async () => {
        try {
          const data = await fetchJson('/api/manual-runs');
          renderManualRunHistory(data);
          renderLog('Storico run aggiornato.', 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function loadRunSessionStatus() {
      try {
        const data = await fetchJson('/api/active-run-session');
        renderRunSessionStatus(data);
        renderLiveFeed(data);
        startLiveFeedPolling();
      } catch (error) {
        renderLog(error.message, 'err');
      }
    }

    async function fetchRecommendedTeamData() {
      const select = document.getElementById('bossSelect');
      const bossKey = select.value;
      const difficulty = document.getElementById('cbDifficulty').value;
      const affinity = document.getElementById('cbAffinity').value;
      const params = new URLSearchParams({ boss: bossKey });
      if (bossKey === 'demon_lord_unm') {
        params.set('difficulty', difficulty);
        params.set('affinity', affinity);
      }
      const data = await fetchJson(`/api/recommend?${params.toString()}`);
      return { data, bossKey, difficulty, affinity };
    }

    async function recommendTeam(button) {
      const bossKey = document.getElementById('bossSelect').value;
      const difficulty = document.getElementById('cbDifficulty').value;
      const affinity = document.getElementById('cbAffinity').value;
      renderLog(
        bossKey === 'demon_lord_unm'
          ? `Analisi team Clan Boss in corso... livello ${difficulty}, affinity ${affinity}`
          : 'Analisi team in corso...'
      );
      await runWithButtonFeedback(button, 'Analizzo...', async () => {
        try {
          const { data } = await fetchRecommendedTeamData();
          renderRecommendations(data);
          const bestMembers = (data.options?.[0]?.members || []).map(member => member.name);
          if (bestMembers.length) {
            setManualMembers(bestMembers);
            document.getElementById('manualTeamName').value = data.options?.[0]?.team_name || '';
          }
          renderLog(`Team consigliati caricati: ${data.options?.length || 0}`, 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function checkRecommendedTeam(button) {
      const bossKey = document.getElementById('bossSelect').value;
      const difficulty = document.getElementById('cbDifficulty').value;
      const affinity = document.getElementById('cbAffinity').value;
      renderLog(
        bossKey === 'demon_lord_unm'
          ? `Controllo assetto team in corso... livello ${difficulty}, affinity ${affinity}`
          : 'Controllo assetto team in corso...'
      );
      await runWithButtonFeedback(button, 'Controllo...', async () => {
        try {
          const { data } = await fetchRecommendedTeamData();
          renderRecommendations(data);
          const best = data.options?.[0];
          const summary = summarizeOptionGear(best || {});
          const bestName = best?.team_name || 'n/d';
          renderLog(`Controllo completato: ${bestName} | confermati ${summary.ready}/${summary.total} | da spostare ${summary.swaps} | non confermati DB ${summary.unconfirmed}`, 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function simulateClanBoss(button) {
      const bossKey = document.getElementById('bossSelect').value;
      if (bossKey !== 'demon_lord_unm') {
        renderLog('La simulazione turn-by-turn e disponibile solo per Clan Boss al momento.', 'err');
        return;
      }
      const difficulty = document.getElementById('cbDifficulty').value;
      const affinity = document.getElementById('cbAffinity').value;
      const turns = Number(document.getElementById('cbTurns').value || '300');
      renderLog(`Preparazione team Clan Boss in corso... target ${turns} turni boss`);
      await runWithButtonFeedback(button, 'Preparo...', async () => {
        try {
          const [data, plan] = await Promise.all([
            fetchJson(`/api/simulate-clan-boss?difficulty=${encodeURIComponent(difficulty)}&affinity=${encodeURIComponent(affinity)}&turns=${encodeURIComponent(turns)}`),
            fetchJson(`/api/clan-boss-survival-plan?difficulty=${encodeURIComponent(difficulty)}&turns=${encodeURIComponent(turns)}`),
          ]);
          renderSimulation(data, plan);
          renderLog(`Team pronto: ${data.team_name} | ora puoi avviare la registrazione run`, 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function saveManualRun(button) {
      const teamName = getPreparedTeamName();
      const damage = Number(document.getElementById('manualDamage').value || '0');
      const bossTurn = Number(document.getElementById('manualBossTurn').value || '0');
      const notes = document.getElementById('manualNotes').value.trim();
      const turnLog = document.getElementById('manualTurnLog').value;
      const difficulty = document.getElementById('cbDifficulty').value;
      const affinity = document.getElementById('cbAffinity').value;
      const members = getPreparedMembers();
      const manualMembers = getManualMembers();
      if (manualMembers.length > 0 && manualMembers.length !== 5) {
        renderLog(`Compila tutti e 5 i campioni manuali prima di salvare. Ora ne vedo ${manualMembers.length}.`, 'err');
        return;
      }
      if (!teamName || !damage || members.length !== 5) {
        renderLog('Inserisci nome team, danno reale e 5 campioni usati.', 'err');
        return;
      }
      renderLog(`Salvataggio run reale in corso... danno ${damage}`);
      await runWithButtonFeedback(button, 'Salvo...', async () => {
        try {
          const data = await fetchJson('/api/manual-runs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              team_name: teamName,
              damage,
              boss_turn: bossTurn,
              difficulty,
              affinity,
              members,
              notes,
              turn_log: turnLog,
              source: 'manual_ui',
            }),
          });
          renderManualRunHistory(data);
          renderLog(`Run salvata: ${data.saved?.team_name} | ${data.saved?.damage}`, 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function startRunRecording(button) {
      const teamName = getPreparedTeamName();
      const notes = document.getElementById('manualNotes').value.trim();
      const difficulty = document.getElementById('cbDifficulty').value;
      const affinity = document.getElementById('cbAffinity').value;
      const members = getPreparedMembers();
      const manualMembers = getManualMembers();
      if (!teamName) {
        renderLog('Inserisci almeno un nome team o test. I campioni ora provo a leggerli dal log di RAID.', 'err');
        return;
      }
      if (manualMembers.length > 0 && manualMembers.length !== 5) {
        renderLog(`Compila tutti e 5 i campioni manuali prima di avviare la registrazione. Ora ne vedo ${manualMembers.length}.`, 'err');
        return;
      }
      document.getElementById('manualTeamName').value = teamName;
      if (members.length === 5) {
        setManualMembers(members);
      }
      renderLog(`Avvio registrazione run con: ${members.join(', ') || 'team da auto-rilevare'}`);
      await runWithButtonFeedback(button, 'Avvio...', async () => {
        try {
          const data = await fetchJson('/api/start-run-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              team_name: teamName,
              difficulty,
              affinity,
              members,
              notes,
            }),
          });
          document.getElementById('manualTeamName').value = data.session?.team_name || teamName;
          setManualMembers(data.session?.members || members);
          renderRunSessionStatus({ session: data.session });
          renderLiveFeed({ session: data.session });
          startLiveFeedPolling();
          renderLog(`Registrazione attiva: ${data.session?.team_name}`, 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function cancelRunRecording(button) {
      renderLog('Annullamento registrazione in corso...');
      await runWithButtonFeedback(button, 'Annullo...', async () => {
        try {
          const data = await fetchJson('/api/cancel-run-session', {
            method: 'POST',
          });
          renderRunSessionStatus({ session: null });
          renderLiveFeed({ session: null });
          stopLiveFeedPolling();
          renderLog(`Registrazione annullata: ${data.cancelled?.team_name || 'sessione chiusa'}`, 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    async function stopRunRecording(button) {
      const damageText = document.getElementById('manualDamage').value.trim();
      const damage = damageText ? Number(damageText) : null;
      const bossTurn = Number(document.getElementById('manualBossTurn').value || '0');
      const notes = document.getElementById('manualNotes').value.trim();
      const turnLog = document.getElementById('manualTurnLog').value;
      const teamName = getPreparedTeamName();
      const members = getPreparedMembers();
      const difficulty = document.getElementById('cbDifficulty').value;
      const affinity = document.getElementById('cbAffinity').value;
      renderLog(damage ? `Chiusura registrazione run... danno ${damage}` : 'Chiusura registrazione run... danno finale non disponibile');
      await runWithButtonFeedback(button, 'Chiudo...', async () => {
        try {
          const data = await fetchJson('/api/stop-run-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              damage,
              boss_turn: bossTurn,
              notes,
              turn_log: turnLog,
              team_name: teamName,
              members,
              difficulty,
              affinity,
            }),
          });
          renderRunSessionStatus({ session: null });
          renderLiveFeed({ session: null });
          stopLiveFeedPolling();
          renderManualRunHistory(data);
          renderLog(`Run registrata: ${data.saved?.team_name} | ${data.saved?.damage}`, 'ok');
        } catch (error) {
          renderLog(error.message, 'err');
        }
      });
    }

    loadBosses();
    loadClanBossConfig();
    loadHellHadesToken();
    loadManualRuns();
    loadRunSessionStatus();
    refreshStatus();
    window.refreshStatus = refreshStatus;
    window.runAction = runAction;
    window.recommendTeam = recommendTeam;
    window.checkRecommendedTeam = checkRecommendedTeam;
    window.simulateClanBoss = simulateClanBoss;
    window.saveManualRun = saveManualRun;
    window.loadManualRuns = loadManualRuns;
    window.applySavedTeam = applySavedTeam;
    window.startRunRecording = startRunRecording;
    window.stopRunRecording = stopRunRecording;
    window.cancelRunRecording = cancelRunRecording;
    window.clearHellHadesToken = clearHellHadesToken;
    window.equipMemberInGame = equipMemberInGame;
    window.persistHellHadesToken = persistHellHadesToken;
    window.loadDiagnostics = loadDiagnostics;
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(HTML)
            return
        if parsed.path == "/api/status":
            self._send_json(build_status())
            return
        if parsed.path == "/api/diagnostics":
            self._send_json(build_runtime_diagnostics())
            return
        if parsed.path == "/api/bosses":
            self._send_json({"bosses": available_bosses()})
            return
        if parsed.path == "/api/clan-boss-config":
            self._send_json(
                {
                    "levels": available_clan_boss_levels(),
                    "affinities": available_clan_boss_affinities(),
                }
            )
            return
        if parsed.path == "/api/loadout-status":
            self._send_json(snapshot_status())
            return
        if parsed.path == "/api/manual-runs":
            runs = list_manual_runs(limit=50)
            self._send_json({"runs": runs, "summary": manual_run_summary(runs)})
            return
        if parsed.path == "/api/active-run-session":
            session = refresh_active_run_session()
            self._send_json({"session": session})
            return
        if parsed.path == "/api/live-run-feed":
            session = refresh_active_run_session()
            global_state = refresh_global_live_combat_state()
            self._send_json(
                {
                    "session": session,
                    "entries": (session or global_state).get("live_feed", []),
                    "summary": (session or global_state).get("live_summary", {}),
                    "battle_result_capture": (session or global_state).get("battle_result_capture", {}),
                }
            )
            return
        if parsed.path == "/api/recommend":
            query = parse_qs(parsed.query)
            boss_key = query.get("boss", ["demon_lord_unm"])[0]
            try:
                if boss_key == "demon_lord_unm" and any(key in query for key in {"difficulty", "affinity", "turns", "damage_scale"}):
                    difficulty = query.get("difficulty", ["ultra_nightmare"])[0]
                    affinity = query.get("affinity", ["void"])[0]
                    turns = int(query.get("turns", ["300"])[0])
                    damage_scale = float(query.get("damage_scale", ["1"])[0])
                    payload = recommend_for_boss(boss_key)
                    payload["options"] = recommend_clan_boss_options(
                        difficulty=difficulty,
                        affinity=affinity,
                        turns=turns,
                        damage_scale=damage_scale,
                    )
                else:
                    payload = recommend_for_boss(boss_key)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/simulate-clan-boss":
            query = parse_qs(parsed.query)
            try:
                difficulty = query.get("difficulty", ["ultra_nightmare"])[0]
                affinity = query.get("affinity", ["void"])[0]
                turns = int(query.get("turns", ["300"])[0])
                damage_scale = float(query.get("damage_scale", ["1"])[0])
                payload = simulate_best_clan_boss_team(
                    difficulty=difficulty,
                    affinity=affinity,
                    turns=turns,
                    damage_scale=damage_scale,
                )
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/clan-boss-affinity-matrix":
            query = parse_qs(parsed.query)
            try:
                difficulty = query.get("difficulty", ["ultra_nightmare"])[0]
                turns = int(query.get("turns", ["300"])[0])
                damage_scale = float(query.get("damage_scale", ["1"])[0])
                payload = simulate_clan_boss_affinity_matrix(difficulty=difficulty, turns=turns, damage_scale=damage_scale)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/clan-boss-survival-plan":
            query = parse_qs(parsed.query)
            try:
                difficulty = query.get("difficulty", ["ultra_nightmare"])[0]
                turns = int(query.get("turns", ["300"])[0])
                damage_scale = float(query.get("damage_scale", ["1"])[0])
                payload = build_clan_boss_survival_plan(difficulty=difficulty, turns=turns, damage_scale=damage_scale)
            except KeyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(payload)
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path == "/api/sync":
            self._save_snapshot_if_possible("pre_sync")
            self._run_pipeline([["python", "extract_local.py"], ["python", "normalize.py"]])
            return
        if self.path == "/api/refresh-gear":
            self._save_snapshot_if_possible("pre_refresh_gear")
            self._run_pipeline_and_snapshot(
                [["python", "extract_local.py"], ["python", "normalize.py"]],
                snapshot_label="gear_refresh",
            )
            return
        if self.path == "/api/manual-runs":
            try:
                payload = self._read_json_body()
                saved = save_manual_run(payload)
                runs = list_manual_runs(limit=50)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json({"saved": saved, "runs": runs, "summary": manual_run_summary(runs)})
            return
        if self.path == "/api/start-run-session":
            try:
                payload = self._read_json_body()
                session = start_run_session(payload)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json({"session": session})
            return
        if self.path == "/api/stop-run-session":
            try:
                payload = self._read_json_body()
                global_capture = refresh_global_live_combat_state().get("battle_result_capture", {})
                if global_capture and "battle_result_capture" not in payload:
                    payload["battle_result_capture"] = global_capture
                saved = stop_run_session(payload)
                runs = list_manual_runs(limit=50)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json({"saved": saved, "runs": runs, "summary": manual_run_summary(runs)})
            return
        if self.path == "/api/cancel-run-session":
            cancelled = cancel_run_session()
            if cancelled is None:
                self._send_json({"error": "nessuna sessione attiva"}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"cancelled": cancelled})
            return
        if self.path == "/api/save-loadout":
            try:
                payload = save_current_loadout_snapshot(label="manual")
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json({"saved": payload, "status": build_status()})
            return
        if self.path == "/api/extract":
            self._run_command(["python", "extract_local.py"])
            return
        if self.path == "/api/normalize":
            self._run_command(["python", "normalize.py"])
            return
        if self.path == "/api/hellhades/equip":
            try:
                payload = self._read_json_body()
                result = equip_artifacts_live(
                    hero_id=str(payload.get("hero_id", "")).strip(),
                    artifact_ids=payload.get("artifact_ids", []),
                    access_token=str(payload.get("access_token", "")).strip() or None,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            except HellHadesEquipError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(result)
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _run_command(self, command: list[str]) -> None:
        completed = subprocess.run(
            command,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = {
            "command": command,
            "returncode": completed.returncode,
            "output": (completed.stdout + completed.stderr).strip(),
            "status": build_status(),
        }
        if completed.returncode == 0:
            self._send_json(payload)
        else:
            self._send_json(payload | {"error": payload["output"] or "Command failed"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _run_pipeline(self, commands: list[list[str]]) -> None:
        results = []
        combined_output: list[str] = []
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (completed.stdout + completed.stderr).strip()
            results.append(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "output": output,
                }
            )
            if output:
                combined_output.append(output)
            if completed.returncode != 0:
                payload = {
                    "results": results,
                    "output": "\n\n".join(combined_output).strip(),
                    "status": build_status(),
                    "error": output or "Command failed",
                }
                self._send_json(payload, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

        self._send_json(
            {
                "results": results,
                "output": "\n\n".join(combined_output).strip(),
                "status": build_status(),
            }
        )

    def _run_pipeline_and_snapshot(self, commands: list[list[str]], snapshot_label: str) -> None:
        results = []
        combined_output: list[str] = []
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (completed.stdout + completed.stderr).strip()
            results.append(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "output": output,
                }
            )
            if output:
                combined_output.append(output)
            if completed.returncode != 0:
                payload = {
                    "results": results,
                    "output": "\n\n".join(combined_output).strip(),
                    "status": build_status(),
                    "error": output or "Command failed",
                }
                self._send_json(payload, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return

        try:
            snapshot = save_current_loadout_snapshot(label=snapshot_label)
        except Exception as exc:
            self._send_json(
                {
                    "results": results,
                    "output": "\n\n".join(combined_output).strip(),
                    "status": build_status(),
                    "error": str(exc),
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json(
            {
                "results": results,
                "output": "\n\n".join(combined_output).strip(),
                "saved": snapshot,
                "status": build_status(),
            }
        )

    def _save_snapshot_if_possible(self, label: str) -> None:
        if not NORMALIZED_PATH.exists():
            return
        try:
            save_current_loadout_snapshot(label=label)
        except Exception:
            return

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body non valido")
        return payload


def build_status() -> Dict[str, Any]:
    return {
        "raw": file_status(RAW_PATH),
        "normalized": file_status(NORMALIZED_PATH),
        "loadout_snapshot": snapshot_status(),
        "sqlite_db": sqlite_status(),
    }


def build_runtime_diagnostics() -> Dict[str, Any]:
    session = get_active_run_session()
    with GLOBAL_LIVE_COMBAT_LOCK:
        live_summary = dict((GLOBAL_LIVE_COMBAT_STATE.get("live_summary") or {}))
        battle_result_capture = dict((GLOBAL_LIVE_COMBAT_STATE.get("battle_result_capture") or {}))
        global_feed_entries = len(GLOBAL_LIVE_COMBAT_STATE.get("live_feed") or [])
    return {
        "server": runtime_state_snapshot(),
        "memory": process_memory_snapshot(),
        "threads": summarize_threads(),
        "thread_count": len(threading.enumerate()),
        "active_run_session": {
            "present": session is not None,
            "team_name": (session or {}).get("team_name", ""),
            "started_at": (session or {}).get("started_at", ""),
            "entries": len((session or {}).get("live_feed") or []),
            "battle_id": ((session or {}).get("live_summary") or {}).get("battle_id", ""),
        },
        "global_live_summary": live_summary | {"entries": live_summary.get("entries", global_feed_entries)},
        "battle_result_watch": dict(BATTLE_RESULT_WATCH_STATE),
        "battle_result_file": battle_result_file_state(BATTLE_RESULTS_PATH),
        "battle_result_capture": {
            "captured_at": battle_result_capture.get("captured_at", ""),
            "size": battle_result_capture.get("size", 0),
            "sha256": battle_result_capture.get("sha256", ""),
            "snapshot_path": battle_result_capture.get("snapshot_path", ""),
        },
    }


def runtime_state_snapshot() -> Dict[str, Any]:
    uptime_seconds = max(time.monotonic() - float(SERVER_RUNTIME_STATE.get("boot_monotonic") or 0.0), 0.0)
    return {
        "pid": os.getpid(),
        "started_at": str(SERVER_RUNTIME_STATE.get("started_at") or ""),
        "uptime_seconds": round(uptime_seconds, 1),
        "host": str(SERVER_RUNTIME_STATE.get("host") or ""),
        "port": int(SERVER_RUNTIME_STATE.get("port") or 0),
        "shutdown_requested": bool(SERVER_RUNTIME_STATE.get("shutdown_requested")),
    }


def summarize_threads() -> list[Dict[str, Any]]:
    rows = []
    for thread in sorted(threading.enumerate(), key=lambda item: item.name):
        rows.append(
            {
                "name": thread.name,
                "ident": thread.ident or 0,
                "daemon": thread.daemon,
                "alive": thread.is_alive(),
            }
        )
    return rows


def process_memory_snapshot() -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "rss_bytes": 0,
        "private_bytes": 0,
        "peak_rss_bytes": 0,
        "source": "unavailable",
    }
    if os.name == "nt":
        windows_snapshot = windows_process_memory_snapshot()
        if windows_snapshot:
            return windows_snapshot

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        peak = int(usage.ru_maxrss)
        peak_bytes = peak if sys.platform == "darwin" else peak * 1024
        snapshot["peak_rss_bytes"] = peak_bytes
        snapshot["source"] = "resource.getrusage"
    except Exception:
        pass
    return snapshot


def windows_process_memory_snapshot() -> Dict[str, Any]:
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        success = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        if not success:
            return {}
        return {
            "rss_bytes": int(counters.WorkingSetSize),
            "private_bytes": int(counters.PrivateUsage),
            "peak_rss_bytes": int(counters.PeakWorkingSetSize),
            "source": "GetProcessMemoryInfo",
        }
    except Exception:
        return {}


def file_status(path: Path) -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "champions": 0,
        "gear": 0,
        "bonuses": 0,
    }
    if not path.exists():
        return status

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        status["error"] = str(exc)
        return status

    champions = payload.get("champions", payload.get("roster", []))
    gear = payload.get("gear", payload.get("inventory", []))
    bonuses = payload.get("account_bonuses", payload.get("bonuses", []))
    status["champions"] = len(champions) if isinstance(champions, list) else 0
    status["gear"] = len(gear) if isinstance(gear, list) else 0
    status["bonuses"] = len(bonuses) if isinstance(bonuses, list) else 0
    status["size"] = path.stat().st_size
    return status


def refresh_global_live_combat_state() -> Dict[str, Any]:
    global GLOBAL_LIVE_COMBAT_STATE
    with GLOBAL_LIVE_COMBAT_LOCK:
        GLOBAL_LIVE_COMBAT_STATE, _ = refresh_live_monitor(GLOBAL_LIVE_COMBAT_STATE)
        return dict(GLOBAL_LIVE_COMBAT_STATE)


def global_live_combat_loop(stop_event: threading.Event, interval_seconds: float = 0.15) -> None:
    while not stop_event.is_set():
        try:
            refresh_global_live_combat_state()
        except Exception:
            pass
        stop_event.wait(interval_seconds)


def current_battle_context() -> Dict[str, Any]:
    session = get_active_run_session()
    if session:
        return {
            "battle_id": ((session.get("live_summary") or {}).get("battle_id") or ""),
            "members": session.get("members") or [],
        }
    global_state = refresh_global_live_combat_state()
    return {
        "battle_id": ((global_state.get("live_summary") or {}).get("battle_id") or ""),
        "members": global_state.get("members") or [],
    }


def update_global_battle_result_capture(capture: Dict[str, Any]) -> None:
    global GLOBAL_LIVE_COMBAT_STATE
    with GLOBAL_LIVE_COMBAT_LOCK:
        GLOBAL_LIVE_COMBAT_STATE["battle_result_capture"] = capture
        summary = GLOBAL_LIVE_COMBAT_STATE.setdefault("live_summary", {})
        summary["last_battle_result_capture_at"] = capture.get("captured_at", "")
        summary["last_battle_result_size"] = capture.get("size", 0)


def battle_result_file_state(path: Path = BATTLE_RESULTS_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "size": 0,
            "mtime_ns": 0,
            "signature": "",
        }

    stat = path.stat()
    size = int(stat.st_size)
    mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
    return {
        "exists": True,
        "size": size,
        "mtime_ns": mtime_ns,
        "signature": f"{size}:{mtime_ns}",
    }


def battle_result_capture_loop(
    stop_event: threading.Event,
    interval_seconds: float = 0.1,
    settle_seconds: float = 0.2,
) -> None:
    global BATTLE_RESULT_WATCH_STATE
    while not stop_event.is_set():
        try:
            state = battle_result_file_state(BATTLE_RESULTS_PATH)
            signature = str(state.get("signature") or "")
            size = int(state.get("size") or 0)
            if not state.get("exists"):
                BATTLE_RESULT_WATCH_STATE["last_seen_signature"] = ""
                BATTLE_RESULT_WATCH_STATE["last_size"] = 0
                BATTLE_RESULT_WATCH_STATE["last_mtime_ns"] = 0
                BATTLE_RESULT_WATCH_STATE["last_change_monotonic"] = 0.0
            elif signature != str(BATTLE_RESULT_WATCH_STATE.get("last_seen_signature") or ""):
                BATTLE_RESULT_WATCH_STATE["last_seen_signature"] = signature
                BATTLE_RESULT_WATCH_STATE["last_size"] = size
                BATTLE_RESULT_WATCH_STATE["last_mtime_ns"] = int(state.get("mtime_ns") or 0)
                BATTLE_RESULT_WATCH_STATE["last_change_monotonic"] = time.monotonic()
            else:
                last_change = float(BATTLE_RESULT_WATCH_STATE.get("last_change_monotonic") or 0.0)
                if (
                    size >= MIN_USEFUL_BATTLE_RESULT_SIZE
                    and signature != str(BATTLE_RESULT_WATCH_STATE.get("last_captured_signature") or "")
                    and (time.monotonic() - last_change) >= settle_seconds
                ):
                    context = current_battle_context()
                    capture = capture_battle_result_snapshot(
                        battle_id=str(context.get("battle_id") or ""),
                        preferred_names=[str(item) for item in (context.get("members") or []) if str(item)],
                    )
                    if capture:
                        BATTLE_RESULT_WATCH_STATE["last_captured_signature"] = signature
                        BATTLE_RESULT_WATCH_STATE["last_captured_sha256"] = str(capture.get("sha256") or "")
                        update_global_battle_result_capture(capture)
        except Exception:
            pass
        stop_event.wait(interval_seconds)


class CBForgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    host = os.environ.get("CBFORGE_HOST", "127.0.0.1")
    port = int(os.environ.get("CBFORGE_PORT", "8765"))
    server: CBForgeServer | None = None
    stop_event = threading.Event()
    live_thread: threading.Thread | None = None
    battle_result_thread: threading.Thread | None = None
    previous_sigterm = None
    previous_sigbreak = None

    def handle_shutdown_signal(signum: int, _frame: Any) -> None:
        print(f"\nCB Forge server stopping on signal {signum}...")
        SERVER_RUNTIME_STATE["shutdown_requested"] = True
        stop_event.set()
        if server is not None:
            server.shutdown()

    try:
        SERVER_RUNTIME_STATE["pid"] = os.getpid()
        SERVER_RUNTIME_STATE["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        SERVER_RUNTIME_STATE["boot_monotonic"] = time.monotonic()
        SERVER_RUNTIME_STATE["host"] = host
        SERVER_RUNTIME_STATE["port"] = port
        SERVER_RUNTIME_STATE["shutdown_requested"] = False
        reset_live_combat_runtime_state()
        try:
            ensure_current_loadout_snapshot()
        except Exception as exc:
            print(f"Warning: unable to prepare loadout snapshot: {exc}")
        try:
            rebuild_registry_database()
        except Exception as exc:
            print(f"Warning: unable to rebuild SQLite registry database: {exc}")
        live_thread = threading.Thread(
            target=global_live_combat_loop,
            args=(stop_event,),
            name="cbforge-live-combat",
            daemon=True,
        )
        live_thread.start()
        battle_result_thread = threading.Thread(
            target=battle_result_capture_loop,
            args=(stop_event,),
            name="cbforge-battle-result",
            daemon=True,
        )
        battle_result_thread.start()
        server = CBForgeServer((host, port), Handler)
        previous_sigterm = signal.signal(signal.SIGTERM, handle_shutdown_signal)
        if hasattr(signal, "SIGBREAK"):
            previous_sigbreak = signal.signal(signal.SIGBREAK, handle_shutdown_signal)
        print(f"CB Forge server listening on http://{host}:{port}")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCB Forge server stopped.")
    finally:
        SERVER_RUNTIME_STATE["shutdown_requested"] = True
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        if previous_sigbreak is not None and hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, previous_sigbreak)
        stop_event.set()
        if live_thread is not None:
            live_thread.join(timeout=1)
        if battle_result_thread is not None:
            battle_result_thread.join(timeout=1)
        if server is not None:
            server.server_close()


if __name__ == "__main__":
    main()
