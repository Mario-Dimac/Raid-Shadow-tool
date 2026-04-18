from __future__ import annotations

import argparse
import json
import os
import re
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
    STATE_RE,
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
RUNTIME_DISCOVERY_EXCLUDED_DIRS = {"LoadedTextures"}
RUNTIME_DISCOVERY_SOURCE_NAME = "runtime_discovery"
BATTLE_RESULTS_BURST_ATTEMPTS = 12
BATTLE_RESULTS_BURST_DELAY_SECONDS = 0.05
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
BATTLE_ID_HINT_RE = re.compile(
    r"(?:CreateBattle with setup:Id:\s*|Created setup for battle Id -\s*|BattleSetup cached:\s*\[\s*Id\s*=\s*|Created battle processor for battleId -\s*)(?P<id>[0-9a-fA-F-]{8,})",
    re.IGNORECASE,
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


def light_file_marker(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "size": 0, "mtime_ns": 0, "sha256": ""}
    stat = path.stat()
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
        "sha256": "",
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


def hinted_battle_id(text: str) -> str:
    match = BATTLE_ID_HINT_RE.search(str(text or "").strip())
    return string_value(match.group("id") if match else "").strip()


def update_battle_activity(active: bool, line: str) -> bool:
    lowered = string_value(line).strip().lower()
    if not lowered:
        return active
    if should_capture_battle_context(lowered):
        return True
    if "change battle state" in lowered:
        state_match = STATE_RE.search(line)
        right = string_value(state_match.group("right") if state_match else "").strip().lower()
        if right in {"startcmdexecuting", "startcmdsucceed", "loading", "started"}:
            return True
        if right in {"finished", "none"}:
            return False
    if "battleresult added:" in lowered or "battleresult deleted:" in lowered:
        return False
    return active


def should_capture_battle_context(line: str) -> bool:
    lowered = line.lower()
    return (
        "createbattle with setup:" in lowered
        or "created setup for battle id -" in lowered
        or "battlesetup cached:" in lowered
        or "created battle processor for battleid -" in lowered
    )


def should_force_file_snapshot(source_name: str, line: str) -> bool:
    lowered = line.lower()
    if source_name == "battle_results":
        return "battleresult added:" in lowered or "processbattlefinish" in lowered or "finishing battle -" in lowered
    if source_name == "workers_serialization":
        return (
            "createbattle with setup:" in lowered
            or "change battle state [loading -> started]" in lowered
            or "change battle state [startcmdsucceed -> started]" in lowered
        )
    return False


def hinted_battle_context(
    line: str,
    log_path: Path,
    raw_account_path: Path,
    normalized_account_path: Path,
) -> Dict[str, Any]:
    battle = latest_battle_context(log_path, raw_account_path, normalized_account_path)
    battle_id = hinted_battle_id(line)
    if not battle_id:
        return battle
    patched = dict(battle) if battle else {}
    patched["battle_id"] = battle_id
    return patched


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


def capture_followup_file_snapshots(
    source_name: str,
    path: Path,
    session_dir: Path,
    battle_context: Dict[str, Any],
    last_marker: Dict[str, Any],
    reason: str,
    attempts: int,
    delay_seconds: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    saved_rows: List[Dict[str, Any]] = []
    current_last_marker = dict(last_marker)
    for attempt_index in range(1, max(int(attempts), 0) + 1):
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        current_marker = file_marker(path)
        if not marker_changed(current_last_marker, current_marker):
            continue
        saved = save_binary_snapshot(
            source_name,
            path,
            session_dir,
            battle_context,
            reason=f"{reason} | followup_{attempt_index}",
        )
        saved_rows.append(saved)
        current_last_marker = dict(saved.get("marker") or current_marker)
    return saved_rows, current_last_marker


def capture_forced_snapshot(
    source_name: str,
    source_path: Path,
    session_dir: Path,
    battle: Dict[str, Any],
    reason: str,
    events_path: Path,
    file_states: Dict[str, Dict[str, Any]],
) -> None:
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
            "captured_at": utc_now(),
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
    if source_name != "battle_results":
        return

    burst_saved_rows, updated_marker = capture_followup_file_snapshots(
        source_name,
        source_path,
        session_dir,
        battle,
        last_marker=dict(saved.get("marker") or {}),
        reason=reason,
        attempts=BATTLE_RESULTS_BURST_ATTEMPTS,
        delay_seconds=BATTLE_RESULTS_BURST_DELAY_SECONDS,
    )
    for burst_saved in burst_saved_rows:
        write_jsonl(
            events_path,
            {
                "captured_at": utc_now(),
                "event_type": "burst_file_snapshot",
                "source_name": source_name,
                "saved": burst_saved,
                "battle": battle,
                "reason": string_value(burst_saved.get("reason")),
            },
        )
        safe_print(
            f"[burst {source_name}] size={burst_saved['marker'].get('size')} sha={string_value(burst_saved['marker'].get('sha256'))[:12]}"
        )
    file_states[source_name] = updated_marker


def is_finish_battle_sqlite_event(row: Dict[str, Any]) -> bool:
    parsed = row.get("parsed")
    if not isinstance(parsed, dict):
        return False
    payload = parsed.get("p")
    if not isinstance(payload, dict):
        return False
    response = payload.get("r")
    if not isinstance(response, dict):
        return False
    return string_value(response.get("t")).strip() == "FinishBattle"


def latest_battle_context(log_path: Path, raw_account_path: Path, normalized_account_path: Path) -> Dict[str, Any]:
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines() if log_path.exists() else []
    name_map = load_champion_type_name_map(raw_account_path, normalized_account_path)
    return parse_latest_battle_block(lines, name_map)


def _normalized_path_key(path: Path) -> str:
    return str(path.resolve()).lower()


def collect_runtime_candidate_markers(root: Path, exclude_paths: List[Path] | None = None) -> Dict[str, Dict[str, Any]]:
    excluded = {_normalized_path_key(path) for path in (exclude_paths or [])}
    markers: Dict[str, Dict[str, Any]] = {}
    if not root.exists():
        return markers

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in RUNTIME_DISCOVERY_EXCLUDED_DIRS]
        directory = Path(dirpath)
        for filename in filenames:
            path = directory / filename
            key = _normalized_path_key(path)
            if key in excluded:
                continue
            markers[key] = {"path": str(path), **light_file_marker(path)}
    return markers


def diff_runtime_candidate_markers(
    previous: Dict[str, Dict[str, Any]],
    current: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    for key in sorted(set(previous) | set(current)):
        left = previous.get(key)
        right = current.get(key)
        if left is None and right is not None:
            changes.append({"change_kind": "created", "path": right["path"], "marker": right})
            continue
        if left is not None and right is None:
            changes.append({"change_kind": "removed", "path": left["path"], "marker": left})
            continue
        if left is not None and right is not None and marker_changed(left, right):
            changes.append({"change_kind": "changed", "path": right["path"], "marker": right})
    return changes


def create_session_dir(session_slug: str = "") -> Path:
    session_dir = ensure_dir(OUTPUT_ROOT / (session_slug.strip() or utc_slug()))
    ensure_dir(session_dir / "snapshots")
    return session_dir


def write_session_metadata(
    session_dir: Path,
    discover_runtime_files: bool = False,
    runtime_discovery_interval: float = 0.0,
    runtime_discovery_max_bytes: int = 0,
) -> None:
    payload = {
        "created_at": utc_now(),
        "log_path": str(DEFAULT_LOG_PATH),
        "battle_results_path": str(DEFAULT_BATTLE_RESULTS_PATH),
        "workers_serialization_path": str(DEFAULT_WORKERS_SERIALIZATION_PATH),
        "sqlite_paths": {name: str(path) for name, path in SQLITE_PATHS.items()},
        "runtime_discovery": {
            "enabled": discover_runtime_files,
            "root": str(DEFAULT_RAID_LOCALLOW),
            "excluded_dirs": sorted(RUNTIME_DISCOVERY_EXCLUDED_DIRS),
            "excluded_paths": [
                str(DEFAULT_BATTLE_RESULTS_PATH),
                str(DEFAULT_WORKERS_SERIALIZATION_PATH),
                *(str(path) for path in SQLITE_PATHS.values()),
            ],
            "interval_seconds": runtime_discovery_interval,
            "snapshot_max_bytes": runtime_discovery_max_bytes,
        },
    }
    (session_dir / "session.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_watch(
    interval_seconds: float,
    duration_seconds: float,
    session_slug: str = "",
    discover_runtime_files: bool = False,
    runtime_discovery_interval: float = 1.0,
    runtime_discovery_max_bytes: int = 262_144,
) -> Path:
    session_dir = create_session_dir(session_slug=session_slug)
    write_session_metadata(
        session_dir,
        discover_runtime_files=discover_runtime_files,
        runtime_discovery_interval=runtime_discovery_interval,
        runtime_discovery_max_bytes=runtime_discovery_max_bytes,
    )
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
    runtime_discovery_exclude_paths = [
        DEFAULT_BATTLE_RESULTS_PATH,
        DEFAULT_WORKERS_SERIALIZATION_PATH,
        *SQLITE_PATHS.values(),
    ]
    runtime_discovery_state = (
        collect_runtime_candidate_markers(DEFAULT_RAID_LOCALLOW, exclude_paths=runtime_discovery_exclude_paths)
        if discover_runtime_files
        else {}
    )
    last_runtime_discovery_at = 0.0
    battle_active = False
    started_at = time.time()

    while True:
        now = utc_now()

        new_lines, log_offset = read_log_append(DEFAULT_LOG_PATH, log_offset)
        interesting_lines = [line for line in new_lines if is_interesting_log_line(line)]
        if interesting_lines:
            for line in interesting_lines:
                battle_active = update_battle_activity(battle_active, line)
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
                seen_battle_keys = set()
                for line in interesting_lines:
                    if not should_capture_battle_context(line):
                        continue
                    battle = hinted_battle_context(
                        line,
                        DEFAULT_LOG_PATH,
                        DEFAULT_RAW_ACCOUNT_PATH,
                        DEFAULT_NORMALIZED_ACCOUNT_PATH,
                    )
                    dedupe_key = string_value(battle.get("battle_id") or "").strip() or line
                    if dedupe_key in seen_battle_keys:
                        continue
                    seen_battle_keys.add(dedupe_key)
                    write_jsonl(
                        events_path,
                        {
                            "captured_at": now,
                            "event_type": "battle_context",
                            "battle": battle,
                            "source_line": line,
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
                    if not should_force_file_snapshot(source_name, line):
                        continue
                    battle = hinted_battle_context(
                        line,
                        DEFAULT_LOG_PATH,
                        DEFAULT_RAW_ACCOUNT_PATH,
                        DEFAULT_NORMALIZED_ACCOUNT_PATH,
                    )
                    capture_forced_snapshot(
                        source_name,
                        source_path,
                        session_dir,
                        battle,
                        line,
                        events_path,
                        file_states,
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
                if is_finish_battle_sqlite_event(row):
                    battle = latest_battle_context(
                        DEFAULT_LOG_PATH,
                        DEFAULT_RAW_ACCOUNT_PATH,
                        DEFAULT_NORMALIZED_ACCOUNT_PATH,
                    )
                    burst_saved_rows, updated_marker = capture_followup_file_snapshots(
                        "battle_results",
                        DEFAULT_BATTLE_RESULTS_PATH,
                        session_dir,
                        battle,
                        last_marker=file_states["battle_results"],
                        reason=f"sqlite_finish_battle:{db_name}",
                        attempts=BATTLE_RESULTS_BURST_ATTEMPTS,
                        delay_seconds=BATTLE_RESULTS_BURST_DELAY_SECONDS,
                    )
                    for burst_saved in burst_saved_rows:
                        write_jsonl(
                            events_path,
                            {
                                "captured_at": utc_now(),
                                "event_type": "burst_file_snapshot",
                                "source_name": "battle_results",
                                "saved": burst_saved,
                                "battle": battle,
                                "reason": string_value(burst_saved.get("reason")),
                            },
                        )
                        safe_print(
                            f"[burst battle_results] size={burst_saved['marker'].get('size')} sha={string_value(burst_saved['marker'].get('sha256'))[:12]}"
                        )
                    file_states["battle_results"] = updated_marker

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

        now_monotonic = time.time()
        if (
            discover_runtime_files
            and battle_active
            and (now_monotonic - last_runtime_discovery_at) >= max(runtime_discovery_interval, 0.2)
        ):
            current_runtime_discovery_state = collect_runtime_candidate_markers(
                DEFAULT_RAID_LOCALLOW,
                exclude_paths=runtime_discovery_exclude_paths,
            )
            runtime_changes = diff_runtime_candidate_markers(runtime_discovery_state, current_runtime_discovery_state)
            for change in runtime_changes:
                marker = dict(change.get("marker") or {})
                candidate_path = Path(string_value(change.get("path")))
                event_payload = {
                    "captured_at": now,
                    "event_type": "runtime_file_candidate",
                    "change_kind": string_value(change.get("change_kind")),
                    "path": str(candidate_path),
                    "marker": marker,
                    "battle": latest_battle_context(
                        DEFAULT_LOG_PATH,
                        DEFAULT_RAW_ACCOUNT_PATH,
                        DEFAULT_NORMALIZED_ACCOUNT_PATH,
                    ),
                }
                snapshot_allowed = (
                    candidate_path.exists()
                    and int_value(marker.get("size")) > 0
                    and int_value(marker.get("size")) <= max(runtime_discovery_max_bytes, 0)
                )
                if snapshot_allowed:
                    saved = save_binary_snapshot(
                        RUNTIME_DISCOVERY_SOURCE_NAME,
                        candidate_path,
                        session_dir,
                        dict(event_payload["battle"]),
                        reason=f"runtime_file_{event_payload['change_kind']}",
                    )
                    event_payload["saved"] = saved
                write_jsonl(events_path, event_payload)
                safe_print(
                    f"[runtime {event_payload['change_kind']}] {candidate_path.name} size={marker.get('size', 0)}"
                )
            runtime_discovery_state = current_runtime_discovery_state
            last_runtime_discovery_at = now_monotonic

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
    parser.add_argument(
        "--session-slug",
        default="",
        help="Slug sessione opzionale per pilotare il recorder da strumenti esterni.",
    )
    parser.add_argument(
        "--discover-runtime-files",
        action="store_true",
        help="Durante la battle cerca file locali che cambiano davvero e salva i candidati piccoli.",
    )
    parser.add_argument(
        "--discover-interval",
        type=float,
        default=1.0,
        help="Intervallo di scan in secondi per la discovery runtime quando la battle e' attiva.",
    )
    parser.add_argument(
        "--discover-max-bytes",
        type=int,
        default=262_144,
        help="Dimensione massima dei file candidati da salvare automaticamente durante la discovery runtime.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session_dir = run_watch(
        interval_seconds=max(args.interval, 0.1),
        duration_seconds=max(args.duration, 0.0),
        session_slug=str(args.session_slug or "").strip(),
        discover_runtime_files=bool(args.discover_runtime_files),
        runtime_discovery_interval=max(args.discover_interval, 0.2),
        runtime_discovery_max_bytes=max(args.discover_max_bytes, 0),
    )
    safe_print(f"Sessione salvata in: {session_dir}")


if __name__ == "__main__":
    main()
