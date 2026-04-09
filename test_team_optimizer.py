from __future__ import annotations

import json
from pathlib import Path

from forge_db import bootstrap_database, record_run_history
from team_optimizer import (
    build_candidate_clan_boss_member_row,
    build_team_optimizer_report,
    infer_capabilities_from_texts,
    infer_roles_from_texts,
    list_team_optimizer_targets,
)


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


def test_infer_capabilities_from_roles_handles_normalized_role_names() -> None:
    capabilities = infer_capabilities_from_texts([], roles=["decrease_attack", "ally_protect", "revive_on_death", "burner"])

    assert "decrease_attack" in capabilities
    assert "ally_protect" in capabilities
    assert "revive_on_death" in capabilities
    assert "hp_burn" in capabilities


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


def test_team_optimizer_surfaces_skill_windows_for_rotation_reasoning(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
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
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=db_path)
    candidate = next(item for item in report["candidates"] if item["champion_name"] == "Stag Knight")

    assert candidate["skills"][0]["slot"] == "A2"
    assert candidate["skill_windows"]["decrease_attack"]["cooldown"] == 4
    assert candidate["skill_windows"]["decrease_attack"]["quality"] > 0.6
    assert candidate["skill_windows"]["decrease_defense"]["duration"] == 2


def test_build_candidate_clan_boss_member_row_applies_manual_opener_override() -> None:
    candidate = {
        "champ_id": "champ-valk",
        "champion_name": "Valkyrie",
        "booked": True,
        "stats": {"spd": 171},
        "skills": [
            {
                "slot": "A2",
                "skill_name": "Stand Firm",
                "cooldown": 4,
                "booked_cooldown": 3,
                "effects": [{"effect_type": "shield", "target": "ally", "duration": 2, "chance": 100}],
            },
            {
                "slot": "A3",
                "skill_name": "Counter",
                "cooldown": 4,
                "booked_cooldown": 4,
                "effects": [{"effect_type": "counterattack", "target": "ally", "duration": 2, "chance": 100}],
            },
        ],
        "skill_windows": {},
    }

    member_row = build_candidate_clan_boss_member_row(candidate, 1, opener_slot="A2")
    a2 = next(skill for skill in member_row["skills"] if skill["slot"] == "A2")
    a3 = next(skill for skill in member_row["skills"] if skill["slot"] == "A3")

    assert a2["use_as_opener"] is True
    assert a2["priority"] >= 500
    assert a3["use_as_opener"] is False
    assert "opener A2" in member_row["notes"]


def test_team_optimizer_penalizes_maneater_without_real_tune_partner(tmp_path: Path) -> None:
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
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["health"],
                "base_stats": {"hp": 20000, "def": 1200, "spd": 98},
                "total_stats": {"hp": 65000, "def": 3600, "spd": 248, "res": 240},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A3",
                        "skill_id": "me-a3",
                        "name": "Ancient Blood",
                        "cooldown": 5,
                        "description": "Places Unkillable and Block Debuffs on all allies.",
                        "effects": [{"type": "unkillable", "target": "ally", "duration": 2}],
                    }
                ],
            },
            {
                "champ_id": "champ-brogni",
                "name": "Underpriest Brogni",
                "rarity": "legendary",
                "affinity": "magic",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "def": 1400, "spd": 96},
                "total_stats": {"hp": 72000, "def": 4100, "spd": 196, "res": 260, "acc": 265},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A3",
                        "skill_id": "brogni-a3",
                        "name": "Resilient Growth",
                        "cooldown": 3,
                        "description": "Places Shield and Block Debuffs on all allies.",
                        "effects": [
                            {"type": "shield", "target": "ally", "duration": 2},
                            {"type": "block_debuffs", "target": "ally", "duration": 2},
                        ],
                    }
                ],
            },
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
                "base_stats": {"atk": 1500, "spd": 98},
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
                "champ_id": "champ-michi",
                "name": "Michinaki",
                "rarity": "legendary",
                "affinity": "magic",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"atk": 1400, "def": 1300, "spd": 97},
                "total_stats": {"hp": 52000, "atk": 4700, "def": 3600, "spd": 192, "acc": 290, "crit_rate": 100, "crit_dmg": 210},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "michi-a2",
                        "name": "Flame-Touched",
                        "cooldown": 4,
                        "description": "Places HP Burn and Decrease DEF.",
                        "effects": [
                            {"type": "hp_burn", "target": "enemy", "duration": 2},
                            {"type": "decrease_def", "target": "enemy", "duration": 2},
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
                "champ_id": "champ-doom",
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
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="spirit", db_path=db_path)
    selected_names = {member["champion_name"] for member in report["selected_team"]}

    assert "Maneater" not in selected_names
    assert "Stag Knight" in selected_names
    assert "Valkyrie" in selected_names
    assert "Underpriest Brogni" in selected_names
    assert report["team_fit"]["has_maneater_tune"] is False


