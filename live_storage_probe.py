from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from client_run_probe import DEFAULT_LOG_PATH, DEFAULT_RAID_LOCALLOW
from deep_battle_probe import (
    configure_stdout,
    ensure_dir,
    latest_battle_context,
    safe_print,
    utc_now,
    utc_slug,
    write_jsonl,
)


OUTPUT_ROOT = Path(__file__).resolve().parent / "input" / "live_storage_probe"
DEFAULT_MAX_SNAPSHOT_BYTES = 2_000_000


@dataclass(frozen=True)
class WatchRoot:
    name: str
    path: Path
    recursive: bool = False


WATCH_ROOTS = [
    WatchRoot(
        "battle_results",
        DEFAULT_RAID_LOCALLOW / "battle-results" / "battleResults",
        recursive=False,
    ),
    WatchRoot(
        "workers_serialization",
        DEFAULT_RAID_LOCALLOW / "workers-serialization" / "serialization",
        recursive=False,
    ),
    WatchRoot(
        "dynamic_data",
        DEFAULT_RAID_LOCALLOW / "dynamic-data",
        recursive=True,
    ),
    WatchRoot(
        "vuplex_session_storage",
        DEFAULT_RAID_LOCALLOW / "Vuplex.WebView" / "chromium-cache" / "Session Storage",
        recursive=False,
    ),
    WatchRoot(
        "vuplex_local_leveldb",
        DEFAULT_RAID_LOCALLOW / "Vuplex.WebView" / "chromium-cache" / "Local Storage" / "leveldb",
        recursive=False,
    ),
    WatchRoot(
        "vuplex_raidevents_indexeddb",
        DEFAULT_RAID_LOCALLOW / "Vuplex.WebView" / "chromium-cache" / "IndexedDB" / "https_raidevents.plarium.com_0.indexeddb.leveldb",
        recursive=False,
    ),
    WatchRoot(
        "vuplex_raidtournaments_indexeddb",
        DEFAULT_RAID_LOCALLOW / "Vuplex.WebView" / "chromium-cache" / "IndexedDB" / "https_raidtournaments.plarium.com_0.indexeddb.leveldb",
        recursive=False,
    ),
]


def fast_file_marker(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {
            "exists": False,
            "size": 0,
            "mtime_ns": 0,
        }
    stat = path.stat()
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
    }


def iter_root_files(root: WatchRoot) -> Iterable[Path]:
    if not root.path.exists():
        return []
    if root.path.is_file():
        return [root.path]
    if root.recursive:
        return [path for path in root.path.rglob("*") if path.is_file()]
    return [path for path in root.path.iterdir() if path.is_file()]


