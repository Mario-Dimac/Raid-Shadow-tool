from __future__ import annotations

import time
from pathlib import Path

from deep_battle_probe import (
    capture_forced_snapshot,
    capture_followup_file_snapshots,
    collect_runtime_candidate_markers,
    diff_runtime_candidate_markers,
    file_marker,
    hinted_battle_id,
    is_finish_battle_sqlite_event,
    is_interesting_log_line,
    marker_changed,
    should_capture_battle_context,
    should_force_file_snapshot,
    update_battle_activity,
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


def test_update_battle_activity_tracks_start_and_finish_lines() -> None:
    active = False
    active = update_battle_activity(active, ">>> CreateBattle with setup:Id: abc RandomSeed: 1 Stage: 2 FormationIndex 0")
    assert active is True
    active = update_battle_activity(active, "Change battle state [Loading -> Started]")
    assert active is True
    active = update_battle_activity(active, "BattleResult added: [Id=abc] TotalCount=1")
    assert active is False


def test_runtime_discovery_collects_and_diffs_candidate_files(tmp_path: Path) -> None:
    root = tmp_path / "raid_runtime"
    root.mkdir()
    included = root / "runtime_state.bin"
    included.write_bytes(b"abc")
    excluded = root / "serialization"
    excluded.write_bytes(b"ignored")
    ignored_dir = root / "LoadedTextures"
    ignored_dir.mkdir()
    (ignored_dir / "texture.cache").write_bytes(b"texture")

    initial = collect_runtime_candidate_markers(root, exclude_paths=[excluded])
    assert any(Path(row["path"]) == included for row in initial.values())
    assert all(Path(row["path"]) != excluded for row in initial.values())
    assert all("LoadedTextures" not in row["path"] for row in initial.values())

    time.sleep(0.01)
    included.write_bytes(b"abcdef")
    created = root / "runtime_delta.bin"
    created.write_bytes(b"delta")

    updated = collect_runtime_candidate_markers(root, exclude_paths=[excluded])
    changes = diff_runtime_candidate_markers(initial, updated)
    change_by_name = {Path(row["path"]).name: row["change_kind"] for row in changes}
    assert change_by_name["runtime_state.bin"] == "changed"
    assert change_by_name["runtime_delta.bin"] == "created"


def test_is_finish_battle_sqlite_event_matches_expected_shape() -> None:
    assert is_finish_battle_sqlite_event({"parsed": {"p": {"r": {"t": "FinishBattle"}}}}) is True
    assert is_finish_battle_sqlite_event({"parsed": {"p": {"r": {"t": "GetUserNotesV2"}}}}) is False
    assert is_finish_battle_sqlite_event({"parsed": {}}) is False


def test_capture_followup_file_snapshots_returns_empty_when_marker_does_not_change(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    path = tmp_path / "battleResults"
    path.write_bytes(b"stable-payload")
    last_marker = file_marker(path)

    saved_rows, updated_marker = capture_followup_file_snapshots(
        "battle_results",
        path,
        session_dir,
        battle_context={},
        last_marker=last_marker,
        reason="unit-test",
        attempts=2,
        delay_seconds=0.0,
    )

    assert saved_rows == []
    assert updated_marker["exists"] is True
    assert updated_marker["size"] == len(b"stable-payload")


def test_capture_forced_snapshot_saves_current_rich_payload_before_followup_placeholder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    events_path = session_dir / "events.jsonl"
    source_path = tmp_path / "battleResults"
    source_path.write_bytes(b"rich-payload-contents")
    file_states = {"battle_results": file_marker(source_path)}

    def fake_followup(*args, **kwargs):
        source_path.write_bytes(b"placeholder")
        return [], file_marker(source_path)

    monkeypatch.setattr(
        "deep_battle_probe.capture_followup_file_snapshots",
        fake_followup,
    )

    capture_forced_snapshot(
        "battle_results",
        source_path,
        session_dir,
        battle={"battle_id": "battle-1"},
        reason="BattleResult added: [Id=battle-1] TotalCount=1",
        events_path=events_path,
        file_states=file_states,
    )

    saved_bins = sorted((session_dir / "snapshots" / "battle_results").glob("*.bin"))
    assert len(saved_bins) == 1
    assert saved_bins[0].read_bytes() == b"rich-payload-contents"
    assert file_states["battle_results"]["size"] == len(b"placeholder")
