from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cb_live_monitor import (
    build_initial_live_monitor_state,
    detect_latest_player_team,
    merge_turn_logs,
    refresh_live_monitor,
)
from cb_sqlite_db import (
    SQLITE_DB_PATH as COMBAT_DB_PATH,
    get_active_session as get_active_session_db,
    insert_combat_run,
    insert_combat_session,
    list_combat_runs,
    set_active_session as set_active_session_db,
)
from loadout_snapshot import LATEST_SNAPSHOT_PATH, save_current_loadout_snapshot

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
RUN_HISTORY_PATH = INPUT_DIR / "cb_manual_runs.jsonl"
ACTIVE_RUN_SESSION_PATH = INPUT_DIR / "cb_active_run_session.json"


def list_manual_runs(path: Path = COMBAT_DB_PATH, limit: int = 50) -> List[Dict[str, Any]]:
    if path == COMBAT_DB_PATH:
        rows = [normalize_run_entry(row) for row in list_combat_runs(limit=limit, path=path)]
    else:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(normalize_run_entry(json.loads(stripped)))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda item: string_value(item.get("saved_at")), reverse=True)
    return rows[:limit]


def save_manual_run(
    payload: Dict[str, Any],
    path: Path = COMBAT_DB_PATH,
    snapshot_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    members = [string_value(item) for item in list_value(payload.get("members")) if string_value(item)]
    turn_log = normalize_turn_log(payload.get("turn_log"))
    snapshot_meta = save_current_loadout_snapshot(label="manual_run")
    snapshot = snapshot_payload or load_json_file(Path(snapshot_meta["snapshot_path"]))
    entry = {
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "team_name": string_value(payload.get("team_name")),
        "difficulty": string_value(payload.get("difficulty")),
        "affinity": string_value(payload.get("affinity")),
        "boss_turn": boss_turn_value(payload),
        "damage": float_value(payload.get("damage")),
        "members": members,
        "member_details": extract_member_details(snapshot, members),
        "turn_log": turn_log,
        "notes": string_value(payload.get("notes")),
        "source": string_value(payload.get("source")) or "manual",
        "loadout_snapshot_path": string_value(snapshot_meta.get("snapshot_path")),
        "loadout_latest_path": string_value(snapshot_meta.get("latest_path")),
        "loadout_saved_at": string_value(snapshot.get("saved_at")),
    }
    entry["turns"] = entry["boss_turn"]
    if not entry["team_name"]:
        raise ValueError("team_name mancante")
    if entry["damage"] <= 0:
        raise ValueError("damage deve essere > 0")
    if len(entry["members"]) != 5:
        raise ValueError("servono 5 campioni usati")
    if path == COMBAT_DB_PATH:
        insert_combat_run(entry, path)
    else:
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def start_run_session(payload: Dict[str, Any], path: Path = COMBAT_DB_PATH) -> Dict[str, Any]:
    members = [string_value(item) for item in list_value(payload.get("members")) if string_value(item)]
    auto_detected = detect_latest_player_team() if len(members) != 5 else {}
    if len(members) != 5:
        members = [string_value(item) for item in list_value(auto_detected.get("members")) if string_value(item)]
    if len(members) != 5:
        raise ValueError("servono 5 campioni usati oppure un battle setup recente nel log di RAID")
    snapshot_meta = save_current_loadout_snapshot(label="run_start")
    snapshot = load_json_file(Path(snapshot_meta["snapshot_path"]))
    session = {
        "started_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "team_name": string_value(payload.get("team_name")),
        "difficulty": string_value(payload.get("difficulty")),
        "affinity": string_value(payload.get("affinity")),
        "members": members,
        "member_details": extract_member_details(snapshot, members),
        "notes": string_value(payload.get("notes")),
        "start_snapshot_path": string_value(snapshot_meta.get("snapshot_path")),
        "start_latest_path": string_value(snapshot_meta.get("latest_path")),
        "auto_detected_team": auto_detected,
        "live_feed": [],
        "live_monitor": build_initial_live_monitor_state(),
        "live_summary": {},
    }
    if not session["team_name"]:
        raise ValueError("team_name mancante")
    if path == COMBAT_DB_PATH:
        set_active_session_db(session, path)
        insert_combat_session(
            {
                "started_at": session["started_at"],
                "ended_at": "",
                "team_name": session["team_name"],
                "difficulty": session["difficulty"],
                "affinity": session["affinity"],
                "members": list(session["members"]),
                "source": "started_session",
            },
            path,
        )
    else:
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return session


def get_active_run_session(path: Path = COMBAT_DB_PATH) -> Optional[Dict[str, Any]]:
    if path == COMBAT_DB_PATH:
        return get_active_session_db(path)
    if not path.exists():
        return None
    return load_json_file(path)


def refresh_active_run_session(path: Path = COMBAT_DB_PATH) -> Optional[Dict[str, Any]]:
    session = get_active_run_session(path)
    if session is None:
        return None
    refreshed, _ = refresh_live_monitor(session)
    if path == COMBAT_DB_PATH:
        set_active_session_db(refreshed, path)
    else:
        path.write_text(json.dumps(refreshed, indent=2, ensure_ascii=False), encoding="utf-8")
    return refreshed


def stop_run_session(
    payload: Dict[str, Any],
    session_path: Path = COMBAT_DB_PATH,
    history_path: Path = COMBAT_DB_PATH,
) -> Dict[str, Any]:
    session = get_active_run_session(session_path)
    if session is None:
        recovered = recover_run_without_active_session(payload, history_path)
        if recovered:
            return recovered
        raise ValueError("nessuna sessione attiva")
    session, _ = refresh_live_monitor(session)
    damage = float_value(payload.get("damage"))
    battle_result_capture = dict_value(session.get("battle_result_capture"))
    if not battle_result_capture:
        battle_result_capture = dict_value(payload.get("battle_result_capture"))
    battle_damage = float_value(
        dict_value(battle_result_capture.get("damage_summary")).get("total_damage")
    )
    if damage <= 0 and battle_damage > 0:
        damage = battle_damage
    boss_turn = boss_turn_value(payload)
    end_snapshot_meta = save_current_loadout_snapshot(label="run_end")
    live_feed = normalize_turn_log(session.get("live_feed"))
    entry = {
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "team_name": string_value(session.get("team_name")),
        "difficulty": string_value(session.get("difficulty")),
        "affinity": string_value(session.get("affinity")),
        "boss_turn": boss_turn,
        "damage": damage,
        "damage_known": damage > 0,
        "battle_result_capture": battle_result_capture,
        "members": list_value(session.get("members")),
        "member_details": list_value(session.get("member_details")),
        "turn_log": merge_turn_logs(live_feed, payload.get("turn_log")),
        "live_feed": live_feed,
        "live_summary": dict_value(session.get("live_summary")),
        "notes": merge_notes(string_value(session.get("notes")), string_value(payload.get("notes"))),
        "source": "recorded_session",
        "started_at": string_value(session.get("started_at")),
        "ended_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "elapsed_seconds": elapsed_seconds(string_value(session.get("started_at"))),
        "loadout_snapshot_path": string_value(session.get("start_snapshot_path")),
        "loadout_latest_path": string_value(session.get("start_latest_path")),
        "loadout_saved_at": snapshot_saved_at(string_value(session.get("start_snapshot_path"))),
        "end_snapshot_path": string_value(end_snapshot_meta.get("snapshot_path")),
        "end_latest_path": string_value(end_snapshot_meta.get("latest_path")),
    }
    entry["turns"] = entry["boss_turn"]
    if history_path == COMBAT_DB_PATH:
        insert_combat_run(entry, history_path)
        set_active_session_db(None, history_path)
        insert_combat_session(
            {
                "started_at": string_value(session.get("started_at")),
                "ended_at": string_value(entry.get("ended_at")),
                "team_name": string_value(entry.get("team_name")),
                "difficulty": string_value(entry.get("difficulty")),
                "affinity": string_value(entry.get("affinity")),
                "members": list_value(entry.get("members")),
                "source": "recorded_session",
            },
            history_path,
        )
    else:
        append_run_entry(entry, history_path)
    if session_path.exists() and session_path != COMBAT_DB_PATH:
        session_path.unlink()
    return entry


def recover_run_without_active_session(
    payload: Dict[str, Any],
    history_path: Path,
) -> Optional[Dict[str, Any]]:
    battle_result_capture = dict_value(payload.get("battle_result_capture"))
    members = [string_value(item) for item in list_value(payload.get("members")) if string_value(item)]
    detected = detect_latest_player_team() if len(members) != 5 else {}
    if len(members) != 5:
        members = [string_value(item) for item in list_value(detected.get("members")) if string_value(item)]
    team_name = derive_recovered_team_name(
        string_value(payload.get("team_name")),
        members,
        fallback_name=string_value(detected.get("team_id")),
    )
    if len(members) != 5 and not battle_result_capture:
        return None

    damage = float_value(payload.get("damage"))
    battle_damage = float_value(dict_value(battle_result_capture.get("damage_summary")).get("total_damage"))
    if damage <= 0 and battle_damage > 0:
        damage = battle_damage

    snapshot_meta = save_current_loadout_snapshot(label="run_end")
    snapshot = load_json_file(Path(snapshot_meta["snapshot_path"]))
    entry = {
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "team_name": team_name,
        "difficulty": string_value(payload.get("difficulty")),
        "affinity": string_value(payload.get("affinity")),
        "boss_turn": boss_turn_value(payload),
        "damage": damage,
        "damage_known": damage > 0,
        "battle_result_capture": battle_result_capture,
        "members": members,
        "member_details": extract_member_details(snapshot, members) if len(members) == 5 else [],
        "turn_log": normalize_turn_log(payload.get("turn_log")),
        "live_feed": [],
        "live_summary": {},
        "notes": string_value(payload.get("notes")),
        "source": "recovered_session",
        "started_at": "",
        "ended_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "elapsed_seconds": 0,
        "loadout_snapshot_path": string_value(snapshot_meta.get("snapshot_path")),
        "loadout_latest_path": string_value(snapshot_meta.get("latest_path")),
        "loadout_saved_at": string_value(snapshot.get("saved_at")),
        "end_snapshot_path": string_value(snapshot_meta.get("snapshot_path")),
        "end_latest_path": string_value(snapshot_meta.get("latest_path")),
    }
    entry["turns"] = entry["boss_turn"]
    if history_path == COMBAT_DB_PATH:
        insert_combat_run(entry, history_path)
        set_active_session_db(None, history_path)
        insert_combat_session(
            {
                "started_at": "",
                "ended_at": string_value(entry.get("ended_at")),
                "team_name": string_value(entry.get("team_name")),
                "difficulty": string_value(entry.get("difficulty")),
                "affinity": string_value(entry.get("affinity")),
                "members": list_value(entry.get("members")),
                "source": "recovered_session",
            },
            history_path,
        )
    else:
        append_run_entry(entry, history_path)
    session_path = ACTIVE_RUN_SESSION_PATH
    if session_path.exists():
        session_path.unlink(missing_ok=True)
    return entry


def derive_recovered_team_name(
    requested_name: str,
    members: List[str],
    fallback_name: str = "",
) -> str:
    clean_requested = string_value(requested_name).strip()
    if clean_requested and normalize_name(clean_requested) not in {"recoveredrun", "recovered"}:
        return clean_requested

    clean_fallback = string_value(fallback_name).strip()
    if clean_fallback:
        return clean_fallback

    clean_members = [string_value(item).strip() for item in members if string_value(item).strip()]
    if len(clean_members) >= 2:
        remaining = len(clean_members) - 2
        suffix = f" + {remaining}" if remaining > 0 else ""
        return f"{clean_members[0]} / {clean_members[1]}{suffix}"
    if clean_members:
        return clean_members[0]
    return "Recovered run"


def cancel_run_session(path: Path = COMBAT_DB_PATH) -> Optional[Dict[str, Any]]:
    session = get_active_run_session(path)
    if session is None:
        return None
    if path == COMBAT_DB_PATH:
        set_active_session_db(None, path)
    else:
        path.unlink(missing_ok=True)
    return session


def manual_run_summary(runs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = runs if runs is not None else list_manual_runs()
    if not rows:
        return {
            "count": 0,
            "best_run": None,
            "best_survival_run": None,
            "best_damage_run": None,
            "team_stats": [],
        }

    best_survival_run = max(rows, key=run_survival_score)
    best_damage_run = max(rows, key=lambda item: float_value(item.get("damage")))
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[string_value(row.get("team_name"))].append(row)

    team_stats: List[Dict[str, Any]] = []
    for team_name, team_rows in grouped.items():
        damages = [float_value(item.get("damage")) for item in team_rows]
        boss_turns = [boss_turn_value(item) for item in team_rows]
        recorded_turns = [value for value in boss_turns if value > 0]
        team_stats.append(
            {
                "team_name": team_name,
                "count": len(team_rows),
                "best_boss_turn": max(boss_turns) if boss_turns else 0,
                "avg_boss_turn": round(sum(boss_turns) / len(boss_turns), 1) if boss_turns else 0.0,
                "survival_recorded_runs": len(recorded_turns),
                "best_damage": round(max(damages), 1),
                "avg_damage": round(sum(damages) / len(damages), 1),
                "members": list_value(team_rows[0].get("members")),
                "affinities": sorted(
                    {
                        string_value(item.get("affinity"))
                        for item in team_rows
                        if string_value(item.get("affinity"))
                    }
                ),
                "latest_snapshot_path": string_value(team_rows[0].get("loadout_snapshot_path")),
                "best_run": max(team_rows, key=run_survival_score),
            }
        )
    team_stats.sort(
        key=lambda item: (
            item["best_boss_turn"],
            item["avg_boss_turn"],
            item["best_damage"],
            item["avg_damage"],
        ),
        reverse=True,
    )

    return {
        "count": len(rows),
        "best_run": best_survival_run,
        "best_survival_run": best_survival_run,
        "best_damage_run": best_damage_run,
        "team_stats": team_stats[:10],
    }


def append_run_entry(entry: Dict[str, Any], path: Path = RUN_HISTORY_PATH) -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def normalize_run_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    normalized = dict(entry)
    normalized["boss_turn"] = boss_turn_value(normalized)
    if "turns" not in normalized:
        normalized["turns"] = normalized["boss_turn"]
    return normalized


def load_snapshot_payload(path: Path = LATEST_SNAPSHOT_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return load_json_file(path)


def extract_member_details(snapshot: Dict[str, Any], members: List[str]) -> List[Dict[str, Any]]:
    champions = list_value(snapshot.get("champions"))
    details: List[Dict[str, Any]] = []
    for name in members:
        match = best_snapshot_champion_by_name(champions, name)
        if not match:
            details.append({"name": name, "found_in_snapshot": False, "equipped_items": []})
            continue
        details.append(
            {
                "name": name,
                "found_in_snapshot": True,
                "champ_id": string_value(match.get("champ_id")),
                "level": int_value(match.get("level")),
                "rank": int_value(match.get("rank")),
                "equipped_items": list_value(match.get("equipped_items")),
            }
        )
    return details


def best_snapshot_champion_by_name(champions: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    normalized = normalize_name(name)
    candidates = [
        champion
        for champion in champions
        if normalize_name(string_value(champion.get("name"))) == normalized
    ]
    if not candidates:
        return {}
    candidates.sort(
        key=lambda champion: (
            len(list_value(champion.get("equipped_items"))),
            int_value(champion.get("level")),
            int_value(champion.get("rank")),
        ),
        reverse=True,
    )
    return candidates[0]


def normalize_turn_log(value: Any) -> List[str]:
    if isinstance(value, list):
        return [string_value(item).strip() for item in value if string_value(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def load_json_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_notes(left: str, right: str) -> str:
    if left and right:
        return f"{left}\n{right}"
    return left or right


def snapshot_saved_at(path_text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    if not path.exists():
        return ""
    return string_value(load_json_file(path).get("saved_at"))


def elapsed_seconds(started_at: str) -> int:
    if not started_at:
        return 0
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(int((datetime.now(timezone.utc) - started).total_seconds()), 0)


def boss_turn_value(payload: Dict[str, Any]) -> int:
    value = payload.get("boss_turn")
    if value in (None, "", 0, 0.0, "0"):
        value = payload.get("turns")
    return int_value(value)


def run_survival_score(payload: Dict[str, Any]) -> tuple[int, float]:
    return (
        boss_turn_value(payload),
        float_value(payload.get("damage")),
    )


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_name(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())
