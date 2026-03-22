from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Tuple

from client_run_probe import (
    DEFAULT_BATTLE_RESULTS_PATH,
    DEFAULT_LOG_PATH,
    DEFAULT_NORMALIZED_ACCOUNT_PATH,
    DEFAULT_RAID_LOCALLOW,
    DEFAULT_RAW_ACCOUNT_PATH,
    DEFAULT_WORKERS_SERIALIZATION_PATH,
    decode_binary_payload,
    load_champion_type_name_map,
    parse_latest_battle_block,
    string_value,
)


OUTPUT_ROOT = Path(__file__).resolve().parent / "input" / "client_probe"
SQLITE_PATHS = {
    "raid.db": DEFAULT_RAID_LOCALLOW / "raid.db",
    "raidV2.db": DEFAULT_RAID_LOCALLOW / "raidV2.db",
}
INTERESTING_LOG_TOKENS = (
    "CreateBattle",
    "BattleStateNotifier",
    "Change battle state",
    "BattleViewContext",
    "BattleResult",
    "BattleSetup",
    "FinishBattleCmd",
    "First Team:",
    "Second Team:",
    "Round:",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_stdout() -> None:
    stream = getattr(sys, "stdout", None)
    if stream is None:
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def write_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=repr) + "\n")


def write_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")


def file_marker(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "size": 0, "mtime_ns": 0, "sha256": ""}
    stat = path.stat()
    payload = path.read_bytes()
    return {
        "exists": True,
        "size": len(payload),
        "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
        "sha256": sha256(payload).hexdigest() if payload else "",
    }


