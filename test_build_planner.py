from __future__ import annotations

import json
from pathlib import Path

from build_planner import build_champion_plan, list_build_profiles
from forge_db import bootstrap_database


def test_build_profiles_are_exposed() -> None:
    profiles = list_build_profiles()

    assert any(profile["key"] == "arena_speed_lead" for profile in profiles)
    assert any(profile["key"] == "arena_nuker" for profile in profiles)


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
    assert any(item["source_kind"] == "inventory" for item in inventory_only["items"])
    assert any(item["substats"] for item in inventory_only["items"])
    assert overall["stats"]["spd"] >= inventory_only["stats"]["spd"]
    assert overall["borrowed_items"] >= 1
    assert any(item["item_id"] == "skull-banner" for item in overall["items"])
