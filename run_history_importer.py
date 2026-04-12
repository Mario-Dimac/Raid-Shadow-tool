from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from account_stats import summarize_sets
from battle_event_decoder import extract_skill_usage_counts
from forge_db import DB_PATH, ensure_schema, insert_run_effect_timeline, load_equipped_gear_by_owner, load_set_rules, record_run_history
from run_damage_decoder import extract_damage_summary
from run_effect_timeline import extract_effect_timeline
from run_mapper import HH_HERO_TYPES_PATH, derive_run_mapping


BASE_DIR = Path(__file__).resolve().parent
CLIENT_PROBE_ROOT = BASE_DIR / "input" / "client_probe"
LIVE_STORAGE_ROOT = BASE_DIR / "input" / "live_storage_probe"
BATTLE_ID_IN_REASON_RE = re.compile(r"Id=([^\]]+)")


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return dict_value(json.loads(path.read_text(encoding="utf-8")))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    payload: List[Dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload.append(dict_value(json.loads(line)))
    return payload


def parse_rank(grade: Any) -> Optional[int]:
    text = string_value(grade).strip()
    if text.startswith("Stars"):
        value = text.removeprefix("Stars")
        parsed = int_value(value)
        return parsed if parsed > 0 else None
    return None


def parse_iso(value: Any) -> Optional[datetime]:
    text = string_value(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def event_battle_id(event: Dict[str, Any]) -> str:
    battle = dict_value(event.get("battle"))
    saved = dict_value(event.get("saved"))
    reason = string_value(saved.get("reason")).strip()
    reason_match = BATTLE_ID_IN_REASON_RE.search(reason)
    if reason_match:
        return string_value(reason_match.group(1)).strip()
    if battle:
        return string_value(battle.get("battle_id"))
    battle_context = dict_value(saved.get("battle_context"))
    return string_value(battle_context.get("battle_id"))


def is_rich_battle_results_event(event: Dict[str, Any]) -> bool:
    if string_value(event.get("source_name")) != "battle_results":
        return False
    saved = dict_value(event.get("saved"))
    marker = dict_value(saved.get("marker"))
    return int_value(marker.get("size")) > 11


def _battle_results_priority(event: Dict[str, Any]) -> tuple[int, str, str]:
    saved = dict_value(event.get("saved"))
    marker = dict_value(saved.get("marker"))
    return (
        int_value(marker.get("size")),
        string_value(event.get("captured_at")),
        string_value(saved.get("raw_path")),
    )


def select_best_rich_battle_result_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered_battle_ids: List[str] = []
    selected_by_battle_id: Dict[str, Dict[str, Any]] = {}

    for event in events:
        battle_id = event_battle_id(event)
        if not battle_id:
            continue
        current = selected_by_battle_id.get(battle_id)
        if current is None:
            ordered_battle_ids.append(battle_id)
            selected_by_battle_id[battle_id] = event
            continue
        if _battle_results_priority(event) > _battle_results_priority(current):
            selected_by_battle_id[battle_id] = event

    return [selected_by_battle_id[battle_id] for battle_id in ordered_battle_ids]


def existing_run_id(source: str, source_run_uid: str, db_path: Path) -> Optional[int]:
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT run_id
            FROM run_history_runs
            WHERE source = ? AND source_run_uid = ?
            ORDER BY run_id DESC
            LIMIT 1
            """,
            (source, source_run_uid),
        ).fetchone()
    return int(row[0]) if row else None


def latest_event_index_for_battle(events: List[Dict[str, Any]], battle_id: str) -> int:
    for index in range(len(events) - 1, -1, -1):
        if event_battle_id(events[index]) == battle_id:
            return index
    return -1


def first_event_index_for_battle(events: List[Dict[str, Any]], battle_id: str) -> int:
    for index, event in enumerate(events):
        if event_battle_id(event) == battle_id:
            return index
    return -1


def find_nearest_sqlite_create_event(events: List[Dict[str, Any]], start_index: int) -> Dict[str, Any]:
    for index in range(start_index, -1, -1):
        event = dict_value(events[index])
        if string_value(event.get("event_type")) != "sqlite_event":
            continue
        parsed = dict_value(event.get("row")).get("parsed")
        request = dict_value(dict_value(dict_value(parsed).get("p")).get("r"))
        if string_value(request.get("t")).startswith("Create"):
            return event
    return {}


def find_started_at(events: List[Dict[str, Any]], start_index: int, end_index: int) -> str:
    for index in range(start_index, min(end_index + 1, len(events))):
        event = dict_value(events[index])
        if string_value(event.get("event_type")) != "log_line":
            continue
        if "Change battle state [Loading -> Started]" in string_value(event.get("line")):
            return string_value(event.get("captured_at"))
    return ""


def find_finished_at(events: List[Dict[str, Any]], start_index: int, end_index: int) -> str:
    for index in range(end_index, start_index - 1, -1):
        event = dict_value(events[index])
        if string_value(event.get("event_type")) != "log_line":
            continue
        if "Change battle state [Started -> Finished]" in string_value(event.get("line")):
            return string_value(event.get("captured_at"))
    return string_value(dict_value(events[end_index]).get("captured_at")) if end_index >= 0 else ""


def elapsed_seconds(started_at: str, finished_at: str) -> Optional[float]:
    start_dt = parse_iso(started_at)
    finish_dt = parse_iso(finished_at)
    if start_dt is None or finish_dt is None:
        return None
    elapsed = (finish_dt - start_dt).total_seconds()
    return elapsed if elapsed >= 0 else None


def build_members(battle_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = sorted(list_value(battle_context.get("player_team")), key=lambda row: int_value(dict_value(row).get("slot")))
    members: List[Dict[str, Any]] = []
    for row in rows:
        row_map = dict_value(row)
        members.append(
            {
                "champion_name": string_value(row_map.get("name")),
                "champion_type_id": int_value(row_map.get("type_id")) or None,
                "slot_index": max(int_value(row_map.get("slot")) - 1, 0),
                "level": int_value(row_map.get("level")) or None,
                "rank": parse_rank(row_map.get("grade")),
            }
        )
    return members


def build_fingerprint_for_items(items: List[Dict[str, Any]]) -> str:
    item_ids = sorted(string_value(item.get("item_id")).strip() for item in items if string_value(item.get("item_id")).strip())
    if not item_ids:
        return ""
    payload = "|".join(item_ids)
    return sha1(payload.encode("utf-8")).hexdigest()[:16]


def load_account_member_enrichment(db_path: Path = DB_PATH) -> Dict[str, Dict[str, Any]]:
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        set_rules = load_set_rules(conn)
        gear_by_owner = load_equipped_gear_by_owner(conn)
        champion_rows = conn.execute(
            """
            SELECT champ_id, champion_name, level, rank, awakening_level, empowerment_level, booked
            FROM account_champions
            ORDER BY champion_name ASC, level DESC, rank DESC, booked DESC, champ_id ASC
            """
        ).fetchall()
        stat_rows = conn.execute(
            """
            SELECT champ_id, stat_name, stat_value
            FROM account_champion_total_stats
            ORDER BY champ_id ASC, stat_name ASC
            """
        ).fetchall()

    stats_by_champ_id: Dict[str, Dict[str, Any]] = {}
    for row in stat_rows:
        champ_id = string_value(row["champ_id"])
        stats_by_champ_id.setdefault(champ_id, {})[string_value(row["stat_name"])] = row["stat_value"]

    enrichment_by_name: Dict[str, Dict[str, Any]] = {}
    for row in champion_rows:
        champion_name = string_value(row["champion_name"]).strip()
        champ_id = string_value(row["champ_id"]).strip()
        if not champion_name or champion_name in enrichment_by_name:
            continue
        equipped_items = list_value(gear_by_owner.get(champ_id))
        applied_sets, unsupported_sets = summarize_sets(equipped_items, set_rules)
        enrichment_by_name[champion_name] = {
            "champ_id": champ_id,
            "level": int_value(row["level"]) or None,
            "rank": int_value(row["rank"]) or None,
            "awakening_level": int_value(row["awakening_level"]) or None,
            "empowerment_level": int_value(row["empowerment_level"]) or None,
            "booked": bool(row["booked"]),
            "stats": dict(stats_by_champ_id.get(champ_id, {})),
            "set_summary": applied_sets + [{"set_name": set_name, "set_kind": "unsupported"} for set_name in unsupported_sets],
            "build_fingerprint": build_fingerprint_for_items(equipped_items),
        }
    return enrichment_by_name


def build_member_skill_usage_by_slot(raw_path: str) -> Dict[int, List[Dict[str, Any]]]:
    path_text = string_value(raw_path).strip()
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists() or not path.is_file():
        return {}

    usage_rows = extract_skill_usage_counts(path)
    usage_by_slot: Dict[int, List[Dict[str, Any]]] = {}
    for row in usage_rows:
        slot_index = int_value(row.get("resolved_slot_index"))
        champion_type_id = int_value(row.get("champion_type_id"))
        skill_counts = dict_value(row.get("skill_usage_counts"))
        entries: List[Dict[str, Any]] = []
        for skill_key, usage_count in sorted(skill_counts.items(), key=lambda item: int_value(string_value(item[0]).removeprefix("A"))):
            skill_order = int_value(string_value(skill_key).removeprefix("A"))
            if skill_order <= 0:
                continue
            skill_code = ""
            if champion_type_id > 0:
                skill_code = str((champion_type_id // 10) * 100 + skill_order)
            entries.append(
                {
                    "skill_order": skill_order,
                    "skill_slot": f"A{skill_order}",
                    "skill_code": skill_code,
                    "usage_count": int_value(usage_count),
                }
            )
        if entries:
            usage_by_slot[slot_index] = entries
    return usage_by_slot


def infer_turn_counts_from_effect_timeline(effect_timeline: Dict[str, Any]) -> Dict[str, Optional[int]]:
    timeline_rows = list_value(dict_value(effect_timeline).get("timeline"))
    if not timeline_rows:
        return {"boss_turn": None, "turns": None}

    boss_turn = 0
    allied_turns = 0
    for row in timeline_rows:
        row_map = dict_value(row)
        if string_value(row_map.get("source_party_role")) == "enemy":
            boss_turn = max(boss_turn, int_value(row_map.get("enemy_turn_index")))
            continue
        allied_turns = max(allied_turns, int_value(row_map.get("source_party_turn_index")))

    return {
        "boss_turn": boss_turn or None,
        "turns": allied_turns or None,
    }


def build_assets(
    client_event: Dict[str, Any],
    live_events: List[Dict[str, Any]],
    battle_id: str,
) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []

    saved = dict_value(client_event.get("saved"))
    marker = dict_value(saved.get("marker"))
    raw_path = string_value(saved.get("raw_path"))
    meta_path = string_value(saved.get("meta_path"))
    captured_at = string_value(client_event.get("captured_at"))

    if raw_path:
        assets.append(
            {
                "asset_kind": "client_probe_battle_results_bin",
                "asset_path": raw_path,
                "sha256": string_value(marker.get("sha256")),
                "size_bytes": int_value(marker.get("size")) or None,
                "captured_at": captured_at,
                "metadata": {"probe": "client_probe"},
            }
        )
    if meta_path:
        assets.append(
            {
                "asset_kind": "client_probe_battle_results_meta",
                "asset_path": meta_path,
                "captured_at": captured_at,
                "metadata": {"probe": "client_probe"},
            }
        )

    for live_event in live_events:
        if event_battle_id(live_event) != battle_id:
            continue
        snapshot = dict_value(live_event.get("snapshot"))
        live_marker = dict_value(snapshot.get("marker"))
        if int_value(live_marker.get("size")) <= 11:
            continue
        saved_path = string_value(snapshot.get("saved_path"))
        if not saved_path:
            continue
        assets.append(
            {
                "asset_kind": "live_storage_battle_results_bin",
                "asset_path": saved_path,
                "size_bytes": int_value(live_marker.get("size")) or None,
                "captured_at": string_value(live_event.get("captured_at")),
                "metadata": {"probe": "live_storage_probe"},
            }
        )
        break

    return assets


def build_timeline_events(events: List[Dict[str, Any]], start_index: int, end_index: int) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for index in range(start_index, min(end_index + 1, len(events))):
        event = dict_value(events[index])
        event_type = string_value(event.get("event_type"))
        captured_at = string_value(event.get("captured_at"))
        if event_type == "sqlite_event":
            parsed = dict_value(dict_value(event.get("row")).get("parsed"))
            request = dict_value(dict_value(dict_value(parsed).get("p")).get("r"))
            request_type = string_value(request.get("t"))
            if request_type.startswith("Create"):
                payload.append(
                    {
                        "event_time": captured_at,
                        "event_type": "battle_created",
                        "source_name": string_value(event.get("db_name")),
                        "payload": {"request_type": request_type},
                    }
                )
        elif event_type == "log_line":
            line = string_value(event.get("line"))
            if "Change battle state" in line:
                payload.append(
                    {
                        "event_time": captured_at,
                        "event_type": "battle_state_changed",
                        "source_name": "log.txt",
                        "payload": {"line": line},
                    }
                )
            elif "BattleResult added:" in line:
                payload.append(
                    {
                        "event_time": captured_at,
                        "event_type": "battle_result_detected",
                        "source_name": "log.txt",
                        "payload": {"line": line},
                    }
                )
            elif "Close view - [View: Battle]" in line:
                payload.append(
                    {
                        "event_time": captured_at,
                        "event_type": "battle_view_closed",
                        "source_name": "log.txt",
                        "payload": {"line": line},
                    }
                )
    return payload


def build_run_payload(
    session_slug: str,
    client_event: Dict[str, Any],
    client_events: List[Dict[str, Any]],
    live_events: List[Dict[str, Any]],
    hero_types_path: Path,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    battle_context = dict_value(client_event.get("battle"))
    battle_id = event_battle_id(client_event) or string_value(battle_context.get("battle_id"))
    end_index = latest_event_index_for_battle(client_events, battle_id)
    start_index = first_event_index_for_battle(client_events, battle_id)
    sqlite_event = find_nearest_sqlite_create_event(client_events, start_index if start_index >= 0 else 0)
    mapping = derive_run_mapping(battle_context, sqlite_row=dict_value(dict_value(sqlite_event).get("row")), hero_types_path=hero_types_path)
    started_at = find_started_at(client_events, max(start_index, 0), max(end_index, 0))
    finished_at = find_finished_at(client_events, max(start_index, 0), max(end_index, 0))
    saved = dict_value(client_event.get("saved"))
    raw_path = Path(string_value(saved.get("raw_path")))
    damage_summary = extract_damage_summary(raw_path)
    skill_usage_by_slot = build_member_skill_usage_by_slot(string_value(saved.get("raw_path")))
    effect_timeline: Dict[str, Any] = {}
    if raw_path.exists() and raw_path.is_file():
        try:
            effect_timeline = extract_effect_timeline(raw_path, hero_types_path=hero_types_path)
        except Exception:
            effect_timeline = {}
    turn_counts = infer_turn_counts_from_effect_timeline(effect_timeline)
    damage_members_by_order = {
        int_value(row.get("member_order")): dict_value(row)
        for row in list_value(damage_summary.get("members"))
    }
    total_damage_value = damage_summary.get("total_damage")
    total_damage_available = total_damage_value is not None and parse_float_value(total_damage_value) > 0
    member_damage_status = string_value(damage_summary.get("member_damage_status")) or "not_available"
    if bool(damage_summary.get("damage_trusted")) and total_damage_available:
        damage_status = "imported_trusted_decoder"
    elif total_damage_available or member_damage_status != "not_available":
        damage_status = "imported_candidate_decoder"
    else:
        damage_status = "not_available"
    members = build_members(battle_context)
    member_enrichment_by_name = load_account_member_enrichment(db_path=db_path)
    for member in members:
        champion_name = string_value(member.get("champion_name")).strip()
        enrichment = dict_value(member_enrichment_by_name.get(champion_name))
        if enrichment:
            member["champ_id"] = string_value(enrichment.get("champ_id"))
            if int_value(member.get("level")) <= 0 and int_value(enrichment.get("level")) > 0:
                member["level"] = int_value(enrichment.get("level"))
            if int_value(member.get("rank")) <= 0 and int_value(enrichment.get("rank")) > 0:
                member["rank"] = int_value(enrichment.get("rank"))
            if int_value(enrichment.get("awakening_level")) > 0:
                member["awakening_level"] = int_value(enrichment.get("awakening_level"))
            if int_value(enrichment.get("empowerment_level")) > 0:
                member["empowerment_level"] = int_value(enrichment.get("empowerment_level"))
            member["booked"] = bool(enrichment.get("booked"))
            if dict_value(enrichment.get("stats")):
                member["stats"] = dict_value(enrichment.get("stats"))
                member["stat_source"] = "account_champion_total_stats"
            if list_value(enrichment.get("set_summary")):
                member["set_summary"] = list_value(enrichment.get("set_summary"))
            if string_value(enrichment.get("build_fingerprint")):
                member["build_fingerprint"] = string_value(enrichment.get("build_fingerprint"))
        slot_index = int_value(member.get("slot_index"))
        member_order = slot_index + 1
        damage_member = dict_value(damage_members_by_order.get(member_order))
        metrics: Dict[str, Any] = {}
        if damage_member:
            metrics["damage_taken"] = damage_member.get("damage_taken")
            metrics["damage_taken_trusted"] = bool(damage_summary.get("damage_taken_trusted"))
            if string_value(damage_member.get("damage_taken_status")):
                metrics["damage_taken_status"] = string_value(damage_member.get("damage_taken_status"))
            if damage_member.get("damage_done") is not None:
                metrics["damage_done"] = damage_member.get("damage_done")
            if string_value(damage_member.get("damage_done_status")):
                metrics["damage_done_status"] = string_value(damage_member.get("damage_done_status"))
            if damage_member.get("raw_damage_done") is not None:
                metrics["damage_done_weight"] = damage_member.get("raw_damage_done")
            metrics["raw_damage_taken"] = damage_member.get("raw_damage_taken")
        if metrics:
            member["metrics"] = metrics
        member["skill_usage"] = list_value(skill_usage_by_slot.get(slot_index))

    payload: Dict[str, Any] = {
        "saved_at": string_value(client_event.get("captured_at")) or finished_at,
        "source": "probe_import",
        "source_run_uid": battle_id,
        "battle_id": battle_id,
        "probe_session_slug": session_slug,
        "formation_index": battle_context.get("formation_index"),
        "result_code": "battle_results_detected",
        "success": True,
        "completed": True,
        "elapsed_seconds": elapsed_seconds(started_at, finished_at),
        "turns": turn_counts.get("turns"),
        "boss_turn": turn_counts.get("boss_turn"),
        "total_damage": total_damage_value,
        "notes": "Imported from probe session. success is inferred from a completed battleResults capture.",
        "labels": {
            "mapping_confidence": string_value(mapping.get("mapping_confidence")),
            "import_source": "probe_session",
        },
        "context": {
            "started_at": started_at,
            "finished_at": finished_at,
            "mapping_sources": list_value(mapping.get("mapping_sources")),
            "difficulty_source": string_value(mapping.get("difficulty_source")),
            "damage_status": damage_status,
            "total_damage_status": string_value(damage_summary.get("total_damage_status")) or "not_available",
            "member_damage_status": member_damage_status,
            "skill_usage_status": "imported_from_raw_events" if skill_usage_by_slot else "not_available",
            "effect_timeline_status": string_value(effect_timeline.get("status_timeline_status")) or "not_available",
            "effect_timeline_rows": int_value(effect_timeline.get("status_timeline_count")),
            "boss_turn_status": "inferred_from_effect_timeline" if turn_counts.get("boss_turn") else "not_available",
        },
        "members": members,
        "assets": build_assets(client_event, live_events, battle_id),
        "events": build_timeline_events(client_events, max(start_index, 0), max(end_index, 0)),
        "effect_timeline": effect_timeline,
    }
    payload.update(mapping)
    return payload


def import_probe_session(
    session_slug: str,
    client_root: Path = CLIENT_PROBE_ROOT,
    live_root: Path = LIVE_STORAGE_ROOT,
    db_path: Path = DB_PATH,
    hero_types_path: Path = HH_HERO_TYPES_PATH,
) -> Dict[str, Any]:
    client_session_dir = client_root / session_slug
    if not client_session_dir.exists():
        raise FileNotFoundError(f"Client probe session not found: {client_session_dir}")

    client_events = read_jsonl(client_session_dir / "events.jsonl")
    live_events = read_jsonl((live_root / session_slug) / "events.jsonl")
    battle_result_events = select_best_rich_battle_result_events(
        [event for event in client_events if is_rich_battle_results_event(event)]
    )

    summaries: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for event in battle_result_events:
        battle_id = event_battle_id(event)
        if not battle_id:
            continue
        run_id = existing_run_id("probe_import", battle_id, db_path=db_path)
        if run_id is not None:
            skipped.append({"battle_id": battle_id, "run_id": run_id, "reason": "already_imported"})
            continue
        payload = build_run_payload(
            session_slug=session_slug,
            client_event=event,
            client_events=client_events,
            live_events=live_events,
            hero_types_path=hero_types_path,
            db_path=db_path,
        )
        summaries.append(record_run_history(payload, db_path=db_path))

    return {
        "session_slug": session_slug,
        "imported_runs": len(summaries),
        "skipped_runs": len(skipped),
        "summaries": summaries,
        "skipped": skipped,
    }


def import_probe_sessions(
    session_slugs: Iterable[str],
    client_root: Path = CLIENT_PROBE_ROOT,
    live_root: Path = LIVE_STORAGE_ROOT,
    db_path: Path = DB_PATH,
    hero_types_path: Path = HH_HERO_TYPES_PATH,
) -> Dict[str, Any]:
    results = [
        import_probe_session(
            session_slug=string_value(session_slug),
            client_root=client_root,
            live_root=live_root,
            db_path=db_path,
            hero_types_path=hero_types_path,
        )
        for session_slug in session_slugs
        if string_value(session_slug).strip()
    ]
    return {
        "sessions": len(results),
        "imported_runs": sum(int_value(result.get("imported_runs")) for result in results),
        "skipped_runs": sum(int_value(result.get("skipped_runs")) for result in results),
        "results": results,
    }


def backfill_probe_skill_usage(db_path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    imported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_rows = conn.execute(
            """
            SELECT r.run_id, r.battle_id, a.asset_path
            FROM run_history_runs r
            JOIN run_history_assets a
              ON a.run_id = r.run_id
            WHERE r.source = 'probe_import'
              AND a.asset_kind = 'client_probe_battle_results_bin'
            ORDER BY r.run_id ASC
            """
        ).fetchall()

        for run_row in run_rows:
            run_id = int(run_row["run_id"])
            battle_id = string_value(run_row["battle_id"])
            existing_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM run_history_member_skill_usage WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
            )
            if existing_count > 0:
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "already_backfilled"})
                continue

            usage_by_slot = build_member_skill_usage_by_slot(string_value(run_row["asset_path"]))
            if not usage_by_slot:
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "no_skill_usage_found"})
                continue

            member_rows = conn.execute(
                """
                SELECT member_order
                FROM run_history_members
                WHERE run_id = ?
                ORDER BY member_order ASC
                """,
                (run_id,),
            ).fetchall()

            inserted = 0
            for member_row in member_rows:
                member_order = int(member_row["member_order"])
                slot_index = member_order - 1
                for skill_usage in list_value(usage_by_slot.get(slot_index)):
                    skill_usage_map = dict_value(skill_usage)
                    conn.execute(
                        """
                        INSERT INTO run_history_member_skill_usage (
                            run_id, member_order, skill_order, skill_slot, skill_code, usage_count, usage_payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            member_order,
                            int_value(skill_usage_map.get("skill_order")),
                            string_value(skill_usage_map.get("skill_slot")),
                            string_value(skill_usage_map.get("skill_code")),
                            int_value(skill_usage_map.get("usage_count")),
                            json.dumps(skill_usage_map, ensure_ascii=False, separators=(",", ":")),
                        ),
                    )
                    inserted += 1

            if inserted > 0:
                imported.append({"run_id": run_id, "battle_id": battle_id, "skill_usages": inserted})
            else:
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "no_matching_members"})

        conn.commit()

    return {
        "backfilled_runs": len(imported),
        "skipped_runs": len(skipped),
        "imported": imported,
        "skipped": skipped,
    }