def test_team_optimizer_detects_ready_maneater_ninja_tune(tmp_path: Path) -> None:
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
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["health"],
                "base_stats": {"hp": 20000, "def": 1200, "spd": 98},
                "total_stats": {"hp": 65000, "def": 3600, "spd": 240, "res": 240},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A3",
                        "skill_id": "me-a3",
                        "name": "Ancient Blood",
                        "cooldown": 7,
                        "booked_cooldown": 5,
                        "description": "Places Unkillable and Block Debuffs on all allies.",
                        "effects": [{"type": "unkillable", "target": "ally", "duration": 2}],
                    }
                ],
            },
            {
                "champ_id": "champ-pk",
                "name": "Pain Keeper",
                "rarity": "rare",
                "affinity": "void",
                "faction": "Dark Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 18000, "def": 1200, "spd": 102},
                "total_stats": {"hp": 48000, "def": 2600, "spd": 220, "res": 190},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A3",
                        "skill_id": "pk-a3",
                        "name": "Combat Tactics",
                        "cooldown": 4,
                        "booked_cooldown": 3,
                        "description": "Reduces the cooldowns of all ally skills by 1 turn.",
                        "effects": [{"type": "decrease_cooldown", "target": "ally"}],
                    }
                ],
            },
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
                "base_stats": {"atk": 1500, "spd": 98},
                "total_stats": {"hp": 42000, "atk": 5400, "def": 2800, "spd": 162, "acc": 265, "crit_rate": 100, "crit_dmg": 220},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A3",
                        "skill_id": "ninja_a3",
                        "name": "Cyan Slash",
                        "cooldown": 4,
                        "booked_cooldown": 3,
                        "description": "Attacks 1 enemy and activates HP Burn debuffs.",
                        "effects": [{"type": "hp_burn", "target": "enemy", "duration": 3, "chance": 100}],
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
                "total_stats": {"hp": 54000, "atk": 2400, "def": 3600, "spd": 176, "acc": 345, "res": 210},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "stag_a2",
                        "name": "Huntmaster",
                        "cooldown": 4,
                        "booked_cooldown": 4,
                        "description": "Places Decrease ATK and Decrease DEF.",
                        "effects": [
                            {"type": "decrease_attack", "target": "enemy", "duration": 2, "chance": 100},
                            {"type": "decrease_def", "target": "enemy", "duration": 2, "chance": 100},
                        ],
                    }
                ],
            },
            {
                "champ_id": "champ-coffin",
                "name": "Coffin Smasher",
                "rarity": "rare",
                "affinity": "magic",
                "faction": "Undead Hordes",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 18000, "atk": 1000, "def": 1200, "spd": 96},
                "total_stats": {"hp": 50000, "atk": 2200, "def": 3200, "spd": 112, "acc": 280, "res": 180},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "coffin-a1",
                        "name": "Smash",
                        "cooldown": 0,
                        "description": "Has a chance to place Decrease ATK.",
                        "effects": [{"type": "decrease_attack", "target": "enemy", "duration": 2, "chance": 100}],
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

    assert "Maneater" in selected_names
    assert "Pain Keeper" in selected_names
    assert report["team_fit"]["has_maneater_tune"] is True
    assert report["team_fit"]["maneater_tune_label"] == "Budget Unkillable Ninja"
    assert any("ME 240-241" in item for item in report["team_fit"]["build_requirements"])


