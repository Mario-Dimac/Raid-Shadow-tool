from __future__ import annotations

import json
from pathlib import Path

from run_mapper import derive_run_mapping


def test_derive_run_mapping_for_confirmed_demon_lord_stage(tmp_path: Path) -> None:
    hero_types_path = tmp_path / "hh_hero_types.json"
    hero_types_path.write_text(
        json.dumps(
            [
                {
                    "id": 22296,
                    "name": "Demon Lord",
                    "forms": [
                        {
                            "element": 4,
                            "baseStats": {"speed": 170.0},
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    battle_context = {
        "battle_id": "3b36e42b-7f4c-4fbf-aa06-82ce6e070bc6",
        "stage_id": "4019021",
        "formation_index": 0,
        "enemy_rows": [
            {
                "round": 1,
                "slot": 1,
                "type_id": 22296,
                "name": "Type 22296",
                "level": 250,
            }
        ],
    }
    sqlite_row = {
        "parsed": {
            "p": {
                "r": {
                    "t": "CreateAllianceBossBattle",
                }
            }
        }
    }

    mapped = derive_run_mapping(battle_context, sqlite_row=sqlite_row, hero_types_path=hero_types_path)

    assert mapped["encounter_key"] == "demon_lord_ultra_nightmare"
    assert mapped["encounter_family"] == "demon_lord"
    assert mapped["area_region"] == "clan_boss"
    assert mapped["difficulty"] == "ultra_nightmare"
    assert mapped["boss_affinity"] == "void"
    assert mapped["enemy_type_id"] == 22296
    assert mapped["enemy_level"] == 250
    assert mapped["mapping_confidence"] == "high"


def test_derive_run_mapping_for_magic_ultra_nightmare_demon_lord_stage(tmp_path: Path) -> None:
    hero_types_path = tmp_path / "hh_hero_types.json"
    hero_types_path.write_text(
        json.dumps(
            [
                {
                    "id": 22266,
                    "name": "Demon Lord",
                    "forms": [
                        {
                            "element": 1,
                            "baseStats": {"speed": 170.0},
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    battle_context = {
        "battle_id": "a601b893-5a0d-40f8-b985-a31794b840d5",
        "stage_id": "4019022",
        "formation_index": 0,
        "enemy_rows": [
            {
                "round": 1,
                "slot": 1,
                "type_id": 22266,
                "name": "Type 22266",
                "level": 250,
            }
        ],
    }

    mapped = derive_run_mapping(battle_context, sqlite_row=None, hero_types_path=hero_types_path)

    assert mapped["encounter_key"] == "demon_lord_ultra_nightmare"
    assert mapped["encounter_name"] == "Demon Lord Ultra-Nightmare"
    assert mapped["difficulty"] == "ultra_nightmare"
    assert mapped["boss_affinity"] == "magic"
    assert mapped["mapping_confidence"] == "high"


def test_derive_run_mapping_for_spirit_ultra_nightmare_demon_lord_stage(tmp_path: Path) -> None:
    hero_types_path = tmp_path / "hh_hero_types.json"
    hero_types_path.write_text(
        json.dumps(
            [
                {
                    "id": 22326,
                    "name": "Demon Lord",
                    "forms": [
                        {
                            "element": 3,
                            "baseStats": {"speed": 170.0},
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    battle_context = {
        "battle_id": "0f67dd9f-18fb-4d2d-884f-af4de77ec9ab",
        "stage_id": "4019024",
        "formation_index": 0,
        "enemy_rows": [
            {
                "round": 1,
                "slot": 1,
                "type_id": 22326,
                "name": "Type 22326",
                "level": 250,
            }
        ],
    }

    mapped = derive_run_mapping(battle_context, sqlite_row=None, hero_types_path=hero_types_path)

    assert mapped["encounter_key"] == "demon_lord_ultra_nightmare"
    assert mapped["encounter_name"] == "Demon Lord Ultra-Nightmare"
    assert mapped["difficulty"] == "ultra_nightmare"
    assert mapped["boss_affinity"] == "spirit"
    assert mapped["mapping_confidence"] == "high"


def test_derive_run_mapping_returns_low_confidence_for_unknown_stage(tmp_path: Path) -> None:
    hero_types_path = tmp_path / "hh_hero_types.json"
    hero_types_path.write_text("[]", encoding="utf-8")

    mapped = derive_run_mapping({"stage_id": "9999999"}, sqlite_row=None, hero_types_path=hero_types_path)

    assert mapped["encounter_key"] == "9999999"
    assert mapped["difficulty"] == ""
    assert mapped["boss_affinity"] == ""
    assert mapped["mapping_confidence"] == "low"
