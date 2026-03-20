from __future__ import annotations

import cb_run_history
from pathlib import Path

from cb_run_history import (
    cancel_run_session,
    get_active_run_session,
    list_manual_runs,
    manual_run_summary,
    save_manual_run,
    start_run_session,
    stop_run_session,
)


def test_save_and_list_manual_runs(tmp_path: Path) -> None:
    history_path = tmp_path / "cb_manual_runs.jsonl"
    save_manual_run(
        {
            "team_name": "Test Team",
            "difficulty": "ultra_nightmare",
            "affinity": "void",
            "boss_turn": 50,
            "damage": 12345678,
            "members": ["A", "B", "C", "D", "E"],
            "notes": "manual test",
        },
        path=history_path,
    )

    runs = list_manual_runs(path=history_path)

    assert len(runs) == 1
    assert runs[0]["team_name"] == "Test Team"
    assert runs[0]["damage"] == 12345678.0
    assert runs[0]["boss_turn"] == 50


def test_manual_run_summary_groups_by_team(tmp_path: Path) -> None:
    history_path = tmp_path / "cb_manual_runs.jsonl"
    members_alpha = ["A", "B", "C", "D", "E"]
    members_beta = ["F", "G", "H", "I", "L"]
    save_manual_run({"team_name": "Alpha", "damage": 10, "boss_turn": 80, "members": members_alpha}, path=history_path)
    save_manual_run({"team_name": "Alpha", "damage": 30, "boss_turn": 60, "members": members_alpha}, path=history_path)
    save_manual_run({"team_name": "Beta", "damage": 20, "boss_turn": 40, "members": members_beta}, path=history_path)

    summary = manual_run_summary(list_manual_runs(path=history_path))

    assert summary["count"] == 3
    assert summary["best_run"]["team_name"] == "Alpha"
    assert summary["best_survival_run"]["boss_turn"] == 80
    assert summary["best_damage_run"]["damage"] == 30.0
    assert summary["team_stats"][0]["team_name"] == "Alpha"
    assert summary["team_stats"][0]["best_boss_turn"] == 80
    assert summary["team_stats"][0]["avg_boss_turn"] == 70.0
    assert summary["team_stats"][0]["best_damage"] == 30.0
    assert summary["team_stats"][0]["avg_damage"] == 20.0


def test_start_and_stop_session_records_run(tmp_path: Path) -> None:
    session_path = tmp_path / "active.json"
    history_path = tmp_path / "history.jsonl"
    members = ["A", "B", "C", "D", "E"]

    session = start_run_session(
        {
            "team_name": "Session Team",
            "difficulty": "ultra_nightmare",
            "affinity": "void",
            "members": members,
            "notes": "start note",
        },
        path=session_path,
    )
    assert session["team_name"] == "Session Team"
    assert get_active_run_session(session_path)["team_name"] == "Session Team"

    saved = stop_run_session(
        {
            "damage": 42,
            "boss_turn": 50,
            "notes": "stop note",
            "turn_log": ["T1 A3 Maneater", "T2 stun ok"],
        },
        session_path=session_path,
        history_path=history_path,
    )

    assert saved["damage"] == 42.0
    assert saved["boss_turn"] == 50
    assert saved["members"] == members
    assert "T1 A3 Maneater" in saved["turn_log"]
    assert "T2 stun ok" in saved["turn_log"]
    assert get_active_run_session(session_path) is None
    assert list_manual_runs(history_path)[0]["team_name"] == "Session Team"


def test_cancel_session_closes_without_saving(tmp_path: Path) -> None:
    session_path = tmp_path / "active.json"
    members = ["A", "B", "C", "D", "E"]

    start_run_session(
        {
            "team_name": "Test Free Run",
            "members": members,
        },
        path=session_path,
    )

    cancelled = cancel_run_session(session_path)

    assert cancelled is not None
    assert cancelled["team_name"] == "Test Free Run"
    assert get_active_run_session(session_path) is None


def test_start_session_can_autodetect_members_from_latest_battle(monkeypatch, tmp_path: Path) -> None:
    session_path = tmp_path / "active.json"

    monkeypatch.setattr(
        cb_run_history,
        "detect_latest_player_team",
        lambda: {"members": ["A", "B", "C", "D", "E"], "battle_id": "battle-123"},
    )

    session = start_run_session(
        {
            "team_name": "Auto Team",
            "members": [],
        },
        path=session_path,
    )

    assert session["members"] == ["A", "B", "C", "D", "E"]
    assert session["auto_detected_team"]["battle_id"] == "battle-123"


def test_stop_session_allows_missing_damage(tmp_path: Path) -> None:
    session_path = tmp_path / "active.json"
    history_path = tmp_path / "history.jsonl"

    start_run_session(
        {
            "team_name": "No Damage Team",
            "members": ["A", "B", "C", "D", "E"],
        },
        path=session_path,
    )

    saved = stop_run_session(
        {
            "boss_turn": 12,
        },
        session_path=session_path,
        history_path=history_path,
    )

    assert saved["damage"] == 0.0
    assert saved["damage_known"] is False
    assert saved["boss_turn"] == 12


def test_stop_session_uses_battle_result_damage_when_available(monkeypatch, tmp_path: Path) -> None:
    session_path = tmp_path / "active.json"
    history_path = tmp_path / "history.jsonl"

    start_run_session(
        {
            "team_name": "BattleResult Team",
            "members": ["A", "B", "C", "D", "E"],
        },
        path=session_path,
    )

    original = cb_run_history.refresh_live_monitor

    def fake_refresh(session):
        refreshed, new_entries = original(session)
        refreshed["battle_result_capture"] = {
            "damage_summary": {
                "total_damage": 555.5,
                "damage_by_champion": [],
            }
        }
        return refreshed, new_entries

    monkeypatch.setattr(cb_run_history, "refresh_live_monitor", fake_refresh)

    saved = stop_run_session(
        {},
        session_path=session_path,
        history_path=history_path,
    )

    assert saved["damage"] == 555.5
    assert saved["damage_known"] is True


def test_stop_session_recovers_run_without_active_session(monkeypatch, tmp_path: Path) -> None:
    history_path = tmp_path / "history.jsonl"

    monkeypatch.setattr(
        cb_run_history,
        "detect_latest_player_team",
        lambda: {"members": ["A", "B", "C", "D", "E"], "team_id": ""},
    )

    saved = stop_run_session(
        {
            "notes": "recovered",
            "boss_turn": 7,
            "battle_result_capture": {
                "damage_summary": {
                    "total_damage": 321.0,
                }
            },
        },
        session_path=tmp_path / "missing.json",
        history_path=history_path,
    )

    assert saved["source"] == "recovered_session"
    assert saved["team_name"] == "A / B + 3"
    assert saved["damage"] == 321.0
    assert saved["members"] == ["A", "B", "C", "D", "E"]
    assert list_manual_runs(history_path)[0]["team_name"] == "A / B + 3"
