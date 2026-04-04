from __future__ import annotations

import json
from pathlib import Path

from boss_modules import build_boss_intel
import cbforge_web
import pytest
from cbforge_web import (
    RunRecorderController,
    build_gear_summary,
    build_run_recorder_db_import_index,
    build_run_recorder_status,
    build_set_curation_payload,
    equip_team_optimizer_in_game,
    build_team_optimizer_local_bridge_plan,
    build_team_optimizer_loadout,
    build_team_optimizer_view,
    delete_run_recorder_session,
    build_set_registry,
    build_sell_queue_summary,
    build_web_summary,
    champion_detail,
    gear_item_detail,
    import_all_run_recorder_sessions,
    import_run_recorder_session,
    list_gear_items,
    list_run_history_runs_for_session,
    list_owned_champions,
    list_owned_champions_with_speed,
    build_clan_boss_recommendations,
    build_ai_training_overview,
    train_ai_baseline_model,
    list_run_recorder_sessions,
    prepare_server_runtime,
    refresh_gear_from_game,
    run_history_run_detail,
    run_recorder_session_detail,
    sell_artifacts_from_queue,
)
from forge_db import bootstrap_database, record_run_history


class _DisconnectingWriter:
    def write(self, _: bytes) -> None:
        raise ConnectionAbortedError(10053, "client disconnected")


class _ExplodingWriter:
    def write(self, _: bytes) -> None:
        raise RuntimeError("boom")


def _build_handler_with_writer(writer: object) -> cbforge_web.CBForgeHandler:
    handler = object.__new__(cbforge_web.CBForgeHandler)
    handler.wfile = writer
    handler.send_response = lambda status: None
    handler.send_header = lambda name, value: None
    handler.end_headers = lambda: None
    return handler


def test_emit_response_ignores_client_disconnects() -> None:
    handler = _build_handler_with_writer(_DisconnectingWriter())
    handler._emit_response(b"{}", "application/json; charset=utf-8")


def test_emit_response_reraises_unexpected_write_errors() -> None:
    handler = _build_handler_with_writer(_ExplodingWriter())
    with pytest.raises(RuntimeError, match="boom"):
        handler._emit_response(b"{}", "application/json; charset=utf-8")


def test_web_queries_expose_owned_roster_and_detail(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 1,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack", "support"],
                "base_stats": {"hp": 20000, "def": 1200},
                "total_stats": {"hp": 50000, "def": 3000, "spd": 210},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "geo_a1",
                        "name": "Stone Hammer",
                        "cooldown": 0,
                        "description": "A1 text",
                        "effects": [{"type": "damage", "target": "enemy", "value": 1.0}],
                    },
                    {
                        "slot": "A2",
                        "skill_id": "geo_a2",
                        "name": "Stone Burn",
                        "cooldown": 3,
                        "description": "A2 text",
                        "effects": [{"type": "hp_burn", "target": "enemy", "duration": 3, "chance": 100}],
                    },
                ],
            },
            {
                "champ_id": "champ-2",
                "name": "Coldheart",
                "rarity": "rare",
                "affinity": "void",
                "faction": "Dark Elves",
                "level": 50,
                "rank": 5,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": False,
                "role_tags": ["attack"],
                "base_stats": {"hp": 15000},
                "total_stats": {"hp": 32000},
                "equipped_item_ids": [],
                "skills": [],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_web_summary(db_path)
    roster = list_owned_champions(db_path, scope="all", sort="name")
    detail = champion_detail("Geomancer", db_path)

    assert summary["owned_champions"] == 2
    assert summary["registry_targets_ready"] == 1
    assert [item["champion_name"] for item in roster["champions"]] == ["Coldheart", "Geomancer"]
    assert roster["champions"][1]["is_registry_target"] is True
    assert roster["champions"][1]["enriched"] is True
    assert roster["champions"][1]["data_status"] == "complete"
    assert detail["account"]["champion_name"] == "Geomancer"
    assert detail["roles"] == ["attack", "support"]
    assert detail["base_stats"]["hp"] == 20000.0
    assert detail["base_totals"]["hp"] == 20000.0
    assert detail["total_stats"]["spd"] == 210.0
    assert detail["stat_model"]["source"] == "raw"
    assert detail["skill_data"]["data_status"] == "complete"
    assert detail["skills"][0]["skill_name"] == "Stone Hammer"
    assert detail["skills"][1]["effects"][0]["effect_type"] == "hp_burn"


def test_web_roster_filters_missing_enrichment(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": [],
                "skills": [{"slot": "A1", "skill_id": "geo_a1", "name": "48801", "effects": []}],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    missing = list_owned_champions(db_path, scope="missing")

    assert len(missing["champions"]) == 1
    assert missing["champions"][0]["champion_name"] == "Geomancer"
    assert missing["champions"][0]["enriched"] is False
    assert missing["champions"][0]["data_status"] == "missing"


def test_web_roster_deduplicates_multiple_owned_instances(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 50,
                "rank": 5,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": False,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": [],
                "skills": [],
            },
            {
                "champ_id": "champ-2",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": [],
                "skills": [],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    roster = list_owned_champions(db_path)

    assert len(roster["champions"]) == 1
    assert roster["champions"][0]["champ_id"] == "champ-2"


def test_owned_champions_with_speed_tolerates_partial_rows(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 50,
                "rank": 5,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": False,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {"spd": 190},
                "equipped_item_ids": [],
                "skills": [],
            },
            {
                "champ_id": "champ-2",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {"spd": 210},
                "equipped_item_ids": [],
                "skills": [],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    roster = list_owned_champions_with_speed(db_path)

    assert len(roster) == 1
    assert roster[0]["champ_id"] == "champ-2"
    assert roster[0]["speed"] == 210.0


def test_web_team_optimizer_view_exposes_team_and_targets(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Ninja",
                "rarity": "legendary",
                "affinity": "magic",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 18000, "atk": 1500, "def": 1100, "spd": 98},
                "total_stats": {"hp": 42000, "atk": 5400, "def": 2800, "spd": 177, "acc": 265, "crit_rate": 100, "crit_dmg": 220},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "ninja_a2",
                        "name": "Hailburn",
                        "cooldown": 3,
                        "description": "Attacks and places HP Burn.",
                        "effects": [{"type": "hp_burn", "target": "enemy", "duration": 3, "chance": 100}],
                    }
                ],
            },
            {
                "champ_id": "champ-2",
                "name": "Stag Knight",
                "rarity": "epic",
                "affinity": "magic",
                "faction": "Banner Lords",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 19000, "atk": 1200, "def": 1200, "spd": 102},
                "total_stats": {"hp": 54000, "atk": 2400, "def": 3600, "spd": 219, "acc": 345},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "stag_a2",
                        "name": "Huntmaster",
                        "cooldown": 4,
                        "description": "Places Decrease ATK and Decrease DEF.",
                        "effects": [
                            {"type": "decrease_attack", "target": "enemy", "duration": 2, "chance": 100},
                            {"type": "decrease_def", "target": "enemy", "duration": 2, "chance": 100},
                        ],
                    }
                ],
            },
            {
                "champ_id": "champ-3",
                "name": "Valkyrie",
                "rarity": "legendary",
                "affinity": "spirit",
                "faction": "Barbarians",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["defense", "support"],
                "base_stats": {"hp": 21000, "def": 1500, "spd": 95},
                "total_stats": {"hp": 70000, "def": 5200, "spd": 171, "acc": 230, "crit_rate": 100, "crit_dmg": 165, "res": 260},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "valk_a2",
                        "name": "Stand Firm",
                        "cooldown": 3,
                        "description": "Places Shield and Counterattack on all allies.",
                        "effects": [
                            {"type": "shield", "target": "ally", "value": 10},
                            {"type": "counterattack", "target": "ally", "duration": 2},
                        ],
                    }
                ],
            },
            {
                "champ_id": "champ-4",
                "name": "Teodor the Savant",
                "rarity": "legendary",
                "affinity": "spirit",
                "faction": "Knight Revenant",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "def": 1400, "spd": 100},
                "total_stats": {"hp": 62000, "def": 3400, "spd": 214, "acc": 360, "res": 250},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "teodor_a2",
                        "name": "Thralls of Misery",
                        "cooldown": 4,
                        "description": "Places Poisons and heals this Champion.",
                        "effects": [
                            {"type": "poison", "target": "enemy", "duration": 2, "chance": 100},
                            {"type": "heal", "target": "self", "value": 10},
                        ],
                    }
                ],
            },
            {
                "champ_id": "champ-5",
                "name": "Doompriest",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Knight Revenant",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "def": 1300, "spd": 100},
                "total_stats": {"hp": 68000, "def": 4300, "spd": 198, "res": 320},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "P1",
                        "skill_id": "doom_p1",
                        "name": "Bolster",
                        "cooldown": 0,
                        "description": "Removes a random debuff and heals all allies.",
                        "effects": [
                            {"type": "remove_debuff", "target": "ally"},
                            {"type": "heal", "target": "ally", "value": 7.5},
                        ],
                    }
                ],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    payload = build_team_optimizer_view(boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=db_path)

    assert any(target["key"] == "demon_lord" for target in payload["targets"])
    assert any(target["key"] == "hydra" for target in payload["targets"])
    assert any(target["key"] == "iron_twins" for target in payload["targets"])
    assert payload["selection"]["boss_key"] == "demon_lord"
    assert payload["selection"]["level_key"] == "ultra_nightmare"
    assert payload["selection"]["affinity"] == "void"
    assert payload["boss_intel"]["boss_key"] == "demon_lord"
    assert payload["boss_intel"]["selected_level_key"] == "ultra_nightmare"
    assert payload["boss_intel"]["implemented_in_optimizer"] is True
    assert any(item["label"] == "Hydra" for item in payload["boss_intel"]["catalog"])
    assert "training_overview" in payload
    assert payload["report"]["target"]["key"] == "demon_lord_unm"
    assert len(payload["report"]["selected_team"]) == 5
    assert payload["report"]["missing_required_roles"] == []


