from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import build_planner
from build_planner import build_champion_plan, choose_best_beam_state, effective_beam_width, list_build_profiles
from forge_db import bootstrap_database


def test_build_profiles_are_exposed() -> None:
    profiles = list_build_profiles()

    assert any(profile["key"] == "arena_speed_lead" for profile in profiles)
    assert any(profile["key"] == "arena_nuker" for profile in profiles)


def test_effective_beam_width_expands_for_guardrailed_profiles() -> None:
    support_profile = build_planner.BUILD_PROFILES["support_tank"]
    speed_profile = build_planner.BUILD_PROFILES["arena_speed_lead"]
    scope = {"beam_width": 48}

    assert effective_beam_width(scope, support_profile) == 192
    assert effective_beam_width(scope, speed_profile) == 48


def test_build_plan_can_apply_region_specific_area_bonus(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-arbiter",
                "name": "Arbiter",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "High Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "atk": 1200, "def": 1300, "spd": 110, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {},
                "equipped_item_ids": [],
                "skills": [],
            }
        ],
        "gear": [],
        "account_bonuses": [
            {"bonus_id": "gh_void_acc", "source": "great_hall", "scope": "global", "target": "void", "stat": "acc", "value": 5, "active": True},
            {"bonus_id": "cb_spd", "source": "area_bonus", "scope": "area", "target": "clan_boss", "stat": "spd", "value": 6, "active": True},
        ],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    plain = build_champion_plan("Arbiter", "arena_speed_lead", db_path=db_path)
    clan_boss = build_champion_plan("Arbiter", "arena_speed_lead", area_region="clan_boss", db_path=db_path)

    assert plain["current_build"]["stats"]["spd"] == 110.0
    assert clan_boss["current_build"]["stats"]["spd"] == 116.0
    assert clan_boss["selected_area_region"] == "clan_boss"
    assert "Bonus area: Clan Boss" in clan_boss["current_build"]["notes"]


