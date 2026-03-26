from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from enrichment_sources import ChampionSkillMatch, get_skill_enrichment_provider, register_skill_enrichment_provider
from forge_db import bootstrap_database, collect_gear_validation_issues, load_source_account, record_run_history, refresh_account_stat_models
from hellhades_enrich import HellHadesChampionMatch, enrich_registry_from_hellhades, enrich_registry_from_source
from providers.local_registry_provider import export_local_skill_registry


def test_bootstrap_database_builds_relational_tables(tmp_path: Path) -> None:
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
                "base_stats": {"hp": 20000, "def": 1200, "spd": 100},
                "total_stats": {"hp": 50000, "def": 3000, "spd": 210, "acc": 320},
                "equipped_item_ids": ["gear-1"],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "geo_a1",
                        "name": "Stone Hammer",
                        "cooldown": 0,
                        "effects": [{"type": "damage", "target": "enemy", "value": 1.0}],
                    },
                    {
                        "slot": "A3",
                        "skill_id": "geo_a3",
                        "name": "Burning Resolve",
                        "cooldown": 3,
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
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "ch_a1",
                        "name": "Heartseeker Start",
                        "cooldown": None,
                        "effects": [],
                    }
                ],
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
                "locked": True,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [{"type": "acc", "value": 20, "rolls": 2, "glyph_value": 0}],
            }
        ],
        "account_bonuses": [
            {
                "bonus_id": "great_hall_force_acc",
                "source": "great_hall",
                "scope": "global",
                "target": "force",
                "stat": "acc",
                "value": 10,
                "active": True,
            }
        ],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    assert summary["champion_catalog"] == 2
    assert summary["champion_roles"] == 3
    assert summary["champion_base_stats"] == 4
    assert summary["champion_skills"] == 3
    assert summary["champion_skill_effects"] == 2
    assert summary["account_champions"] == 2
    assert summary["account_champion_total_stats"] == 5
    assert summary["account_champion_imported_total_stats"] == 5
    assert summary["account_champion_masteries"] == 0
    assert summary["gear_items"] == 1
    assert summary["gear_substats"] == 1
    assert summary["account_bonuses"] == 1
    assert summary["set_definitions"] >= 1
    assert summary["set_definition_piece_bonuses"] >= 1
    assert summary["registry_targets"] == 1
    assert summary["app_state"] >= 3
    assert summary["account_champion_stat_models"] == 2

    with sqlite3.connect(db_path) as conn:
        champion_catalog_columns = {row[1] for row in conn.execute("PRAGMA table_info(champion_catalog)").fetchall()}
        champion_skill_columns = {row[1] for row in conn.execute("PRAGMA table_info(champion_skills)").fetchall()}
        set_definition_columns = {row[1] for row in conn.execute("PRAGMA table_info(set_definitions)").fetchall()}

    assert "hellhades_post_id" in champion_catalog_columns
    assert "skill_type" in champion_skill_columns
    assert "description_clean" in champion_skill_columns
    assert "source" in champion_skill_columns
    assert "set_kind" in set_definition_columns
    assert "counts_accessories" in set_definition_columns
    assert "max_pieces" in set_definition_columns


def test_load_source_account_repairs_gear_slots_from_raw_kind_map(tmp_path: Path) -> None:
    normalized_path = tmp_path / "normalized_account.json"
    raw_path = tmp_path / "raw_account.json"
    normalized_payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "accessory",
                "slot": "banner",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 398},
                "substats": [],
            }
        ],
        "account_bonuses": [],
    }
    raw_payload = {
        "inventory": [
            {
                "item_id": "gear-1",
                "kind": 9,
                "item_class": "accessory",
                "slot": "banner",
                "main_stat": {"type": "atk", "value": 398},
            }
        ]
    }
    normalized_path.write_text(json.dumps(normalized_payload), encoding="utf-8")
    raw_path.write_text(json.dumps(raw_payload), encoding="utf-8")

    account = load_source_account(normalized_path)

    assert account["gear"][0]["slot"] == "banner"
    assert account["gear"][0]["item_class"] == "accessory"