def test_team_optimizer_warns_when_team_lacks_sustain_defense_and_key_debuffs(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": f"champ-dps-{index}",
                "name": f"DPS {index}",
                "rarity": "epic",
                "affinity": "magic",
                "faction": "Banner Lords",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"atk": 1300, "spd": 100},
                "total_stats": {"hp": 36000, "atk": 5100, "def": 2400, "spd": 180, "acc": 90, "crit_rate": 100, "crit_dmg": 220},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": f"dps-{index}-a1",
                        "name": "Hit",
                        "cooldown": 0,
                        "description": "Attacks 1 enemy.",
                        "effects": [{"type": "damage", "target": "enemy", "value": 1.0}],
                    }
                ],
            }
            for index in range(1, 6)
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=db_path)
    warnings_text = " | ".join(report["warnings"])

    assert "cure o sustain affidabile" in warnings_text
    assert "strati difensivi" in warnings_text
    assert "Decrease ATK" in warnings_text
    assert "Decrease DEF o Weaken" in warnings_text


def test_team_optimizer_warns_when_shields_are_stacked_without_true_sustain(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-brogni-lite",
                "name": "Shield One",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Sacred Order",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "def": 1300, "spd": 100},
                "total_stats": {"hp": 76000, "def": 4100, "spd": 214, "res": 240},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A3",
                        "skill_id": "shield-one-a3",
                        "name": "Team Shield",
                        "cooldown": 3,
                        "description": "Places a Shield buff on all allies.",
                        "effects": [{"type": "shield", "target": "ally", "duration": 2, "chance": 100}],
                    }
                ],
            },
            {
                "champ_id": "champ-valk-lite",
                "name": "Shield Two",
                "rarity": "legendary",
                "affinity": "spirit",
                "faction": "Barbarians",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["defense", "support"],
                "base_stats": {"hp": 20000, "def": 1500, "spd": 95},
                "total_stats": {"hp": 72000, "def": 4700, "spd": 201, "res": 210},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A2",
                        "skill_id": "shield-two-a2",
                        "name": "Counter Shield",
                        "cooldown": 3,
                        "description": "Places Shield and Counterattack on all allies.",
                        "effects": [
                            {"type": "shield", "target": "ally", "duration": 2, "chance": 100},
                            {"type": "counterattack", "target": "ally", "duration": 2, "chance": 100},
                        ],
                    }
                ],
            },
            *[
                {
                    "champ_id": f"champ-dps-lite-{index}",
                    "name": f"DPS Lite {index}",
                    "rarity": "epic",
                    "affinity": "magic",
                    "faction": "Banner Lords",
                    "level": 60,
                    "rank": 6,
                    "awakening_level": 0,
                    "empowerment_level": 0,
                    "booked": True,
                    "role_tags": ["attack"],
                    "base_stats": {"atk": 1300, "spd": 100},
                    "total_stats": {"hp": 42000, "atk": 5100, "def": 2500, "spd": 182, "acc": 140, "crit_rate": 100, "crit_dmg": 215},
                    "equipped_item_ids": [],
                    "skills": [
                        {
                            "slot": "A1",
                            "skill_id": f"dps-lite-{index}-a1",
                            "name": "Hit",
                            "cooldown": 0,
                            "description": "Attacks 1 enemy.",
                            "effects": [{"type": "damage", "target": "enemy", "value": 1.0}],
                        }
                    ],
                }
                for index in range(1, 4)
            ],
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=db_path)
    warnings_text = " | ".join(report["warnings"])

    assert "Sustain reale assente" in warnings_text
    assert "Scudi sovrapposti" in warnings_text


