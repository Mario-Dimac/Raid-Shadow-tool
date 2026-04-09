from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import run_history_importer
from forge_db import bootstrap_database
from run_history_importer import backfill_probe_effect_timeline, backfill_probe_skill_usage, event_battle_id, import_probe_session, select_best_rich_battle_result_events


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


def test_select_best_rich_battle_result_events_keeps_one_event_per_battle_id() -> None:
    selected = select_best_rich_battle_result_events(
        [
            {
                "captured_at": "2026-04-05T19:57:14+00:00",
                "source_name": "battle_results",
                "saved": {
                    "reason": "BattleResult added: [Id=battle-1] TotalCount=1",
                    "marker": {"size": 12680},
                    "raw_path": "battle-1-rich-a.bin",
                },
                "battle": {"battle_id": "battle-1"},
            },
            {
                "captured_at": "2026-04-05T19:57:14+00:00",
                "source_name": "battle_results",
                "saved": {
                    "reason": "BattleResult added: [Id=battle-1] TotalCount=1",
                    "marker": {"size": 12690},
                    "raw_path": "battle-1-rich-b.bin",
                },
                "battle": {"battle_id": "battle-1"},
            },
            {
                "captured_at": "2026-04-05T20:29:22+00:00",
                "source_name": "battle_results",
                "saved": {
                    "reason": "BattleResult added: [Id=battle-2] TotalCount=1",
                    "marker": {"size": 12250},
                    "raw_path": "battle-2-rich.bin",
                },
                "battle": {"battle_id": "battle-2"},
            },
        ]
    )

    assert len(selected) == 2
    assert selected[0]["saved"]["raw_path"] == "battle-1-rich-b.bin"
    assert selected[1]["saved"]["raw_path"] == "battle-2-rich.bin"


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