def test_load_source_account_keeps_raw_slot_when_kind_repair_would_create_invalid_accessory(tmp_path: Path) -> None:
    normalized_path = tmp_path / "normalized_account.json"
    raw_path = tmp_path / "raw_account.json"
    normalized_payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "accessory",
                "slot": "banner",
                "set_name": "",
                "rarity": "epic",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "crit_dmg", "value": 96},
                "substats": [{"type": "spd", "value": 16, "rolls": 2, "glyph_value": 0}],
            }
        ],
        "account_bonuses": [],
    }
    raw_payload = {
        "inventory": [
            {
                "item_id": "gear-1",
                "kind": 9,
                "item_class": "accessory",
                "slot": "banner",
                "main_stat": {"type": "crit_dmg", "value": 96},
                "substats": [{"type": "spd", "value": 16}],
            }
        ]
    }
    normalized_path.write_text(json.dumps(normalized_payload), encoding="utf-8")
    raw_path.write_text(json.dumps(raw_payload), encoding="utf-8")

    account = load_source_account(normalized_path)
    item = account["gear"][0]

    assert item["slot"] == "banner"
    assert collect_gear_validation_issues(item) == ["main_stat:crit_dmg@banner"]


def test_bootstrap_database_repairs_illegal_slot_main_stat_combinations(tmp_path: Path) -> None:
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
                "booked": False,
                "role_tags": [],
                "base_stats": {"hp": 100, "atk": 100, "def": 100, "spd": 100, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": ["gear-1", "gear-2"],
                "skills": [],
            }
        ],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "accessory",
                "slot": "amulet",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "acc", "value": 0.4},
                "substats": [],
            },
            {
                "item_id": "gear-2",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "res", "value": 0.6},
                "substats": [],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT item_id, slot FROM gear_items ORDER BY item_id").fetchall()

    assert rows == [("gear-1", "banner"), ("gear-2", "chest")]


def test_bootstrap_database_tracks_relic_count_on_owned_champions(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Arbiter",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "High Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 2,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"spd": 110},
                "total_stats": {"spd": 0},
                "equipped_item_ids": [],
                "relic_ids": ["203"],
                "skills": [],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT relic_count FROM account_champions WHERE champ_id = 'champ-1'").fetchone()

    assert row is not None
    assert int(row[0]) == 1


def test_bootstrap_database_persists_account_masteries(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Arbiter",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "High Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 2,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"spd": 110},
                "total_stats": {"spd": 0},
                "equipped_item_ids": [],
                "masteries": [
                    {"mastery_id": "500313", "name": "Pinpoint Accuracy", "tree": "support", "active": True},
                    {"mastery_id": "500343", "name": "Lore of Steel", "tree": "support", "active": True},
                ],
                "skills": [],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    assert summary["account_champion_masteries"] == 2
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT mastery_id, mastery_name, tree, active FROM account_champion_masteries WHERE champ_id = 'champ-1' ORDER BY mastery_order"
        ).fetchall()

    assert rows == [
        ("500313", "Pinpoint Accuracy", "support", 1),
        ("500343", "Lore of Steel", "support", 1),
    ]


