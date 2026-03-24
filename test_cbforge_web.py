from __future__ import annotations

import json
from pathlib import Path

import cbforge_web
from cbforge_web import (
    RunRecorderController,
    build_gear_summary,
    build_run_recorder_db_import_index,
    build_run_recorder_status,
    build_set_curation_payload,
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
    list_run_recorder_sessions,
    refresh_gear_from_game,
    run_history_run_detail,
    run_recorder_session_detail,
    sell_artifacts_from_queue,
)
from forge_db import bootstrap_database, record_run_history


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
    assert payload["selection"]["boss_key"] == "demon_lord"
    assert payload["selection"]["level_key"] == "ultra_nightmare"
    assert payload["selection"]["affinity"] == "void"
    assert payload["report"]["target"]["key"] == "demon_lord_unm"
    assert len(payload["report"]["selected_team"]) == 5
    assert payload["report"]["missing_required_roles"] == []


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
    assert sessions_payload["sessions"][0]["latest_run"]["damage_trusted"] is False
    assert sessions_payload["sessions"][0]["snapshot_count"] == 2
    assert detail["metadata"]["interval"] == 0.35
    assert detail["latest_battle"]["team_members"] == ["Rakka", "Valkyrie", "Ninja", "Jintoro", "Stag Knight"]
    assert detail["event_type_counts"]["forced_file_snapshot"] == 1
    assert detail["runs"][0]["battle_id"] == "battle-123"
    assert detail["runs"][0]["started_at"] == "2026-03-23T08:15:03+00:00"
    assert detail["runs"][0]["finished_at"] == "2026-03-23T08:15:15+00:00"
    assert detail["runs"][0]["best_battle_results_size"] == 12201
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
    assert detail["run"]["battle_id"] == "368e1bb0-a147-4b58-9c85-668f395e3cb7"
    assert detail["members"][0]["skill_usage"][0]["skill_slot"] == "A1"
    assert detail["members"][0]["raw"]["member_payload"]["dt"] == 113494749388923
    assert detail["members"][0]["pressure"]["incoming_target_events"] == 4
    assert detail["members"][0]["pressure"]["incoming_boss_target_events"] == 3
    assert detail["members"][0]["derived"]["damage_done_share_pct"] == 100.0
    assert detail["members"][0]["derived"]["incoming_target_share_pct"] == 100.0
    assert detail["derived_totals"]["incoming_target_events"] == 4
    assert session_detail["db_runs"][0]["run_id"] == summary["run_id"]