def test_team_optimizer_prefers_historically_proven_unm_shell(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-rakka",
                "name": "Rakka Viletide",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Sacred Order",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 21000, "atk": 1100, "def": 1400, "spd": 100},
                "total_stats": {"hp": 77582, "atk": 2465, "def": 2320, "spd": 223, "acc": 233, "res": 105, "crit_rate": 70, "crit_dmg": 93},
                "equipped_item_ids": [],
                "skills": [{"slot": "A3", "skill_id": "rakka-a3", "name": "Support", "cooldown": 4, "description": "Places defensive support.", "effects": [{"type": "shield", "target": "ally", "duration": 2}]}],
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
                "total_stats": {"hp": 92375, "atk": 2092, "def": 3105, "spd": 207, "acc": 56, "res": 115, "crit_rate": 100, "crit_dmg": 120},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "valk-a2", "name": "Stand Firm", "cooldown": 3, "description": "Places Shield and Counterattack on all allies.", "effects": [{"type": "shield", "target": "ally", "duration": 2}, {"type": "counterattack", "target": "ally", "duration": 2}]}],
            },
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
                "total_stats": {"hp": 57762, "atk": 4470, "def": 2897, "spd": 188, "acc": 78, "res": 174, "crit_rate": 48, "crit_dmg": 181},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "ninja-a2", "name": "Burn", "cooldown": 3, "description": "Places HP Burn.", "effects": [{"type": "hp_burn", "target": "enemy", "duration": 3, "chance": 100}]}],
            },
            {
                "champ_id": "champ-jintoro",
                "name": "Jintoro",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 17000, "atk": 1500, "def": 1000, "spd": 98},
                "total_stats": {"hp": 57615, "atk": 4136, "def": 2152, "spd": 210, "acc": 168, "res": 235, "crit_rate": 97, "crit_dmg": 204},
                "equipped_item_ids": [],
                "skills": [{"slot": "A3", "skill_id": "jintoro-a3", "name": "Damage", "cooldown": 4, "description": "Heavy single target damage.", "effects": [{"type": "damage", "target": "enemy", "value": 2.0}]}],
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
                "total_stats": {"hp": 87018, "atk": 1929, "def": 1831, "spd": 186, "acc": 332, "res": 144, "crit_rate": 20, "crit_dmg": 166},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "stag-a2", "name": "Huntmaster", "cooldown": 4, "description": "Places Decrease ATK and Decrease DEF.", "effects": [{"type": "decrease_attack", "target": "enemy", "duration": 2, "chance": 100}, {"type": "decrease_def", "target": "enemy", "duration": 2, "chance": 100}]}],
            },
            {
                "champ_id": "champ-me",
                "name": "Maneater",
                "rarity": "epic",
                "affinity": "void",
                "faction": "Ogryn Tribes",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["health"],
                "base_stats": {"hp": 20000, "def": 1200, "spd": 98},
                "total_stats": {"hp": 98000, "def": 1583, "spd": 245, "acc": 166, "res": 124},
                "equipped_item_ids": [],
                "skills": [{"slot": "A3", "skill_id": "me-a3", "name": "Ancient Blood", "cooldown": 5, "description": "Places Unkillable and Block Debuffs on all allies.", "effects": [{"type": "unkillable", "target": "ally", "duration": 2}]}],
            },
            {
                "champ_id": "champ-pk",
                "name": "Pain Keeper",
                "rarity": "epic",
                "affinity": "void",
                "faction": "Dark Elves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 18000, "def": 1100, "spd": 102},
                "total_stats": {"hp": 73710, "def": 1401, "spd": 234, "acc": 288, "res": 108, "crit_rate": 42, "crit_dmg": 217},
                "equipped_item_ids": [],
                "skills": [{"slot": "A4", "skill_id": "pk-a4", "name": "Reset", "cooldown": 4, "description": "Decreases ally skill cooldowns.", "effects": [{"type": "decrease_cooldown", "target": "ally"}]}],
            },
            {
                "champ_id": "champ-venus",
                "name": "Venus",
                "rarity": "legendary",
                "affinity": "magic",
                "faction": "Sacred Order",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack", "support"],
                "base_stats": {"hp": 18000, "atk": 1500, "def": 1100, "spd": 100},
                "total_stats": {"hp": 69014, "atk": 2291, "def": 1491, "spd": 261, "acc": 436, "res": 66, "crit_rate": 36, "crit_dmg": 101},
                "equipped_item_ids": [],
                "skills": [{"slot": "A1", "skill_id": "venus-a1", "name": "Poison", "cooldown": 0, "description": "Places Poison debuffs.", "effects": [{"type": "poison", "target": "enemy", "duration": 2, "chance": 100}]}],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    proven_team = ["Rakka Viletide", "Valkyrie", "Ninja", "Jintoro", "Stag Knight"]
    for index, total_damage in enumerate((45_621_541.0, 45_205_413.0, 43_522_952.0), start=1):
        record_run_history(
            {
                "source": "test",
                "battle_id": f"battle-proven-{index}",
                "encounter_key": "demon_lord_ultra_nightmare",
                "encounter_name": "Demon Lord Ultra-Nightmare",
                "encounter_family": "demon_lord",
                "difficulty": "ultra_nightmare",
                "boss_affinity": "void",
                "success": 1,
                "elapsed_seconds": 500.0,
                "total_damage": total_damage,
                "members": [
                    {
                        "champion_name": champion_name,
                        "stats": {"spd": 200 + position, "acc": 250 + position},
                    }
                    for position, champion_name in enumerate(proven_team, start=1)
                ],
            },
            db_path=db_path,
        )

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=db_path)
    selected_names = {member["champion_name"] for member in report["selected_team"]}

    assert selected_names == set(proven_team)
    assert report["historical_team_evidence"]["run_count"] == 3
    assert report["historical_team_evidence"]["avg_total_damage"] > 44_000_000
    assert any("Storico forte" in note for note in report["notes"])


