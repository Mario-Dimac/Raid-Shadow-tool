from __future__ import annotations

import json
from pathlib import Path

from forge_db import bootstrap_database
from team_optimizer import build_team_optimizer_report, infer_roles_from_texts, list_team_optimizer_targets


def test_team_optimizer_targets_are_exposed() -> None:
    targets = list_team_optimizer_targets()

    assert any(target["key"] == "demon_lord" for target in targets)


def test_infer_roles_from_texts_detects_clan_boss_signals() -> None:
    roles = infer_roles_from_texts(
        [
            "Places a Shield buff and Counterattack on all allies.",
            "Has a 75% chance of placing Decrease ATK.",
            "Removes all debuffs from all allies.",
        ]
    )

    assert "support" in roles
    assert "survival" in roles
    assert "counterattack" in roles
    assert "debuffer" in roles
    assert "decrease_attack" in roles
    assert "cleanse" in roles


def test_team_optimizer_builds_a_sensible_unm_skeleton(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-ninja",
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
                        "description": "Attacks 3 times and places HP Burn.",
                        "effects": [{"type": "hp_burn", "target": "enemy", "duration": 3, "chance": 100}],
                    }
                ],
            },
            {
                "champ_id": "champ-valk",
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
                "base_stats": {"hp": 21000, "atk": 1000, "def": 1500, "spd": 95},
                "total_stats": {"hp": 70000, "atk": 1800, "def": 5200, "spd": 171, "acc": 230, "crit_rate": 100, "crit_dmg": 165, "res": 260},
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
                "champ_id": "champ-stag",
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
                "total_stats": {"hp": 54000, "atk": 2400, "def": 3600, "spd": 219, "acc": 345, "res": 210},
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
                "champ_id": "champ-teodor",
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
                "base_stats": {"hp": 21000, "atk": 1000, "def": 1400, "spd": 100},
                "total_stats": {"hp": 62000, "atk": 1900, "def": 3400, "spd": 214, "acc": 360, "res": 250},
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
                "champ_id": "champ-doompriest",
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
                "base_stats": {"hp": 21000, "atk": 900, "def": 1300, "spd": 100},
                "total_stats": {"hp": 68000, "atk": 1700, "def": 4300, "spd": 198, "res": 320},
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
            {
                "champ_id": "champ-kael",
                "name": "Kael",
                "rarity": "rare",
                "affinity": "magic",
                "faction": "Dark Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 17000, "atk": 1400, "def": 900, "spd": 103},
                "total_stats": {"hp": 38000, "atk": 4600, "def": 2500, "spd": 175, "acc": 220, "crit_rate": 100, "crit_dmg": 205},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A3",
                        "skill_id": "kael_a3",
                        "name": "Disintegrate",
                        "cooldown": 4,
                        "description": "Places Poison debuffs.",
                        "effects": [{"type": "poison", "target": "enemy", "duration": 2, "chance": 100}],
                    }
                ],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=db_path)
    selected_names = {member["champion_name"] for member in report["selected_team"]}

    assert len(report["selected_team"]) == 5
    assert "Ninja" in selected_names
    assert "Valkyrie" in selected_names
    assert "Stag Knight" in selected_names
    assert "Teodor the Savant" in selected_names
    assert report["missing_required_roles"] == []
    ninja = next(item for item in report["selected_team"] if item["champion_name"] == "Ninja")
    assert ninja["stat_reliability"]["source"] == "raw"
    assert ninja["stat_reliability"]["confidence"] == 1.0


def test_team_optimizer_can_infer_roles_for_unknown_champion(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-guardian",
                "name": "Unknown Guardian",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Sacred Order",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": False,
                "role_tags": [],
                "base_stats": {"hp": 22000, "def": 1400, "spd": 95},
                "total_stats": {"hp": 72000, "def": 4800, "spd": 181, "res": 290},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "guardian_a2",
                        "name": "Wall of Oaths",
                        "cooldown": 4,
                        "description": "Places Ally Protect and Shield on all allies.",
                        "effects": [
                            {"type": "ally_protect", "target": "ally", "duration": 2},
                            {"type": "shield", "target": "ally", "value": 12},
                        ],
                    }
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=db_path)
    candidate = next(item for item in report["candidates"] if item["champion_name"] == "Unknown Guardian")

    assert "ally_protect" in candidate["roles"]
    assert "support" in candidate["roles"]
    assert "survival" in candidate["roles"]


def test_team_optimizer_applies_affinity_context(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-force",
                "name": "Force Damage",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Banner Lords",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"atk": 1300, "spd": 100},
                "total_stats": {"atk": 5000, "spd": 185, "crit_rate": 100, "crit_dmg": 230, "acc": 260},
                "equipped_item_ids": [],
                "skills": [{"slot": "A1", "skill_id": "f_a1", "name": "Hit", "cooldown": 0, "description": "Damage.", "effects": [{"type": "damage", "target": "enemy", "value": 1.0}]}],
            },
            {
                "champ_id": "champ-spirit",
                "name": "Spirit Damage",
                "rarity": "epic",
                "affinity": "spirit",
                "faction": "Banner Lords",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"atk": 1300, "spd": 100},
                "total_stats": {"atk": 5000, "spd": 185, "crit_rate": 100, "crit_dmg": 230, "acc": 260},
                "equipped_item_ids": [],
                "skills": [{"slot": "A1", "skill_id": "s_a1", "name": "Hit", "cooldown": 0, "description": "Damage.", "effects": [{"type": "damage", "target": "enemy", "value": 1.0}]}],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="magic", db_path=db_path)
    force_candidate = next(item for item in report["candidates"] if item["champion_name"] == "Force Damage")
    spirit_candidate = next(item for item in report["candidates"] if item["champion_name"] == "Spirit Damage")

    assert force_candidate["affinity_matchup"] == "strong"
    assert spirit_candidate["affinity_matchup"] == "weak"
    assert force_candidate["score"] > spirit_candidate["score"]


def test_team_optimizer_marks_derived_stats_as_untrusted(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-me",
                "name": "Maneater",
                "rarity": "epic",
                "affinity": "void",
                "faction": "Ogryn Tribes",
                "level": 60,
                "rank": 6,
                "awakening_level": 2,
                "empowerment_level": 0,
                "booked": False,
                "role_tags": ["health"],
                "base_stats": {"hp": 123.0, "atk": 76.0, "def": 101.0, "spd": 98.0, "crit_rate": 15.0, "crit_dmg": 50.0, "res": 45.0, "acc": 0.0},
                "total_stats": {"hp": 0, "atk": 0, "def": 0, "spd": 0, "crit_rate": 0, "crit_dmg": 0, "res": 0, "acc": 0},
                "equipped_item_ids": [],
                "relic_ids": ["relic-1"],
                "skills": [
                    {"slot": "A3", "skill_id": "me-a3", "name": "Ancient Blood", "cooldown": 5, "description": "Places Unkillable and Block Debuffs on all allies.", "effects": [{"type": "unkillable", "target": "ally", "duration": 2}]}
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=db_path)
    candidate = next(item for item in report["candidates"] if item["champion_name"] == "Maneater")

    assert candidate["stat_reliability"]["source"] == "derived"
    assert candidate["stat_reliability"]["confidence"] < 1.0
    assert "imported_total_stats" in candidate["stat_reliability"]["missing_sources"]
    assert "relic_stats" in candidate["stat_reliability"]["missing_sources"]
