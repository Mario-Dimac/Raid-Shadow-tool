from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from cb_battle_results import capture_battle_result_snapshot
from cbforge_extractor.paths import RAID_BUILD_LOG, RAID_LOCALLOW


BASE_DIR = Path(__file__).resolve().parent
RAW_ACCOUNT_PATH = BASE_DIR / "input" / "raw_account.json"
BATTLE_RESULTS_PATH = RAID_LOCALLOW / "battle-results" / "battleResults"
WORKERS_SERIALIZATION_PATH = RAID_LOCALLOW / "workers-serialization" / "serialization"
SQLITE_PATHS = {
    "raid.db": RAID_LOCALLOW / "raid.db",
    "raidV2.db": RAID_LOCALLOW / "raidV2.db",
}
LOG_KEYWORDS = (
    "CreateBattle",
    "BattleStateNotifier",
    "BattleViewContext",
    "BattleResult",
    "BattleSetup",
    "BattleFinishAllianceBossDialog",
    "FinishBattleCmd",
)
STATE_RE = re.compile(r"Change battle state \[(?P<left>[^\]]+?) -> (?P<right>[^\]]+?)\]")
BATTLE_ID_RE = re.compile(
    r"(?:battleId - |Battle \[|BattleResult added: \[Id=|BattleResult deleted: \[Id=)(?P<id>[0-9a-fA-F-]{8,})"
)
CREATE_BATTLE_RE = re.compile(
    r"^>>> CreateBattle with setup:Id: (?P<battle_id>[0-9a-fA-F-]+) RandomSeed: (?P<seed>\d+) Stage: (?P<stage>\d+) FormationIndex (?P<formation>\d+)$"
)
TEAM_SETUP_RE = re.compile(r"^Round:\s*(?P<round>\d+)\s+Slot:\s*(?P<slot>\d+)\s+Type:\s*(?P<type_id>\d+)")


def build_initial_live_monitor_state() -> Dict[str, Any]:
    return {
        "started_at": utc_now(),
        "build_log": {
            "path": str(RAID_BUILD_LOG),
            "offset": current_file_size(RAID_BUILD_LOG),
        },
        "sqlite_events": {
            name: {
                "path": str(path),
                "last_id": current_max_event_id(path),
            }
            for name, path in SQLITE_PATHS.items()
        },
        "tracked_files": {
            "battle_results": file_marker(BATTLE_RESULTS_PATH),
            "workers_serialization": file_marker(WORKERS_SERIALIZATION_PATH),
        },
        "battle_id": "",
        "battle_state": "",
        "entry_count": 0,
        "last_poll_at": "",
    }