def test_bootstrap_database_rebuilds_without_unlinking_database_file(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    def fail_unlink(self, missing_ok: bool = False):
        raise AssertionError("reset_database should not unlink the sqlite file during rebuild")

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    summary = bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    assert db_path.exists()
    assert summary["account_champions"] == 0
    assert summary["app_state"] >= 1


def test_bootstrap_database_exposes_run_history_tables(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")

    summary = bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    assert summary["run_history_runs"] == 0
    assert summary["run_history_members"] == 0
    assert summary["run_history_member_stats"] == 0
    assert summary["run_history_member_metrics"] == 0
    assert summary["run_history_member_skill_usage"] == 0
    assert summary["run_history_assets"] == 0
    assert summary["run_history_events"] == 0
    assert summary["run_history_effect_timeline"] == 0


def test_record_run_history_persists_ai_friendly_training_rows(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    payload = {
        "saved_at": "2026-03-22T11:07:06+00:00",
        "source": "client_probe",
        "battle_id": "dc24ce97-2906-49c1-95cc-cc97e190df9f",
        "probe_session_slug": "20260322T110139Z",
        "encounter_key": "dragons_lair_hard_10",
        "encounter_name": "Dragon Hard 10",
        "encounter_family": "dragon",
        "area_region": "dragons_lair",
        "game_mode": "dungeon",
        "difficulty": "hard",
        "stage_id": "2062010",
        "stage_label": "Dragon Hard 10",
        "stage_tier": 10,
        "boss_affinity": "spirit",
        "affinity_context": "fixed_stage_affinity",
        "result_code": "win",
        "success": True,
        "completed": True,
        "auto_play": True,
        "formation_index": 0,
        "team_name": "Dragon Hard 10 Fast Farm",
        "team_hash": "dragon_h10_fast_01",
        "leader_slot": 2,
        "elapsed_seconds": 244.6,
        "turns": 157,
        "boss_turn": 0,
        "total_damage": 314451.3,
        "account_power": 196500.0,
        "model_target": "optimize_dragon_hard_speed",
        "labels": {"speed_bucket": "fast", "farm_viable": True},
        "context": {"client": "raid_pc", "capture": "battleResults"},
        "assets": [
            {
                "asset_kind": "battle_results_bin",
                "asset_path": "input/live_storage_probe/20260322T110139Z/snapshots/battle_results/20260322T110658Z_battleResults_13528.bin",
                "sha256": "abc123",
                "size_bytes": 13528,
                "captured_at": "2026-03-22T11:06:58+00:00",
                "metadata": {"probe": "live_storage_probe"},
            }
        ],
        "events": [
            {
                "event_time": "2026-03-22T11:06:58+00:00",
                "event_type": "battle_results_captured",
                "source_name": "live_storage_probe",
                "value_numeric": 13528,
                "payload": {"size": 13528},
            }
        ],
        "effect_timeline": {
            "status_timeline_status": "candidate_from_cast_order_plus_skill_metadata",
            "status_timeline_count": 1,
            "timeline": [
                {
                    "event_index": 0,
                    "source_slot": 1,
                    "source_name": "Jintoro",
                    "source_type_id": 5836,
                    "target_party_id": -1,
                    "target_slot": 5,
                    "skill_order": 3,
                    "skill_slot": "A3",
                    "skill_code": "58303",
                    "skill_name": "Oni's Rage",
                    "skill_type": "Active",
                    "skill_provider": "ayumilove",
                    "status_effects": [
                        {
                            "effect_type": "decrease_def",
                            "category": "debuff",
                            "action": "place",
                            "target": "enemy",
                            "duration": 2,
                            "chance": None,
                            "effect_value": 60.0,
                            "resolution": "candidate_from_skill_metadata",
                            "condition_text": "Places a 60% [Decrease DEF] debuff for 2 turns.",
                        },
                        {
                            "effect_type": "weaken",
                            "category": "debuff",
                            "action": "place",
                            "target": "enemy",
                            "duration": 2,
                            "chance": None,
                            "effect_value": 25.0,
                            "resolution": "candidate_from_skill_metadata",
                            "condition_text": "Places a 25% [Weaken] debuff for 2 turns.",
                        },
                    ],
                }
            ],
        },
        "members": [
            {
                "champ_id": "champ-rakka",
                "champion_name": "Rakka Viletide",
                "champion_type_id": 3666,
                "role_hint": "support_revive",
                "level": 60,
                "rank": 6,
                "awakening_level": 2,
                "empowerment_level": 0,
                "booked": True,
                "build_fingerprint": "rakka_v1",
                "set_summary": ["Feral", "Protection"],
                "tags": ["run_stable", "reviver"],
                "stats": {"hp": 81234, "spd": 251, "res": 525},
                "metrics": {"damage_done": 46384.5, "damage_taken": 15872.4, "alive_at_end": 1},
                "skill_usage": [
                    {"skill_order": 1, "skill_slot": "A1", "skill_code": "36601", "usage_count": 10},
                    {"skill_order": 2, "skill_slot": "A2", "skill_code": "36602", "usage_count": 12},
                ],
            },
            {
                "champ_id": "champ-jintoro",
                "champion_name": "Jintoro",
                "champion_type_id": 5836,
                "role_hint": "boss_damage",
                "level": 60,
                "rank": 6,
                "awakening_level": 4,
                "empowerment_level": 0,
                "booked": True,
                "build_fingerprint": "jintoro_v2",
                "set_summary": ["Merciless", "Cruel"],
                "tags": ["damage_core"],
                "stats": {"atk": 6230, "spd": 228, "crit_dmg": 281},
                "metrics": {"damage_done": 129318.6, "damage_taken": 9442.1, "alive_at_end": 1},
                "skill_usage": [
                    {"skill_order": 1, "skill_slot": "A1", "skill_code": "58301", "usage_count": 11},
                ],
            },
        ],
    }

    summary = record_run_history(payload, db_path=db_path)

    assert summary["encounter_key"] == "dragons_lair_hard_10"
    assert summary["battle_id"] == "dc24ce97-2906-49c1-95cc-cc97e190df9f"
    assert summary["success"] is True
    assert summary["members"] == 2
    assert summary["events"] == 1
    assert summary["assets"] == 1
    assert summary["skill_usages"] == 3
    assert summary["effect_timeline_rows"] == 2
    assert summary["total_damage"] == 314451.3

    with sqlite3.connect(db_path) as conn:
        run_row = conn.execute(
            """
            SELECT source, encounter_family, area_region, game_mode, boss_affinity, model_target, labels_json
            FROM run_history_runs
            WHERE run_id = ?
            """,
            (summary["run_id"],),
        ).fetchone()
        stat_rows = conn.execute(
            """
            SELECT member_order, stat_name, stat_value
            FROM run_history_member_stats
            WHERE run_id = ?
            ORDER BY member_order, stat_name
            """,
            (summary["run_id"],),
        ).fetchall()
        metric_rows = conn.execute(
            """
            SELECT member_order, damage_done, alive_at_end
            FROM run_history_member_metrics
            WHERE run_id = ?
            ORDER BY member_order
            """,
            (summary["run_id"],),
        ).fetchall()
        skill_usage_rows = conn.execute(
            """
            SELECT member_order, skill_order, skill_slot, skill_code, usage_count
            FROM run_history_member_skill_usage
            WHERE run_id = ?
            ORDER BY member_order, skill_order
            """,
            (summary["run_id"],),
        ).fetchall()
        effect_timeline_rows = conn.execute(
            """
            SELECT source_name, skill_slot, effect_type, effect_action, effect_target, duration_turns
            FROM run_history_effect_timeline
            WHERE run_id = ?
            ORDER BY timeline_index, effect_index
            """,
            (summary["run_id"],),
        ).fetchall()

    assert run_row is not None
    assert run_row[0] == "client_probe"
    assert run_row[1] == "dragon"
    assert run_row[2] == "dragons_lair"
    assert run_row[3] == "dungeon"
    assert run_row[4] == "spirit"
    assert run_row[5] == "optimize_dragon_hard_speed"
    assert json.loads(run_row[6])["farm_viable"] is True
    assert stat_rows == [
        (1, "hp", 81234.0),
        (1, "res", 525.0),
        (1, "spd", 251.0),
        (2, "atk", 6230.0),
        (2, "crit_dmg", 281.0),
        (2, "spd", 228.0),
    ]
    assert metric_rows == [
        (1, 46384.5, 1),
        (2, 129318.6, 1),
    ]
    assert skill_usage_rows == [
        (1, 1, "A1", "36601", 10),
        (1, 2, "A2", "36602", 12),
        (2, 1, "A1", "58301", 11),
    ]
    assert effect_timeline_rows == [
        ("Jintoro", "A3", "decrease_def", "place", "enemy", 2),
        ("Jintoro", "A3", "weaken", "place", "enemy", 2),
    ]


def test_hellhades_enrichment_updates_skills_and_effects(tmp_path: Path, monkeypatch) -> None:
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
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                    {"slot": "A2", "skill_id": "48802", "name": "48802", "effects": []},
                    {"slot": "A3", "skill_id": "48804", "name": "48804", "effects": []},
                    {"slot": "A4", "skill_id": "48805", "name": "48805", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    remote_skills = [
        {
            "name": "Tremor Staff",
            "type": "Basic",
            "cooldown": 0,
            "description": (
                "<p>Attacks 1 enemy. Has a 30% chance of placing a [Decrease ACC] debuff for 2 turns.<br />"
                "Level 2: Damage +5%</p>"
            ),
            "books": [],
        },
        {
            "name": "Creeping Petrify",
            "type": "Active",
            "cooldown": 4,
            "description": (
                "<p>Fully depletes the target's Turn Meter. Fills this Champion's Turn Meter by 25%.<br />"
                "Level 2: Cooldown -1</p>"
            ),
            "books": [],
        },
        {
            "name": "Quicksand Grasp",
            "type": "Active",
            "cooldown": 5,
            "description": (
                "<p>Places a [HP Burn] debuff for 3 turns and a [Weaken] debuff for 2 turns.<br />"
                "Level 2: Cooldown -1<br />"
                "Level 3: Cooldown -1</p>"
            ),
            "books": [],
        },
        {
            "name": "Stoneguard [P]",
            "type": "Passive",
            "cooldown": "",
            "description": "<p>Places a [Block Debuffs] buff on all allies for 1 turn.</p>",
            "books": [],
        },
    ]

    monkeypatch.setattr(
        "hellhades_enrich.resolve_champion_match",
        lambda champion_name: HellHadesChampionMatch(
            post_id=17837,
            title=champion_name,
            url="https://hellhades.com/raid/champions/geomancer/",
        ),
    )
    monkeypatch.setattr("hellhades_enrich.fetch_champion_skills", lambda post_id: remote_skills)

    summary = enrich_registry_from_hellhades(db_path=db_path)

    assert summary["requested"] == 1
    assert summary["matched"] == 1
    assert summary["updated"] == 1

    with sqlite3.connect(db_path) as conn:
        catalog_row = conn.execute(
            """
            SELECT hellhades_post_id, hellhades_url
            FROM champion_catalog
            WHERE champion_name = 'Geomancer'
            """
        ).fetchone()
        skill_rows = conn.execute(
            """
            SELECT slot, skill_name, cooldown, booked_cooldown, skill_type, description_clean, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()
        effect_types = {
            row[0]
            for row in conn.execute(
                """
                SELECT effect_type
                FROM champion_skill_effects
                WHERE champion_name = 'Geomancer'
                """
            ).fetchall()
        }

    assert catalog_row == (17837, "https://hellhades.com/raid/champions/geomancer/")
    assert skill_rows[0][0] == "A1"
    assert skill_rows[0][1] == "Tremor Staff"
    assert skill_rows[0][2] == 0
    assert skill_rows[0][4] == "Basic"
    assert "Level 2:" not in (skill_rows[0][5] or "")
    assert skill_rows[0][6] == "hellhades"
    assert skill_rows[2][1] == "Quicksand Grasp"
    assert skill_rows[2][2] == 5
    assert skill_rows[2][3] == 3
    assert skill_rows[3][4] == "Passive"
    assert "decrease_acc" in effect_types
    assert "turn_meter_reduce" in effect_types
    assert "turn_meter_fill" in effect_types
    assert "hp_burn" in effect_types
    assert "weaken" in effect_types
    assert "block_debuffs" in effect_types


def test_enrichment_can_run_through_generic_provider_layer(tmp_path: Path) -> None:
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
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                    {"slot": "A2", "skill_id": "48802", "name": "48802", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    class FakeProvider:
        source_name = "fake-provider"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(
                source_name=self.source_name,
                source_ref="9001",
                title=champion_name,
                url="https://example.invalid/champions/geomancer",
            )

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {
                    "name": "Provider A1",
                    "type": "Basic",
                    "cooldown": 0,
                    "description": "<p>Places a [Decrease DEF] debuff for 2 turns.</p>",
                    "books": [],
                },
                {
                    "name": "Provider A2",
                    "type": "Active",
                    "cooldown": 4,
                    "description": "<p>Places a [HP Burn] debuff for 3 turns.</p>",
                    "books": [],
                },
            ]

    register_skill_enrichment_provider(FakeProvider())

    summary = enrich_registry_from_source("fake-provider", db_path=db_path)

    assert summary["provider"] == "fake-provider"
    assert summary["updated"] == 1

    with sqlite3.connect(db_path) as conn:
        skill_rows = conn.execute(
            """
            SELECT skill_name, skill_type, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()
        effect_types = {
            row[0]
            for row in conn.execute(
                """
                SELECT effect_type
                FROM champion_skill_effects
                WHERE champion_name = 'Geomancer'
                """
            ).fetchall()
        }

    assert skill_rows == [
        ("Provider A1", "Basic", "fake-provider"),
        ("Provider A2", "Active", "fake-provider"),
    ]
    assert "decrease_def" in effect_types
    assert "hp_burn" in effect_types


def test_local_skill_registry_export_roundtrips_db_skill_data(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    registry_path = tmp_path / "local_skill_registry.json"
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
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "geo_a1",
                        "name": "Stone Hammer",
                        "cooldown": 0,
                        "description": "Places [HP Burn].",
                        "effects": [{"type": "hp_burn", "target": "enemy", "duration": 2}],
                    }
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = export_local_skill_registry(db_path=db_path, output_path=registry_path)

    exported = json.loads(registry_path.read_text(encoding="utf-8"))
    assert summary["champion_count"] == 1
    assert summary["skill_count"] == 1
    assert exported["champions"][0]["champion_name"] == "Geomancer"
    assert exported["champions"][0]["skills"][0]["name"] == "Stone Hammer"
    assert exported["champions"][0]["skills"][0]["effects"][0]["effect_type"] == "hp_burn"


def test_auto_provider_prefers_local_registry_before_hellhades(tmp_path: Path) -> None:
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
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                    {"slot": "A2", "skill_id": "48802", "name": "48802", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    original_local = get_skill_enrichment_provider("local_registry")
    original_ayumi = get_skill_enrichment_provider("ayumilove")
    original_hh = get_skill_enrichment_provider("hellhades")

    class LocalProvider:
        source_name = "local_registry"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, champion_name, champion_name, "")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "Local A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Decrease ATK] debuff.</p>", "effects": []},
                {"name": "Local A2", "type": "Active", "cooldown": 4, "description": "<p>Places a [HP Burn] debuff.</p>", "effects": []},
            ]

    class HellHadesProvider:
        source_name = "hellhades"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, "17837", champion_name, "https://example.invalid/hh")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "HH A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Decrease DEF] debuff.</p>", "effects": []},
                {"name": "HH A2", "type": "Active", "cooldown": 4, "description": "<p>Places a [Weaken] debuff.</p>", "effects": []},
            ]

    class AyumiLoveProvider:
        source_name = "ayumilove"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, champion_name, champion_name, "https://example.invalid/ayumi")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "Ayumi A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Leech] debuff.</p>", "effects": []},
                {"name": "Ayumi A2", "type": "Active", "cooldown": 4, "description": "<p>Places a [Fear] debuff.</p>", "effects": []},
            ]

    register_skill_enrichment_provider(LocalProvider())
    register_skill_enrichment_provider(AyumiLoveProvider())
    register_skill_enrichment_provider(HellHadesProvider())
    try:
        summary = enrich_registry_from_source("auto", db_path=db_path)
    finally:
        register_skill_enrichment_provider(original_local)
        register_skill_enrichment_provider(original_ayumi)
        register_skill_enrichment_provider(original_hh)

    assert summary["provider"] == "auto"
    assert summary["provider_hits"]["local_registry"] == 1
    assert summary["provider_hits"]["ayumilove"] == 0
    assert summary["provider_hits"]["hellhades"] == 0

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT skill_name, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()

    assert rows == [("Local A1", "local_registry"), ("Local A2", "local_registry")]


