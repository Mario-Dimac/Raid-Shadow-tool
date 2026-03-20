from __future__ import annotations

import json
from pathlib import Path

import cbforge_web
from cbforge_web import (
    build_gear_summary,
    build_sell_queue_summary,
    build_web_summary,
    champion_detail,
    gear_item_detail,
    list_gear_items,
    list_owned_champions,
    refresh_gear_from_game,
    sell_artifacts_from_queue,
)
from forge_db import bootstrap_database


def test_web_queries_expose_owned_roster_and_detail(tmp_path: Path) -> None:
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
                "base_stats": {"hp": 20000, "def": 1200},
                "total_stats": {"hp": 50000, "def": 3000, "spd": 210},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "geo_a1",
                        "name": "Stone Hammer",
                        "cooldown": 0,
                        "description": "A1 text",
                        "effects": [{"type": "damage", "target": "enemy", "value": 1.0}],
                    },
                    {
                        "slot": "A2",
                        "skill_id": "geo_a2",
                        "name": "Stone Burn",
                        "cooldown": 3,
                        "description": "A2 text",
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
                "skills": [],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_web_summary(db_path)
    roster = list_owned_champions(db_path, scope="all", sort="name")
    detail = champion_detail("Geomancer", db_path)

    assert summary["owned_champions"] == 2
    assert summary["registry_targets_ready"] == 1
    assert [item["champion_name"] for item in roster["champions"]] == ["Coldheart", "Geomancer"]
    assert roster["champions"][1]["is_registry_target"] is True
    assert roster["champions"][1]["enriched"] is True
    assert roster["champions"][1]["data_status"] == "complete"
    assert detail["account"]["champion_name"] == "Geomancer"
    assert detail["roles"] == ["attack", "support"]
    assert detail["base_stats"]["hp"] == 20000.0
    assert detail["base_totals"]["hp"] == 20000.0
    assert detail["total_stats"]["spd"] == 210.0
    assert detail["stat_model"]["source"] == "raw"
    assert detail["skill_data"]["data_status"] == "complete"
    assert detail["skills"][0]["skill_name"] == "Stone Hammer"
    assert detail["skills"][1]["effects"][0]["effect_type"] == "hp_burn"


def test_web_roster_filters_missing_enrichment(tmp_path: Path) -> None:
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
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": [],
                "skills": [{"slot": "A1", "skill_id": "geo_a1", "name": "48801", "effects": []}],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    missing = list_owned_champions(db_path, scope="missing")

    assert len(missing["champions"]) == 1
    assert missing["champions"][0]["champion_name"] == "Geomancer"
    assert missing["champions"][0]["enriched"] is False
    assert missing["champions"][0]["data_status"] == "missing"


def test_web_roster_deduplicates_multiple_owned_instances(tmp_path: Path) -> None:
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
                "level": 50,
                "rank": 5,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": False,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": [],
                "skills": [],
            },
            {
                "champ_id": "champ-2",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": [],
                "skills": [],
            },
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    roster = list_owned_champions(db_path)

    assert len(roster["champions"]) == 1
    assert roster["champions"][0]["champ_id"] == "champ-2"


