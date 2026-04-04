from __future__ import annotations

import json
from pathlib import Path

import cbforge_web
from clan_boss_simulator import simulate_clan_boss_battle
from forge_db import bootstrap_database


def build_member(name: str, speed: float, effects: list[dict], target: str = "boss") -> dict:
    normalized_effects = []
    for effect in effects:
        row = dict(effect)
        row.setdefault("target", target)
        normalized_effects.append(row)
    return {
        "slot_index": 1,
        "champion_name": name,
        "champ_id": f"{name.lower().replace(' ', '-')}-id",
        "speed": speed,
        "skills": [
            {
                "slot": "A1",
                "skill_name": "Primary",
                "cooldown": 0,
                "priority": 100,
                "use_as_opener": False,
                "enabled": True,
                "effects": normalized_effects,
            },
            {"slot": "A2", "skill_name": "A2", "cooldown": 3, "priority": 240, "use_as_opener": False, "enabled": False, "effects": []},
            {"slot": "A3", "skill_name": "A3", "cooldown": 3, "priority": 320, "use_as_opener": False, "enabled": False, "effects": []},
            {"slot": "A4", "skill_name": "A4", "cooldown": 3, "priority": 160, "use_as_opener": False, "enabled": False, "effects": []},
        ],
    }


def test_simulator_requires_at_least_one_champion() -> None:
    payload = simulate_clan_boss_battle({"settings": {"max_boss_turns": 3}, "team": []})

    assert payload["ok"] is False
    assert payload["errors"] == ["Inserisci almeno un campione nel team."]


def test_simulator_reports_full_decrease_attack_uptime() -> None:
    payload = simulate_clan_boss_battle(
        {
            "settings": {"difficulty": "ultra_nightmare", "max_boss_turns": 4, "stun_target_slot": 1},
            "team": [
                build_member(
                    "Coffin Smasher",
                    255,
                    [{"effect_type": "decrease_attack", "duration": 2}],
                )
            ],
        }
    )

    assert payload["ok"] is True
    assert payload["summary"]["boss_turns"] == 4
    assert payload["summary"]["decrease_attack_uptime_pct"] == 100.0


def test_simulator_blocks_stun_when_block_debuffs_is_active() -> None:
    payload = simulate_clan_boss_battle(
        {
            "settings": {"difficulty": "ultra_nightmare", "max_boss_turns": 3, "stun_target_slot": 1},
            "team": [
                build_member(
                    "Anchor",
                    260,
                    [{"effect_type": "block_debuffs", "target": "self", "duration": 1}],
                    target="self",
                )
            ],
        }
    )

    assert payload["ok"] is True
    assert payload["boss_turns"][-1]["skill_label"] == "Stun"
    assert payload["boss_turns"][-1]["stun_blocked"] is True
    assert payload["summary"]["blocked_stuns_pct"] == 100.0
    assert payload["team_state"][0]["skipped_turns"] == 0


def test_simulator_marks_skipped_turn_after_unblocked_stun() -> None:
    payload = simulate_clan_boss_battle(
        {
            "settings": {"difficulty": "ultra_nightmare", "max_boss_turns": 4, "stun_target_slot": 1},
            "team": [build_member("DPS", 230, [])],
        }
    )

    assert payload["ok"] is True
    assert payload["boss_turns"][2]["skill_label"] == "Stun"
    assert payload["boss_turns"][2]["stun_blocked"] is False
    assert payload["team_state"][0]["skipped_turns"] >= 1
    assert any("Lo stun passa senza Block Debuffs" in warning for warning in payload["summary"]["warnings"])


def test_clan_boss_bootstrap_prefills_optimizer_team(monkeypatch, tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    source_path.write_text(
        json.dumps(
            {
                "champions": [
                    {
                        "champ_id": "champ-1",
                        "name": "Valkyrie",
                        "rarity": "legendary",
                        "affinity": "spirit",
                        "faction": "Barbarians",
                        "level": 60,
                        "rank": 6,
                        "awakening_level": 0,
                        "empowerment_level": 0,
                        "booked": True,
                        "role_tags": ["defense"],
                        "base_stats": {"spd": 95},
                        "total_stats": {"spd": 171},
                        "equipped_item_ids": [],
                        "skills": [],
                    },
                    {
                        "champ_id": "champ-2",
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
                        "base_stats": {"spd": 98},
                        "total_stats": {"spd": 177},
                        "equipped_item_ids": [],
                        "skills": [],
                    },
                ],
                "gear": [],
                "account_bonuses": [],
            }
        ),
        encoding="utf-8",
    )
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    monkeypatch.setattr(
        cbforge_web,
        "build_team_optimizer_report",
        lambda boss_key="demon_lord", level_key="ultra_nightmare", affinity="void", db_path=None: {
            "selected_team": [
                {"champion_name": "Valkyrie"},
                {"champion_name": "Ninja"},
            ]
        },
    )

    payload = cbforge_web.build_clan_boss_simulator_bootstrap(db_path=db_path)

    assert payload["difficulty_options"]
    assert payload["affinity_options"]
    assert payload["effect_library"]
    assert payload["team_presets"]
    assert payload["default_team"][0]["champion_name"] == "Valkyrie"
    assert payload["default_team"][0]["speed"] == 171.0
    assert payload["default_team"][1]["champion_name"] == "Ninja"
    assert payload["default_team"][1]["speed"] == 177.0