def test_boss_intel_loader_supports_modular_boss_definitions() -> None:
    hydra = build_boss_intel("hydra", level_key="hard", affinity="rotation_2")
    hydra_rotation_4 = build_boss_intel("hydra", level_key="hard", affinity="rotation_4")
    iron_twins = build_boss_intel("iron_twins", level_key="stage_15", affinity="void")

    assert hydra["boss_key"] == "hydra"
    assert hydra["selected_level_key"] == "hard"
    assert hydra["selected_affinity_key"] == "rotation_2"
    assert hydra["selected_affinity_label"] == "Rotazione 2"
    assert hydra["implemented_in_optimizer"] is True
    assert any(source["kind"] == "official" for source in hydra["sources"])
    assert hydra["selected_level_targets"][0]["value"] == "215 SPD"
    assert hydra["selected_rotation"]["starter_heads"] == ["Blight", "Torment", "Mischief", "Wrath"]
    assert hydra["selected_rotation"]["head_affinities"]["Wrath"] == "Magic"
    assert any(item["label"] == "Spider" for item in hydra["planned_modules"])
    assert hydra_rotation_4["selected_rotation"]["head_affinities"]["Suffering"] == "Magic"
    assert "inferenza community" in hydra_rotation_4["optimizer_gaps"][-1]

    assert iron_twins["boss_key"] == "iron_twins"
    assert iron_twins["selected_level_key"] == "stage_15"
    assert iron_twins["selected_affinity_key"] == "void"
    assert iron_twins["selected_level_targets"][1]["value"] == "360 ACC"
    assert any(entry["label"] == "Demon Lord" for entry in iron_twins["catalog"])


def test_hydra_optimizer_uses_boss_specific_roles_and_team_size(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Firrol the Barkhorn",
                "rarity": "legendary",
                "affinity": "spirit",
                "faction": "Sylvan Watchers",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 22000, "def": 1400, "spd": 100},
                "total_stats": {"hp": 82000, "def": 4200, "spd": 256, "acc": 390, "res": 520},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "firrol_a2",
                        "name": "Boreal Growth",
                        "cooldown": 3,
                        "description": "Places Block Buffs and Decrease Speed on all enemies.",
                        "effects": [
                            {"type": "block_buffs", "target": "enemy", "duration": 2, "chance": 100},
                            {"type": "decrease_speed", "target": "enemy", "duration": 2, "chance": 100},
                        ],
                    },
                    {
                        "slot": "A3",
                        "skill_id": "firrol_a3",
                        "name": "Oakskin Ward",
                        "cooldown": 4,
                        "description": "Places Increase Resistance and Perfect Veil on allies.",
                        "effects": [
                            {"type": "increase_resistance", "target": "ally", "duration": 2, "chance": 100},
                            {"type": "perfect_veil", "target": "ally", "duration": 2, "chance": 100},
                        ],
                    },
                ],
            },
            {
                "champ_id": "champ-2",
                "name": "Husk",
                "rarity": "epic",
                "affinity": "spirit",
                "faction": "Skinwalkers",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 18000, "def": 1300, "spd": 100},
                "total_stats": {"hp": 69000, "def": 3300, "spd": 224, "acc": 320, "crit_rate": 100, "crit_dmg": 240},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "husk_a2",
                        "name": "Fearsome Presence",
                        "cooldown": 4,
                        "description": "Attacks all enemies and places Provoke.",
                        "effects": [{"type": "provoke", "target": "enemy", "duration": 1, "chance": 100}],
                    }
                ],
            },
            {
                "champ_id": "champ-3",
                "name": "Mithrala Lifebane",
                "rarity": "legendary",
                "affinity": "force",
                "faction": "Lizardmen",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "def": 1500, "spd": 102},
                "total_stats": {"hp": 76000, "def": 3700, "spd": 245, "acc": 410, "res": 540},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "mith_a2",
                        "name": "Sigil of Corruption",
                        "cooldown": 3,
                        "description": "Places Hex on all enemies.",
                        "effects": [{"type": "hex", "target": "enemy", "duration": 2, "chance": 100}],
                    },
                    {
                        "slot": "A3",
                        "skill_id": "mith_a3",
                        "name": "Crystal Blessing",
                        "cooldown": 4,
                        "description": "Removes debuffs and protects allies.",
                        "effects": [{"type": "cleanse", "target": "ally", "chance": 100}],
                    },
                ],
            },
            {
                "champ_id": "champ-4",
                "name": "Duchess Lilitu",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Demonspawn",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 22000, "def": 1400, "spd": 98},
                "total_stats": {"hp": 83000, "def": 4100, "spd": 238, "res": 510},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A3",
                        "skill_id": "duchess_a3",
                        "name": "Shroud of Souls",
                        "cooldown": 5,
                        "description": "Revives all allies and places Perfect Veil.",
                        "effects": [
                            {"type": "revive", "target": "ally", "chance": 100},
                            {"type": "perfect_veil", "target": "ally", "duration": 2, "chance": 100},
                        ],
                    }
                ],
            },
            {
                "champ_id": "champ-5",
                "name": "Uugo",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Ogryn Tribes",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 19000, "def": 1300, "spd": 97},
                "total_stats": {"hp": 70000, "def": 3200, "spd": 228, "acc": 355},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "uugo_a2",
                        "name": "Cleansing Feast",
                        "cooldown": 4,
                        "description": "Places Block Buffs and Decrease DEF, then heals allies.",
                        "effects": [
                            {"type": "block_buffs", "target": "enemy", "duration": 2, "chance": 100},
                            {"type": "decrease_defense", "target": "enemy", "duration": 2, "chance": 100},
                            {"type": "heal", "target": "ally", "chance": 100},
                        ],
                    }
                ],
            },
            {
                "champ_id": "champ-6",
                "name": "Ninja",
                "rarity": "legendary",
                "affinity": "magic",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 18000, "atk": 1500, "def": 1100, "spd": 98},
                "total_stats": {"hp": 42000, "atk": 5600, "def": 2700, "spd": 231, "acc": 330, "crit_rate": 100, "crit_dmg": 240},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "ninja_a2",
                        "name": "Hailburn",
                        "cooldown": 3,
                        "description": "Places HP Burn on the target.",
                        "effects": [{"type": "hp_burn", "target": "enemy", "duration": 3, "chance": 100}],
                    }
                ],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    result = build_team_optimizer_view(boss_key="hydra", level_key="hard", affinity="rotation_2", db_path=db_path)

    assert result["report"]["target"]["boss_key"] == "hydra"
    assert result["report"]["target"]["key"] == "hydra_hard"
    assert result["report"]["target"]["affinity_label"] == "Rotazione 2"
    assert len(result["report"]["selected_team"]) == 6
    assert result["report"]["missing_required_roles"] == []
    assert "block_buffs" in result["report"]["team_fit"]["capability_coverage"]
    assert "provoke" in result["report"]["team_fit"]["capability_coverage"]
    assert "hex" in result["report"]["team_fit"]["capability_coverage"]
    assert any("Rotazione 2" in note for note in result["report"]["team_fit"]["notes"])


def test_clan_boss_recommendations_expose_heuristic_and_ai(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cbforge_web,
        "build_team_optimizer_report",
        lambda boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=None: {
            "target": {"key": "demon_lord_unm"},
            "selected_team": [
                {
                    "champ_id": "champ-1",
                    "champion_name": "Valkyrie",
                    "score": 94.0,
                    "default_build": "ally_protector",
                    "roles": ["support", "counterattack"],
                    "capability_tags": ["counterattack", "shield", "sustain"],
                    "stats": {"spd": 171},
                },
                {
                    "champ_id": "champ-2",
                    "champion_name": "Ninja",
                    "score": 93.0,
                    "default_build": "clan_boss_dps",
                    "roles": ["damage", "burner"],
                    "capability_tags": ["hp_burn", "boss_pressure"],
                    "stats": {"spd": 177},
                },
                {
                    "champ_id": "champ-3",
                    "champion_name": "Stag Knight",
                    "score": 90.0,
                    "default_build": "decrease_attack_support",
                    "roles": ["support", "decrease_attack"],
                    "capability_tags": ["decrease_attack"],
                    "stats": {"spd": 219},
                },
                {
                    "champ_id": "champ-4",
                    "champion_name": "Teodor the Savant",
                    "score": 89.0,
                    "default_build": "poisoner",
                    "roles": ["poisoner", "support"],
                    "capability_tags": ["poison"],
                    "stats": {"spd": 214},
                },
                {
                    "champ_id": "champ-5",
                    "champion_name": "Doompriest",
                    "score": 84.0,
                    "default_build": "cleanser",
                    "roles": ["cleanse", "support"],
                    "capability_tags": ["cleanse"],
                    "stats": {"spd": 198},
                },
            ],
            "candidates": [
                {
                    "champ_id": "champ-1",
                    "champion_name": "Valkyrie",
                    "score": 94.0,
                    "default_build": "ally_protector",
                    "roles": ["support", "counterattack"],
                    "capability_tags": ["counterattack", "shield", "sustain"],
                    "stats": {"spd": 171},
                }
            ],
            "warnings": ["warning one"],
            "notes": ["note one"],
        },
    )

    import ml_team_baseline

    monkeypatch.setattr(cbforge_web, "MODEL_DIR", tmp_path)
    dummy_model = tmp_path / "dummy.joblib"
    dummy_model.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ml_team_baseline, "default_model_path", lambda encounter_key: Path("dummy.joblib"))
    monkeypatch.setattr(
        ml_team_baseline,
        "recommend_best_team_from_candidates",
        lambda candidates, encounter_key, difficulty, boss_affinity, model_path, team_size=5, pool_size=10: {
            "best_team": [
                {
                    "champ_id": "champ-9",
                    "champion_name": "Maneater",
                    "score": 99.0,
                    "default_build": "speed_tuned_support",
                    "roles": ["support", "unkillable"],
                    "capability_tags": ["unkillable"],
                    "stats": {"spd": 265},
                }
            ]
            * 5,
            "predicted_total_damage": 41234567.0,
            "predicted_success_probability": 0.82,
            "evaluated_combinations": 128,
            "pool_size": 9,
            "model_path": str(dummy_model),
        },
    )

    payload = build_clan_boss_recommendations()

    assert payload["heuristic"]["available"] is True
    assert payload["heuristic"]["team"][0]["champion_name"] == "Valkyrie"
    assert payload["ai"]["available"] is True
    assert payload["ai"]["team"][0]["champion_name"] == "Maneater"
    assert payload["ai"]["predicted_total_damage"] == 41234567.0


