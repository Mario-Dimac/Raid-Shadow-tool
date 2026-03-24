from __future__ import annotations

from deep_battle_probe import (
    hinted_battle_id,
    is_interesting_log_line,
    marker_changed,
    should_capture_battle_context,
    should_force_file_snapshot,
)


def test_is_interesting_log_line_filters_expected_tokens() -> None:
    assert is_interesting_log_line(">>> CreateBattle with setup:Id: abc RandomSeed: 1 Stage: 2 FormationIndex 0")
    assert is_interesting_log_line("Round: 1 Slot: 1 Type: 396 Grd: Stars6 Lvl: 60")
    assert is_interesting_log_line("Change battle state [Loading -> Started]")
    assert not is_interesting_log_line("Loaded texture bundle")


def test_marker_changed_detects_real_changes() -> None:
    left = {"exists": True, "size": 11, "mtime_ns": 10, "sha256": "aaa"}
    assert not marker_changed(left, dict(left))
    assert marker_changed(left, {"exists": True, "size": 12, "mtime_ns": 10, "sha256": "aaa"})
    assert marker_changed(left, {"exists": True, "size": 11, "mtime_ns": 11, "sha256": "aaa"})
    assert marker_changed(left, {"exists": True, "size": 11, "mtime_ns": 10, "sha256": "bbb"})


def test_context_and_forced_snapshot_rules() -> None:
    create_line = ">>> CreateBattle with setup:Id: abc RandomSeed: 1 Stage: 2 FormationIndex 0"
    result_line = "BattleResult added: [Id=abc] TotalCount=1"
    replay_setup_line = "Created setup for battle Id - 912db89b-69b9-41c7-a672-44d0c3703639"
    replay_started_line = "Change battle state [StartCmdSucceed -> Started]"

    assert should_capture_battle_context(create_line)
    assert should_capture_battle_context(replay_setup_line)
    assert should_force_file_snapshot("workers_serialization", create_line)
    assert should_force_file_snapshot("workers_serialization", replay_started_line)
    assert should_force_file_snapshot("battle_results", result_line)
    assert not should_force_file_snapshot("workers_serialization", result_line)


def test_hinted_battle_id_extracts_replay_patterns() -> None:
    assert hinted_battle_id("Created setup for battle Id - 912db89b-69b9-41c7-a672-44d0c3703639") == "912db89b-69b9-41c7-a672-44d0c3703639"
    assert hinted_battle_id("BattleSetup cached: [ Id = 75f03bd8-7c8c-4062-90a7-cf828d6be2d4, StartTime = 23/03/2026 19:22:01 ]") == "75f03bd8-7c8c-4062-90a7-cf828d6be2d4"
