from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict

from client_run_probe import DEFAULT_BATTLE_RESULTS_PATH, DEFAULT_LOG_PATH, decode_binary_payload
from deep_battle_probe import (
    configure_stdout,
    ensure_dir,
    file_marker,
    latest_battle_context,
    marker_changed,
    read_log_append,
    safe_print,
    utc_now,
    utc_slug,
    write_jsonl,
    write_text,
)


OUTPUT_ROOT = Path(__file__).resolve().parent / "input" / "battle_results_probe"
INTERESTING_TOKENS = (
    "ProcessBattleFinish",
    "BattleResult added:",
    "BattleResult deleted:",
    "Finishing Battle -",
    "StageCompleted",
    "BattleFinish",
    "Change battle state",
)


def is_battle_results_trigger(line: str) -> bool:
    lowered = line.lower()
    return (
        "processbattlefinish" in lowered
        or "battleresult added:" in lowered
        or "finishing battle -" in lowered
    )


def is_interesting_line(line: str) -> bool:
    lowered = line.lower()
    return any(token.lower() in lowered for token in INTERESTING_TOKENS)


def create_session_dir() -> Path:
    session_dir = ensure_dir(OUTPUT_ROOT / utc_slug())
    ensure_dir(session_dir / "snapshots")
    return session_dir


def save_session_metadata(session_dir: Path, burst_seconds: float, sample_interval: float) -> None:
    payload = {
        "created_at": utc_now(),
        "log_path": str(DEFAULT_LOG_PATH),
        "battle_results_path": str(DEFAULT_BATTLE_RESULTS_PATH),
        "burst_seconds": burst_seconds,
        "sample_interval": sample_interval,
    }
    (session_dir / "session.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_battle_results_snapshot(session_dir: Path, battle_context: Dict[str, Any], reason: str) -> Dict[str, Any]:
    marker = file_marker(DEFAULT_BATTLE_RESULTS_PATH)
    snapshots_dir = ensure_dir(session_dir / "snapshots")
    payload = DEFAULT_BATTLE_RESULTS_PATH.read_bytes() if DEFAULT_BATTLE_RESULTS_PATH.exists() else b""
    stem = f"{utc_slug()}_battle_results_{marker['size']}_{str(marker['sha256'])[:12]}"
    raw_path = snapshots_dir / f"{stem}.bin"
    meta_path = snapshots_dir / f"{stem}.json"
    raw_path.write_bytes(payload)
    meta = {
        "captured_at": utc_now(),
        "reason": reason,
        "source_path": str(DEFAULT_BATTLE_RESULTS_PATH),
        "marker": marker,
        "battle_context": battle_context,
        "decoded": decode_binary_payload(DEFAULT_BATTLE_RESULTS_PATH) if DEFAULT_BATTLE_RESULTS_PATH.exists() else {},
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=repr), encoding="utf-8")
    return {"raw_path": str(raw_path), "meta_path": str(meta_path), "marker": marker, "reason": reason}


def run_watch(duration_seconds: float, burst_seconds: float, sample_interval: float) -> Path:
    session_dir = create_session_dir()
    save_session_metadata(session_dir, burst_seconds=burst_seconds, sample_interval=sample_interval)
    events_path = session_dir / "events.jsonl"
    log_capture_path = session_dir / "interesting_log_lines.txt"
    configure_stdout()

    safe_print(f"BattleResults burst session: {session_dir}")
    safe_print("In ascolto sul finale battle per catturare battleResults ad alta frequenza...")

    log_offset = DEFAULT_LOG_PATH.stat().st_size if DEFAULT_LOG_PATH.exists() else 0
    started_at = time.time()
    burst_until = 0.0
    next_sample_at = 0.0
    last_saved_marker: Dict[str, Any] = {"exists": False, "size": 0, "mtime_ns": 0, "sha256": ""}
    active_reason = ""

    while True:
        now = time.time()
        captured_at = utc_now()

        new_lines, log_offset = read_log_append(DEFAULT_LOG_PATH, log_offset)
        interesting_lines = [line for line in new_lines if is_interesting_line(line)]
        for line in interesting_lines:
            safe_print(f"[log] {line}")
            write_text(log_capture_path, line)
            write_jsonl(
                events_path,
                {
                    "captured_at": captured_at,
                    "event_type": "log_line",
                    "line": line,
                },
            )
            if is_battle_results_trigger(line):
                burst_until = max(burst_until, now + burst_seconds)
                next_sample_at = now
                active_reason = line
                safe_print(f"[burst] trigger -> {line}")

        if burst_until > now and now >= next_sample_at:
            battle_context = latest_battle_context(
                DEFAULT_LOG_PATH,
                Path(__file__).resolve().parent / "input" / "raw_account.json",
                Path(__file__).resolve().parent / "input" / "normalized_account.json",
            )
            current_marker = file_marker(DEFAULT_BATTLE_RESULTS_PATH)
            if current_marker.get("exists"):
                should_save = (
                    not bool(last_saved_marker.get("exists"))
                    or marker_changed(last_saved_marker, current_marker)
                )
                if should_save:
                    saved = save_battle_results_snapshot(session_dir, battle_context, active_reason or "burst_sample")
                    last_saved_marker = current_marker
                    safe_print(
                        f"[battle_results] size={saved['marker'].get('size')} sha={str(saved['marker'].get('sha256'))[:12]}"
                    )
                    write_jsonl(
                        events_path,
                        {
                            "captured_at": captured_at,
                            "event_type": "battle_results_snapshot",
                            "saved": saved,
                            "battle_context": battle_context,
                        },
                    )
            next_sample_at = now + sample_interval

        if duration_seconds > 0 and (now - started_at) >= duration_seconds:
            safe_print("Durata massima raggiunta, chiusura probe.")
            return session_dir

        time.sleep(min(sample_interval, 0.05))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe mirato a battleResults con burst capture sul finale della fight."
    )
    parser.add_argument("--duration", type=float, default=300.0, help="Durata massima in secondi.")
    parser.add_argument("--burst-seconds", type=float, default=5.0, help="Quanto dura la finestra di burst dopo un trigger.")
    parser.add_argument("--sample-interval", type=float, default=0.05, help="Intervallo tra campioni di battleResults durante il burst.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session_dir = run_watch(
        duration_seconds=max(args.duration, 0.0),
        burst_seconds=max(args.burst_seconds, 0.5),
        sample_interval=max(args.sample_interval, 0.01),
    )
    safe_print(f"Sessione salvata in: {session_dir}")


if __name__ == "__main__":
    main()