def backfill_probe_effect_timeline(db_path: Path = DB_PATH, hero_types_path: Path = HH_HERO_TYPES_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    imported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_rows = conn.execute(
            """
            SELECT r.run_id, r.battle_id, r.context_json, a.asset_path
            FROM run_history_runs r
            JOIN run_history_assets a
              ON a.run_id = r.run_id
            WHERE r.source = 'probe_import'
              AND a.asset_kind = 'client_probe_battle_results_bin'
            ORDER BY r.run_id ASC
            """
        ).fetchall()

        for run_row in run_rows:
            run_id = int(run_row["run_id"])
            battle_id = string_value(run_row["battle_id"])
            existing_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM run_history_effect_timeline WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
            )
            if existing_count > 0:
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "already_backfilled"})
                continue

            raw_path = Path(string_value(run_row["asset_path"]))
            if not raw_path.exists() or not raw_path.is_file():
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "raw_asset_missing"})
                continue

            try:
                effect_timeline = extract_effect_timeline(raw_path, hero_types_path=hero_types_path)
            except Exception:
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "decode_failed"})
                continue

            inserted = insert_run_effect_timeline(conn, run_id=run_id, effect_timeline=effect_timeline)
            if inserted <= 0:
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "no_effect_rows_found"})
                continue

            try:
                context = dict_value(json.loads(string_value(run_row["context_json"]) or "{}"))
            except json.JSONDecodeError:
                context = {}
            context["effect_timeline_status"] = string_value(effect_timeline.get("status_timeline_status")) or "not_available"
            context["effect_timeline_rows"] = int_value(effect_timeline.get("status_timeline_count"))
            conn.execute(
                "UPDATE run_history_runs SET context_json = ? WHERE run_id = ?",
                (json.dumps(context, ensure_ascii=False, separators=(",", ":")), run_id),
            )
            imported.append({"run_id": run_id, "battle_id": battle_id, "effect_timeline_rows": inserted})

        conn.commit()

    return {
        "backfilled_runs": len(imported),
        "skipped_runs": len(skipped),
        "imported": imported,
        "skipped": skipped,
    }


