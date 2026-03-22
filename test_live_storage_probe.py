from __future__ import annotations

from pathlib import Path

from live_storage_probe import WatchRoot, build_watch_state, diff_states, fast_file_marker, read_file_preview


def test_fast_file_marker_for_missing_file(tmp_path: Path) -> None:
    marker = fast_file_marker(tmp_path / "missing.bin")
    assert marker["exists"] is False
    assert marker["size"] == 0


def test_build_watch_state_and_diff_for_created_modified_deleted(tmp_path: Path) -> None:
    root_dir = tmp_path / "Session Storage"
    root_dir.mkdir()
    first = root_dir / "000001.log"
    first.write_text("abc", encoding="utf-8")
    roots = [WatchRoot("session_storage", root_dir, recursive=False)]

    state_a = build_watch_state(roots)
    assert "000001.log" in state_a["session_storage"]

    first.write_text("abcd", encoding="utf-8")
    second = root_dir / "000002.ldb"
    second.write_bytes(b"\x00\x01")
    state_b = build_watch_state(roots)
    changes = diff_states(state_a, state_b)
    assert {item["change_type"] for item in changes} == {"created", "modified"}

    second.unlink()
    state_c = build_watch_state(roots)
    deleted_changes = diff_states(state_b, state_c)
    assert any(item["change_type"] == "deleted" for item in deleted_changes)


def test_read_file_preview_for_binary_payload(tmp_path: Path) -> None:
    path = tmp_path / "payload.bin"
    path.write_bytes(b"ABC\x00\x01xyz")
    preview = read_file_preview(path, max_bytes=8)
    assert preview["preview_hex"].startswith("414243")
    assert preview["preview_ascii"].startswith("ABC")