def marker_changed(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return (
        bool(left.get("exists")) != bool(right.get("exists"))
        or int_value(left.get("size")) != int_value(right.get("size"))
        or int_value(left.get("mtime_ns")) != int_value(right.get("mtime_ns"))
        or string_value(left.get("sha256")) != string_value(right.get("sha256"))
    )


def read_log_append(path: Path, offset: int) -> Tuple[List[str], int]:
    if not path.exists():
        return [], 0
    file_size = path.stat().st_size
    if offset > file_size:
        offset = 0
    if offset == file_size:
        return [], file_size
    with path.open("rb") as handle:
        handle.seek(offset)
        raw = handle.read()
    lines = raw.decode("utf-8", errors="ignore").splitlines()
    return lines, file_size


def is_interesting_log_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(token.lower() in stripped.lower() for token in INTERESTING_LOG_TOKENS)


def should_capture_battle_context(line: str) -> bool:
    lowered = line.lower()
    return "createbattle with setup:" in lowered


def should_force_file_snapshot(source_name: str, line: str) -> bool:
    lowered = line.lower()
    if source_name == "battle_results":
        return "battleresult added:" in lowered or "processbattlefinish" in lowered or "finishing battle -" in lowered
    if source_name == "workers_serialization":
        return "createbattle with setup:" in lowered or "change battle state [loading -> started]" in lowered
    return False


def poll_sqlite_events(path: Path, last_id: int) -> Tuple[List[Dict[str, Any]], int]:
    if not path.exists():
        return [], last_id
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        tables = {row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "Events" not in tables:
            conn.close()
            return [], last_id
        rows = cur.execute(
            "SELECT Id, Body FROM Events WHERE Id > ? ORDER BY Id ASC LIMIT 200",
            (last_id,),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return [], last_id

    entries: List[Dict[str, Any]] = []
    next_last_id = last_id
    for row_id, body in rows:
        next_last_id = max(next_last_id, int_value(row_id))
        text = body.decode("utf-8", errors="ignore") if isinstance(body, bytes) else string_value(body)
        cleaned = text.replace("\x00", "").strip()
        parsed: Any = None
        if cleaned:
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                parsed = None
        entries.append(
            {
                "id": int_value(row_id),
                "body": cleaned,
                "parsed": parsed,
            }
        )
    return entries, next_last_id


def save_binary_snapshot(
    source_name: str,
    path: Path,
    session_dir: Path,
    battle_context: Dict[str, Any],
    reason: str = "",
) -> Dict[str, Any]:
    marker = file_marker(path)
    snapshots_dir = ensure_dir(session_dir / "snapshots" / source_name)
    payload = path.read_bytes() if path.exists() else b""
    stem = f"{utc_slug()}_{source_name}_{marker['size']}_{string_value(marker['sha256'])[:12]}"
    raw_path = snapshots_dir / f"{stem}.bin"
    meta_path = snapshots_dir / f"{stem}.json"
    raw_path.write_bytes(payload)
    meta = {
        "captured_at": utc_now(),
        "source_name": source_name,
        "source_path": str(path),
        "marker": marker,
        "battle_context": battle_context,
        "reason": reason,
        "decoded": decode_binary_payload(path) if path.exists() else {},
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=repr), encoding="utf-8")
    return {"raw_path": str(raw_path), "meta_path": str(meta_path), "marker": marker, "reason": reason}


def latest_battle_context(log_path: Path, raw_account_path: Path, normalized_account_path: Path) -> Dict[str, Any]:
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines() if log_path.exists() else []
    name_map = load_champion_type_name_map(raw_account_path, normalized_account_path)
    return parse_latest_battle_block(lines, name_map)


def create_session_dir() -> Path:
    session_dir = ensure_dir(OUTPUT_ROOT / utc_slug())
    ensure_dir(session_dir / "snapshots")
    return session_dir


def write_session_metadata(session_dir: Path) -> None:
    payload = {
        "created_at": utc_now(),
        "log_path": str(DEFAULT_LOG_PATH),
        "battle_results_path": str(DEFAULT_BATTLE_RESULTS_PATH),
        "workers_serialization_path": str(DEFAULT_WORKERS_SERIALIZATION_PATH),
        "sqlite_paths": {name: str(path) for name, path in SQLITE_PATHS.items()},
    }
    (session_dir / "session.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_watch(interval_seconds: float, duration_seconds: float) -> Path:
    session_dir = create_session_dir()
    write_session_metadata(session_dir)
    events_path = session_dir / "events.jsonl"
    log_capture_path = session_dir / "interesting_log_lines.txt"
    configure_stdout()

    safe_print(f"Deep probe session: {session_dir}")
    safe_print("In ascolto su log, sqlite events, battleResults e workers-serialization...")

    log_offset = DEFAULT_LOG_PATH.stat().st_size if DEFAULT_LOG_PATH.exists() else 0
    sqlite_state = {name: 0 for name in SQLITE_PATHS}
    file_states = {
        "battle_results": file_marker(DEFAULT_BATTLE_RESULTS_PATH),
        "workers_serialization": file_marker(DEFAULT_WORKERS_SERIALIZATION_PATH),
    }
    started_at = time.time()

    while True:
        now = utc_now()

        new_lines, log_offset = read_log_append(DEFAULT_LOG_PATH, log_offset)
        interesting_lines = [line for line in new_lines if is_interesting_log_line(line)]
        if interesting_lines:
            for line in interesting_lines:
                safe_print(f"[log] {line}")
                write_text(log_capture_path, line)
                write_jsonl(
                    events_path,
                    {
                        "captured_at": now,
                        "event_type": "log_line",
                        "line": line,
                    },
                )
            if any(should_capture_battle_context(line) for line in interesting_lines):
                battle = latest_battle_context(
                    DEFAULT_LOG_PATH,
                    DEFAULT_RAW_ACCOUNT_PATH,
                    DEFAULT_NORMALIZED_ACCOUNT_PATH,
                )
                write_jsonl(
                    events_path,
                    {
                        "captured_at": now,
                        "event_type": "battle_context",
                        "battle": battle,
                    },
                )
                if battle:
                    members = ", ".join(str(name) for name in battle.get("player_members") or [])
                    safe_print(
                        f"[battle] id={battle.get('battle_id')} stage={battle.get('stage_id')} team={members}"
                    )
            for source_name, source_path in (
                ("battle_results", DEFAULT_BATTLE_RESULTS_PATH),
                ("workers_serialization", DEFAULT_WORKERS_SERIALIZATION_PATH),
            ):
                matching_lines = [line for line in interesting_lines if should_force_file_snapshot(source_name, line)]
                if not matching_lines:
                    continue
                battle = latest_battle_context(
                    DEFAULT_LOG_PATH,
                    DEFAULT_RAW_ACCOUNT_PATH,
                    DEFAULT_NORMALIZED_ACCOUNT_PATH,
                )
                reason = matching_lines[-1]
                saved = save_binary_snapshot(
                    source_name,
                    source_path,
                    session_dir,
                    battle,
                    reason=reason,
                )
                write_jsonl(
                    events_path,
                    {
                        "captured_at": now,
                        "event_type": "forced_file_snapshot",
                        "source_name": source_name,
                        "saved": saved,
                        "battle": battle,
                        "reason": reason,
                    },
                )
                file_states[source_name] = file_marker(source_path)
                safe_print(
                    f"[forced {source_name}] size={saved['marker'].get('size')} sha={string_value(saved['marker'].get('sha256'))[:12]}"
                )

        for db_name, db_path in SQLITE_PATHS.items():
            rows, next_last_id = poll_sqlite_events(db_path, sqlite_state[db_name])
            sqlite_state[db_name] = next_last_id
            for row in rows:
                preview = string_value(row.get("body"))[:240]
                safe_print(f"[sqlite {db_name}#{row.get('id')}] {preview}")
                write_jsonl(
                    events_path,
                    {
                        "captured_at": now,
                        "event_type": "sqlite_event",
                        "db_name": db_name,
                        "row": row,
                    },
                )

        for source_name, source_path in (
            ("battle_results", DEFAULT_BATTLE_RESULTS_PATH),
            ("workers_serialization", DEFAULT_WORKERS_SERIALIZATION_PATH),
        ):
            current_marker = file_marker(source_path)
            if marker_changed(file_states[source_name], current_marker):
                battle = latest_battle_context(
                    DEFAULT_LOG_PATH,
                    DEFAULT_RAW_ACCOUNT_PATH,
                    DEFAULT_NORMALIZED_ACCOUNT_PATH,
                )
                saved = save_binary_snapshot(source_name, source_path, session_dir, battle, reason="file_marker_changed")
                safe_print(
                    f"[file {source_name}] size={current_marker.get('size')} sha={string_value(current_marker.get('sha256'))[:12]}"
                )
                write_jsonl(
                    events_path,
                    {
                        "captured_at": now,
                        "event_type": "file_snapshot",
                        "source_name": source_name,
                        "saved": saved,
                        "battle": battle,
                    },
                )
                file_states[source_name] = current_marker

        if duration_seconds > 0 and (time.time() - started_at) >= duration_seconds:
            safe_print("Durata massima raggiunta, chiusura probe.")
            return session_dir

        time.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe profondo per catturare più segnale possibile durante una battle RAID."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.35,
        help="Intervallo di polling in secondi.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Durata massima in secondi. 0 = infinito.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session_dir = run_watch(interval_seconds=max(args.interval, 0.1), duration_seconds=max(args.duration, 0.0))
    safe_print(f"Sessione salvata in: {session_dir}")


if __name__ == "__main__":
    main()
