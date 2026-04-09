from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent
HH_HERO_TYPES_PATH = BASE_DIR / "input" / "hh_hero_types.json"

AFFINITY_BY_ELEMENT = {
    1: "magic",
    2: "force",
    3: "spirit",
    4: "void",
}

DEMON_LORD_STAGE_MAP: Dict[str, Dict[str, Any]] = {
    # Confirmed from probe telemetry: these stage ids are the Demon Lord's
    # highest difficulty, while affinity is resolved from the enemy type.
    "4019021": {
        "encounter_key": "demon_lord_ultra_nightmare",
        "encounter_name": "Demon Lord Ultra-Nightmare",
        "encounter_family": "demon_lord",
        "area_region": "clan_boss",
        "game_mode": "clan_boss",
        "difficulty": "ultra_nightmare",
        "stage_label": "Demon Lord. Ultra-Nightmare",
        "stage_tier": 6,
        "difficulty_source": "confirmed_probe_observation_2026_03_22",
    },
    "4019022": {
        "encounter_key": "demon_lord_ultra_nightmare",
        "encounter_name": "Demon Lord Ultra-Nightmare",
        "encounter_family": "demon_lord",
        "area_region": "clan_boss",
        "game_mode": "clan_boss",
        "difficulty": "ultra_nightmare",
        "stage_label": "Demon Lord. Ultra-Nightmare",
        "stage_tier": 6,
        "difficulty_source": "confirmed_probe_observation_2026_04_06",
    },
    "4019023": {
        "encounter_key": "demon_lord_ultra_nightmare",
        "encounter_name": "Demon Lord Ultra-Nightmare",
        "encounter_family": "demon_lord",
        "area_region": "clan_boss",
        "game_mode": "clan_boss",
        "difficulty": "ultra_nightmare",
        "stage_label": "Demon Lord. Ultra-Nightmare",
        "stage_tier": 6,
        "difficulty_source": "confirmed_probe_observation_2026_04_06",
    },
    "4019024": {
        "encounter_key": "demon_lord_ultra_nightmare",
        "encounter_name": "Demon Lord Ultra-Nightmare",
        "encounter_family": "demon_lord",
        "area_region": "clan_boss",
        "game_mode": "clan_boss",
        "difficulty": "ultra_nightmare",
        "stage_label": "Demon Lord. Ultra-Nightmare",
        "stage_tier": 6,
        "difficulty_source": "confirmed_probe_observation_2026_04_06",
    },
}


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


@lru_cache(maxsize=1)
def load_enemy_type_map(hero_types_path: Path = HH_HERO_TYPES_PATH) -> Dict[int, Dict[str, Any]]:
    if not hero_types_path.exists():
        return {}
    payload = json.loads(hero_types_path.read_text(encoding="utf-8-sig"))
    mapping: Dict[int, Dict[str, Any]] = {}
    for item in list_value(payload):
        item_map = dict_value(item)
        type_id = int_value(item_map.get("id"))
        if type_id <= 0:
            continue
        forms = list_value(item_map.get("forms"))
        form = dict_value(forms[0]) if forms else {}
        mapping[type_id] = {
            "name": string_value(item_map.get("name")),
            "element": int_value(form.get("element")),
            "speed": float(dict_value(form.get("baseStats")).get("speed") or 0.0),
        }
    return mapping


