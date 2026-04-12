from __future__ import annotations

import json
from pathlib import Path

from forge_db import bootstrap_database, record_run_history
from ml_team_baseline import build_supervised_rows, recommend_best_team_from_candidates, train_team_baseline


def test_ml_team_baseline_builds_rows_and_trains(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    model_path = tmp_path / "models" / "baseline.joblib"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    teams = [
        (["Valkyrie", "Ninja", "Stag Knight", "Teodor the Savant", "Doompriest"], [171, 177, 219, 214, 198], 28500000.0, 36, 1),
        (["Valkyrie", "Jintoro", "Stag Knight", "Underpriest Brogni", "Minaya"], [171, 188, 219, 182, 201], 34300000.0, 41, 1),
        (["Kael", "Frozen Banshee", "Apothecary", "Stag Knight", "Doompriest"], [175, 179, 240, 219, 198], 18100000.0, 24, 0),
        (["Ninja", "Teodor the Savant", "Doompriest", "Aox the Rememberer", "Valkyrie"], [177, 214, 198, 191, 171], 30100000.0, 38, 1),
    ]

    for index, (names, speeds, total_damage, boss_turn, success) in enumerate(teams, start=1):
        record_run_history(
            {
                "source": "test",
                "battle_id": f"battle-{index}",
                "encounter_key": "demon_lord_ultra_nightmare",
                "encounter_name": "Demon Lord Ultra-Nightmare",
                "encounter_family": "demon_lord",
                "area_region": "clan_boss",
                "game_mode": "clan_boss",
                "difficulty": "ultra_nightmare",
                "boss_affinity": "void",
                "success": success,
                "elapsed_seconds": 510.0 + index,
                "boss_turn": boss_turn,
                "total_damage": total_damage,
                "members": [
                    {
                        "champion_name": name,
                        "role_hint": "support" if "priest" in name.lower() or name in {"Valkyrie", "Minaya"} else "damage",
                        "level": 60,
                        "rank": 6,
                        "awakening_level": 1,
                        "empowerment_level": 0,
                        "booked": True,
                        "set_summary": [{"set_name": "Attack Speed", "display_name": "Speed", "completed_sets": 3}],
                        "stats": {
                            "hp": 50000 + position * 1000,
                            "atk": 2500 + position * 200,
                            "def": 3000 + position * 150,
                            "spd": speeds[position - 1],
                            "acc": 250 + position * 10,
                            "res": 180 + position * 10,
                            "crit_rate": 100,
                            "crit_dmg": 180 + position * 5,
                        },
                    }
                    for position, name in enumerate(names, start=1)
                ],
            },
            db_path=db_path,
        )

    rows = build_supervised_rows(db_path=db_path, encounter_key="demon_lord_ultra_nightmare")

    assert len(rows) == 4
    assert rows[0]["features"]["team_size"] == 5
    assert "champ:Valkyrie" in rows[0]["features"]
    assert "spd_avg" in rows[0]["features"]
    assert "sustain_members" in rows[0]["features"]
    assert "speed_floor_hits" in rows[0]["features"]
    assert rows[0]["target_boss_turn"] is not None

    summary = train_team_baseline(rows, model_path)

    assert summary["ok"] is True
    assert summary["rows"] == 4
    assert model_path.exists()
    assert summary["feature_importances"]

    candidate_pool = [
        {
            "champion_name": "Valkyrie",
            "champ_id": "champ-valk",
            "score": 95.0,
            "level": 60,
            "rank": 6,
            "booked": True,
            "roles": ["support", "counterattack"],
            "capability_tags": ["counterattack", "shield", "sustain"],
            "stats": {"hp": 68000, "def": 5000, "spd": 171, "acc": 220, "res": 260, "crit_rate": 100, "crit_dmg": 160, "atk": 1800},
        },
        {
            "champion_name": "Ninja",
            "champ_id": "champ-ninja",
            "score": 94.0,
            "level": 60,
            "rank": 6,
            "booked": True,
            "roles": ["damage", "burner"],
            "capability_tags": ["hp_burn", "boss_pressure"],
            "stats": {"hp": 43000, "def": 2800, "spd": 177, "acc": 260, "res": 150, "crit_rate": 100, "crit_dmg": 220, "atk": 5400},
        },
        {
            "champion_name": "Stag Knight",
            "champ_id": "champ-stag",
            "score": 92.0,
            "level": 60,
            "rank": 6,
            "booked": True,
            "roles": ["support", "decrease_attack"],
            "capability_tags": ["decrease_attack", "decrease_defense"],
            "stats": {"hp": 54000, "def": 3600, "spd": 219, "acc": 345, "res": 210, "crit_rate": 40, "crit_dmg": 90, "atk": 2400},
        },
        {
            "champion_name": "Teodor the Savant",
            "champ_id": "champ-teodor",
            "score": 90.0,
            "level": 60,
            "rank": 6,
            "booked": True,
            "roles": ["poisoner", "support"],
            "capability_tags": ["poison", "sustain"],
            "stats": {"hp": 62000, "def": 3400, "spd": 214, "acc": 360, "res": 250, "crit_rate": 25, "crit_dmg": 70, "atk": 1900},
        },
        {
            "champion_name": "Doompriest",
            "champ_id": "champ-doom",
            "score": 84.0,
            "level": 60,
            "rank": 6,
            "booked": True,
            "roles": ["cleanse", "support"],
            "capability_tags": ["cleanse", "sustain"],
            "stats": {"hp": 68000, "def": 4300, "spd": 198, "acc": 120, "res": 320, "crit_rate": 30, "crit_dmg": 70, "atk": 1700},
        },
        {
            "champion_name": "Kael",
            "champ_id": "champ-kael",
            "score": 73.0,
            "level": 60,
            "rank": 6,
            "booked": True,
            "roles": ["damage", "poisoner"],
            "capability_tags": ["poison", "boss_pressure"],
            "stats": {"hp": 38000, "def": 2500, "spd": 175, "acc": 220, "res": 140, "crit_rate": 100, "crit_dmg": 205, "atk": 4600},
        },
    ]

    recommendation = recommend_best_team_from_candidates(
        candidates=candidate_pool,
        encounter_key="demon_lord_ultra_nightmare",
        difficulty="ultra_nightmare",
        boss_affinity="void",
        model_path=model_path,
        team_size=5,
        pool_size=6,
    )

    assert recommendation["best_team"]
    assert recommendation["evaluated_combinations"] >= 1
    assert recommendation["predicted_total_damage"] > 0
    assert recommendation["predicted_boss_turn"] is not None
    assert recommendation["predicted_boss_turn"] > 0

    constrained = recommend_best_team_from_candidates(
        candidates=candidate_pool,
        encounter_key="demon_lord_ultra_nightmare",
        difficulty="ultra_nightmare",
        boss_affinity="void",
        model_path=model_path,
        team_size=5,
        pool_size=6,
        hard_rules={
            "required_champion_names": ["Stag Knight"],
            "required_tags": ["cleanse", "counterattack"],
            "minimum_speed": 190,
            "minimum_speed_hits": 3,
        },
    )

    constrained_names = {member["champion_name"] for member in constrained["best_team"]}
    assert "Stag Knight" in constrained_names
    assert constrained["hard_rules"]["minimum_speed_hits"] == 3