def test_team_optimizer_distinguishes_stable_from_push_objective(tmp_path: Path) -> None:
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
                "total_stats": {"hp": 42000, "atk": 5400, "def": 2800, "spd": 191, "acc": 265, "crit_rate": 100, "crit_dmg": 220},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "ninja_a2", "name": "Hailburn", "cooldown": 3, "description": "Attacks 3 times and places HP Burn.", "effects": [{"type": "hp_burn", "target": "enemy", "duration": 3, "chance": 100}]}],
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
                "total_stats": {"hp": 70000, "atk": 1800, "def": 5200, "spd": 193, "acc": 230, "crit_rate": 100, "crit_dmg": 165, "res": 260},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "valk_a2", "name": "Stand Firm", "cooldown": 3, "description": "Places Shield and Counterattack on all allies.", "effects": [{"type": "shield", "target": "ally", "value": 10}, {"type": "counterattack", "target": "ally", "duration": 2}]}],
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
                "total_stats": {"hp": 54000, "atk": 2400, "def": 3600, "spd": 201, "acc": 345, "res": 210},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "stag_a2", "name": "Huntmaster", "cooldown": 4, "description": "Places Decrease ATK, Decrease DEF and Weaken.", "effects": [{"type": "decrease_attack", "target": "enemy", "duration": 2, "chance": 100}, {"type": "decrease_def", "target": "enemy", "duration": 2, "chance": 100}, {"type": "weaken", "target": "enemy", "duration": 2, "chance": 100}]}],
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
                "total_stats": {"hp": 62000, "atk": 1900, "def": 3400, "spd": 198, "acc": 360, "res": 250},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "teodor_a2", "name": "Thralls of Misery", "cooldown": 4, "description": "Places Poison debuffs and heals this Champion.", "effects": [{"type": "poison", "target": "enemy", "duration": 2, "chance": 100}, {"type": "heal", "target": "self", "value": 10}]}],
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
                "total_stats": {"hp": 68000, "atk": 1700, "def": 4300, "spd": 196, "res": 320},
                "equipped_item_ids": [],
                "skills": [{"slot": "P1", "skill_id": "doom_p1", "name": "Bolster", "cooldown": 0, "description": "Removes a random debuff and heals all allies.", "effects": [{"type": "remove_debuff", "target": "ally"}, {"type": "heal", "target": "ally", "value": 7.5}]}],
            },
            {
                "champ_id": "champ-jintoro",
                "name": "Jintoro",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 17000, "atk": 1600, "def": 1000, "spd": 99},
                "total_stats": {"hp": 39000, "atk": 6100, "def": 2900, "spd": 194, "acc": 255, "crit_rate": 100, "crit_dmg": 260},
                "equipped_item_ids": [],
                "skills": [{"slot": "A3", "skill_id": "jintoro_a3", "name": "Flurry", "cooldown": 4, "description": "Attacks an enemy and deals heavy damage.", "effects": [{"type": "damage", "target": "enemy", "value": 3.0}]}],
            },
            {
                "champ_id": "champ-venus",
                "name": "Venus",
                "rarity": "legendary",
                "affinity": "magic",
                "faction": "Sacred Order",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack", "support"],
                "base_stats": {"hp": 18000, "atk": 1500, "def": 1100, "spd": 100},
                "total_stats": {"hp": 50000, "atk": 4200, "def": 2600, "spd": 202, "acc": 370, "res": 170, "crit_rate": 100, "crit_dmg": 210},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "venus_a2", "name": "Poison Cloud", "cooldown": 4, "description": "Places Poison, Decrease DEF and Weaken debuffs.", "effects": [{"type": "poison", "target": "enemy", "duration": 2, "chance": 100}, {"type": "decrease_def", "target": "enemy", "duration": 2, "chance": 100}, {"type": "weaken", "target": "enemy", "duration": 2, "chance": 100}]}],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    stable_team = ["Doompriest", "Valkyrie", "Ninja", "Stag Knight", "Teodor the Savant"]
    push_team = ["Valkyrie", "Ninja", "Jintoro", "Stag Knight", "Venus"]

    for index, total_damage in enumerate((41_800_000.0, 42_400_000.0, 43_100_000.0, 43_500_000.0, 44_000_000.0, 44_300_000.0), start=1):
        record_run_history(
            {
                "source": "test",
                "battle_id": f"battle-stable-{index}",
                "encounter_key": "demon_lord_ultra_nightmare",
                "encounter_name": "Demon Lord Ultra-Nightmare",
                "encounter_family": "demon_lord",
                "difficulty": "ultra_nightmare",
                "boss_affinity": "void",
                "success": 1,
                "elapsed_seconds": 500.0,
                "total_damage": total_damage,
                "members": [{"champion_name": champion_name, "stats": {"spd": 200 + position, "acc": 250 + position}} for position, champion_name in enumerate(stable_team, start=1)],
            },
            db_path=db_path,
        )
    for index, total_damage in enumerate((68_200_000.0, 72_300_000.0), start=1):
        record_run_history(
            {
                "source": "test",
                "battle_id": f"battle-push-{index}",
                "encounter_key": "demon_lord_ultra_nightmare",
                "encounter_name": "Demon Lord Ultra-Nightmare",
                "encounter_family": "demon_lord",
                "difficulty": "ultra_nightmare",
                "boss_affinity": "void",
                "success": 1,
                "elapsed_seconds": 500.0,
                "total_damage": total_damage,
                "members": [{"champion_name": champion_name, "stats": {"spd": 205 + position, "acc": 255 + position}} for position, champion_name in enumerate(push_team, start=1)],
            },
            db_path=db_path,
        )

    stable_report = build_team_optimizer_report(
        boss_key="demon_lord",
        level_key="ultra_nightmare",
        affinity="void",
        recommendation_source="optimizer",
        db_path=db_path,
    )
    push_report = build_team_optimizer_report(
        boss_key="demon_lord",
        level_key="ultra_nightmare",
        affinity="void",
        recommendation_source="optimizer_push",
        db_path=db_path,
    )

    assert {member["champion_name"] for member in stable_report["selected_team"]} == set(stable_team)
    assert {member["champion_name"] for member in push_report["selected_team"]} == set(push_team)
    assert stable_report["target"]["objective_key"] == "stable"
    assert push_report["target"]["objective_key"] == "push_70m"
    assert push_report["target"]["target_damage"] == 70_000_000.0
    assert "Push 70M" in push_report["target"]["recommendation_label"]


