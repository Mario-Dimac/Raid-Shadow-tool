from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ai_training_dataset import build_ai_training_skill_dataset_overview, refresh_ai_training_skill_dataset
from cbforge_web import build_ai_training_overview
from forge_db import bootstrap_database, record_run_history


def _bootstrap_empty_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)
    return db_path


def test_refresh_ai_training_skill_dataset_materializes_normalized_rows(tmp_path: Path) -> None:
    db_path = _bootstrap_empty_db(tmp_path)

    for battle_id, usage_count, damage_taken, feature_c, feature_x in (
        ("battle-1", 9, 100.0, 1, 21),
        ("battle-2", 12, 220.0, 3, 27),
    ):
        record_run_history(
            {
                "source": "probe_import",
                "source_run_uid": battle_id,
                "battle_id": battle_id,
                "encounter_key": "demon_lord_ultra_nightmare",
                "encounter_name": "Demon Lord Ultra-Nightmare",
                "stage_id": "4019024",
                "members": [
                    {
                        "champion_name": "Ninja",
                        "champion_type_id": 6206,
                        "metrics": {
                            "damage_taken": damage_taken,
                            "incoming_target_events": 0,
                            "incoming_boss_target_events": 0,
                        },
                        "skill_usage": [
                            {"skill_order": 2, "skill_slot": "A2", "skill_code": "62002", "usage_count": usage_count}
                        ],
                        "skill_features": [
                            {
                                "skill_order": 2,
                                "skill_slot": "A2",
                                "skill_code": "62002",
                                "champion_type_id": 6206,
                                "enabled": True,
                                "internal_i": False,
                                "internal_d": False,
                                "c": feature_c,
                                "m": 3,
                                "x": feature_x,
                                "r": 0,
                                "a": 0,
                                "h": 0,
                                "s": 0,
                                "ir": 0,
                                "y": 6,
                            }
                        ],
                    }
                ],
            },
            db_path=db_path,
        )

    refresh = refresh_ai_training_skill_dataset(db_path=db_path)

    assert refresh["ok"] is True
    assert refresh["overview"]["sample_count"] == 2
    assert refresh["overview"]["normalized_sample_count"] == 2

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT target_value, raw_features_json, normalized_features_json, normalization_ready
            FROM ai_training_skill_samples
            ORDER BY run_id ASC
            """
        ).fetchall()

    assert len(rows) == 2
    first_raw = json.loads(rows[0]["raw_features_json"])
    second_raw = json.loads(rows[1]["raw_features_json"])
    first_norm = json.loads(rows[0]["normalized_features_json"])
    second_norm = json.loads(rows[1]["normalized_features_json"])
    assert first_raw["x"] == 21
    assert second_raw["x"] == 27
    assert rows[0]["target_value"] == 9
    assert rows[1]["target_value"] == 12
    assert rows[0]["normalization_ready"] == 1
    assert first_norm["x"] == 0.0
    assert second_norm["x"] == 1.0


def test_build_ai_training_overview_exposes_materialized_skill_dataset(tmp_path: Path) -> None:
    db_path = _bootstrap_empty_db(tmp_path)

    record_run_history(
        {
            "source": "probe_import",
            "source_run_uid": "battle-1",
            "battle_id": "battle-1",
            "encounter_key": "dragon_10",
            "encounter_name": "Dragon",
            "stage_id": "2062010",
            "members": [
                {
                    "champion_name": "Ninja",
                    "champion_type_id": 6206,
                    "metrics": {
                        "damage_taken": 80.0,
                        "incoming_target_events": 1,
                        "incoming_boss_target_events": 0,
                    },
                    "skill_usage": [
                        {"skill_order": 2, "skill_slot": "A2", "skill_code": "62002", "usage_count": 7}
                    ],
                    "skill_features": [
                        {
                            "skill_order": 2,
                            "skill_slot": "A2",
                            "skill_code": "62002",
                            "champion_type_id": 6206,
                            "enabled": True,
                            "internal_i": False,
                            "internal_d": False,
                            "c": 1,
                            "m": 3,
                            "x": 11,
                            "r": 0,
                            "a": 0,
                            "h": 0,
                            "s": 0,
                            "ir": 0,
                            "y": 6,
                        }
                    ],
                }
            ],
        },
        db_path=db_path,
    )

    refresh_ai_training_skill_dataset(db_path=db_path)
    overview = build_ai_training_overview(db_path=db_path)
    dataset = build_ai_training_skill_dataset_overview(db_path=db_path)

    assert overview["skill_dataset"]["sample_count"] == 1
    assert overview["skill_dataset"]["run_count"] == 1
    assert dataset["top_encounters"][0]["encounter_key"] == "dragon_10"