def build_watch_state(roots: Iterable[WatchRoot]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    state: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for root in roots:
        root_state: Dict[str, Dict[str, Any]] = {}
        for path in iter_root_files(root):
            relative = path.relative_to(root.path.parent if root.path.is_file() else root.path)
            key = relative.as_posix()
            root_state[key] = fast_file_marker(path)
        state[root.name] = root_state
    return state


def diff_states(
    previous: Dict[str, Dict[str, Dict[str, Any]]],
    current: Dict[str, Dict[str, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    root_names = sorted(set(previous.keys()) | set(current.keys()))
    for root_name in root_names:
        left = previous.get(root_name, {})
        right = current.get(root_name, {})
        file_names = sorted(set(left.keys()) | set(right.keys()))
        for file_name in file_names:
            left_marker = left.get(file_name)
            right_marker = right.get(file_name)
            if left_marker is None and right_marker is not None:
                changes.append(
                    {
                        "root_name": root_name,
                        "relative_path": file_name,
                        "change_type": "created",
                        "marker": right_marker,
                    }
                )
                continue
            if left_marker is not None and right_marker is None:
                changes.append(
                    {
                        "root_name": root_name,
                        "relative_path": file_name,
                        "change_type": "deleted",
                        "marker": left_marker,
                    }
                )
                continue
            if left_marker != right_marker and right_marker is not None:
                changes.append(
                    {
                        "root_name": root_name,
                        "relative_path": file_name,
                        "change_type": "modified",
                        "marker": right_marker,
                        "previous_marker": left_marker,
                    }
                )
    return changes


def resolve_changed_path(root: WatchRoot, relative_path: str) -> Path:
    if root.path.is_file():
        return root.path
    return root.path / Path(relative_path)


def read_file_preview(path: Path, max_bytes: int = 96) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"preview_hex": "", "preview_ascii": ""}
    payload = path.read_bytes()[:max_bytes]
    return {
        "preview_hex": payload.hex(),
        "preview_ascii": "".join(chr(byte) if 32 <= byte < 127 else "." for byte in payload),
    }


def save_changed_file_snapshot(
    session_dir: Path,
    root: WatchRoot,
    relative_path: str,
    max_snapshot_bytes: int,
) -> Dict[str, Any]:
    source_path = resolve_changed_path(root, relative_path)
    marker = fast_file_marker(source_path)
    preview = read_file_preview(source_path)
    if not source_path.exists() or not source_path.is_file():
        return {
            "source_path": str(source_path),
            "marker": marker,
            "preview": preview,
            "saved_path": "",
            "saved": False,
        }

    snapshots_dir = ensure_dir(session_dir / "snapshots" / root.name)
    stem = f"{utc_slug()}_{Path(relative_path).name}_{marker['size']}"
    saved_path = snapshots_dir / f"{stem}.bin"
    if marker["size"] <= max_snapshot_bytes:
        saved_path.write_bytes(source_path.read_bytes())
        saved = True
    else:
        saved = False
    return {
        "source_path": str(source_path),
        "marker": marker,
        "preview": preview,
        "saved_path": str(saved_path) if saved else "",
        "saved": saved,
    }


def create_session_dir() -> Path:
    session_dir = ensure_dir(OUTPUT_ROOT / utc_slug())
    ensure_dir(session_dir / "snapshots")
    return session_dir


def write_session_metadata(session_dir: Path, roots: Iterable[WatchRoot], interval: float, duration: float) -> None:
    payload = {
        "created_at": utc_now(),
        "log_path": str(DEFAULT_LOG_PATH),
        "interval": interval,
        "duration": duration,
        "watch_roots": [
            {
                "name": root.name,
                "path": str(root.path),
                "recursive": root.recursive,
            }
            for root in roots
        ],
    }
    (session_dir / "session.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def summarize_change(change: Dict[str, Any]) -> str:
    marker = change.get("marker") or {}
    return (
        f"[{change.get('root_name')}] {change.get('change_type')} "
        f"{change.get('relative_path')} size={marker.get('size', 0)}"
    )


def run_watch(
    interval_seconds: float,
    duration_seconds: float,
    max_snapshot_bytes: int,
) -> Path:
    roots = list(WATCH_ROOTS)
    session_dir = create_session_dir()
    write_session_metadata(session_dir, roots, interval_seconds, duration_seconds)
    events_path = session_dir / "events.jsonl"
    configure_stdout()

    safe_print(f"Live storage probe session: {session_dir}")
    safe_print("In ascolto sui file locali che possono cambiare durante la battle...")

    previous_state = build_watch_state(roots)
    started_at = time.time()

    while True:
        captured_at = utc_now()
        current_state = build_watch_state(roots)
        changes = diff_states(previous_state, current_state)
        if changes:
            battle = latest_battle_context(
                DEFAULT_LOG_PATH,
                Path(__file__).resolve().parent / "input" / "raw_account.json",
                Path(__file__).resolve().parent / "input" / "normalized_account.json",
            )
            for change in changes:
                root = next(root for root in roots if root.name == change["root_name"])
                snapshot = save_changed_file_snapshot(
                    session_dir,
                    root,
                    str(change["relative_path"]),
                    max_snapshot_bytes=max_snapshot_bytes,
                )
                safe_print(summarize_change(change))
                write_jsonl(
                    events_path,
                    {
                        "captured_at": captured_at,
                        "event_type": "file_change",
                        "change": change,
                        "snapshot": snapshot,
                        "battle": battle,
                    },
                )
            previous_state = current_state

        if duration_seconds > 0 and (time.time() - started_at) >= duration_seconds:
            safe_print("Durata massima raggiunta, chiusura probe.")
            return session_dir

        time.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe per i file live locali del client RAID durante una battle."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.25,
        help="Intervallo di polling in secondi.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=900.0,
        help="Durata massima in secondi.",
    )
    parser.add_argument(
        "--max-snapshot-bytes",
        type=int,
        default=DEFAULT_MAX_SNAPSHOT_BYTES,
        help="Dimensione massima dei file da copiare per intero.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session_dir = run_watch(
        interval_seconds=max(args.interval, 0.05),
        duration_seconds=max(args.duration, 0.0),
        max_snapshot_bytes=max(args.max_snapshot_bytes, 0),
    )
    safe_print(f"Sessione salvata in: {session_dir}")


if __name__ == "__main__":
    main()
