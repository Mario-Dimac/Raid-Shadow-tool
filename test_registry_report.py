from __future__ import annotations

import json
from pathlib import Path

from forge_db import bootstrap_database
from registry_report import build_registry_report


def test_registry_report_treats_complete_skill_rows_as_ready_without_effects(tmp_path: Path) -> None:
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
                    {
                        "slot": "A1",
                        "skill_id": "geo_a1",
                        "name": "Stone Hammer",
                        "cooldown": 0,
                        "description": "Attack one enemy.",
                        "effects": [],
                    },
                    {
                        "slot": "A2",
                        "skill_id": "geo_a2",
                        "name": "Stone Burn",
                        "cooldown": 3,
                        "description": "Places HP Burn.",
                        "effects": [],
                    },
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)
    report = build_registry_report(db_path)

    assert report["registry_targets"] == 1
    assert report["registry_targets_ready"] == 1
    assert report["registry_targets_with_effect_data"] == 0
    assert report["registry_targets_fully_enriched"] == 0
    assert report["targets_needing_data"] == []
    assert report["targets_needing_effects"] == [
        {
            "champion_name": "Geomancer",
            "skill_rows": 2,
            "skill_rows_with_data": 2,
            "effect_rows": 0,
        }
    ]