def test_ai_training_overview_reports_runs_and_models(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    record_run_history(
        {
            "source": "test",
            "battle_id": "battle-ai-1",
            "encounter_key": "demon_lord_ultra_nightmare",
            "encounter_name": "Demon Lord Ultra-Nightmare",
            "encounter_family": "demon_lord",
            "difficulty": "ultra_nightmare",
            "boss_affinity": "void",
            "success": 1,
            "total_damage": 32100000.0,
            "members": [{"champion_name": "Ninja", "stats": {"spd": 177}}],
        },
        db_path=db_path,
    )
    monkeypatch.setattr(cbforge_web, "MODEL_DIR", tmp_path)
    model_path = tmp_path / "demon_lord_ultra_nightmare_team_baseline_v1.joblib"
    model_path.write_text("model", encoding="utf-8")

    overview = build_ai_training_overview(db_path=db_path)

    assert overview["ai_available"] is True
    assert overview["summary"]["encounters"] >= 1
    assert overview["summary"]["models_present"] == 1
    assert overview["encounters"][0]["encounter_key"] == "demon_lord_ultra_nightmare"
    assert overview["encounters"][0]["model_exists"] is True
    assert overview["encounters"][0]["category_key"] == "clan_boss"
    assert overview["categories"][0]["category_label"] == "Clan Boss"


def test_ai_training_overview_exposes_dependency_runtime_when_training_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    import ml_team_baseline

    monkeypatch.setattr(
        ml_team_baseline,
        "ai_dependency_status",
        lambda: {
            "ok": False,
            "error": "Dipendenze AI mancanti nel Python del server.",
            "detail": "No module named 'sklearn'",
            "runtime": {
                "python_executable": r"C:\Python311\python.exe",
                "python_version": "3.11.9",
            },
        },
    )

    overview = build_ai_training_overview(db_path=db_path)

    assert overview["training_available"] is False
    assert overview["dependency_detail"] == "No module named 'sklearn'"
    assert overview["dependency_runtime"]["python_executable"] == r"C:\Python311\python.exe"


def test_train_ai_baseline_model_uses_training_module(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    record_run_history(
        {
            "source": "test",
            "battle_id": "battle-ai-2",
            "encounter_key": "demon_lord_ultra_nightmare",
            "encounter_name": "Demon Lord Ultra-Nightmare",
            "encounter_family": "demon_lord",
            "difficulty": "ultra_nightmare",
            "boss_affinity": "void",
            "success": 1,
            "total_damage": 33000000.0,
            "members": [{"champion_name": "Ninja", "stats": {"spd": 177}}],
        },
        db_path=db_path,
    )
    monkeypatch.setattr(cbforge_web, "MODEL_DIR", tmp_path)

    import ml_team_baseline

    expected_output = tmp_path / "dummy.joblib"
    monkeypatch.setattr(ml_team_baseline, "default_model_path", lambda encounter_key: Path("dummy.joblib"))
    monkeypatch.setattr(
        ml_team_baseline,
        "train_from_database",
        lambda db_path, encounter_key, output_path=None: {
            "ok": True,
            "output_path": str(output_path or expected_output),
            "rows": 12,
            "metrics": {"rows": 12},
            "feature_importances": [{"feature": "spd_avg", "importance": 0.3}],
        },
    )

    payload = train_ai_baseline_model("demon_lord_ultra_nightmare", db_path=db_path)

    assert payload["ok"] is True
    assert payload["encounter_key"] == "demon_lord_ultra_nightmare"
    assert payload["training"]["rows"] == 12


def test_team_optimizer_loadout_detects_shared_items(monkeypatch) -> None:
    monkeypatch.setattr(
        cbforge_web,
        "build_team_optimizer_report",
        lambda boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=None: {
            "target": {"key": "demon_lord_unm", "boss_label": "Demon Lord"},
            "selected_team": [
                {"champion_name": "Ninja", "default_build": "clan_boss_dps", "score": 99.0},
                {"champion_name": "Jintoro", "default_build": "clan_boss_dps", "score": 98.0},
            ],
        },
    )

    def fake_build_plan(name: str, profile_key: str, area_region: str = "", db_path: Path | None = None) -> dict:
        shared_helmet = {
            "item_id": "shared-helmet",
            "slot": "helmet",
            "set_name": "Attack Speed",
            "source_kind": "inventory",
            "source_label": "Magazzino",
            "main_stat_type": "hp",
            "main_stat_value": 3510,
        }
        unique_weapon = {
            "item_id": f"{name.lower()}-weapon",
            "slot": "weapon",
            "set_name": "Attack Speed",
            "source_kind": "current",
            "source_label": f"Gia su {name}",
            "main_stat_type": "atk",
            "main_stat_value": 265,
        }
        return {
            "current_build": {"label": "Attuale", "score": 1000},
            "proposals": [
                {
                    "label": "Best Proposal",
                    "score": 1200,
                    "swap_count": 2,
                    "inventory_items": 1,
                    "borrowed_items": 0,
                    "scope_label": "Mix",
                    "set_coherence": {"label": "Buona"},
                    "items": [unique_weapon, dict(shared_helmet)],
                }
            ],
        }

    monkeypatch.setattr(cbforge_web, "build_champion_plan", fake_build_plan)

    payload = build_team_optimizer_loadout()

    assert payload["summary"]["champions"] == 2
    assert payload["summary"]["total_swap_count"] == 4
    assert payload["summary"]["conflict_count"] == 1
    assert payload["conflicts"][0]["item_id"] == "shared-helmet"
    assert payload["team"][0]["conflict_item_ids"] == ["shared-helmet"]
    assert payload["team"][1]["conflict_item_ids"] == ["shared-helmet"]


def test_prepare_server_runtime_rebuilds_from_local_source(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")

    called: dict[str, object] = {}

    def fake_refresh(db_path: Path, source_path: Path, mode: str = "legacy_bridge") -> dict:
        called["db_path"] = db_path
        called["source_path"] = source_path
        called["mode"] = mode
        return {"ok": True, "mode": mode, "message": "startup refreshed"}

    monkeypatch.setattr(cbforge_web, "refresh_gear_from_game", fake_refresh)

    payload = prepare_server_runtime(db_path=db_path, source_path=source_path, refresh_on_start=True)

    assert payload["ok"] is True
    assert payload["mode"] == "local_only"
    assert called["db_path"] == db_path
    assert called["source_path"] == source_path
    assert called["mode"] == "local_only"


def test_team_optimizer_local_bridge_plan_wraps_loadout_into_manual_plan(monkeypatch) -> None:
    monkeypatch.setattr(
        cbforge_web,
        "build_team_optimizer_loadout",
        lambda boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=None: {
            "target": {"key": "demon_lord_unm"},
            "summary": {"champions": 1},
            "team": [
                {
                    "champion_name": "Ninja",
                    "build_label": "CB DPS",
                    "items": [
                        {"item_id": "gear-1", "slot": "weapon", "source_kind": "current", "source_label": "Gia su Ninja"},
                        {"item_id": "gear-2", "slot": "boots", "source_kind": "inventory", "source_label": "Magazzino"},
                    ],
                }
            ],
            "conflicts": [],
        },
    )

    payload = build_team_optimizer_local_bridge_plan()

    assert payload["target"]["key"] == "demon_lord_unm"
    assert payload["summary"]["champions"] == 1
    assert payload["plan"]["provider"] == "local_manual"
    assert payload["plan"]["action_count"] == 1
    assert payload["plan"]["free_equip_count"] == 1


def test_build_team_optimizer_loadout_preserves_selected_team_champion_id(monkeypatch) -> None:
    monkeypatch.setattr(
        cbforge_web,
        "build_team_optimizer_report",
        lambda boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=None: {
            "target": {"key": "demon_lord_unm"},
            "selected_team": [
                {
                    "champ_id": "16571",
                    "champion_name": "Pain Keeper",
                    "default_build": "cooldown_support",
                    "score": 138.07,
                }
            ],
        },
    )
    monkeypatch.setattr(
        cbforge_web,
        "build_champion_plan",
        lambda champion_name, profile_key="support_general", area_region="clan_boss", db_path=None: {
            "current_build": {"label": "Attuale", "score": 1000},
            "proposals": [
                {
                    "label": "Best Proposal",
                    "score": 1200,
                    "swap_count": 0,
                    "inventory_items": 0,
                    "borrowed_items": 0,
                    "scope_label": "Mix",
                    "set_coherence": {"label": "Buona"},
                    "items": [{"item_id": "gear-1", "slot": "weapon", "source_kind": "current"}],
                }
            ],
        },
    )

    payload = build_team_optimizer_loadout()

    assert payload["team"][0]["champ_id"] == "16571"


def test_build_team_optimizer_loadout_routes_area_region_from_selected_boss(monkeypatch) -> None:
    monkeypatch.setattr(
        cbforge_web,
        "build_team_optimizer_report",
        lambda boss_key="hydra", level_key="hard", affinity="void", db_path=None: {
            "target": {"key": "hydra_hard", "boss_key": "hydra"},
            "selected_team": [
                {
                    "champ_id": "9001",
                    "champion_name": "Mithrala Lifebane",
                    "default_build": "debuffer_acc_spd",
                    "score": 144.5,
                }
            ],
        },
    )

    calls: list[dict[str, str]] = []

    def fake_build_plan(champion_name, profile_key="support_general", area_region="clan_boss", db_path=None):
        calls.append({"champion_name": champion_name, "profile_key": profile_key, "area_region": area_region})
        return {
            "current_build": {"label": "Attuale", "score": 1000},
            "proposals": [
                {
                    "label": "Best Proposal",
                    "score": 1200,
                    "swap_count": 0,
                    "inventory_items": 0,
                    "borrowed_items": 0,
                    "scope_label": "Mix",
                    "set_coherence": {"label": "Buona"},
                    "items": [{"item_id": "gear-1", "slot": "weapon", "source_kind": "current"}],
                }
            ],
        }

    monkeypatch.setattr(cbforge_web, "build_champion_plan", fake_build_plan)

    payload = build_team_optimizer_loadout(boss_key="hydra", level_key="hard", affinity="void")

    assert payload["target"]["key"] == "hydra_hard"
    assert calls[0]["area_region"] == "hydra"


def test_equip_team_optimizer_in_game_invokes_local_bridge_for_each_member(monkeypatch) -> None:
    monkeypatch.setattr(
        cbforge_web,
        "build_team_optimizer_loadout",
        lambda boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=None: {
            "target": {"key": "demon_lord_unm"},
            "team": [
                {
                    "champion_name": "Maneater",
                    "champ_id": "9170",
                    "items": [{"item_id": "1001"}, {"item_id": "1002"}],
                },
                {
                    "champion_name": "Pain Keeper",
                    "champ_id": "16571",
                    "items": [{"item_id": "2001"}],
                },
            ],
            "conflicts": [],
        },
    )

    captured: list[tuple[str, tuple[str, ...]]] = []

    def fake_invoke(command: str, *arguments: str) -> dict:
        captured.append((command, arguments))
        return {"ok": True, "action": command}

    monkeypatch.setattr(cbforge_web, "invoke_local_hh_bridge", fake_invoke)
    monkeypatch.setattr(
        cbforge_web,
        "save_team_optimizer_restore_snapshot",
        lambda loadout, db_path=None: {
            "saved_at": "2026-03-27T20:00:00+00:00",
            "summary": {"champions": 2, "artifacts": 3},
            "champions": [],
        },
    )

    payload = equip_team_optimizer_in_game()

    assert payload["ok"] is True
    assert payload["summary"]["members_requested"] == 2
    assert payload["summary"]["members_succeeded"] == 2
    assert payload["restore_snapshot"]["summary"]["champions"] == 2
    assert captured == [
        ("equip", ("9170", "1001,1002")),
        ("equip", ("16571", "2001")),
    ]


def test_restore_last_team_optimizer_equip_invokes_local_bridge_from_snapshot(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "cbforge.sqlite3"
    cbforge_web.save_gear_snapshot_record(
        snapshot_key=cbforge_web.TEAM_OPTIMIZER_LAST_RESTORE_KEY,
        label="Ultimo equip test",
        scope=cbforge_web.TEAM_OPTIMIZER_SNAPSHOT_SCOPE,
        snapshot_kind="auto_restore",
        context={},
        snapshot={
            "saved_at": "2026-03-27T20:05:00+00:00",
            "summary": {"champions": 2, "artifacts": 3},
            "champions": [
                {"champion_name": "Maneater", "champ_id": "9170", "artifact_ids": ["1001", "1002"]},
                {"champion_name": "Pain Keeper", "champ_id": "16571", "artifact_ids": ["2001"]},
            ],
        },
        db_path=db_path,
    )

    captured: list[tuple[str, tuple[str, ...]]] = []

    def fake_invoke(command: str, *arguments: str) -> dict:
        captured.append((command, arguments))
        return {"ok": True, "action": command}

    monkeypatch.setattr(cbforge_web, "invoke_local_hh_bridge", fake_invoke)

    payload = cbforge_web.restore_last_team_optimizer_equip(db_path=db_path)

    assert payload["ok"] is True
    assert payload["summary"]["members_requested"] == 2
    assert payload["summary"]["members_succeeded"] == 2
    assert captured == [
        ("equip", ("9170", "1001,1002")),
        ("equip", ("16571", "2001")),
    ]


def test_equip_team_optimizer_member_in_game_invokes_local_bridge_for_single_member(monkeypatch) -> None:
    monkeypatch.setattr(
        cbforge_web,
        "build_team_optimizer_loadout",
        lambda boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=None: {
            "target": {"key": "demon_lord_unm"},
            "team": [
                {
                    "champion_name": "Maneater",
                    "champ_id": "9170",
                    "items": [{"item_id": "1001"}, {"item_id": "1002"}],
                },
                {
                    "champion_name": "Pain Keeper",
                    "champ_id": "16571",
                    "items": [{"item_id": "2001"}],
                },
            ],
            "conflicts": [],
        },
    )
    monkeypatch.setattr(
        cbforge_web,
        "save_team_optimizer_restore_snapshot",
        lambda loadout, db_path=None: {
            "saved_at": "2026-03-27T20:00:00+00:00",
            "summary": {"champions": 1, "artifacts": 2},
            "champions": [],
        },
    )

    captured: list[tuple[str, tuple[str, ...]]] = []

    def fake_invoke(command: str, *arguments: str) -> dict:
        captured.append((command, arguments))
        return {"ok": True, "action": command}

    monkeypatch.setattr(cbforge_web, "invoke_local_hh_bridge", fake_invoke)

    payload = cbforge_web.equip_team_optimizer_member_in_game(champion_name="Pain Keeper")

    assert payload["ok"] is True
    assert payload["summary"]["members_requested"] == 1
    assert payload["summary"]["members_succeeded"] == 1
    assert captured == [("equip", ("16571", "2001"))]


def test_web_detail_exposes_derived_stats_and_warnings(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Yumeko",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 129, "atk": 79, "def": 117, "spd": 105, "crit_rate": 15, "crit_dmg": 50, "res": 30, "acc": 10},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "res": 0, "acc": 0},
                "equipped_item_ids": ["gear-1", "gear-2"],
                "skills": [],
            }
        ],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "artifact",
                "slot": "weapon",
                "set_name": "Stone Skin",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "atk", "value": 265},
                "substats": [{"type": "spd", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "gear-2",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "HP And Heal",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [{"type": "res", "value": 0.2, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    detail = champion_detail("Yumeko", db_path)

    assert detail["stat_model"]["source"] == "derived"
    assert detail["stat_model"]["completeness"] == "derived"
    assert detail["stat_model"]["unsupported_sets"] == []
    assert detail["stat_model"]["imported_total_stats_present"] is False
    assert "imported_total_stats" in detail["stat_model"]["missing_sources"]
    assert detail["stat_model"]["bonus_sources"] == []
    assert detail["account"]["relic_count"] == 0
    assert detail["stat_model"]["applied_sets"] == [
        {
            "set_name": "Stone Skin",
            "set_kind": "variable",
            "pieces_required": 1,
            "pieces_equipped": 1,
            "completed_sets": 1,
            "max_pieces": 9,
            "active_bonus_count": 1,
        }
    ]
    assert detail["base_totals"]["hp"] == 30960.0
    assert detail["total_stats"]["hp"] == 33436.8
    assert detail["total_stats"]["spd"] == 160.0


def test_set_registry_exposes_fixed_and_variable_rules_with_inventory_counts(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Yumeko",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": ["gear-1", "gear-2", "gear-3"],
                "skills": [],
            }
        ],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [],
            },
            {
                "item_id": "gear-1b",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "hp_pct", "value": 60},
                "substats": [],
            },
            {
                "item_id": "gear-2",
                "item_class": "artifact",
                "slot": "weapon",
                "set_name": "Stone Skin",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "atk", "value": 265},
                "substats": [],
            },
            {
                "item_id": "gear-3",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "Stone Skin",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "hp", "value": 2650},
                "substats": [],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    registry = build_set_registry(db_path)

    assert registry["summary"]["total_sets"] >= 2
    assert registry["summary"]["observed_sets"] >= 2
    speed = next(row for row in registry["sets"] if row["set_name"] == "Attack Speed")
    stoneskin = next(row for row in registry["sets"] if row["set_name"] == "Stone Skin")

    assert speed["display_name"] == "Speed"
    assert speed["set_kind"] == "fixed"
    assert speed["counts_accessories"] is False
    assert speed["inventory"]["artifact_items"] == 2
    assert speed["inventory"]["accessory_items"] == 0
    assert speed["progress"]["relevant_total_items"] == 2
    assert speed["progress"]["relevant_inventory_items"] == 1
    assert speed["progress"]["complete_sets_total"] == 1
    assert speed["progress"]["complete_sets_inventory"] == 0
    assert speed["stats"] == [{"stat_type": "spd", "stat_value": 12.0}]

    assert stoneskin["set_kind"] == "variable"
    assert stoneskin["counts_accessories"] is True
    assert stoneskin["inventory"]["artifact_items"] == 1
    assert stoneskin["inventory"]["accessory_items"] == 1
    assert stoneskin["progress"]["relevant_total_items"] == 2
    assert stoneskin["progress"]["highest_bonus_threshold_total"] == 2
    assert stoneskin["progress"]["next_threshold_total"] == 3
    assert stoneskin["progress"]["missing_for_next_total"] == 1
    assert any(row["pieces_required"] == 1 for row in stoneskin["piece_bonuses"])
    assert any(row["pieces_required"] == 4 and row["effects"] for row in stoneskin["piece_bonuses"])


def test_set_registry_classifies_counterattack_accessory_set(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "acc-1",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "Counterattack Accessory",
                "rarity": "epic",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "hp", "value": 2650},
                "substats": [],
            },
            {
                "item_id": "acc-2",
                "item_class": "accessory",
                "slot": "amulet",
                "set_name": "Counterattack Accessory",
                "rarity": "epic",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 265},
                "substats": [],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    registry = build_set_registry(db_path)
    counter = next(row for row in registry["sets"] if row["set_name"] == "Counterattack Accessory")

    assert counter["display_name"] == "Revenge Accessory"
    assert counter["set_kind"] == "accessory"
    assert counter["counts_accessories"] is True
    assert counter["summary"].startswith("Accessory set 1/2/3")
    assert counter["progress"]["relevant_total_items"] == 2
    assert counter["progress"]["highest_bonus_threshold_total"] == 2
    assert counter["progress"]["next_threshold_total"] == 3
    assert counter["progress"]["missing_for_next_total"] == 1
    assert counter["piece_bonuses"][0]["effects"] == ["5% chance to counterattack when hit"]


def test_set_curation_payload_exposes_observed_pieces_and_owners(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Yumeko",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": ["gear-1"],
                "skills": [],
            }
        ],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Block Heal Chance",
                "rarity": "epic",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [],
            },
            {
                "item_id": "gear-2",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "Block Heal Chance",
                "rarity": "epic",
                "rank": 6,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "crit_rate", "value": 50},
                "substats": [],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    curation = build_set_curation_payload(db_path)
    row = next(item for item in curation["items"] if item["set_name"] == "Block Heal Chance")

    assert row["inventory"]["total_items"] == 2
    assert row["observed_samples"]["slot_counts"] == [
        {"slot": "gloves", "count": 1},
        {"slot": "boots", "count": 1},
    ]
    assert row["observed_samples"]["owner_counts"] == [
        {"owner_name": "Yumeko", "count": 1},
    ]
    assert row["observed_samples"]["sample_items"][0]["slot"] == "boots"
    assert row["observed_samples"]["sample_items"][0]["owner_name"] == "Yumeko"
    assert row["observed_samples"]["sample_items"][1]["slot"] == "gloves"
    assert row["observed_samples"]["sample_items"][1]["equipped"] is False


