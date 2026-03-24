from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import run_history_importer
from forge_db import bootstrap_database
from run_history_importer import backfill_probe_skill_usage, event_battle_id, import_probe_session


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_import_probe_session_persists_encounter_mapping_into_db(tmp_path: Path) -> None:
    client_root = tmp_path / "client_probe"
    live_root = tmp_path / "live_storage_probe"
    session_slug = "20260322T114745Z"
    client_session = client_root / session_slug
    live_session = live_root / session_slug
    client_session.mkdir(parents=True)
    live_session.mkdir(parents=True)

    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    hero_types_path = tmp_path / "hh_hero_types.json"
    hero_types_path.write_text(
        json.dumps(
            [
                {
                    "id": 22296,
                    "name": "Demon Lord",
                    "forms": [{"element": 4, "baseStats": {"speed": 170}}],
                }
            ]
        ),
        encoding="utf-8",
    )

    raw_asset = client_session / "battle_results.bin"
    raw_asset.write_bytes(b"rich-battle-results")
    meta_asset = client_session / "battle_results.json"
    meta_asset.write_text("{}", encoding="utf-8")
    live_asset = live_session / "battleResults_12201.bin"
    live_asset.write_bytes(b"live-storage-rich-battle-results")

    battle = {
        "battle_id": "5d46944e-8521-4640-a635-f2d4a609b05f",
        "seed": 2035714064,
        "stage_id": "4019021",
        "formation_index": 0,
        "player_team": [
            {"slot": 1, "type_id": 3666, "name": "Rakka Viletide", "grade": "Stars6", "level": 60},
            {"slot": 2, "type_id": 2166, "name": "Valkyrie", "grade": "Stars6", "level": 60},
            {"slot": 3, "type_id": 6206, "name": "Ninja", "grade": "Stars6", "level": 60},
            {"slot": 4, "type_id": 5836, "name": "Jintoro", "grade": "Stars6", "level": 60},
            {"slot": 5, "type_id": 4496, "name": "Stag Knight", "grade": "Stars6", "level": 60},
        ],
        "enemy_rows": [{"slot": 1, "type_id": 22296, "name": "Type 22296", "grade": "Stars6", "level": 250}],
    }

    client_events = [
        {"captured_at": "2026-03-22T11:47:51+00:00", "event_type": "log_line", "line": "Change battle state [StartCmdSucceed -> Loading]"},
        {"captured_at": "2026-03-22T11:47:51+00:00", "event_type": "battle_context", "battle": battle},
        {
            "captured_at": "2026-03-22T11:47:51+00:00",
            "event_type": "sqlite_event",
            "db_name": "raidV2.db",
            "row": {
                "parsed": {
                    "p": {
                        "r": {
                            "t": "CreateAllianceBossBattle",
                        }
                    }
                }
            },
        },
        {"captured_at": "2026-03-22T11:47:53+00:00", "event_type": "log_line", "line": "Change battle state [Loading -> Started]"},
        {"captured_at": "2026-03-22T11:56:40+00:00", "event_type": "log_line", "line": "BattleResult added: [Id=5d46944e-8521-4640-a635-f2d4a609b05f] TotalCount=1"},
        {
            "captured_at": "2026-03-22T11:56:40+00:00",
            "event_type": "forced_file_snapshot",
            "source_name": "battle_results",
            "saved": {
                "raw_path": str(raw_asset),
                "meta_path": str(meta_asset),
                "marker": {"size": 12201, "sha256": "abc123"},
            },
            "battle": battle,
        },
        {"captured_at": "2026-03-22T11:56:42+00:00", "event_type": "log_line", "line": "Change battle state [Started -> Finished]"},
    ]
    live_events = [
        {
            "captured_at": "2026-03-22T11:56:40+00:00",
            "event_type": "file_change",
            "snapshot": {
                "saved_path": str(live_asset),
                "marker": {"size": 12201},
            },
            "battle": battle,
        }
    ]

    write_jsonl(client_session / "events.jsonl", client_events)
    write_jsonl(live_session / "events.jsonl", live_events)

    summary = import_probe_session(
        session_slug=session_slug,
        client_root=client_root,
        live_root=live_root,
        db_path=db_path,
        hero_types_path=hero_types_path,
    )

    assert summary["imported_runs"] == 1
    assert summary["skipped_runs"] == 0

    run_summary = summary["summaries"][0]
    assert run_summary["encounter_key"] == "demon_lord_ultra_nightmare"
    assert run_summary["battle_id"] == "5d46944e-8521-4640-a635-f2d4a609b05f"
    assert run_summary["members"] == 5
    assert run_summary["assets"] == 3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT source, encounter_key, encounter_family, area_region, game_mode, difficulty, stage_id, boss_affinity, total_damage
            FROM run_history_runs
            """
        ).fetchone()

    assert row == (
        "probe_import",
        "demon_lord_ultra_nightmare",
        "demon_lord",
        "clan_boss",
        "clan_boss",
        "ultra_nightmare",
        "4019021",
        "void",
        None,
    )

    second_summary = import_probe_session(
        session_slug=session_slug,
        client_root=client_root,
        live_root=live_root,
        db_path=db_path,
        hero_types_path=hero_types_path,
    )
    assert second_summary["imported_runs"] == 0
    assert second_summary["skipped_runs"] == 1


def test_event_battle_id_prefers_saved_reason_when_battle_context_is_stale() -> None:
    event = {
        "saved": {"reason": "BattleResult added: [Id=correct-battle-id] TotalCount=1"},
        "battle": {"battle_id": "stale-battle-id"},
    }

    assert event_battle_id(event) == "correct-battle-id"


def test_import_probe_session_persists_skill_usage_when_available(tmp_path: Path, monkeypatch) -> None:
    client_root = tmp_path / "client_probe"
    live_root = tmp_path / "live_storage_probe"
    session_slug = "20260324T090000Z"
    client_session = client_root / session_slug
    live_session = live_root / session_slug
    client_session.mkdir(parents=True)
    live_session.mkdir(parents=True)

    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    hero_types_path = tmp_path / "hh_hero_types.json"
    hero_types_path.write_text(json.dumps([]), encoding="utf-8")

    raw_asset = client_session / "battle_results.bin"
    raw_asset.write_bytes(b"rich-battle-results")
    meta_asset = client_session / "battle_results.json"
    meta_asset.write_text("{}", encoding="utf-8")

    battle = {
        "battle_id": "368e1bb0-a147-4b58-9c85-668f395e3cb7",
        "stage_id": "2062010",
        "formation_index": 0,
        "player_team": [
            {"slot": 1, "type_id": 3666, "name": "Rakka Viletide", "grade": "Stars6", "level": 60},
            {"slot": 2, "type_id": 6906, "name": "Yumeko", "grade": "Stars6", "level": 60},
        ],
        "enemy_rows": [{"slot": 1, "type_id": 12345, "name": "Dragon", "grade": "Stars6", "level": 250}],
    }
    client_events = [
        {"captured_at": "2026-03-24T09:00:01+00:00", "event_type": "battle_context", "battle": battle},
        {"captured_at": "2026-03-24T09:00:02+00:00", "event_type": "log_line", "line": "Change battle state [Loading -> Started]"},
        {
            "captured_at": "2026-03-24T09:05:00+00:00",
            "event_type": "forced_file_snapshot",
            "source_name": "battle_results",
            "saved": {
                "raw_path": str(raw_asset),
                "meta_path": str(meta_asset),
                "marker": {"size": 12201, "sha256": "abc123"},
            },
            "battle": battle,
        },
        {"captured_at": "2026-03-24T09:05:02+00:00", "event_type": "log_line", "line": "Change battle state [Started -> Finished]"},
    ]
    write_jsonl(client_session / "events.jsonl", client_events)
    write_jsonl(live_session / "events.jsonl", [])

    monkeypatch.setattr(
        run_history_importer,
        "build_member_skill_usage_by_slot",
        lambda raw_path: {
            0: [{"skill_order": 1, "skill_slot": "A1", "skill_code": "36601", "usage_count": 10}],
            1: [
                {"skill_order": 1, "skill_slot": "A1", "skill_code": "69001", "usage_count": 12},
                {"skill_order": 3, "skill_slot": "A3", "skill_code": "69003", "usage_count": 5},
            ],
        },
    )

    summary = import_probe_session(
        session_slug=session_slug,
        client_root=client_root,
        live_root=live_root,
        db_path=db_path,
        hero_types_path=hero_types_path,
    )

    run_summary = summary["summaries"][0]
    assert run_summary["skill_usages"] == 3

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT member_order, skill_order, skill_slot, skill_code, usage_count
            FROM run_history_member_skill_usage
            ORDER BY member_order, skill_order
            """
        ).fetchall()

    assert rows == [
        (1, 1, "A1", "36601", 10),
        (2, 1, "A1", "69001", 12),
        (2, 3, "A3", "69003", 5),
    ]