def test_auto_provider_falls_back_to_hellhades_when_local_registry_missing(tmp_path: Path) -> None:
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
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    original_local = get_skill_enrichment_provider("local_registry")
    original_ayumi = get_skill_enrichment_provider("ayumilove")
    original_hh = get_skill_enrichment_provider("hellhades")

    class EmptyLocalProvider:
        source_name = "local_registry"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return None

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return []

    class HellHadesProvider:
        source_name = "hellhades"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, "17837", champion_name, "https://example.invalid/hh")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "HH A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Decrease DEF] debuff.</p>", "effects": []},
            ]

    class AyumiLoveProvider:
        source_name = "ayumilove"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, champion_name, champion_name, "https://example.invalid/ayumi")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "Ayumi A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Leech] debuff.</p>", "effects": []},
            ]

    register_skill_enrichment_provider(EmptyLocalProvider())
    register_skill_enrichment_provider(AyumiLoveProvider())
    register_skill_enrichment_provider(HellHadesProvider())
    try:
        summary = enrich_registry_from_source("auto", db_path=db_path)
    finally:
        register_skill_enrichment_provider(original_local)
        register_skill_enrichment_provider(original_ayumi)
        register_skill_enrichment_provider(original_hh)

    assert summary["provider_hits"]["local_registry"] == 0
    assert summary["provider_hits"]["ayumilove"] == 1
    assert summary["provider_hits"]["hellhades"] == 0

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT skill_name, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()

    assert rows == [("Ayumi A1", "ayumilove")]