def test_set_registry_prefers_canonical_name_when_display_matches_raw(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Heal",
                "rarity": "epic",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [],
            }
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)
    monkeypatch.setattr(
        cbforge_web,
        "load_local_set_entries",
        lambda: [
            {
                "set_name": "Heal",
                "canonical_name": "Regeneration",
                "display_name": "Heal",
            }
        ],
    )

    registry = build_set_registry(db_path)
    heal = next(row for row in registry["sets"] if row["set_name"] == "Heal")

    assert heal["display_name"] == "Regeneration"
    assert heal["canonical_name"] == "Regeneration"


def test_gear_queries_cover_equipped_and_inventory_items(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": ["gear-1"],
                "skills": [],
            }
        ],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 1,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [
                    {"type": "acc", "value": 20, "rolls": 2, "glyph_value": 4},
                    {"type": "hp_pct", "value": 0.1, "rolls": 1, "glyph_value": 0},
                ],
            },
            {
                "item_id": "gear-2",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "Feral",
                "rarity": "epic",
                "rank": 5,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "crit_rate", "value": 50},
                "substats": [
                    {"type": "spd", "value": 5, "rolls": 0, "glyph_value": 0},
                ],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_gear_summary(db_path)
    all_items = list_gear_items(db_path)
    equipped_items = list_gear_items(db_path, ownership="equipped")
    inventory_items = list_gear_items(db_path, ownership="inventory")
    artifacts_only = list_gear_items(db_path, item_class="artifact")
    filtered = list_gear_items(db_path, slot="boots", set_name="Attack Speed")
    detail = gear_item_detail("gear-1", db_path)

    assert summary["total_items"] == 2
    assert summary["equipped_items"] == 1
    assert summary["inventory_items"] == 1
    assert summary["locked_items"] == 1
    assert len(all_items["items"]) == 2
    assert len(equipped_items["items"]) == 1
    assert equipped_items["items"][0]["owner_name"] == "Geomancer"
    assert len(inventory_items["items"]) == 1
    assert inventory_items["items"][0]["item_id"] == "gear-2"
    assert len(artifacts_only["items"]) == 2
    assert artifacts_only["filters"]["item_classes"] == ["artifact"]
    assert len(filtered["items"]) == 1
    assert filtered["items"][0]["item_id"] == "gear-1"
    assert filtered["items"][0]["advice_verdict"] == "keep_16"
    assert "main stat forte: spd" in filtered["items"][0]["advice_reasons"][0]
    assert detail["item"]["equipped"] is True
    assert detail["item"]["owner_name"] == "Geomancer"
    assert detail["substats"][0]["glyph_value"] == 4
    assert detail["advice"]["verdict"] == "keep_16"
    assert summary["verdict_counts"]["keep_16"] >= 1