def test_team_optimizer_excludes_weak_affinity_for_non_void_clan_boss(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-weak-dps",
                "name": "Force Nuker",
                "rarity": "legendary",
                "affinity": "force",
                "faction": "Banner Lords",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"atk": 1400, "spd": 100},
                "total_stats": {"hp": 42000, "atk": 6200, "def": 2600, "spd": 210, "acc": 260, "crit_rate": 100, "crit_dmg": 280},
                "equipped_item_ids": [],
                "skills": [{"slot": "A1", "skill_id": "weak_a1", "name": "Hit", "cooldown": 0, "description": "Damage.", "effects": [{"type": "damage", "target": "enemy", "value": 1.0}]}],
            },
            {
                "champ_id": "champ-strong-dps",
                "name": "Magic Nuker",
                "rarity": "legendary",
                "affinity": "magic",
                "faction": "Banner Lords",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"atk": 1400, "spd": 100},
                "total_stats": {"hp": 40500, "atk": 5900, "def": 2550, "spd": 205, "acc": 255, "crit_rate": 100, "crit_dmg": 265},
                "equipped_item_ids": [],
                "skills": [{"slot": "A1", "skill_id": "strong_a1", "name": "Hit", "cooldown": 0, "description": "Damage and burn.", "effects": [{"type": "hp_burn", "target": "enemy", "duration": 2, "chance": 100}]}],
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
                "total_stats": {"hp": 54000, "atk": 2400, "def": 3600, "spd": 210, "acc": 345, "res": 210},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "stag_a2", "name": "Huntmaster", "cooldown": 4, "description": "Places Decrease ATK and Decrease DEF.", "effects": [{"type": "decrease_attack", "target": "enemy", "duration": 2, "chance": 100}, {"type": "decrease_def", "target": "enemy", "duration": 2, "chance": 100}]}],
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
                "total_stats": {"hp": 70000, "atk": 1800, "def": 5200, "spd": 200, "acc": 230, "crit_rate": 100, "crit_dmg": 165, "res": 260},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "valk_a2", "name": "Stand Firm", "cooldown": 3, "description": "Places Shield and Counterattack on all allies.", "effects": [{"type": "shield", "target": "ally", "value": 10}, {"type": "counterattack", "target": "ally", "duration": 2}]}],
            },
            {
                "champ_id": "champ-doom",
                "name": "Doompriest",
                "rarity": "epic",
                "affinity": "void",
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
                "skills": [{"slot": "P1", "skill_id": "doom_p1", "name": "Bolster", "cooldown": 0, "description": "Removes a random debuff and heals all allies.", "effects": [{"type": "remove_debuff", "target": "ally"}, {"type": "heal", "target": "ally", "value": 7.5}]}],
            },
            {
                "champ_id": "champ-riho",
                "name": "Riho Bonespear",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["support"],
                "base_stats": {"hp": 19000, "atk": 1100, "def": 1200, "spd": 102},
                "total_stats": {"hp": 56000, "atk": 2200, "def": 3600, "spd": 204, "acc": 320, "res": 250},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "riho_a2", "name": "Purify", "cooldown": 4, "description": "Removes debuffs and heals allies.", "effects": [{"type": "remove_debuff", "target": "ally"}, {"type": "heal", "target": "ally", "value": 15}]}],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(boss_key="demon_lord", level_key="ultra_nightmare", affinity="spirit", db_path=db_path)
    selected_names = {member["champion_name"] for member in report["selected_team"]}

    assert "Force Nuker" not in selected_names
    assert "Magic Nuker" in selected_names
    assert report["team_fit"]["weak_affinity_members"] == []