def test_auto_provider_falls_back_to_hellhades_when_ayumilove_missing(tmp_path: Path) -> None:
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
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    original_local = get_skill_enrichment_provider("local_registry")
    original_ayumi = get_skill_enrichment_provider("ayumilove")
    original_hh = get_skill_enrichment_provider("hellhades")

    class EmptyLocalProvider:
        source_name = "local_registry"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return None

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return []

    class EmptyAyumiLoveProvider:
        source_name = "ayumilove"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return None

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return []

    class HellHadesProvider:
        source_name = "hellhades"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, "17837", champion_name, "https://example.invalid/hh")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "HH A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Decrease DEF] debuff.</p>", "effects": []},
            ]

    register_skill_enrichment_provider(EmptyLocalProvider())
    register_skill_enrichment_provider(EmptyAyumiLoveProvider())
    register_skill_enrichment_provider(HellHadesProvider())
    try:
        summary = enrich_registry_from_source("auto", db_path=db_path)
    finally:
        register_skill_enrichment_provider(original_local)
        register_skill_enrichment_provider(original_ayumi)
        register_skill_enrichment_provider(original_hh)

    assert summary["provider_hits"]["local_registry"] == 0
    assert summary["provider_hits"]["ayumilove"] == 0
    assert summary["provider_hits"]["hellhades"] == 1

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT skill_name, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()

    assert rows == [("HH A1", "hellhades")]


