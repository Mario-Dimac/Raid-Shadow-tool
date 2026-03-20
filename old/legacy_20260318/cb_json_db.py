from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from cb_rules import CHAMPION_HINTS
from cb_teams import load_account


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
DB_DIR = INPUT_DIR / "db"
ROSTER_DB_PATH = DB_DIR / "champion_roster.json"
SKILL_REGISTRY_PATH = DB_DIR / "champion_skill_registry.json"
SET_REGISTRY_PATH = DB_DIR / "set_registry.json"
COMBAT_DB_PATH = DB_DIR / "combat_db.json"


def ensure_json_databases(account: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    account_data = account or load_account()
    roster_payload = build_roster_database(account_data)
    skill_payload = build_skill_registry(account_data)
    set_payload = build_set_registry(account_data)

    save_json(ROSTER_DB_PATH, roster_payload)
    save_json(SKILL_REGISTRY_PATH, skill_payload)
    save_json(SET_REGISTRY_PATH, set_payload)
    ensure_combat_db()

    return {
        "roster": file_status(ROSTER_DB_PATH),
        "skills": file_status(SKILL_REGISTRY_PATH),
        "sets": file_status(SET_REGISTRY_PATH),
        "combat": file_status(COMBAT_DB_PATH),
    }


def ensure_combat_db(path: Path = COMBAT_DB_PATH) -> Dict[str, Any]:
    payload = load_json(path)
    if payload:
        normalized = normalize_combat_db(payload)
        save_json(path, normalized)
        return normalized
    normalized = normalize_combat_db({})
    save_json(path, normalized)
    return normalized


def load_combat_db(path: Path = COMBAT_DB_PATH) -> Dict[str, Any]:
    payload = load_json(path)
    if payload:
        return normalize_combat_db(payload)
    return ensure_combat_db(path)


def save_combat_db(payload: Dict[str, Any], path: Path = COMBAT_DB_PATH) -> Dict[str, Any]:
    normalized = normalize_combat_db(payload)
    save_json(path, normalized)
    return normalized


def normalize_combat_db(payload: Dict[str, Any]) -> Dict[str, Any]:
    runs = payload.get("runs")
    sessions = payload.get("sessions")
    if not isinstance(runs, list):
        runs = []
    if not isinstance(sessions, list):
        sessions = []
    active_session = payload.get("active_session")
    if not isinstance(active_session, dict):
        active_session = None
    return {
        "version": 1,
        "runs": runs,
        "sessions": sessions,
        "active_session": active_session,
    }


def build_roster_database(account: Dict[str, Any]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for champion in list_value(account.get("champions")):
        rows.append(
            {
                "champ_id": string_value(champion.get("champ_id")),
                "name": string_value(champion.get("name")),
                "rarity": string_value(champion.get("rarity")),
                "rank": int_value(champion.get("rank")),
                "level": int_value(champion.get("level")),
                "affinity": string_value(champion.get("affinity")),
                "faction": string_value(champion.get("faction")),
                "awakening_level": int_value(champion.get("awakening_level")),
                "empowerment_level": int_value(champion.get("empowerment_level")),
                "role_tags": list_value(champion.get("role_tags")),
                "base_stats": dict_value(champion.get("base_stats")),
                "total_stats": dict_value(champion.get("total_stats")),
                "equipped_item_ids": [string_value(item) for item in list_value(champion.get("equipped_item_ids"))],
                "booked": bool(champion.get("booked")),
                "skills": list_value(champion.get("skills")),
            }
        )
    rows.sort(key=lambda item: (item["name"], item["level"], item["rank"], item["champ_id"]))
    return {
        "version": 1,
        "champions": rows,
    }


def build_skill_registry(account: Dict[str, Any]) -> Dict[str, Any]:
    from cb_simulator import CHAMPION_DEFINITIONS

    best_by_name: Dict[str, Dict[str, Any]] = {}
    for champion in list_value(account.get("champions")):
        name = string_value(champion.get("name"))
        current = best_by_name.get(name)
        candidate = {
            "name": name,
            "champ_id": string_value(champion.get("champ_id")),
            "rarity": string_value(champion.get("rarity")),
            "rank": int_value(champion.get("rank")),
            "level": int_value(champion.get("level")),
            "skills": list_value(champion.get("skills")),
            "hint_roles": list(CHAMPION_HINTS.get(name).roles) if name in CHAMPION_HINTS else [],
            "hint_boss_scores": dict(CHAMPION_HINTS.get(name).boss_scores) if name in CHAMPION_HINTS else {},
            "simulator_definition": serialize_champion_definition(name),
        }
        if current is None or (candidate["level"], candidate["rank"]) > (current["level"], current["rank"]):
            best_by_name[name] = candidate
    rows = sorted(best_by_name.values(), key=lambda item: item["name"])
    return {
        "version": 1,
        "champions": rows,
        "supported_simulator_definitions": sorted(CHAMPION_DEFINITIONS.keys()),
    }


def build_set_registry(account: Dict[str, Any]) -> Dict[str, Any]:
    from cb_simulator import SET_BONUS_RULES

    observed_sets: Dict[str, int] = {}
    for item in list_value(account.get("gear")):
        set_name = string_value(item.get("set_name")).strip()
        if not set_name:
            continue
        observed_sets[set_name] = observed_sets.get(set_name, 0) + 1

    rows: List[Dict[str, Any]] = []
    for set_name in sorted(set(observed_sets) | set(SET_BONUS_RULES)):
        rule = dict_value(SET_BONUS_RULES.get(set_name))
        rows.append(
            {
                "set_name": set_name,
                "observed_items": int(observed_sets.get(set_name, 0)),
                "pieces_required": int_value(rule.get("pieces")),
                "stats": dict_value(rule.get("stats")),
                "heal_each_turn_pct": float_value(rule.get("heal_each_turn_pct")),
                "supported_in_simulator": bool(rule),
            }
        )
    return {
        "version": 1,
        "sets": rows,
    }


def serialize_champion_definition(name: str) -> Dict[str, Any]:
    from cb_simulator import CHAMPION_DEFINITIONS

    definition = CHAMPION_DEFINITIONS.get(name)
    if not definition:
        return {}
    return {
        "opener": list(definition.opener),
        "priority": list(definition.priority),
        "passive": definition.passive or "",
        "notes": definition.notes,
        "skills": {
            slot: {
                "slot": skill.slot,
                "name": skill.name,
                "cooldown": skill.cooldown,
                "damage_factor": skill.damage_factor,
                "team_buffs": dict(skill.team_buffs),
                "self_buffs": dict(skill.self_buffs),
                "boss_debuffs": dict(skill.boss_debuffs),
                "cooldown_reduction_allies": skill.cooldown_reduction_allies,
                "turn_meter_fill_allies": skill.turn_meter_fill_allies,
                "direct_heal_allies": skill.direct_heal_allies,
            }
            for slot, skill in definition.skills.items()
        },
    }


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def file_status(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "size": 0}
    return {
        "path": str(path),
        "exists": True,
        "size": path.stat().st_size,
    }


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


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


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}