def backfill_probe_boss_turns(db_path: Path = DB_PATH, hero_types_path: Path = HH_HERO_TYPES_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    updated: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_rows = conn.execute(
            """
            SELECT r.run_id, r.battle_id, r.context_json, a.asset_path
            FROM run_history_runs r
            JOIN run_history_assets a
              ON a.run_id = r.run_id
            WHERE r.source = 'probe_import'
              AND a.asset_kind = 'client_probe_battle_results_bin'
            ORDER BY r.run_id ASC
            """
        ).fetchall()

        for run_row in run_rows:
            run_id = int(run_row["run_id"])
            battle_id = string_value(run_row["battle_id"])
            raw_path = Path(string_value(run_row["asset_path"]))
            if not raw_path.exists() or not raw_path.is_file():
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "raw_asset_missing"})
                continue

            try:
                effect_timeline = extract_effect_timeline(raw_path, hero_types_path=hero_types_path)
            except Exception:
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "decode_failed"})
                continue

            turn_counts = infer_turn_counts_from_effect_timeline(effect_timeline)
            boss_turn = turn_counts.get("boss_turn")
            turns = turn_counts.get("turns")
            if boss_turn is None and turns is None:
                skipped.append({"run_id": run_id, "battle_id": battle_id, "reason": "turns_not_available"})
                continue

            try:
                context = dict_value(json.loads(string_value(run_row["context_json"]) or "{}"))
            except json.JSONDecodeError:
                context = {}
            context["boss_turn_status"] = "inferred_from_effect_timeline" if boss_turn else "not_available"

            conn.execute(
                """
                UPDATE run_history_runs
                SET turns = COALESCE(?, turns),
                    boss_turn = COALESCE(?, boss_turn),
                    context_json = ?
                WHERE run_id = ?
                """,
                (
                    turns,
                    boss_turn,
                    json.dumps(context, ensure_ascii=False, separators=(",", ":")),
                    run_id,
                ),
            )
            updated.append({"run_id": run_id, "battle_id": battle_id, "turns": turns, "boss_turn": boss_turn})

        conn.commit()

    return {
        "backfilled_runs": len(updated),
        "skipped_runs": len(skipped),
        "updated": updated,
        "skipped": skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa run da sessioni probe verso run_history_* nel DB CB Forge.")
    parser.add_argument("--session", action="append", default=[], help="Slug sessione probe da importare. Ripetibile.")
    parser.add_argument("--all", action="store_true", help="Importa tutte le sessioni trovate in input/client_probe.")
    parser.add_argument("--db-path", default=str(DB_PATH), help="Path del database SQLite target.")
    parser.add_argument("--client-root", default=str(CLIENT_PROBE_ROOT), help="Root delle sessioni client_probe.")
    parser.add_argument("--live-root", default=str(LIVE_STORAGE_ROOT), help="Root delle sessioni live_storage_probe.")
    parser.add_argument("--hero-types-path", default=str(HH_HERO_TYPES_PATH), help="Path di hh_hero_types.json.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client_root = Path(args.client_root)
    session_slugs = list(args.session)
    if args.all:
        session_slugs.extend(sorted(path.name for path in client_root.iterdir() if path.is_dir()))
    deduped = list(dict.fromkeys(string_value(slug) for slug in session_slugs if string_value(slug).strip()))
    if not deduped:
        raise SystemExit("No sessions selected. Use --session <slug> or --all.")

    summary = import_probe_sessions(
        session_slugs=deduped,
        client_root=client_root,
        live_root=Path(args.live_root),
        db_path=Path(args.db_path),
        hero_types_path=Path(args.hero_types_path),
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
