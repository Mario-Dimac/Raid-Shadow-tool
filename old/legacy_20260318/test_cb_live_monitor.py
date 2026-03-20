from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cb_live_monitor import detect_latest_player_team, extract_combat_log_entries, file_marker, merge_turn_logs, poll_sqlite_events


def test_extract_combat_log_entries_filters_only_battle_lines() -> None:
    lines = [
        "INF | 13:38:40.125 | 1077572 - [BattleStateNotifier]",
        "Change battle state [Loading -> Started]",
        "random unrelated line",
        "BattleResult added: [Id=abc-def] TotalCount=1",
    ]

    entries = extract_combat_log_entries(lines)

    assert entries == [
        "[client-log] INF | 13:38:40.125 | 1077572 - [BattleStateNotifier]",
        "[client-log] Change battle state [Loading -> Started]",
        "[client-log] BattleResult added: [Id=abc-def] TotalCount=1",
    ]


def test_merge_turn_logs_preserves_order_and_skips_duplicates() -> None:
    merged = merge_turn_logs(
        ["T1 buff ok", "T2 stun ok"],
        "T2 stun ok\nT3 wipe",
        ["T1 buff ok", "T4 finish"],
    )

    assert merged == ["T1 buff ok", "T2 stun ok", "T3 wipe", "T4 finish"]


def test_poll_sqlite_events_reads_incremental_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "raidV2.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE Events (Id INTEGER PRIMARY KEY, Body TEXT)")
    cur.execute("INSERT INTO Events (Id, Body) VALUES (1, ?)", ('{"type":"battle_start"}',))
    cur.execute("INSERT INTO Events (Id, Body) VALUES (2, ?)", ("battle finished",))
    conn.commit()
    conn.close()

    entries, state = poll_sqlite_events(db_path, {"last_id": 0})

    assert len(entries) == 2
    assert entries[0] == '[sqlite raidV2.db#1] {"type": "battle_start"}'
    assert entries[1] == "[sqlite raidV2.db#2] battle finished"
    assert state["last_id"] == 2

    later_entries, later_state = poll_sqlite_events(db_path, state)

    assert later_entries == []
    assert later_state["last_id"] == 2


def test_detect_latest_player_team_reads_names_from_create_battle_block(tmp_path: Path) -> None:
    log_path = tmp_path / "log.txt"
    raw_path = tmp_path / "raw_account.json"
    log_path.write_text(
        "\n".join(
                [
                    ">>> CreateBattle with setup:Id: 54c085d8-0bff-4d58-82e4-bcca77402873 RandomSeed: 7 Stage: 7011801 FormationIndex 0",
                " First Team: Owner: 83832666, Hero Setups:",
                "Round: 1 Slot: 1 Type: 3146 Grd: Stars6 Lvl: 60",
                "Round: 1 Slot: 2 Type: 46 Grd: Stars6 Lvl: 60",
                "Round: 1 Slot: 3 Type: 5156 Grd: Stars6 Lvl: 60",
                "Round: 1 Slot: 4 Type: 396 Grd: Stars6 Lvl: 60",
                "Round: 1 Slot: 5 Type: 4506 Grd: Stars6 Lvl: 60",
                " Second Team: Owner: -1, Hero Setups:",
            ]
        ),
        encoding="utf-8",
    )
    raw_path.write_text(
        json.dumps(
            {
                "roster": [
                    {"type_id": 3146, "name": "Pain Keeper"},
                    {"type_id": 46, "name": "Coldheart"},
                    {"type_id": 5156, "name": "Dolor Lorekeeper"},
                    {"type_id": 396, "name": "Heiress"},
                    {"type_id": 4506, "name": "Frozen Banshee"},
                ]
            }
        ),
        encoding="utf-8",
    )

    detected = detect_latest_player_team(log_path, raw_path)

    assert detected["stage_id"] == "7011801"
    assert detected["members"] == [
        "Pain Keeper",
        "Coldheart",
        "Dolor Lorekeeper",
        "Heiress",
        "Frozen Banshee",
    ]


def test_file_marker_uses_only_prefix_for_hex_preview(tmp_path: Path) -> None:
    payload = bytes(range(64))
    sample_path = tmp_path / "sample.bin"
    sample_path.write_bytes(payload)

    marker = file_marker(sample_path)

    assert marker["size"] == 64
    assert marker["hex_preview"] == payload[:24].hex()
