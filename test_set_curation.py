from __future__ import annotations

import json
from pathlib import Path

import cbforge_web
from forge_db import bootstrap_database
from set_curation import load_local_set_entries, normalize_local_set_entry, save_local_set_entry


def test_normalize_local_set_entry_parses_stats_and_effects() -> None:
    entry = normalize_local_set_entry(
        {
            "set_name": "Stone Skin",
            "canonical_name": "Stoneskin",
            "display_name": "Stoneskin",
            "set_kind": "variable",
            "counts_accessories": True,
            "base_bonus_text": "effect: special handling note",
            "thresholds_text": "\n".join(
                [
                    "1 | HP% +8",
                    "2 | RES +40",
                    "4 | effect: Grants Stone Skin for 1 turn at battle start",
                ]
            ),
        }
    )

    assert entry["canonical_name"] == "Stoneskin"
    assert entry["set_kind"] == "variable"
    assert entry["counts_accessories"] is True
    assert entry["piece_bonuses"][0]["stats"] == [{"stat_type": "hp_pct", "stat_value": 8.0}]
    assert entry["piece_bonuses"][1]["stats"] == [{"stat_type": "res", "stat_value": 40.0}]
    assert entry["piece_bonuses"][2]["effect_text"] == "Grants Stone Skin for 1 turn at battle start"


def test_save_local_set_entry_round_trips_to_json(tmp_path: Path) -> None:
    path = tmp_path / "local_set_registry.json"

    save_local_set_entry(
        {
            "set_name": "Counterattack Accessory",
            "canonical_name": "Revenge Accessory",
            "display_name": "Revenge",
            "set_kind": "accessory",
            "counts_accessories": True,
            "base_bonus_text": "",
            "thresholds_text": "1 | effect: 5% chance to counterattack when hit\n2 | effect: 10% chance to counterattack when hit",
        },
        path=path,
    )

    entries = load_local_set_entries(path)

    assert len(entries) == 1
    assert entries[0]["set_name"] == "Counterattack Accessory"
    assert entries[0]["canonical_name"] == "Revenge Accessory"
    assert entries[0]["piece_bonuses"][0]["effect_text"] == "5% chance to counterattack when hit"


def test_build_set_curation_payload_prefills_curated_name(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
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
                "set_name": "Attack Speed",
                "canonical_name": "Speed Set",
                "display_name": "Speed",
                "set_kind": "fixed",
                "counts_accessories": False,
                "pieces_required": 2,
                "max_pieces": 6,
                "base_bonus_text": "SPD +12",
                "thresholds_text": "",
            }
        ],
    )

    curation = cbforge_web.build_set_curation_payload(db_path)
    speed = next(item for item in curation["items"] if item["set_name"] == "Attack Speed")

    assert speed["curated"] is True
    assert speed["curation"]["canonical_name"] == "Speed Set"
    assert speed["curation"]["base_bonus_text"] == "SPD +12"