def test_import_probe_session_persists_total_damage_candidate(tmp_path: Path, monkeypatch) -> None:
    client_root = tmp_path / "client_probe"
    live_root = tmp_path / "live_storage_probe"
    session_slug = "20260325T173527Z"
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
        "battle_id": "fbbbae7e-58d1-461e-8660-7c86297796c8",
        "stage_id": "4019024",
        "formation_index": 0,
        "player_team": [
            {"slot": 1, "type_id": 3666, "name": "Rakka Viletide", "grade": "Stars6", "level": 60},
        ],
        "enemy_rows": [{"slot": 1, "type_id": 22286, "name": "Demon Lord", "grade": "Stars6", "level": 250}],
    }
    client_events = [
        {"captured_at": "2026-03-25T18:00:00+00:00", "event_type": "battle_context", "battle": battle},
        {"captured_at": "2026-03-25T18:00:02+00:00", "event_type": "log_line", "line": "Change battle state [Loading -> Started]"},
        {
            "captured_at": "2026-03-25T18:06:12+00:00",
            "event_type": "forced_file_snapshot",
            "source_name": "battle_results",
            "saved": {
                "raw_path": str(raw_asset),
                "meta_path": str(meta_asset),
                "marker": {"size": 12399, "sha256": "abc123"},
            },
            "battle": battle,
        },
        {"captured_at": "2026-03-25T18:06:13+00:00", "event_type": "log_line", "line": "Change battle state [Started -> Finished]"},
    ]
    write_jsonl(client_session / "events.jsonl", client_events)
    write_jsonl(live_session / "events.jsonl", [])

    monkeypatch.setattr(
        run_history_importer,
        "extract_damage_summary",
        lambda path: {
            "total_damage": 41_949_610,
            "damage_taken_trusted": False,
            "total_damage_status": "candidate_demon_lord_s_a_dt_high32",
            "member_damage_status": "candidate_demon_lord_manual_fit_normalized_total",
            "members": [
                {
                    "member_order": 1,
                    "damage_done": 1_408_214,
                    "damage_done_status": "candidate_demon_lord_manual_fit_normalized_total",
                    "damage_taken": 119_943,
                    "damage_taken_status": "candidate_member_dt_high32_clan_boss",
                    "raw_damage_done": 1_441_193,
                    "raw_damage_taken": 119_943,
                },
            ],
        },
    )
    monkeypatch.setattr(
        run_history_importer,
        "extract_effect_timeline",
        lambda path, hero_types_path=None: {
            "status_timeline_status": "candidate_from_cast_order_plus_skill_metadata",
            "status_timeline_count": 1,
            "timeline": [
                {
                    "event_index": 13,
                    "source_slot": 0,
                    "source_name": "Rakka Viletide",
                    "source_type_id": 3666,
                    "target_party_id": 83832666,
                    "target_slot": 0,
                    "skill_order": 2,
                    "skill_slot": "A2",
                    "skill_code": "36602",
                    "skill_name": "Oozing Blessing",
                    "skill_type": "Active",
                    "skill_provider": "ayumilove",
                    "status_effects": [
                        {
                            "effect_type": "increase_atk",
                            "category": "buff",
                            "action": "place",
                            "target": "all_allies",
                            "duration": 2,
                            "chance": None,
                            "effect_value": 50.0,
                            "resolution": "candidate_from_skill_metadata",
                            "condition_text": "Places Increase ATK.",
                        },
                        {
                            "effect_type": "shield",
                            "category": "buff",
                            "action": "place",
                            "target": "all_allies",
                            "duration": 2,
                            "chance": None,
                            "effect_value": 25.0,
                            "resolution": "candidate_from_skill_metadata",
                            "condition_text": "Places Shield.",
                        },
                    ],
                }
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

    assert summary["imported_runs"] == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT total_damage, context_json
            FROM run_history_runs
            WHERE battle_id = ?
            """,
            ("fbbbae7e-58d1-461e-8660-7c86297796c8",),
        ).fetchone()

    assert row is not None
    assert row[0] == 41_949_610
    context = json.loads(row[1])
    assert context["total_damage_status"] == "candidate_demon_lord_s_a_dt_high32"
    assert context["member_damage_status"] == "candidate_demon_lord_manual_fit_normalized_total"
    assert context["effect_timeline_status"] == "candidate_from_cast_order_plus_skill_metadata"
    assert context["effect_timeline_rows"] == 1

    with sqlite3.connect(db_path) as conn:
        metric_row = conn.execute(
            """
            SELECT damage_done, damage_taken, metric_payload_json
            FROM run_history_member_metrics
            WHERE run_id = 1 AND member_order = 1
            """
        ).fetchone()
        effect_rows = conn.execute(
            """
            SELECT source_name, skill_slot, effect_type, effect_action
            FROM run_history_effect_timeline
            ORDER BY timeline_index, effect_index
            """
        ).fetchall()

    assert metric_row is not None
    assert metric_row[0] == 1_408_214
    assert metric_row[1] == 119_943
    assert json.loads(metric_row[2])["damage_done_status"] == "candidate_demon_lord_manual_fit_normalized_total"
    assert json.loads(metric_row[2])["damage_taken_trusted"] is False
    assert json.loads(metric_row[2])["damage_taken_status"] == "candidate_member_dt_high32_clan_boss"
    assert effect_rows == [
        ("Rakka Viletide", "A2", "increase_atk", "place"),
        ("Rakka Viletide", "A2", "shield", "place"),
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


def test_backfill_probe_effect_timeline_updates_existing_runs(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "cbforge.sqlite3"
    source_path = tmp_path / "normalized_account.json"
    source_path.write_text(json.dumps({"champions": [], "gear": [], "account_bonuses": []}), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    raw_asset = tmp_path / "battle_results.bin"
    raw_asset.write_bytes(b"rich")

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
            INSERT INTO run_history_assets (
                run_id, asset_order, asset_kind, asset_path, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, 1, "client_probe_battle_results_bin", str(raw_asset), "{}"),
        )
        conn.commit()

    monkeypatch.setattr(
        run_history_importer,
        "extract_effect_timeline",
        lambda path, hero_types_path=None: {
            "status_timeline_status": "candidate_from_cast_order_plus_skill_metadata",
            "status_timeline_count": 1,
            "timeline": [
                {
                    "event_index": 8,
                    "source_slot": 4,
                    "source_name": "Stag Knight",
                    "source_type_id": 4496,
                    "target_party_id": -1,
                    "target_slot": 5,
                    "skill_order": 2,
                    "skill_slot": "A2",
                    "skill_code": "44902",
                    "skill_name": "Huntmaster",
                    "skill_type": "Active",
                    "skill_provider": "ayumilove",
                    "status_effects": [
                        {"effect_type": "decrease_def", "category": "debuff", "action": "place", "target": "enemy", "duration": 2},
                        {"effect_type": "decrease_atk", "category": "debuff", "action": "place", "target": "enemy", "duration": 2},
                    ],
                }
            ],
        },
    )

    summary = backfill_probe_effect_timeline(db_path=db_path)

    assert summary["backfilled_runs"] == 1
    assert summary["skipped_runs"] == 0

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT source_name, skill_slot, effect_type, effect_action
            FROM run_history_effect_timeline
            ORDER BY timeline_index, effect_index
            """
        ).fetchall()
        context_row = conn.execute(
            "SELECT context_json FROM run_history_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()

    assert rows == [
        ("Stag Knight", "A2", "decrease_def", "place"),
        ("Stag Knight", "A2", "decrease_atk", "place"),
    ]
    assert context_row is not None
    context = json.loads(context_row[0])
    assert context["effect_timeline_status"] == "candidate_from_cast_order_plus_skill_metadata"
    assert context["effect_timeline_rows"] == 1
