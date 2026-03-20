from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .hellhades_bridge import extract_account_snapshot
from .paths import PLARIUM_LOCAL, RAID_BUILD_LOG, RAID_LOCALLOW
from .runtime import build_runtime_snapshot


def build_raw_snapshot() -> Dict[str, Any]:
    extracted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    sqlite_snapshots = [extract_sqlite_snapshot(path) for path in sqlite_paths()]
    user_ids = collect_user_ids(sqlite_snapshots)
    bridge_snapshot = extract_hellhades_snapshot()

    return {
        "meta": {
            "project": "CB Forge",
            "schema_version": "0.2-runtime-bootstrap",
            "source": "local_raid_client",
            "extracted_at": extracted_at,
            "player_name": "",
            "account_level": 0,
        },
        "local_client": {
            "raid_locallow": str(RAID_LOCALLOW),
            "plarium_local": str(PLARIUM_LOCAL),
            "raid_build_log": str(RAID_BUILD_LOG),
            "user_ids": user_ids,
            "runtime": build_runtime_snapshot(),
            "hellhades_bridge": bridge_snapshot.get("summary", {}),
            "sqlite": sqlite_snapshots,
            "files": [extract_file_snapshot(path) for path in interesting_files()],
            "recent_files": recent_files_snapshot(),
            "log_hints": extract_log_hints(
                RAID_BUILD_LOG,
                (
                    "Full User Refresh",
                    "BattleSetupsCache",
                    "MessagePackBattleResultsCache",
                    "Create folder structure and cache file",
                ),
            ),
        },
        "bonuses": ensure_list(bridge_snapshot.get("bonuses")),
        "roster": ensure_list(bridge_snapshot.get("roster")),
        "inventory": ensure_list(bridge_snapshot.get("inventory")),
    }


def extract_hellhades_snapshot() -> Dict[str, Any]:
    try:
        return extract_account_snapshot()
    except Exception as exc:
        return {
            "summary": {
                "error": str(exc),
            },
            "roster": [],
            "inventory": [],
        }


def ensure_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def sqlite_paths() -> Iterable[Path]:
    yield RAID_LOCALLOW / "raid.db"
    yield RAID_LOCALLOW / "raidV2.db"


def interesting_files() -> Iterable[Path]:
    yield from sqlite_paths()
    yield RAID_LOCALLOW / "workers-serialization" / "serialization"
    yield RAID_LOCALLOW / "dynamic-data" / "DeeplinkCache"
    yield RAID_LOCALLOW / "battle-results" / "battleResults"


def extract_sqlite_snapshot(path: Path) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else None,
    }
    if not path.exists():
        return snapshot

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    try:
        tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        snapshot["tables"] = tables

        if "Dictionary" in tables:
            rows = cur.execute("SELECT Key, Value FROM Dictionary ORDER BY Key").fetchall()
            snapshot["dictionary"] = [{"key": key, "value": safe_json_or_text(value)} for key, value in rows]

        if "Events" in tables:
            snapshot["events_count"] = cur.execute("SELECT COUNT(*) FROM Events").fetchone()[0]
            sample_rows = cur.execute("SELECT Id, Body FROM Events ORDER BY Id DESC LIMIT 5").fetchall()
            snapshot["events_sample"] = [
                {"id": row_id, "body_preview": preview_text(body, 500)} for row_id, body in sample_rows
            ]
    finally:
        conn.close()

    return snapshot


