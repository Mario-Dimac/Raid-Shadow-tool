from __future__ import annotations

import threading

import cbforge_server


def test_runtime_state_snapshot_exposes_basic_server_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        cbforge_server,
        "SERVER_RUNTIME_STATE",
        {
            "pid": 999,
            "started_at": "2026-03-15T10:00:00+00:00",
            "boot_monotonic": 100.0,
            "host": "127.0.0.1",
            "port": 8765,
            "shutdown_requested": True,
        },
    )
    monkeypatch.setattr(cbforge_server.time, "monotonic", lambda: 112.4)
    monkeypatch.setattr(cbforge_server.os, "getpid", lambda: 999)

    snapshot = cbforge_server.runtime_state_snapshot()

    assert snapshot == {
        "pid": 999,
        "started_at": "2026-03-15T10:00:00+00:00",
        "uptime_seconds": 12.4,
        "host": "127.0.0.1",
        "port": 8765,
        "shutdown_requested": True,
    }


def test_build_runtime_diagnostics_collects_server_watch_state(monkeypatch) -> None:
    monkeypatch.setattr(
        cbforge_server,
        "GLOBAL_LIVE_COMBAT_STATE",
        {
            "live_summary": {"battle_id": "battle-1", "entries": 3},
            "battle_result_capture": {
                "captured_at": "2026-03-15T10:10:00+00:00",
                "size": 128,
                "sha256": "abc123",
                "snapshot_path": "input/capture.bin",
            },
            "live_feed": ["one", "two", "three"],
        },
    )
    monkeypatch.setattr(
        cbforge_server,
        "BATTLE_RESULT_WATCH_STATE",
        {
            "last_seen_signature": "128:10",
            "last_captured_signature": "128:10",
            "last_captured_sha256": "abc123",
            "last_size": 128,
            "last_mtime_ns": 10,
            "last_change_monotonic": 11.0,
        },
    )
    monkeypatch.setattr(
        cbforge_server,
        "get_active_run_session",
        lambda: {
            "team_name": "UNM Test",
            "started_at": "2026-03-15T10:00:00+00:00",
            "live_feed": ["a", "b"],
            "live_summary": {"battle_id": "battle-1"},
        },
    )
    monkeypatch.setattr(cbforge_server, "runtime_state_snapshot", lambda: {"pid": 1234})
    monkeypatch.setattr(cbforge_server, "process_memory_snapshot", lambda: {"rss_bytes": 2048, "source": "test"})
    monkeypatch.setattr(
        cbforge_server,
        "summarize_threads",
        lambda: [{"name": "MainThread", "ident": 1, "daemon": False, "alive": True}],
    )
    monkeypatch.setattr(
        cbforge_server,
        "battle_result_file_state",
        lambda path=cbforge_server.BATTLE_RESULTS_PATH: {
            "exists": True,
            "size": 128,
            "mtime_ns": 10,
            "signature": "128:10",
        },
    )
    monkeypatch.setattr(threading, "enumerate", lambda: [threading.current_thread()])

    diagnostics = cbforge_server.build_runtime_diagnostics()

    assert diagnostics["server"] == {"pid": 1234}
    assert diagnostics["memory"] == {"rss_bytes": 2048, "source": "test"}
    assert diagnostics["thread_count"] == 1
    assert diagnostics["active_run_session"] == {
        "present": True,
        "team_name": "UNM Test",
        "started_at": "2026-03-15T10:00:00+00:00",
        "entries": 2,
        "battle_id": "battle-1",
    }
    assert diagnostics["global_live_summary"] == {"battle_id": "battle-1", "entries": 3}
    assert diagnostics["battle_result_capture"] == {
        "captured_at": "2026-03-15T10:10:00+00:00",
        "size": 128,
        "sha256": "abc123",
        "snapshot_path": "input/capture.bin",
    }


def test_html_exposes_clear_gear_refresh_action_and_help_text() -> None:
    assert "Aggiorna elenco equipaggiamento" in cbforge_server.HTML
    assert "Controlla assetto team" in cbforge_server.HTML
    assert "Guida rapida" in cbforge_server.HTML
    assert "/api/refresh-gear" in cbforge_server.HTML
    assert "Lettura ciclo boss" in cbforge_server.HTML
    assert "Nessuna Prima Key Affidabile" in cbforge_server.HTML
    assert "miglior fallback attuale" in cbforge_server.HTML