def test_push_objective_values_generic_build_quality_over_name_bias(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-jintoro",
                "name": "Jintoro",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Shadowkin",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 17000, "atk": 1600, "def": 1000, "spd": 99},
                "total_stats": {"hp": 36000, "atk": 4300, "def": 2200, "spd": 182, "acc": 180, "crit_rate": 85, "crit_dmg": 180},
                "equipped_item_ids": [],
                "skills": [{"slot": "A3", "skill_id": "jintoro_a3", "name": "Flurry", "cooldown": 4, "description": "Attacks an enemy and deals damage.", "effects": [{"type": "damage", "target": "enemy", "value": 3.0}]}],
            },
            {
                "champ_id": "champ-alpha",
                "name": "Alpha Striker",
                "rarity": "epic",
                "affinity": "void",
                "faction": "Banner Lords",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 17000, "atk": 1500, "def": 1000, "spd": 99},
                "total_stats": {"hp": 41000, "atk": 6200, "def": 2600, "spd": 214, "acc": 275, "crit_rate": 100, "crit_dmg": 295},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "alpha_a2", "name": "Expose", "cooldown": 4, "description": "Places Weaken then attacks.", "effects": [{"type": "weaken", "target": "enemy", "duration": 2, "chance": 100}, {"type": "damage", "target": "enemy", "value": 2.4}]}],
            },
            {
                "champ_id": "champ-venus",
                "name": "Venus",
                "rarity": "legendary",
                "affinity": "magic",
                "faction": "Sacred Order",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack", "support"],
                "base_stats": {"hp": 18000, "atk": 1500, "def": 1100, "spd": 100},
                "total_stats": {"hp": 50000, "atk": 4200, "def": 2600, "spd": 202, "acc": 370, "res": 170, "crit_rate": 100, "crit_dmg": 210},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "venus_a2", "name": "Poison Cloud", "cooldown": 4, "description": "Places Poison, Decrease DEF and Weaken debuffs.", "effects": [{"type": "poison", "target": "enemy", "duration": 2, "chance": 100}, {"type": "decrease_def", "target": "enemy", "duration": 2, "chance": 100}, {"type": "weaken", "target": "enemy", "duration": 2, "chance": 100}]}],
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
                "total_stats": {"hp": 54000, "atk": 2400, "def": 3600, "spd": 201, "acc": 345, "res": 210},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "stag_a2", "name": "Huntmaster", "cooldown": 4, "description": "Places Decrease ATK and Decrease DEF.", "effects": [{"type": "decrease_attack", "target": "enemy", "duration": 2, "chance": 100}, {"type": "decrease_def", "target": "enemy", "duration": 2, "chance": 100}]}],
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
                "total_stats": {"hp": 70000, "atk": 1800, "def": 5200, "spd": 193, "acc": 230, "crit_rate": 100, "crit_dmg": 165, "res": 260},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "valk_a2", "name": "Stand Firm", "cooldown": 3, "description": "Places Shield and Counterattack on all allies.", "effects": [{"type": "shield", "target": "ally", "value": 10}, {"type": "counterattack", "target": "ally", "duration": 2}]}],
            },
            {
                "champ_id": "champ-tyrant",
                "name": "Tyrant Ixlimor",
                "rarity": "legendary",
                "affinity": "void",
                "faction": "Lizardmen",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["defense", "support"],
                "base_stats": {"hp": 22000, "atk": 1000, "def": 1500, "spd": 95},
                "total_stats": {"hp": 72000, "atk": 1800, "def": 4700, "spd": 198, "acc": 245, "res": 240},
                "equipped_item_ids": [],
                "skills": [{"slot": "A2", "skill_id": "tyrant_a2", "name": "Protection", "cooldown": 4, "description": "Places Ally Protect and HP Burn.", "effects": [{"type": "ally_protect", "target": "ally", "duration": 2}, {"type": "hp_burn", "target": "enemy", "duration": 2, "chance": 100}]}],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    report = build_team_optimizer_report(
        boss_key="demon_lord",
        level_key="ultra_nightmare",
        affinity="void",
        recommendation_source="optimizer_push",
        db_path=db_path,
    )
    selected_names = {member["champion_name"] for member in report["selected_team"]}

    assert "Alpha Striker" in selected_names