def test_bootstrap_derives_total_stats_when_raw_dump_is_empty(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Seeker",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Barbarians",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {
                    "hp": 100,
                    "atk": 100,
                    "def": 100,
                    "spd": 100,
                    "crit_rate": 15,
                    "crit_dmg": 50,
                    "acc": 0,
                    "res": 30,
                },
                "total_stats": {
                    "hp": 0,
                    "atk": 0,
                    "def": 0,
                    "spd": 0,
                    "crit_rate": 0,
                    "crit_dmg": 0,
                    "acc": 0,
                    "res": 0,
                },
                "equipped_item_ids": ["gear-1", "gear-2"],
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
                "substats": [{"type": "acc", "value": 0.2, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "gear-2",
                "item_class": "artifact",
                "slot": "weapon",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "atk", "value": 265},
                "substats": [{"type": "hp_pct", "value": 0.1, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [
            {
                "bonus_id": "great_hall_force_acc",
                "source": "great_hall",
                "scope": "global",
                "target": "force",
                "stat": "acc",
                "value": 10,
                "active": True,
            }
        ],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    with sqlite3.connect(db_path) as conn:
        total_stats = dict(
            conn.execute(
                """
                SELECT stat_name, stat_value
                FROM account_champion_total_stats
                WHERE champ_id = 'champ-1'
                """
            ).fetchall()
        )
        stat_model = conn.execute(
            """
            SELECT source, completeness
            FROM account_champion_stat_models
            WHERE champ_id = 'champ-1'
            """
        ).fetchone()

    assert total_stats["hp"] == 26400.0
    assert total_stats["atk"] == 1165.0
    assert total_stats["spd"] == 157.0
    assert total_stats["acc"] == 30.0
    assert stat_model == ("derived", "derived")

    refresh_summary = refresh_account_stat_models(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        refreshed_stats = dict(
            conn.execute(
                """
                SELECT stat_name, stat_value
                FROM account_champion_total_stats
                WHERE champ_id = 'champ-1'
                """
            ).fetchall()
        )
        refreshed_model = conn.execute(
            """
            SELECT source, completeness
            FROM account_champion_stat_models
            WHERE champ_id = 'champ-1'
            """
        ).fetchone()

    assert refresh_summary["derived_champions"] == 1
    assert refreshed_stats == total_stats
    assert refreshed_model == ("derived", "derived")


def test_refresh_account_stat_models_applies_awakening_and_empowerment(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Arbiter",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "High Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 2,
                "empowerment_level": 2,
                "booked": True,
                "role_tags": [],
                "base_stats": {"hp": 21000, "atk": 1200, "def": 1300, "spd": 110, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": [],
                "skills": [],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)
    refresh_summary = refresh_account_stat_models(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        refreshed_stats = dict(
            conn.execute(
                """
                SELECT stat_name, stat_value
                FROM account_champion_total_stats
                WHERE champ_id = 'champ-1'
                """
            ).fetchall()
        )

    assert refresh_summary["derived_champions"] == 1
    assert refreshed_stats["hp"] == 32700.0
    assert refreshed_stats["atk"] == 2190.0
    assert refreshed_stats["def"] == 1560.0
    assert refreshed_stats["spd"] == 120.0
    assert refreshed_stats["acc"] == 25.0
    assert refreshed_stats["res"] == 55.0


def test_fixed_set_ignores_accessory_pieces_when_counting_completion(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "High Khatun",
                "rarity": "epic",
                "affinity": "spirit",
                "faction": "Barbarians",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {"hp": 100, "atk": 100, "def": 100, "spd": 100, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": ["gear-1", "gear-2"],
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
                "item_id": "gear-2",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "Attack Speed",
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

    with sqlite3.connect(db_path) as conn:
        total_stats = dict(
            conn.execute(
                """
                SELECT stat_name, stat_value
                FROM account_champion_total_stats
                WHERE champ_id = 'champ-1'
                """
            ).fetchall()
        )
        model = conn.execute(
            """
            SELECT applied_sets_json
            FROM account_champion_stat_models
            WHERE champ_id = 'champ-1'
            """
        ).fetchone()

    assert total_stats["spd"] == 145.0
    applied_sets = json.loads(model[0])
    assert applied_sets == []


def test_variable_set_counts_accessories_and_applies_visible_piece_bonuses(tmp_path: Path) -> None:
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

    with sqlite3.connect(db_path) as conn:
        total_stats = dict(
            conn.execute(
                """
                SELECT stat_name, stat_value
                FROM account_champion_total_stats
                WHERE champ_id = 'champ-1'
                """
            ).fetchall()
        )
        model = conn.execute(
            """
            SELECT source, completeness, unsupported_sets_json, applied_sets_json
            FROM account_champion_stat_models
            WHERE champ_id = 'champ-1'
            """
        ).fetchone()

    assert total_stats["hp"] == 36086.8
    assert total_stats["res"] == 70.0
    assert model[0] == "derived"
    assert model[1] == "derived"
    assert json.loads(model[2]) == []
    applied_sets = json.loads(model[3])
    assert applied_sets == [
        {
            "set_name": "Stone Skin",
            "set_kind": "variable",
            "pieces_required": 1,
            "pieces_equipped": 2,
            "completed_sets": 1,
            "max_pieces": 9,
            "active_bonus_count": 2,
        }
    ]