def collect_user_ids(sqlite_snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str, str]] = set()
    collected: List[Dict[str, Any]] = []
    for snapshot in sqlite_snapshots:
        for entry in snapshot.get("dictionary", []):
            if entry.get("key") != "UserId":
                continue
            value = entry.get("value")
            if not isinstance(value, dict):
                continue
            key = (
                str(value.get("g", "")),
                str(value.get("i", "")),
                str(value.get("m", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            collected.append(value)
    return collected


def extract_file_snapshot(path: Path) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else None,
    }
    if not path.exists():
        return snapshot

    data = path.read_bytes()
    snapshot["sha256"] = hashlib.sha256(data).hexdigest()
    snapshot["first_bytes_hex"] = data[:64].hex()
    snapshot["msgpack_preview"] = decode_msgpack_preview(data)
    snapshot["base64_preview"] = base64.b64encode(data[:64]).decode("ascii")
    return snapshot


def recent_files_snapshot(limit: int = 20) -> List[Dict[str, Any]]:
    if not RAID_LOCALLOW.exists():
        return []

    candidates = sorted(
        (
            path
            for path in RAID_LOCALLOW.rglob("*")
            if path.is_file()
            and "LoadedTextures" not in str(path)
            and "static-data" not in str(path)
            and path.stat().st_size < 10_000_000
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    return [
        {
            "path": str(path),
            "size": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        }
        for path in candidates[:limit]
    ]


def extract_log_hints(path: Path, needles: Tuple[str, ...], lines_per_key: int = 5) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False}

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return {
        "exists": True,
        "matches": {
            needle: [line for line in lines if needle in line][-lines_per_key:]
            for needle in needles
        },
    }


def safe_json_or_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return preview_text(value, 500)


def preview_text(value: str, max_length: int) -> str:
    value = value.replace("\x00", "")
    return value[:max_length]


def decode_msgpack_preview(data: bytes) -> Any:
    try:
        decoded, offset = unpack_msgpack(data, 0)
        if offset != len(data):
            return {"decoded": decoded, "remaining_bytes": len(data) - offset}
        return decoded
    except Exception as exc:
        return {"error": str(exc)}


def unpack_msgpack(data: bytes, offset: int) -> Tuple[Any, int]:
    if offset >= len(data):
        raise ValueError("unexpected end of data")

    first = data[offset]
    offset += 1

    if first <= 0x7F:
        return first, offset
    if first >= 0xE0:
        return first - 0x100, offset
    if 0xA0 <= first <= 0xBF:
        size = first & 0x1F
        return data[offset : offset + size].decode("utf-8"), offset + size
    if 0x90 <= first <= 0x9F:
        size = first & 0x0F
        items = []
        for _ in range(size):
            item, offset = unpack_msgpack(data, offset)
            items.append(item)
        return items, offset
    if 0x80 <= first <= 0x8F:
        size = first & 0x0F
        mapping = {}
        for _ in range(size):
            key, offset = unpack_msgpack(data, offset)
            value, offset = unpack_msgpack(data, offset)
            mapping[str(key)] = value
        return mapping, offset
    if first == 0xC0:
        return None, offset
    if first == 0xC2:
        return False, offset
    if first == 0xC3:
        return True, offset
    if first == 0xC4:
        size = data[offset]
        offset += 1
        return {"bin_hex": data[offset : offset + size].hex()}, offset + size
    if first == 0xC5:
        size = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        return {"bin_hex": data[offset : offset + size].hex()}, offset + size
    if first == 0xC6:
        size = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4
        return {"bin_hex": data[offset : offset + size].hex()}, offset + size
    if first == 0xC7:
        size = data[offset]
        offset += 1
        ext_type = int.from_bytes(data[offset : offset + 1], "big", signed=True)
        offset += 1
        return {"ext_type": ext_type, "data_hex": data[offset : offset + size].hex()}, offset + size
    if first == 0xC8:
        size = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        ext_type = int.from_bytes(data[offset : offset + 1], "big", signed=True)
        offset += 1
        return {"ext_type": ext_type, "data_hex": data[offset : offset + size].hex()}, offset + size
    if first == 0xC9:
        size = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4
        ext_type = int.from_bytes(data[offset : offset + 1], "big", signed=True)
        offset += 1
        return {"ext_type": ext_type, "data_hex": data[offset : offset + size].hex()}, offset + size
    if first == 0xCC:
        return data[offset], offset + 1
    if first == 0xCD:
        return int.from_bytes(data[offset : offset + 2], "big"), offset + 2
    if first == 0xCE:
        return int.from_bytes(data[offset : offset + 4], "big"), offset + 4
    if first == 0xD0:
        return int.from_bytes(data[offset : offset + 1], "big", signed=True), offset + 1
    if first == 0xD1:
        return int.from_bytes(data[offset : offset + 2], "big", signed=True), offset + 2
    if first == 0xD2:
        return int.from_bytes(data[offset : offset + 4], "big", signed=True), offset + 4
    if first == 0xD9:
        size = data[offset]
        offset += 1
        return data[offset : offset + size].decode("utf-8"), offset + size
    if first == 0xDA:
        size = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        return data[offset : offset + size].decode("utf-8"), offset + size
    if first == 0xDB:
        size = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4
        return data[offset : offset + size].decode("utf-8"), offset + size
    if first == 0xDC:
        size = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        items = []
        for _ in range(size):
            item, offset = unpack_msgpack(data, offset)
            items.append(item)
        return items, offset
    if first == 0xDD:
        size = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4
        items = []
        for _ in range(size):
            item, offset = unpack_msgpack(data, offset)
            items.append(item)
        return items, offset
    if first == 0xDE:
        size = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        mapping = {}
        for _ in range(size):
            key, offset = unpack_msgpack(data, offset)
            value, offset = unpack_msgpack(data, offset)
            mapping[str(key)] = value
        return mapping, offset
    if first == 0xDF:
        size = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4
        mapping = {}
        for _ in range(size):
            key, offset = unpack_msgpack(data, offset)
            value, offset = unpack_msgpack(data, offset)
            mapping[str(key)] = value
        return mapping, offset

    raise ValueError(f"unsupported msgpack prefix 0x{first:02x}")