def test_build_plan_returns_current_and_two_speed_proposals(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-arbiter",
                "name": "Arbiter",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "High Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "atk": 1200, "def": 1300, "spd": 110, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": [
                    "arb-weapon",
                    "arb-helmet",
                    "arb-shield",
                    "arb-gloves",
                    "arb-chest",
                    "arb-boots",
                    "arb-ring",
                    "arb-amulet",
                    "arb-banner",
                ],
                "skills": [],
            },
            {
                "champ_id": "champ-skullcrown",
                "name": "Skullcrown",
                "rarity": "epic",
                "affinity": "magic",
                "faction": "Dark Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 18000, "atk": 1400, "def": 1000, "spd": 100, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": ["skull-banner"],
                "skills": [],
            },
        ],
        "gear": [
            {
                "item_id": "arb-weapon",
                "item_class": "artifact",
                "slot": "weapon",
                "set_name": "Cruel",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "atk", "value": 265},
                "substats": [{"type": "spd", "value": 5, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "arb-helmet",
                "item_class": "artifact",
                "slot": "helmet",
                "set_name": "Cruel",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "hp", "value": 3510},
                "substats": [{"type": "spd", "value": 4, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "arb-shield",
                "item_class": "artifact",
                "slot": "shield",
                "set_name": "Cruel",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "def", "value": 330},
                "substats": [{"type": "spd", "value": 4, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "arb-gloves",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "Feral",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "hp_pct", "value": 60},
                "substats": [{"type": "res", "value": 12, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "arb-chest",
                "item_class": "artifact",
                "slot": "chest",
                "set_name": "Immortal",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "hp_pct", "value": 60},
                "substats": [{"type": "spd", "value": 4, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "arb-boots",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [{"type": "hp_pct", "value": 10, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "arb-ring",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "hp", "value": 2650},
                "substats": [{"type": "spd", "value": 5, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "arb-amulet",
                "item_class": "accessory",
                "slot": "amulet",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "hp", "value": 2650},
                "substats": [{"type": "spd", "value": 6, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "arb-banner",
                "item_class": "accessory",
                "slot": "banner",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "acc", "value": 96},
                "substats": [{"type": "spd", "value": 8, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "inv-gloves-speedset",
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
                "substats": [{"type": "hp", "value": 410, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "skull-banner",
                "item_class": "accessory",
                "slot": "banner",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-skullcrown",
                "locked": True,
                "main_stat": {"type": "acc", "value": 96},
                "substats": [{"type": "spd", "value": 16, "rolls": 3, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    plan = build_champion_plan("Arbiter", profile_key="arena_speed_lead", db_path=db_path)

    assert plan["champion"]["champion_name"] == "Arbiter"
    assert plan["current_build"]["label"] == "Build attuale"
    assert [proposal["key"] for proposal in plan["proposals"]] == ["inventory_only", "overall"]

    current_spd = plan["current_build"]["stats"]["spd"]
    inventory_only = plan["proposals"][0]
    overall = plan["proposals"][1]

    assert inventory_only["stats"]["spd"] > current_spd
    assert any(item["item_id"] == "inv-gloves-speedset" for item in inventory_only["items"])
    assert any(set_row["set_name"] == "Attack Speed" for set_row in inventory_only["applied_sets"])
    assert inventory_only["set_coherence"]["label"] in {"Buona", "Alta"}
    assert inventory_only["set_coherence"]["orphan_fixed_pieces"] == 0
    assert any(item["source_kind"] == "inventory" for item in inventory_only["items"])
    assert any(item["substats"] for item in inventory_only["items"])
    assert overall["stats"]["spd"] >= inventory_only["stats"]["spd"]
    assert overall["borrowed_items"] >= 1
    assert any(item["item_id"] == "skull-banner" for item in overall["items"])


def test_build_notes_warn_when_snapshot_has_missing_slots(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-arbiter",
                "name": "Arbiter",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "High Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "atk": 1200, "def": 1300, "spd": 110, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": ["arb-weapon", "arb-helmet", "arb-shield", "arb-gloves", "arb-chest", "arb-boots", "arb-ring", "arb-amulet"],
                "skills": [],
            }
        ],
        "gear": [
            {"item_id": "arb-weapon", "item_class": "artifact", "slot": "weapon", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-arbiter", "locked": True, "main_stat": {"type": "atk", "value": 265}, "substats": []},
            {"item_id": "arb-helmet", "item_class": "artifact", "slot": "helmet", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-arbiter", "locked": True, "main_stat": {"type": "hp", "value": 3510}, "substats": []},
            {"item_id": "arb-shield", "item_class": "artifact", "slot": "shield", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-arbiter", "locked": True, "main_stat": {"type": "def", "value": 330}, "substats": []},
            {"item_id": "arb-gloves", "item_class": "artifact", "slot": "gloves", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-arbiter", "locked": True, "main_stat": {"type": "hp_pct", "value": 60}, "substats": []},
            {"item_id": "arb-chest", "item_class": "artifact", "slot": "chest", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-arbiter", "locked": True, "main_stat": {"type": "hp_pct", "value": 60}, "substats": []},
            {"item_id": "arb-boots", "item_class": "artifact", "slot": "boots", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-arbiter", "locked": True, "main_stat": {"type": "spd", "value": 45}, "substats": []},
            {"item_id": "arb-ring", "item_class": "accessory", "slot": "ring", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-arbiter", "locked": True, "main_stat": {"type": "hp", "value": 2650}, "substats": []},
            {"item_id": "arb-amulet", "item_class": "accessory", "slot": "amulet", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-arbiter", "locked": True, "main_stat": {"type": "hp", "value": 2650}, "substats": []},
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    plan = build_champion_plan("Arbiter", profile_key="arena_speed_lead", db_path=db_path)

    assert plan["current_build"]["missing_slots"] == ["banner"]
    assert plan["current_build"]["notes"][0].startswith("Snapshot incompleto:")


def test_current_build_warns_when_relics_are_present_but_stats_are_derived(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-arbiter",
                "name": "Arbiter",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "High Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "atk": 1200, "def": 1300, "spd": 110, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": ["arb-boots"],
                "relic_ids": ["relic-203"],
                "skills": [],
            }
        ],
        "gear": [
            {
                "item_id": "arb-boots",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 6,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-arbiter",
                "locked": True,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [{"type": "spd", "value": 12, "rolls": 0, "glyph_value": 0}],
            }
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    plan = build_champion_plan("Arbiter", profile_key="arena_speed_lead", db_path=db_path)

    assert any("Relic presenti" in note for note in plan["current_build"]["notes"])


def test_current_build_applies_static_masteries_and_lore_of_steel(tmp_path: Path) -> None:
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
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "atk": 1200, "def": 1300, "spd": 100, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": ["speed-w", "speed-h", "acc-s", "acc-g"],
                "masteries": [
                    {"mastery_id": "500313", "name": "Pinpoint Accuracy", "active": True},
                    {"mastery_id": "500343", "name": "Lore of Steel", "active": True},
                    {"mastery_id": "500364", "name": "Eagle-Eye", "active": True},
                ],
                "skills": [],
            }
        ],
        "gear": [
            {"item_id": "speed-w", "item_class": "artifact", "slot": "weapon", "set_name": "Attack Speed", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "atk", "value": 265}, "substats": []},
            {"item_id": "speed-h", "item_class": "artifact", "slot": "helmet", "set_name": "Attack Speed", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "hp", "value": 3510}, "substats": []},
            {"item_id": "acc-s", "item_class": "artifact", "slot": "shield", "set_name": "Accuracy", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "def", "value": 330}, "substats": []},
            {"item_id": "acc-g", "item_class": "artifact", "slot": "gloves", "set_name": "Accuracy", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "hp_pct", "value": 60}, "substats": []},
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    plan = build_champion_plan("Arbiter", profile_key="arena_speed_lead", db_path=db_path)

    assert plan["current_build"]["stats"]["spd"] == 113.8
    assert plan["current_build"]["stats"]["acc"] == 106.0


def test_current_build_applies_awakening_and_empowerment_bonuses(tmp_path: Path) -> None:
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
                "role_tags": ["support"],
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

    plan = build_champion_plan("Arbiter", profile_key="arena_speed_lead", db_path=db_path)
    stats = plan["current_build"]["stats"]

    assert stats["hp"] == 32700.0
    assert stats["atk"] == 2190.0
    assert stats["def"] == 1560.0
    assert stats["spd"] == 120.0
    assert stats["acc"] == 25.0
    assert stats["res"] == 55.0


def test_build_planner_prefers_completing_speed_set_over_single_faster_off_set_piece(tmp_path: Path) -> None:
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
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "atk": 1200, "def": 1300, "spd": 110, "crit_rate": 15, "crit_dmg": 50, "acc": 0, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": [
                    "weapon-1",
                    "helmet-1",
                    "shield-1",
                    "gloves-speed",
                    "chest-off",
                    "boots-1",
                    "ring-1",
                    "amulet-1",
                    "banner-1",
                ],
                "skills": [],
            }
        ],
        "gear": [
            {
                "item_id": "weapon-1",
                "item_class": "artifact",
                "slot": "weapon",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "atk", "value": 265},
                "substats": [],
            },
            {
                "item_id": "helmet-1",
                "item_class": "artifact",
                "slot": "helmet",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "hp", "value": 3510},
                "substats": [],
            },
            {
                "item_id": "shield-1",
                "item_class": "artifact",
                "slot": "shield",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "def", "value": 330},
                "substats": [],
            },
            {
                "item_id": "gloves-speed",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "hp_pct", "value": 60},
                "substats": [],
            },
            {
                "item_id": "chest-off",
                "item_class": "artifact",
                "slot": "chest",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "hp_pct", "value": 60},
                "substats": [{"type": "spd", "value": 6, "rolls": 1, "glyph_value": 0}],
            },
            {
                "item_id": "chest-speed",
                "item_class": "artifact",
                "slot": "chest",
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
                "item_id": "boots-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [],
            },
            {
                "item_id": "ring-1",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "hp", "value": 2650},
                "substats": [],
            },
            {
                "item_id": "amulet-1",
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
                "locked": True,
                "main_stat": {"type": "hp", "value": 2650},
                "substats": [],
            },
            {
                "item_id": "banner-1",
                "item_class": "accessory",
                "slot": "banner",
                "set_name": "",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "acc", "value": 96},
                "substats": [],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    plan = build_champion_plan("Arbiter", profile_key="arena_speed_lead", db_path=db_path)
    inventory_only = plan["proposals"][0]

    chest_item = next(item for item in inventory_only["items"] if item["slot"] == "chest")

    assert chest_item["item_id"] == "chest-speed"
    assert any(row["set_name"] == "Attack Speed" and row["completed_sets"] == 1 for row in inventory_only["applied_sets"])
    assert inventory_only["stats"]["spd"] > plan["current_build"]["stats"]["spd"]


def test_support_tank_guardrail_falls_back_from_fragile_orphan_build(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Pythion",
                "rarity": "legendary",
                "affinity": "force",
                "faction": "Lizardmen",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 22000, "atk": 1200, "def": 1400, "spd": 100, "crit_rate": 15, "crit_dmg": 50, "acc": 30, "res": 30},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "acc": 0, "res": 0},
                "equipped_item_ids": ["w", "h", "s", "g", "c-good", "b", "r", "a", "bn"],
                "skills": [],
            }
        ],
        "gear": [
            {"item_id": "w", "item_class": "artifact", "slot": "weapon", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "atk", "value": 265}, "substats": []},
            {"item_id": "h", "item_class": "artifact", "slot": "helmet", "set_name": "HP And Defence", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "hp", "value": 3510}, "substats": [{"type": "spd", "value": 5, "rolls": 0, "glyph_value": 0}]},
            {"item_id": "s", "item_class": "artifact", "slot": "shield", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "def", "value": 330}, "substats": []},
            {"item_id": "g", "item_class": "artifact", "slot": "gloves", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "hp_pct", "value": 0.6}, "substats": []},
            {"item_id": "c-good", "item_class": "artifact", "slot": "chest", "set_name": "HP And Defence", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "hp_pct", "value": 0.6}, "substats": [{"type": "spd", "value": 6, "rolls": 0, "glyph_value": 0}]},
            {"item_id": "c-bad", "item_class": "artifact", "slot": "chest", "set_name": "Life Drain", "rarity": "mythical", "rank": 5, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "", "locked": False, "main_stat": {"type": "def_pct", "value": 0.5}, "substats": [{"type": "spd", "value": 27, "rolls": 4, "glyph_value": 0}]},
            {"item_id": "b", "item_class": "artifact", "slot": "boots", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "spd", "value": 45}, "substats": []},
            {"item_id": "r", "item_class": "accessory", "slot": "ring", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "hp", "value": 2650}, "substats": []},
            {"item_id": "a", "item_class": "accessory", "slot": "amulet", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "hp", "value": 2650}, "substats": []},
            {"item_id": "bn", "item_class": "accessory", "slot": "banner", "set_name": "", "rarity": "legendary", "rank": 6, "level": 16, "ascension_level": 0, "required_faction": "", "required_faction_id": 0, "equipped_by": "champ-1", "locked": True, "main_stat": {"type": "res", "value": 96}, "substats": []},
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        all_items = build_planner.load_all_gear(conn)
    current_items = [item for item in all_items if item["equipped_by"] == "champ-1"]
    forced_items = [item for item in current_items if item["slot"] != "chest"] + [next(item for item in all_items if item["item_id"] == "c-bad")]

    monkeypatch.setattr(build_planner, "solve_build_with_beam_search", lambda *args, **kwargs: forced_items)

    plan = build_champion_plan("Pythion", profile_key="support_tank", db_path=db_path)
    inventory_only = plan["proposals"][0]
    chest_item = next(item for item in inventory_only["items"] if item["slot"] == "chest")

    assert chest_item["item_id"] == "c-good"
    assert inventory_only["notes"][0].startswith("Guardrail tank:")
    assert inventory_only["set_coherence"]["label"] in {"Buona", "Alta"}


def test_choose_best_beam_state_prefers_fewer_fixed_orphans_for_support_tank() -> None:
    set_rules = {
        "Accuracy And Speed": {"set_kind": "fixed", "pieces_required": 2},
        "Shield And Speed": {"set_kind": "fixed", "pieces_required": 2},
        "Life Drain": {"set_kind": "fixed", "pieces_required": 4},
    }
    profile = build_planner.BUILD_PROFILES["support_tank"]
    high_score_orphan = {
        "items": [
            {"item_id": "a1", "item_class": "artifact", "set_name": "Accuracy And Speed"},
            {"item_id": "a2", "item_class": "artifact", "set_name": "Accuracy And Speed"},
            {"item_id": "s1", "item_class": "artifact", "set_name": "Shield And Speed"},
            {"item_id": "s2", "item_class": "artifact", "set_name": "Shield And Speed"},
            {"item_id": "l1", "item_class": "artifact", "set_name": "Life Drain"},
        ],
        "score": 500.0,
        "signature": "high",
        "totals": {},
    }
    lower_score_clean = {
        "items": [
            {"item_id": "a1", "item_class": "artifact", "set_name": "Accuracy And Speed"},
            {"item_id": "a2", "item_class": "artifact", "set_name": "Accuracy And Speed"},
            {"item_id": "s1", "item_class": "artifact", "set_name": "Shield And Speed"},
            {"item_id": "s2", "item_class": "artifact", "set_name": "Shield And Speed"},
        ],
        "score": 450.0,
        "signature": "clean",
        "totals": {},
    }

    selected = choose_best_beam_state(
        [high_score_orphan, lower_score_clean],
        set_rules=set_rules,
        profile=profile,
        reference_totals=None,
    )

    assert selected["signature"] == "clean"