def test_web_detail_exposes_derived_stats_and_warnings(tmp_path: Path) -> None:
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
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "HP And Heal",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [{"type": "res", "value": 0.2, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    detail = champion_detail("Yumeko", db_path)

    assert detail["stat_model"]["source"] == "derived"
    assert detail["stat_model"]["completeness"] == "partial"
    assert detail["stat_model"]["unsupported_sets"] == ["Stone Skin"]
    assert detail["base_totals"]["hp"] == 30960.0
    assert detail["total_stats"]["spd"] == 160.0


def test_gear_queries_cover_equipped_and_inventory_items(tmp_path: Path) -> None:
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
                "role_tags": [],
                "base_stats": {},
                "total_stats": {},
                "equipped_item_ids": ["gear-1"],
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
                "ascension_level": 1,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [
                    {"type": "acc", "value": 20, "rolls": 2, "glyph_value": 4},
                    {"type": "hp_pct", "value": 0.1, "rolls": 1, "glyph_value": 0},
                ],
            },
            {
                "item_id": "gear-2",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "Feral",
                "rarity": "epic",
                "rank": 5,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "crit_rate", "value": 50},
                "substats": [
                    {"type": "spd", "value": 5, "rolls": 0, "glyph_value": 0},
                ],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_gear_summary(db_path)
    all_items = list_gear_items(db_path)
    equipped_items = list_gear_items(db_path, ownership="equipped")
    inventory_items = list_gear_items(db_path, ownership="inventory")
    artifacts_only = list_gear_items(db_path, item_class="artifact")
    filtered = list_gear_items(db_path, slot="boots", set_name="Attack Speed")
    detail = gear_item_detail("gear-1", db_path)

    assert summary["total_items"] == 2
    assert summary["equipped_items"] == 1
    assert summary["inventory_items"] == 1
    assert summary["locked_items"] == 1
    assert len(all_items["items"]) == 2
    assert len(equipped_items["items"]) == 1
    assert equipped_items["items"][0]["owner_name"] == "Geomancer"
    assert len(inventory_items["items"]) == 1
    assert inventory_items["items"][0]["item_id"] == "gear-2"
    assert len(artifacts_only["items"]) == 2
    assert artifacts_only["filters"]["item_classes"] == ["artifact"]
    assert len(filtered["items"]) == 1
    assert filtered["items"][0]["item_id"] == "gear-1"
    assert filtered["items"][0]["advice_verdict"] == "keep_16"
    assert "main stat forte: spd" in filtered["items"][0]["advice_reasons"][0]
    assert detail["item"]["equipped"] is True
    assert detail["item"]["owner_name"] == "Geomancer"
    assert detail["substats"][0]["glyph_value"] == 4
    assert detail["advice"]["verdict"] == "keep_16"
    assert summary["verdict_counts"]["keep_16"] >= 1


def test_sell_queue_summary_groups_candidates_by_page(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "art-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "rare",
                "rank": 5,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [
                    {"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0},
                ],
            },
            {
                "item_id": "acc-1",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "Stone Skin",
                "rarity": "rare",
                "rank": 5,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "hp", "value": 10},
                "substats": [
                    {"type": "atk", "value": 10, "rolls": 0, "glyph_value": 0},
                ],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_sell_queue_summary(db_path=db_path, limit_per_page=5)

    pages = {page["page"]: page for page in summary["pages"]}
    assert pages["artifact"]["candidate_count"] == 1
    assert pages["artifact"]["visible_candidates"][0]["item_id"] == "art-1"
    assert pages["accessory"]["candidate_count"] == 1
    assert pages["accessory"]["visible_candidates"][0]["item_id"] == "acc-1"


def test_sell_artifacts_from_queue_only_sends_current_candidates(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "art-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "rare",
                "rank": 5,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "art-2",
                "item_class": "artifact",
                "slot": "gloves",
                "set_name": "Attack Speed",
                "rarity": "rare",
                "rank": 5,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": True,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "acc-1",
                "item_class": "accessory",
                "slot": "ring",
                "set_name": "Stone Skin",
                "rarity": "rare",
                "rank": 5,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "hp", "value": 10},
                "substats": [{"type": "atk", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    captured = {}

    def fake_sell_artifacts_live(artifact_ids, access_token=None, base_url=cbforge_web.hellhades_live.DEFAULT_BASE_URL, timeout_seconds=10.0):
        captured["artifact_ids"] = list(artifact_ids)
        captured["access_token"] = access_token
        return {
            "status": "success",
            "message": "SellArtifacts eseguito correttamente.",
            "requested_count": len(captured["artifact_ids"]),
        }

    monkeypatch.setattr(cbforge_web.hellhades_live, "sell_artifacts_live", fake_sell_artifacts_live)

    result = sell_artifacts_from_queue(
        artifact_ids=["art-1", "art-2", "missing", "art-1"],
        db_path=db_path,
        access_token="secret-token",
    )

    assert captured["artifact_ids"] == ["art-1"]
    assert captured["access_token"] == "secret-token"
    assert result["approved_ids"] == ["art-1"]
    assert result["rejected_ids"] == ["art-2", "missing"]
    assert result["approved_items"][0]["item_id"] == "art-1"


def test_sell_queue_prioritizes_bad_main_stat_plus_zero_first(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "weak-plus0",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "weak-plus12",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 12,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "medium-plus0",
                "item_class": "artifact",
                "slot": "chest",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk_pct", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_sell_queue_summary(db_path=db_path, limit_per_page=5)

    artifact_ids = [item["item_id"] for item in next(page for page in summary["pages"] if page["page"] == "artifact")["visible_candidates"]]
    assert artifact_ids[:3] == ["weak-plus0", "weak-plus12", "medium-plus0"]


def test_sell_queue_summary_can_exclude_already_sent_ids(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [],
        "gear": [
            {
                "item_id": "weak-a",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "atk", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "weak-b",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 0,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "",
                "locked": False,
                "main_stat": {"type": "hp", "value": 10},
                "substats": [{"type": "hp", "value": 10, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = build_sell_queue_summary(db_path=db_path, limit_per_page=5, exclude_ids=["weak-a"])

    artifact_ids = [item["item_id"] for item in next(page for page in summary["pages"] if page["page"] == "artifact")["visible_candidates"]]
    assert artifact_ids == ["weak-b"]


def test_refresh_gear_from_game_copies_legacy_outputs_and_rebuilds(tmp_path: Path, monkeypatch) -> None:
    legacy_dir = tmp_path / "legacy"
    legacy_input = legacy_dir / "input"
    legacy_input.mkdir(parents=True)
    base_dir = tmp_path / "app"
    base_input = base_dir / "input"
    base_input.mkdir(parents=True)
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = base_input / "normalized_account.json"

    raw_payload = {"raw": True}
    normalized_payload = {"champions": [], "gear": [], "account_bonuses": []}
    command_log = []

    def fake_run(command, cwd, capture_output, text, check):
        command_log.append((tuple(command), cwd))
        if command == ["python", "extract_local.py"]:
            (legacy_input / "raw_account.json").write_text(json.dumps(raw_payload), encoding="utf-8")
        if command == ["python", "normalize.py"]:
            (legacy_input / "normalized_account.json").write_text(json.dumps(normalized_payload), encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Completed()

    def fake_bootstrap_database(source_path, db_path, rebuild):
        assert source_path == base_input / "normalized_account.json"
        assert db_path == db_path_arg
        assert rebuild is False
        return {"gear_items": 0, "account_champions": 0}

    db_path_arg = db_path
    monkeypatch.setattr(cbforge_web, "LEGACY_DIR", legacy_dir)
    monkeypatch.setattr(cbforge_web, "LEGACY_INPUT_DIR", legacy_input)
    monkeypatch.setattr(cbforge_web, "BASE_DIR", base_dir)
    monkeypatch.setattr(cbforge_web.subprocess, "run", fake_run)
    monkeypatch.setattr(cbforge_web, "bootstrap_database", fake_bootstrap_database)

    result = refresh_gear_from_game(db_path=db_path, source_path=source_path)

    assert command_log == [
        (("python", "extract_local.py"), legacy_dir),
        (("python", "normalize.py"), legacy_dir),
    ]
    assert json.loads((base_input / "raw_account.json").read_text(encoding="utf-8")) == raw_payload
    assert json.loads((base_input / "normalized_account.json").read_text(encoding="utf-8")) == normalized_payload
    assert result["summary"]["gear_items"] == 0