def build_demon_lord_metadata(
    battle_context: Dict[str, Any],
    sqlite_row: Optional[Dict[str, Any]] = None,
    hero_types_path: Path = HH_HERO_TYPES_PATH,
) -> Dict[str, Any]:
    battle = dict_value(battle_context)
    parsed_row = dict_value(sqlite_row)
    stage_id = string_value(battle.get("stage_id"))
    stage_map = dict_value(DEMON_LORD_STAGE_MAP.get(stage_id))
    enemy_rows = list_value(battle.get("enemy_rows"))
    enemy_type_id = int_value(dict_value(enemy_rows[0]).get("type_id")) if enemy_rows else 0
    enemy_level = int_value(dict_value(enemy_rows[0]).get("level")) if enemy_rows else 0
    enemy_type_map = load_enemy_type_map(hero_types_path)
    enemy_info = dict_value(enemy_type_map.get(enemy_type_id))
    affinity = AFFINITY_BY_ELEMENT.get(int_value(enemy_info.get("element")))

    metadata = {
        "encounter_key": string_value(stage_map.get("encounter_key")) or "demon_lord_unknown",
        "encounter_name": string_value(stage_map.get("encounter_name")) or "Demon Lord",
        "encounter_family": "demon_lord",
        "area_region": "clan_boss",
        "game_mode": "clan_boss",
        "difficulty": string_value(stage_map.get("difficulty")) or "",
        "difficulty_source": string_value(stage_map.get("difficulty_source")) or "",
        "stage_id": stage_id,
        "stage_label": string_value(stage_map.get("stage_label")),
        "stage_tier": int_value(stage_map.get("stage_tier")) if stage_map.get("stage_tier") is not None else None,
        "boss_affinity": affinity or "",
        "affinity_context": "enemy_type_element" if affinity else "",
        "enemy_type_id": enemy_type_id or None,
        "enemy_name": string_value(enemy_info.get("name")) or string_value(dict_value(enemy_rows[0]).get("name")),
        "enemy_level": enemy_level or None,
        "mapping_confidence": "high" if stage_map and affinity else ("medium" if stage_map or affinity else "low"),
        "mapping_sources": [
            item
            for item in [
                "CreateAllianceBossBattle" if is_create_alliance_boss_battle(parsed_row) else "",
                "stage_map" if stage_map else "",
                "enemy_type_element" if affinity else "",
            ]
            if item
        ],
    }
    return metadata


def is_create_alliance_boss_battle(sqlite_row: Dict[str, Any]) -> bool:
    payload = dict_value(dict_value(dict_value(sqlite_row).get("parsed")).get("p")).get("r")
    return string_value(dict_value(payload).get("t")) == "CreateAllianceBossBattle"


def derive_run_mapping(
    battle_context: Dict[str, Any],
    sqlite_row: Optional[Dict[str, Any]] = None,
    hero_types_path: Path = HH_HERO_TYPES_PATH,
) -> Dict[str, Any]:
    if is_create_alliance_boss_battle(sqlite_row):
        return build_demon_lord_metadata(battle_context, sqlite_row=sqlite_row, hero_types_path=hero_types_path)

    stage_id = string_value(dict_value(battle_context).get("stage_id"))
    if stage_id in DEMON_LORD_STAGE_MAP:
        return build_demon_lord_metadata(battle_context, sqlite_row=sqlite_row, hero_types_path=hero_types_path)

    enemy_rows = list_value(dict_value(battle_context).get("enemy_rows"))
    enemy_type_id = int_value(dict_value(enemy_rows[0]).get("type_id")) if enemy_rows else 0
    enemy_level = int_value(dict_value(enemy_rows[0]).get("level")) if enemy_rows else 0
    enemy_type_map = load_enemy_type_map(hero_types_path)
    enemy_info = dict_value(enemy_type_map.get(enemy_type_id))
    enemy_name = string_value(enemy_info.get("name")) or (string_value(dict_value(enemy_rows[0]).get("name")) if enemy_rows else "")
    affinity = AFFINITY_BY_ELEMENT.get(int_value(enemy_info.get("element")))
    is_demon_lord = enemy_name.strip().lower() == "demon lord"

    return {
        "encounter_key": stage_id or (enemy_name.lower().replace(" ", "_") if enemy_name else "unknown_encounter"),
        "encounter_name": enemy_name,
        "encounter_family": "demon_lord" if is_demon_lord else "",
        "area_region": "clan_boss" if is_demon_lord else "",
        "game_mode": "clan_boss" if is_demon_lord else "",
        "difficulty": "",
        "difficulty_source": "",
        "stage_id": stage_id,
        "stage_label": "",
        "stage_tier": None,
        "boss_affinity": affinity or "",
        "affinity_context": "enemy_type_element" if affinity else "",
        "enemy_type_id": enemy_type_id or None,
        "enemy_name": enemy_name,
        "enemy_level": enemy_level or None,
        "mapping_confidence": "medium" if enemy_name or affinity else "low",
        "mapping_sources": [
            item
            for item in [
                "enemy_type_name" if enemy_name else "",
                "enemy_type_element" if affinity else "",
            ]
            if item
        ],
    }