def test_sell_queue_summary_groups_candidates_by_page(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "art-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "rare",
                "rank": 5,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [
                    {"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0},
                ],
            },
            {
                "item_id": "acc-1",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "Stone Skin",
                "rarity": "rare",
                "rank": 5,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "hp", "value": 10},
                "substats": [
                    {"type": "atk", "value": 10, "rolls": 0, "glyph_value": 0},
                ],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_sell_queue_summary(db_path=db_path, limit_per_page=5)

    pages = {page["page"]: page for page in summary["pages"]}
    assert pages["artifact"]["candidate_count"] == 1
    assert pages["artifact"]["visible_candidates"][0]["item_id"] == "art-1"
    assert pages["accessory"]["candidate_count"] == 1
    assert pages["accessory"]["visible_candidates"][0]["item_id"] == "acc-1"


def test_sell_artifacts_from_queue_only_sends_current_candidates(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "art-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "rare",
                "rank": 5,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "art-2",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "Attack Speed",
                "rarity": "rare",
                "rank": 5,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": True,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "acc-1",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "Stone Skin",
                "rarity": "rare",
                "rank": 5,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "hp", "value": 10},
                "substats": [{"type": "atk", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    captured = {}

    def fake_sell_artifacts_live(artifact_ids, access_token=None, base_url=cbforge_web.hellhades_live.DEFAULT_BASE_URL, timeout_seconds=10.0):
        captured["artifact_ids"] = list(artifact_ids)
        captured["access_token"] = access_token
        return {
            "status": "success",
            "message": "SellArtifacts eseguito correttamente.",
            "requested_count": len(captured["artifact_ids"]),
        }

    monkeypatch.setattr(cbforge_web.hellhades_live, "sell_artifacts_live", fake_sell_artifacts_live)

    result = sell_artifacts_from_queue(
        artifact_ids=["art-1", "art-2", "missing", "art-1"],
        db_path=db_path,
        access_token="secret-token",
    )

    assert captured["artifact_ids"] == ["art-1"]
    assert captured["access_token"] == "secret-token"
    assert result["approved_ids"] == ["art-1"]
    assert result["rejected_ids"] == ["art-2", "missing"]
    assert result["approved_items"][0]["item_id"] == "art-1"


def test_sell_queue_prioritizes_bad_main_stat_plus_zero_first(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "weak-plus0",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "weak-plus12",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "medium-plus0",
                "item_class": "artifact",
                "slot": "chest",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk_pct", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_sell_queue_summary(db_path=db_path, limit_per_page=5)

    artifact_ids = [item["item_id"] for item in next(page for page in summary["pages"] if page["page"] == "artifact")["visible_candidates"]]
    assert artifact_ids[:3] == ["weak-plus0", "weak-plus12", "medium-plus0"]


def test_sell_queue_summary_can_exclude_already_sent_ids(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "weak-a",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "weak-b",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "hp", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_sell_queue_summary(db_path=db_path, limit_per_page=5, exclude_ids=["weak-a"])

    artifact_ids = [item["item_id"] for item in next(page for page in summary["pages"] if page["page"] == "artifact")["visible_candidates"]]
    assert artifact_ids == ["weak-b"]


def test_refresh_gear_from_game_copies_legacy_outputs_and_rebuilds(tmp_path: Path, monkeypatch) -> None:
    legacy_dir = tmp_path / "legacy"
    legacy_input = legacy_dir / "input"
    legacy_input.mkdir(parents=True)
    base_dir = tmp_path / "app"
    base_input = base_dir / "input"
    base_input.mkdir(parents=True)
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = base_input / "normalized_account.json"

    raw_payload = {"raw": True}
    normalized_payload = {"champions": [], "gear": [], "account_bonuses": []}
    command_log = []

    def fake_run(command, cwd, capture_output, text, check):
        command_log.append((tuple(command), cwd))
        if command == ["python", "extract_local.py"]:
            (legacy_input / "raw_account.json").write_text(json.dumps(raw_payload), encoding="utf-8")
        if command == ["python", "normalize.py"]:
            (legacy_input / "normalized_account.json").write_text(json.dumps(normalized_payload), encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Completed()

    def fake_bootstrap_database(source_path, db_path, rebuild):
        assert source_path == base_input / "normalized_account.json"
        assert db_path == db_path_arg
        assert rebuild is False
        return {"gear_items": 0, "account_champions": 0}

    db_path_arg = db_path
    monkeypatch.setattr(cbforge_web, "LEGACY_DIR", legacy_dir)
    monkeypatch.setattr(cbforge_web, "LEGACY_INPUT_DIR", legacy_input)
    monkeypatch.setattr(cbforge_web, "BASE_DIR", base_dir)
    monkeypatch.setattr(cbforge_web.subprocess, "run", fake_run)
    monkeypatch.setattr(cbforge_web, "bootstrap_database", fake_bootstrap_database)

    result = refresh_gear_from_game(db_path=db_path, source_path=source_path)

    assert command_log == [
        (("python", "extract_local.py"), legacy_dir),
        (("python", "normalize.py"), legacy_dir),
    ]
    assert json.loads((base_input / "raw_account.json").read_text(encoding="utf-8")) == raw_payload
    assert json.loads((base_input / "normalized_account.json").read_text(encoding="utf-8")) == normalized_payload
    assert result["summary"]["gear_items"] == 0


def test_refresh_gear_from_game_does_not_copy_empty_outputs_when_bridge_is_outdated(tmp_path: Path, monkeypatch) -> None:
    legacy_dir = tmp_path / "legacy"
    legacy_input = legacy_dir / "input"
    legacy_input.mkdir(parents=True)
    base_dir = tmp_path / "app"
    base_input = base_dir / "input"
    base_input.mkdir(parents=True)
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = base_input / "normalized_account.json"

    raw_payload = {
        "local_client": {
            "hellhades_bridge": {
                "error": (
                    "HellHades.ArtifactExtractor.RaidReader.ExtractorOutdatedException: "
                    "Raid: Shadow Legends has been updated and needs a newer version of HellHades Artifact RaidReader."
                )
            }
        }
    }
    normalized_payload = {"champions": [], "gear": [], "account_bonuses": []}

    def fake_run(command, cwd, capture_output, text, check):
        if command == ["python", "extract_local.py"]:
            (legacy_input / "raw_account.json").write_text(json.dumps(raw_payload), encoding="utf-8")
        if command == ["python", "normalize.py"]:
            (legacy_input / "normalized_account.json").write_text(json.dumps(normalized_payload), encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Completed()

    def fail_bootstrap_database(*args, **kwargs):
        raise AssertionError("bootstrap_database non dovrebbe partire con dump vuoto e bridge fallito")

    monkeypatch.setattr(cbforge_web, "LEGACY_DIR", legacy_dir)
    monkeypatch.setattr(cbforge_web, "LEGACY_INPUT_DIR", legacy_input)
    monkeypatch.setattr(cbforge_web, "BASE_DIR", base_dir)
    monkeypatch.setattr(cbforge_web.subprocess, "run", fake_run)
    monkeypatch.setattr(cbforge_web, "bootstrap_database", fail_bootstrap_database)

    with pytest.raises(RuntimeError, match="reader non compatibile"):
        refresh_gear_from_game(db_path=db_path, source_path=source_path)

    assert not (base_input / "raw_account.json").exists()
    assert not (base_input / "normalized_account.json").exists()


def test_run_recorder_controller_starts_and_stops_probe_process(tmp_path: Path, monkeypatch) -> None:
    started = {}

    class FakeProcess:
        def __init__(self, command, cwd, stdout, stderr, text):
            started["command"] = command
            started["cwd"] = cwd
            started["stdout_name"] = getattr(stdout, "name", "")
            started["stderr"] = stderr
            started["text"] = text
            self.pid = 4321
            self._returncode = None

        def poll(self):
            return self._returncode

        def terminate(self):
            self._returncode = 0

        def wait(self, timeout=None):
            return self._returncode

        def kill(self):
            self._returncode = -9

    monkeypatch.setattr(cbforge_web.subprocess, "Popen", FakeProcess)

    controller = RunRecorderController(
        base_dir=tmp_path,
        script_path=tmp_path / "deep_battle_probe.py",
        output_root=tmp_path / "client_probe",
        python_executable="python-test",
    )

    status = controller.start(interval_seconds=0.2, duration_seconds=900)

    assert status["running"] is True
    assert status["pid"] == 4321
    assert status["session_slug"]
    assert started["command"][:2] == ["python-test", str(tmp_path / "deep_battle_probe.py")]
    assert "--session-slug" in started["command"]
    assert started["cwd"] == tmp_path
    assert started["stderr"] == cbforge_web.subprocess.STDOUT
    assert started["text"] is True
    assert started["stdout_name"].endswith("stdout.log")

    stopped = controller.stop()

    assert stopped["running"] is False
    assert stopped["last_exit_code"] == 0
    assert build_run_recorder_status(controller)["session_slug"] == status["session_slug"]


def test_run_recorder_session_queries_expose_saved_probe_data(tmp_path: Path) -> None:
    output_root = tmp_path / "client_probe"
    session_dir = output_root / "20260323T081500Z"
    snapshots_dir = session_dir / "snapshots" / "battle_results"
    snapshots_dir.mkdir(parents=True)
    raw_snapshot = snapshots_dir / "capture.bin"
    (session_dir / "session.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-23T08:15:00+00:00",
                "interval": 0.35,
                "duration": 900,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    events = [
        {"captured_at": "2026-03-23T08:15:01+00:00", "event_type": "log_line", "line": ">>> CreateBattle with setup:Id: battle-123 RandomSeed: 1 Stage: 4019021 FormationIndex 0"},
        {
            "captured_at": "2026-03-23T08:15:01+00:00",
            "event_type": "battle_context",
            "battle": {
                "battle_id": "battle-123",
                "stage_id": "4019021",
                "formation_index": 0,
                "player_members": ["Rakka", "Valkyrie", "Ninja", "Jintoro", "Stag Knight"],
                "enemy_rows": [{"slot": 1, "type_id": 22296, "name": "Type 22296", "level": 250}],
            },
        },
        {"captured_at": "2026-03-23T08:15:03+00:00", "event_type": "log_line", "line": "Change battle state [Loading -> Started]"},
        {
            "captured_at": "2026-03-23T08:15:12+00:00",
            "event_type": "forced_file_snapshot",
            "source_name": "battle_results",
            "saved": {"marker": {"size": 12201}, "raw_path": str(raw_snapshot)},
            "battle": {
                "battle_id": "battle-123",
                "stage_id": "4019021",
                "formation_index": 0,
                "player_members": ["Rakka", "Valkyrie", "Ninja", "Jintoro", "Stag Knight"],
                "enemy_rows": [{"slot": 1, "type_id": 22296, "name": "Type 22296", "level": 250}],
            },
            "reason": "BattleResult added",
        },
        {"captured_at": "2026-03-23T08:15:15+00:00", "event_type": "log_line", "line": "Change battle state [Started -> Finished]"},
    ]
    (session_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in events) + "\n",
        encoding="utf-8",
    )
    (session_dir / "interesting_log_lines.txt").write_text("CreateBattle with setup\n", encoding="utf-8")
    raw_snapshot.write_bytes(b"rich-battle-results-captured-but-not-trusted")
    (snapshots_dir / "capture.json").write_text("{}", encoding="utf-8")

    controller = RunRecorderController(
        base_dir=tmp_path,
        script_path=tmp_path / "deep_battle_probe.py",
        output_root=output_root,
        python_executable="python-test",
    )

    sessions_payload = list_run_recorder_sessions(output_root=output_root, recorder=controller)
    detail = run_recorder_session_detail("20260323T081500Z", output_root=output_root, recorder=controller)

    assert sessions_payload["summary"]["sessions"] == 1
    assert sessions_payload["summary"]["runs"] == 1
    assert sessions_payload["summary"]["events"] == 5
    assert sessions_payload["sessions"][0]["latest_battle"]["battle_id"] == "battle-123"
    assert sessions_payload["sessions"][0]["run_count"] == 1
    assert sessions_payload["sessions"][0]["latest_run"]["has_rich_battle_results"] is True
    assert sessions_payload["sessions"][0]["latest_run"]["boss_name"] == "Demon Lord"
    assert sessions_payload["sessions"][0]["latest_run"]["boss_affinity"] == "void"
    assert sessions_payload["sessions"][0]["latest_run"]["category_key"] == "clan_boss"
    assert sessions_payload["sessions"][0]["latest_run"]["damage_trusted"] is False
    assert sessions_payload["sessions"][0]["snapshot_count"] == 2
    assert detail["metadata"]["interval"] == 0.35
    assert detail["latest_battle"]["team_members"] == ["Rakka", "Valkyrie", "Ninja", "Jintoro", "Stag Knight"]
    assert detail["event_type_counts"]["forced_file_snapshot"] == 1
    assert detail["runs"][0]["battle_id"] == "battle-123"
    assert detail["runs"][0]["started_at"] == "2026-03-23T08:15:03+00:00"
    assert detail["runs"][0]["finished_at"] == "2026-03-23T08:15:15+00:00"
    assert detail["runs"][0]["best_battle_results_size"] == 12201
    assert detail["runs"][0]["category_label"] == "Clan Boss"
    assert detail["runs"][0]["total_damage"] is None
    assert detail["runs"][0]["member_damage"] == []
    assert detail["snapshots"][0]["relative_path"].startswith("snapshots/battle_results/")


def test_run_recorder_session_queries_count_replay_runs_without_createbattle_block(tmp_path: Path) -> None:
    output_root = tmp_path / "client_probe"
    session_dir = output_root / "20260323T202200Z"
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(json.dumps({"created_at": "2026-03-23T20:22:00+00:00"}), encoding="utf-8")
    battle_one = "912db89b-69b9-41c7-a672-44d0c3703639"
    battle_two = "75f03bd8-7c8c-4062-90a7-cf828d6be2d4"
    events = [
        {
            "captured_at": "2026-03-23T20:22:01+00:00",
            "event_type": "battle_context",
            "battle": {
                "battle_id": battle_one,
                "stage_id": "2062010",
                "formation_index": 0,
                "player_members": ["Rakka", "Yumeko", "Ninja", "Jintoro", "Valkyrie"],
                "enemy_rows": [{"slot": 1, "type_id": 26486, "name": "Type 26486", "level": 350}],
            },
        },
        {"captured_at": "2026-03-23T20:22:02+00:00", "event_type": "log_line", "line": "Change battle state [Loading -> Started]"},
        {"captured_at": "2026-03-23T20:27:05+00:00", "event_type": "log_line", "line": f"BattleResult added: [Id={battle_one}] TotalCount=1"},
        {"captured_at": "2026-03-23T20:27:06+00:00", "event_type": "log_line", "line": "Change battle state [Started -> Finished]"},
        {"captured_at": "2026-03-23T20:28:01+00:00", "event_type": "log_line", "line": "Change battle state [Finished -> RestartPending]"},
        {"captured_at": "2026-03-23T20:28:01+00:00", "event_type": "log_line", "line": f"Created setup for battle Id - {battle_two}"},
        {"captured_at": "2026-03-23T20:28:01+00:00", "event_type": "log_line", "line": f"BattleSetup cached: [ Id = {battle_two}, StartTime = 23/03/2026 19:28:01 ]"},
        {"captured_at": "2026-03-23T20:28:02+00:00", "event_type": "log_line", "line": "Change battle state [StartCmdSucceed -> Started]"},
        {"captured_at": "2026-03-23T20:33:05+00:00", "event_type": "log_line", "line": f"BattleResult added: [Id={battle_two}] TotalCount=1"},
        {
            "captured_at": "2026-03-23T20:33:05+00:00",
            "event_type": "forced_file_snapshot",
            "source_name": "battle_results",
            "battle": {
                "battle_id": battle_one,
                "stage_id": "2062010",
                "formation_index": 0,
                "player_members": ["Rakka", "Yumeko", "Ninja", "Jintoro", "Valkyrie"],
                "enemy_rows": [{"slot": 1, "type_id": 26486, "name": "Type 26486", "level": 350}],
            },
            "saved": {"marker": {"size": 12345}, "raw_path": "stale-capture.bin"},
            "reason": f"BattleResult added: [Id={battle_two}] TotalCount=1",
        },
        {
            "captured_at": "2026-03-23T20:33:05+00:00",
            "event_type": "file_snapshot",
            "source_name": "battle_results",
            "battle": {
                "battle_id": battle_one,
                "stage_id": "2062010",
                "formation_index": 0,
                "player_members": ["Rakka", "Yumeko", "Ninja", "Jintoro", "Valkyrie"],
                "enemy_rows": [{"slot": 1, "type_id": 26486, "name": "Type 26486", "level": 350}],
            },
            "saved": {"marker": {"size": 11}, "raw_path": "stale-after-delete.bin"},
        },
        {"captured_at": "2026-03-23T20:33:06+00:00", "event_type": "log_line", "line": "Change battle state [Started -> Finished]"},
    ]
    (session_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in events) + "\n",
        encoding="utf-8",
    )

    controller = RunRecorderController(
        base_dir=tmp_path,
        script_path=tmp_path / "deep_battle_probe.py",
        output_root=output_root,
        python_executable="python-test",
    )

    detail = run_recorder_session_detail("20260323T202200Z", output_root=output_root, recorder=controller)

    assert detail["run_count"] == 2
    assert detail["runs"][0]["battle_id"] == battle_two
    assert detail["runs"][0]["started_at"] == "2026-03-23T20:28:02+00:00"
    assert detail["runs"][0]["result_detected_at"] == "2026-03-23T20:33:05+00:00"
    assert detail["runs"][0]["finished_at"] == "2026-03-23T20:33:06+00:00"
    assert detail["runs"][1]["battle_id"] == battle_one


def test_categorize_run_distinguishes_clan_boss_special_and_stage_pve() -> None:
    assert cbforge_web.categorize_run(
        encounter_name="Demon Lord Ultra-Nightmare",
        stage_id="4019021",
        game_mode="clan_boss",
    ) == {
        "category_key": "clan_boss",
        "category_label": "Clan Boss",
    }
    assert cbforge_web.categorize_run(
        encounter_name="Type 28016",
        stage_id="15019003",
    ) == {
        "category_key": "special_pve_unmapped",
        "category_label": "PvE Speciale / Non Mappato",
    }
    assert cbforge_web.categorize_run(
        encounter_name="Venus",
        stage_id="2062010",
    ) == {
        "category_key": "stage_pve",
        "category_label": "Stage / Campagna / Altra PvE",
    }


def test_delete_run_recorder_session_removes_saved_session(tmp_path: Path) -> None:
    output_root = tmp_path / "client_probe"
    session_dir = output_root / "20260323T090000Z"
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text("{}", encoding="utf-8")

    controller = RunRecorderController(
        base_dir=tmp_path,
        script_path=tmp_path / "deep_battle_probe.py",
        output_root=output_root,
        python_executable="python-test",
    )

    result = delete_run_recorder_session("20260323T090000Z", output_root=output_root, recorder=controller)

    assert result["ok"] is True
    assert result["deleted_session_slug"] == "20260323T090000Z"
    assert not session_dir.exists()


def test_import_run_recorder_session_persists_into_db_and_exposes_import_status(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    output_root = tmp_path / "client_probe"
    live_root = tmp_path / "live_storage_probe"
    session_slug = "20260322T114745Z"
    session_dir = output_root / session_slug
    live_session_dir = live_root / session_slug
    session_dir.mkdir(parents=True)
    live_session_dir.mkdir(parents=True)

    hero_types_path = tmp_path / "hh_hero_types.json"
    hero_types_path.write_text(
        json.dumps(
            [
                {
                    "id": 22296,
                    "name": "Demon Lord",
                    "forms": [{"element": 4, "baseStats": {"speed": 170}}],
                }
            ]
        ),
        encoding="utf-8",
    )

    raw_asset = session_dir / "battle_results.bin"
    raw_asset.write_bytes(b"rich-battle-results")
    meta_asset = session_dir / "battle_results.json"
    meta_asset.write_text("{}", encoding="utf-8")
    live_asset = live_session_dir / "battleResults_12201.bin"
    live_asset.write_bytes(b"live-storage-rich-battle-results")

    battle = {
        "battle_id": "5d46944e-8521-4640-a635-f2d4a609b05f",
        "seed": 2035714064,
        "stage_id": "4019021",
        "formation_index": 0,
        "player_members": ["Rakka Viletide", "Valkyrie", "Ninja", "Jintoro", "Stag Knight"],
        "player_team": [
            {"slot": 1, "type_id": 3666, "name": "Rakka Viletide", "grade": "Stars6", "level": 60},
            {"slot": 2, "type_id": 2166, "name": "Valkyrie", "grade": "Stars6", "level": 60},
            {"slot": 3, "type_id": 6206, "name": "Ninja", "grade": "Stars6", "level": 60},
            {"slot": 4, "type_id": 5836, "name": "Jintoro", "grade": "Stars6", "level": 60},
            {"slot": 5, "type_id": 4496, "name": "Stag Knight", "grade": "Stars6", "level": 60},
        ],
        "enemy_rows": [{"slot": 1, "type_id": 22296, "name": "Type 22296", "grade": "Stars6", "level": 250}],
    }
    client_events = [
        {"captured_at": "2026-03-22T11:47:51+00:00", "event_type": "log_line", "line": "Change battle state [StartCmdSucceed -> Loading]"},
        {"captured_at": "2026-03-22T11:47:51+00:00", "event_type": "battle_context", "battle": battle},
        {
            "captured_at": "2026-03-22T11:47:51+00:00",
            "event_type": "sqlite_event",
            "db_name": "raidV2.db",
            "row": {"parsed": {"p": {"r": {"t": "CreateAllianceBossBattle"}}}},
        },
        {"captured_at": "2026-03-22T11:47:53+00:00", "event_type": "log_line", "line": "Change battle state [Loading -> Started]"},
        {"captured_at": "2026-03-22T11:56:40+00:00", "event_type": "log_line", "line": "BattleResult added: [Id=5d46944e-8521-4640-a635-f2d4a609b05f] TotalCount=1"},
        {
            "captured_at": "2026-03-22T11:56:40+00:00",
            "event_type": "forced_file_snapshot",
            "source_name": "battle_results",
            "saved": {
                "raw_path": str(raw_asset),
                "meta_path": str(meta_asset),
                "marker": {"size": 12201, "sha256": "abc123"},
            },
            "battle": battle,
        },
        {"captured_at": "2026-03-22T11:56:42+00:00", "event_type": "log_line", "line": "Change battle state [Started -> Finished]"},
    ]
    live_events = [
        {
            "captured_at": "2026-03-22T11:56:40+00:00",
            "event_type": "file_change",
            "snapshot": {"saved_path": str(live_asset), "marker": {"size": 12201}},
            "battle": battle,
        }
    ]
    (session_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in client_events) + "\n",
        encoding="utf-8",
    )
    (live_session_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in live_events) + "\n",
        encoding="utf-8",
    )

    controller = RunRecorderController(
        base_dir=tmp_path,
        script_path=tmp_path / "deep_battle_probe.py",
        output_root=output_root,
        python_executable="python-test",
    )

    result = import_run_recorder_session(
        session_slug,
        db_path=db_path,
        client_root=output_root,
        live_root=live_root,
        hero_types_path=hero_types_path,
        recorder=controller,
    )
    sessions_payload = list_run_recorder_sessions(output_root=output_root, recorder=controller, db_path=db_path)
    detail = run_recorder_session_detail(session_slug, output_root=output_root, recorder=controller, db_path=db_path)
    db_index = build_run_recorder_db_import_index(db_path)

    assert result["imported_runs"] == 1
    assert result["skipped_runs"] == 0
    assert result["db_import"]["imported"] is True
    assert db_index["runs"] == 1
    assert db_index["sessions"] == 1
    assert sessions_payload["summary"]["db_runs"] == 1
    assert sessions_payload["summary"]["db_sessions"] == 1
    assert sessions_payload["sessions"][0]["db_import"]["imported"] is True
    assert sessions_payload["sessions"][0]["db_import"]["imported_runs"] == 1
    assert detail["db_import"]["imported"] is True
    assert detail["db_import"]["pending_runs_estimate"] == 0


def test_import_all_run_recorder_sessions_skips_running_session(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    output_root = tmp_path / "client_probe"
    live_root = tmp_path / "live_storage_probe"
    session_ready = output_root / "20260322T114745Z"
    session_running = output_root / "20260323T210000Z"
    live_ready = live_root / "20260322T114745Z"
    session_ready.mkdir(parents=True)
    session_running.mkdir(parents=True)
    live_ready.mkdir(parents=True)

    hero_types_path = tmp_path / "hh_hero_types.json"
    hero_types_path.write_text(
        json.dumps([{"id": 22296, "name": "Demon Lord", "forms": [{"element": 4}]}]),
        encoding="utf-8",
    )
    (session_running / "session.json").write_text("{}", encoding="utf-8")

    raw_asset = session_ready / "battle_results.bin"
    raw_asset.write_bytes(b"rich-battle-results")
    meta_asset = session_ready / "battle_results.json"
    meta_asset.write_text("{}", encoding="utf-8")
    live_asset = live_ready / "battleResults_12201.bin"
    live_asset.write_bytes(b"live-storage-rich-battle-results")
    battle = {
        "battle_id": "5d46944e-8521-4640-a635-f2d4a609b05f",
        "stage_id": "4019021",
        "formation_index": 0,
        "player_team": [{"slot": 1, "type_id": 3666, "name": "Rakka Viletide", "grade": "Stars6", "level": 60}],
        "enemy_rows": [{"slot": 1, "type_id": 22296, "name": "Type 22296", "grade": "Stars6", "level": 250}],
    }
    client_events = [
        {"captured_at": "2026-03-22T11:47:51+00:00", "event_type": "battle_context", "battle": battle},
        {
            "captured_at": "2026-03-22T11:47:51+00:00",
            "event_type": "sqlite_event",
            "db_name": "raidV2.db",
            "row": {"parsed": {"p": {"r": {"t": "CreateAllianceBossBattle"}}}},
        },
        {"captured_at": "2026-03-22T11:47:53+00:00", "event_type": "log_line", "line": "Change battle state [Loading -> Started]"},
        {
            "captured_at": "2026-03-22T11:56:40+00:00",
            "event_type": "forced_file_snapshot",
            "source_name": "battle_results",
            "saved": {"raw_path": str(raw_asset), "meta_path": str(meta_asset), "marker": {"size": 12201}},
            "battle": battle,
        },
        {"captured_at": "2026-03-22T11:56:42+00:00", "event_type": "log_line", "line": "Change battle state [Started -> Finished]"},
    ]
    live_events = [
        {
            "captured_at": "2026-03-22T11:56:40+00:00",
            "event_type": "file_change",
            "snapshot": {"saved_path": str(live_asset), "marker": {"size": 12201}},
            "battle": battle,
        }
    ]
    (session_ready / "events.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in client_events) + "\n",
        encoding="utf-8",
    )
    (live_ready / "events.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in live_events) + "\n",
        encoding="utf-8",
    )

    controller = RunRecorderController(
        base_dir=tmp_path,
        script_path=tmp_path / "deep_battle_probe.py",
        output_root=output_root,
        python_executable="python-test",
    )
    class _FakeProcess:
        pid = 9999

        def poll(self) -> None:
            return None

    controller._process = _FakeProcess()  # type: ignore[assignment]
    controller._session_slug = "20260323T210000Z"
    controller._session_dir = session_running

    result = import_all_run_recorder_sessions(
        db_path=db_path,
        output_root=output_root,
        live_root=live_root,
        hero_types_path=hero_types_path,
        recorder=controller,
        include_running=False,
    )

    assert result["selected_sessions"] == 1
    assert result["imported_runs"] == 1
    assert result["skipped_sessions"] == [{"session_slug": "20260323T210000Z", "reason": "running"}]


def test_run_history_run_detail_exposes_skill_usage_and_raw_payload(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    session_slug = "20260324T073610Z"
    output_root = tmp_path / "client_probe"
    session_dir = output_root / session_slug
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text("{}", encoding="utf-8")
    (session_dir / "events.jsonl").write_text("", encoding="utf-8")

    raw_asset = tmp_path / "battle_results.bin"
    raw_asset.write_bytes(b"placeholder")

    summary = record_run_history(
        {
            "saved_at": "2026-03-24T07:36:10+00:00",
            "source": "probe_import",
            "source_run_uid": "368e1bb0-a147-4b58-9c85-668f395e3cb7",
            "battle_id": "368e1bb0-a147-4b58-9c85-668f395e3cb7",
            "probe_session_slug": session_slug,
            "encounter_key": "2062010",
            "encounter_name": "Dragon's Lair",
            "stage_id": "2062010",
            "stage_label": "Dragon's Lair. Stage 10",
            "success": True,
            "completed": True,
            "members": [
                {
                    "champion_name": "Ninja",
                    "champion_type_id": 6206,
                    "level": 60,
                    "rank": 6,
                    "stats": {"atk": 3885.94, "crit_dmg": 313.0},
                    "metrics": {"damage_done": 7101899, "damage_taken": 26425},
                    "skill_usage": [
                        {"skill_order": 1, "skill_slot": "A1", "skill_code": "62001", "usage_count": 10},
                        {"skill_order": 2, "skill_slot": "A2", "skill_code": "62002", "usage_count": 12},
                    ],
                }
            ],
            "assets": [
                {
                    "asset_kind": "client_probe_battle_results_bin",
                    "asset_path": str(raw_asset),
                }
            ],
        },
        db_path=db_path,
    )

    monkeypatch.setattr(
        cbforge_web,
        "extract_member_result_rows",
        lambda path: [
            {
                "member_order": 1,
                "champion_type_id": 6206,
                "slot_index": 2,
                "damage_taken": 26425,
                "raw_damage_taken": 113494749388923,
                "member_payload": {"dt": 113494749388923},
                "profile_payload": {"f": {"a": 1}},
            }
        ],
    )
    monkeypatch.setattr(
        cbforge_web,
        "extract_incoming_target_counts",
        lambda path: [
            {
                "member_order": 1,
                "incoming_target_events": 4,
                "incoming_boss_target_events": 3,
                "incoming_enemy_skill_codes": {"264801": 2, "264802": 2},
                "incoming_boss_skill_codes": {"264801": 1, "264802": 2},
            }
        ],
    )

    session_runs = list_run_history_runs_for_session(session_slug, db_path=db_path)
    detail = run_history_run_detail(summary["run_id"], db_path=db_path)
    session_detail = run_recorder_session_detail(session_slug, output_root=output_root, db_path=db_path)

    assert session_runs[0]["battle_id"] == "368e1bb0-a147-4b58-9c85-668f395e3cb7"
    assert session_runs[0]["skill_usages"] == 2
    assert session_runs[0]["category_key"] == "dungeon_boss"
    assert detail["run"]["battle_id"] == "368e1bb0-a147-4b58-9c85-668f395e3cb7"
    assert detail["run"]["category_label"] == "Dungeon / Boss PvE"
    assert detail["members"][0]["skill_usage"][0]["skill_slot"] == "A1"
    assert detail["members"][0]["raw"]["member_payload"]["dt"] == 113494749388923
    assert detail["members"][0]["pressure"]["incoming_target_events"] == 4
    assert detail["members"][0]["pressure"]["incoming_boss_target_events"] == 3
    assert detail["members"][0]["derived"]["damage_done_share_pct"] == 100.0
    assert detail["members"][0]["derived"]["incoming_target_share_pct"] == 100.0
    assert detail["derived_totals"]["incoming_target_events"] == 4
    assert session_detail["db_runs"][0]["run_id"] == summary["run_id"]