def test_backfill_probe_skill_usage_updates_existing_runs(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO run_history_runs (
                saved_at, source, source_run_uid, battle_id, encounter_key, success, completed, auto_play,
                feature_schema_version, labels_json, context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-03-24T09:05:00+00:00",
                "probe_import",
                "battle-1",
                "battle-1",
                "dragon_10",
                1,
                1,
                1,
                "run_history_v1",
                "{}",
                "{}",
            ),
        )
        run_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            """
            INSERT INTO run_history_members (
                run_id, member_order, champion_name, champion_type_id, booked, set_summary_json, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, 1, "Rakka Viletide", 3666, 0, "[]", "[]"),
        )
        conn.execute(
            """
            INSERT INTO run_history_members (
                run_id, member_order, champion_name, champion_type_id, booked, set_summary_json, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, 2, "Yumeko", 6906, 0, "[]", "[]"),
        )
        conn.execute(
            """
            INSERT INTO run_history_assets (
                run_id, asset_order, asset_kind, asset_path, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, 1, "client_probe_battle_results_bin", str(tmp_path / "battle_results.bin"), "{}"),
        )
        conn.commit()

    monkeypatch.setattr(
        run_history_importer,
        "build_member_skill_usage_by_slot",
        lambda raw_path: {
            0: [{"skill_order": 1, "skill_slot": "A1", "skill_code": "36601", "usage_count": 10}],
            1: [{"skill_order": 3, "skill_slot": "A3", "skill_code": "69003", "usage_count": 5}],
        },
    )

    summary = backfill_probe_skill_usage(db_path=db_path)

    assert summary["backfilled_runs"] == 1
    assert summary["skipped_runs"] == 0

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT member_order, skill_order, skill_slot, skill_code, usage_count
            FROM run_history_member_skill_usage
            ORDER BY member_order, skill_order
            """
        ).fetchall()

    assert rows == [
        (1, 1, "A1", "36601", 10),
        (2, 3, "A3", "69003", 5),
    ]