def refresh_live_monitor(session: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    updated = dict(session)
    monitor = dict_mapping(updated.get("live_monitor"))
    if not monitor:
        monitor = build_initial_live_monitor_state()

    existing_entries = normalize_turn_log(updated.get("live_feed"))
    new_entries: List[str] = []

    build_log_state = dict_mapping(monitor.get("build_log"))
    log_entries, build_log_state = poll_build_log(build_log_state)
    new_entries.extend(log_entries)
    monitor["build_log"] = build_log_state

    sqlite_state = dict_mapping(monitor.get("sqlite_events"))
    next_sqlite_state: Dict[str, Any] = {}
    for name, path in SQLITE_PATHS.items():
        entries, state = poll_sqlite_events(path, dict_mapping(sqlite_state.get(name)))
        new_entries.extend(entries)
        next_sqlite_state[name] = state
    monitor["sqlite_events"] = next_sqlite_state

    tracked_files_state = dict_mapping(monitor.get("tracked_files"))
    next_tracked_files: Dict[str, Any] = {}
    for key, path in (
        ("battle_results", BATTLE_RESULTS_PATH),
        ("workers_serialization", WORKERS_SERIALIZATION_PATH),
    ):
        entries, state = poll_tracked_file(path, dict_mapping(tracked_files_state.get(key)), key)
        new_entries.extend(entries)
        next_tracked_files[key] = state
    monitor["tracked_files"] = next_tracked_files

    battle_capture = dict_mapping(monitor.get("battle_result_capture"))
    should_capture_result = any("BattleResult added:" in entry for entry in new_entries)
    if should_capture_result:
        capture = capture_battle_result_snapshot(
            battle_id=extract_latest_battle_id(new_entries) or string_value(monitor.get("battle_id")),
            preferred_names=[string_value(item) for item in updated.get("members", []) if string_value(item)],
        )
        if capture:
            battle_capture = capture
            total_damage = dict_mapping(capture.get("damage_summary")).get("total_damage")
            captured_size = capture.get("size")
            new_entries.append(
                f"[battle-result] snapshot catturata | size {captured_size} | total_damage {total_damage or 'n/d'}"
            )
    if battle_capture:
        monitor["battle_result_capture"] = battle_capture
        updated["battle_result_capture"] = battle_capture

    feed = trim_entries(existing_entries + new_entries)
    battle_id, battle_state = summarize_live_feed(feed, monitor)
    monitor["battle_id"] = battle_id
    monitor["battle_state"] = battle_state
    monitor["entry_count"] = len(feed)
    monitor["last_poll_at"] = utc_now()

    updated["live_monitor"] = monitor
    updated["live_feed"] = feed
    updated["live_summary"] = {
        "battle_id": battle_id,
        "battle_state": battle_state,
        "entries": len(feed),
        "last_poll_at": monitor["last_poll_at"],
    }
    return updated, new_entries


def poll_build_log(state: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    path = Path(string_value(state.get("path")) or str(RAID_BUILD_LOG))
    offset = int_value(state.get("offset"))
    if not path.exists():
        return [], {"path": str(path), "offset": 0}

    file_size = current_file_size(path)
    if file_size < offset:
        offset = 0

    raw = b""
    if file_size > offset:
        with path.open("rb") as handle:
            handle.seek(offset)
            raw = handle.read()

    lines = raw.decode("utf-8", errors="ignore").splitlines()
    entries = extract_combat_log_entries(lines)
    next_state = {
        "path": str(path),
        "offset": file_size,
    }
    return entries, next_state


def poll_sqlite_events(path: Path, state: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    last_id = int_value(state.get("last_id"))
    if not path.exists():
        return [], {"path": str(path), "last_id": last_id}

    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        tables = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "Events" not in tables:
            conn.close()
            return [], {"path": str(path), "last_id": last_id}
        rows = cur.execute(
            "SELECT Id, Body FROM Events WHERE Id > ? ORDER BY Id ASC LIMIT 50",
            (last_id,),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return [], {"path": str(path), "last_id": last_id}

    entries: List[str] = []
    max_id = last_id
    for row_id, body in rows:
        max_id = max(max_id, int_value(row_id))
        preview = preview_sqlite_event_body(body)
        if preview:
            entries.append(f"[sqlite {path.name}#{row_id}] {preview}")
    return entries, {"path": str(path), "last_id": max_id}


def poll_tracked_file(path: Path, state: Dict[str, Any], label: str) -> Tuple[List[str], Dict[str, Any]]:
    previous = state or file_marker(path)
    current = file_marker(path)
    if current == previous:
        return [], current

    entries: List[str] = []
    if current["exists"]:
        hex_preview = current.get("hex_preview") or ""
        detail = f"{current['size']} bytes"
        if hex_preview:
            detail = f"{detail} | hex {hex_preview}"
        entries.append(f"[cache {label}] aggiornato | {detail}")
    else:
        entries.append(f"[cache {label}] rimosso")
    return entries, current


def extract_combat_log_entries(lines: List[str]) -> List[str]:
    entries: List[str] = []
    for line in lines:
        cleaned = " ".join(string_value(line).strip().split())
        if not cleaned:
            continue
        is_state_line = cleaned.lower().startswith("change battle state ")
        if not is_state_line and not any(keyword.lower() in cleaned.lower() for keyword in LOG_KEYWORDS):
            continue
        entries.append(f"[client-log] {cleaned[:360]}")
    return trim_entries(entries)


def summarize_live_feed(feed: List[str], monitor: Dict[str, Any]) -> Tuple[str, str]:
    battle_id = string_value(monitor.get("battle_id"))
    battle_state = string_value(monitor.get("battle_state"))
    for entry in feed:
        match = BATTLE_ID_RE.search(entry)
        if match:
            battle_id = match.group("id")
        state_match = STATE_RE.search(entry)
        if state_match:
            battle_state = state_match.group("right").strip()
    return battle_id, battle_state


def extract_latest_battle_id(entries: List[str]) -> str:
    for entry in reversed(entries):
        match = BATTLE_ID_RE.search(entry)
        if match:
            return match.group("id")
    return ""


def merge_turn_logs(*values: Any) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for value in values:
        for entry in normalize_turn_log(value):
            if entry in seen:
                continue
            seen.add(entry)
            merged.append(entry)
    return merged


def detect_latest_player_team(log_path: Path = RAID_BUILD_LOG, raw_account_path: Path = RAW_ACCOUNT_PATH) -> Dict[str, Any]:
    if not log_path.exists():
        return {}

    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    battle_index = -1
    battle_match = None
    for index in range(len(lines) - 1, -1, -1):
        match = CREATE_BATTLE_RE.match(lines[index].strip())
        if match:
            battle_index = index
            battle_match = match
            break
    if battle_match is None:
        return {}

    type_ids: List[int] = []
    player_section = False
    for line in lines[battle_index + 1 : battle_index + 20]:
        stripped = line.strip()
        if stripped.startswith("First Team:"):
            player_section = True
            continue
        if stripped.startswith("Second Team:") or stripped.startswith(">>> CreateBattle with setup:"):
            break
        if not player_section:
            continue
        setup_match = TEAM_SETUP_RE.match(stripped)
        if setup_match:
            type_ids.append(int_value(setup_match.group("type_id")))

    if not type_ids:
        return {}

    name_map = load_champion_type_name_map(raw_account_path)
    members = [name_map.get(type_id, f"Type {type_id}") for type_id in type_ids[:5]]
    return {
        "battle_id": battle_match.group("battle_id"),
        "stage_id": battle_match.group("stage"),
        "formation_index": int_value(battle_match.group("formation")),
        "member_type_ids": type_ids[:5],
        "members": members,
    }


def normalize_turn_log(value: Any) -> List[str]:
    if isinstance(value, list):
        return [string_value(item).strip() for item in value if string_value(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def preview_sqlite_event_body(value: Any) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = string_value(value)
    text = text.replace("\x00", "").strip()
    if not text:
        return ""
    try:
        loaded = json.loads(text)
        text = json.dumps(loaded, ensure_ascii=False)
    except json.JSONDecodeError:
        pass
    return text[:280]


def trim_entries(entries: List[str], limit: int = 160) -> List[str]:
    return entries[-limit:]


def file_marker(path: Path) -> Dict[str, Any]:
    marker: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size": 0,
        "mtime_ns": 0,
        "hex_preview": "",
    }
    if not path.exists():
        return marker

    stat = path.stat()
    marker["size"] = stat.st_size
    marker["mtime_ns"] = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
    marker["hex_preview"] = read_file_hex_preview(path)
    return marker


def read_file_hex_preview(path: Path, limit: int = 24) -> str:
    if limit <= 0 or not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            return handle.read(limit).hex()
    except OSError:
        return ""


def current_file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def current_max_event_id(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        tables = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "Events" not in tables:
            conn.close()
            return 0
        row = cur.execute("SELECT COALESCE(MAX(Id), 0) FROM Events").fetchone()
        conn.close()
    except sqlite3.Error:
        return 0
    return int_value(row[0] if row else 0)


def dict_mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_champion_type_name_map(path: Path = RAW_ACCOUNT_PATH) -> Dict[int, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    roster = payload.get("roster") or payload.get("champions") or []
    mapping: Dict[int, str] = {}
    for item in roster:
        if not isinstance(item, dict):
            continue
        type_id = int_value(item.get("type_id"))
        name = string_value(item.get("name")).strip()
        if type_id and name and type_id not in mapping:
            mapping[type_id] = name
    return mapping


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
