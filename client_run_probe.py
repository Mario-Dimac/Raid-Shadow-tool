from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import lz4.block
import msgpack


DEFAULT_RAID_BUILD_DIR = Path.home() / "AppData" / "Local" / "PlariumPlay" / "StandAloneApps" / "raid-shadow-legends" / "build"
DEFAULT_RAID_LOCALLOW = Path.home() / "AppData" / "LocalLow" / "Plarium" / "Raid_ Shadow Legends"
DEFAULT_LOG_PATH = DEFAULT_RAID_BUILD_DIR / "log.txt"
DEFAULT_BATTLE_RESULTS_PATH = DEFAULT_RAID_LOCALLOW / "battle-results" / "battleResults"
DEFAULT_WORKERS_SERIALIZATION_PATH = DEFAULT_RAID_LOCALLOW / "workers-serialization" / "serialization"
DEFAULT_RAW_ACCOUNT_PATH = Path(__file__).resolve().parent / "input" / "raw_account.json"
DEFAULT_NORMALIZED_ACCOUNT_PATH = Path(__file__).resolve().parent / "input" / "normalized_account.json"

CREATE_BATTLE_RE = re.compile(
    r"^>>> CreateBattle with setup:Id: (?P<battle_id>[0-9a-fA-F-]+) RandomSeed: (?P<seed>\d+) Stage: (?P<stage>\d+) FormationIndex (?P<formation>\d+)$"
)
TEAM_SETUP_RE = re.compile(r"^Round:\s*(?P<round>\d+)\s+Slot:\s*(?P<slot>\d+)\s+Type:\s*(?P<type_id>\d+)(?:\s+Grd:\s*(?P<grade>\S+))?(?:\s+Lvl:\s*(?P<level>\d+))?")
BATTLE_ID_RE = re.compile(
    r"(?:battleId - |Battle \[|BattleResult added: \[Id=|BattleResult deleted: \[Id=)(?P<id>[0-9a-fA-F-]{8,})"
)
STATE_RE = re.compile(r"Change battle state \[(?P<left>[^\]]+?) -> (?P<right>[^\]]+?)\]")


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def read_text_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def load_champion_type_name_map(
    raw_account_path: Path = DEFAULT_RAW_ACCOUNT_PATH,
    normalized_account_path: Path = DEFAULT_NORMALIZED_ACCOUNT_PATH,
) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    for path in (raw_account_path, normalized_account_path):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        roster = payload.get("roster") or payload.get("champions") or []
        if not isinstance(roster, list):
            continue
        for item in roster:
            if not isinstance(item, dict):
                continue
            type_id = int_value(item.get("type_id"))
            name = string_value(item.get("name")).strip()
            if type_id > 0 and name and type_id not in mapping:
                mapping[type_id] = name
        if mapping:
            break
    return mapping


def parse_team_rows(lines: List[str], start_index: int, name_map: Dict[int, str]) -> Dict[str, Any]:
    player_rows: List[Dict[str, Any]] = []
    enemy_rows: List[Dict[str, Any]] = []
    current_side = ""
    for raw_line in lines[start_index + 1 : start_index + 40]:
        stripped = raw_line.strip()
        if stripped.startswith("First Team:"):
            current_side = "player"
            continue
        if stripped.startswith("Second Team:"):
            current_side = "enemy"
            continue
        if stripped.startswith(">>> CreateBattle with setup:"):
            break
        match = TEAM_SETUP_RE.match(stripped)
        if not match or not current_side:
            continue
        type_id = int_value(match.group("type_id"))
        row = {
            "round": int_value(match.group("round")),
            "slot": int_value(match.group("slot")),
            "type_id": type_id,
            "name": name_map.get(type_id, f"Type {type_id}"),
            "grade": string_value(match.group("grade")),
            "level": int_value(match.group("level")),
        }
        if current_side == "player":
            player_rows.append(row)
        else:
            enemy_rows.append(row)
    return {"player_rows": player_rows, "enemy_rows": enemy_rows}


def parse_latest_battle_block(
    lines: List[str],
    name_map: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    mapping = name_map or {}
    battle_index = -1
    battle_match = None
    for index in range(len(lines) - 1, -1, -1):
        match = CREATE_BATTLE_RE.match(lines[index].strip())
        if match:
            battle_index = index
            battle_match = match
            break
    if battle_match is None:
        return {}

    parsed_rows = parse_team_rows(lines, battle_index, mapping)
    player_rows = parsed_rows["player_rows"]
    enemy_rows = parsed_rows["enemy_rows"]
    return {
        "battle_id": battle_match.group("battle_id"),
        "seed": int_value(battle_match.group("seed")),
        "stage_id": battle_match.group("stage"),
        "formation_index": int_value(battle_match.group("formation")),
        "player_team": player_rows[:5],
        "player_members": [row["name"] for row in player_rows[:5]],
        "player_type_ids": [row["type_id"] for row in player_rows[:5]],
        "enemy_rows": enemy_rows,
    }


def summarize_recent_log_signals(lines: List[str], limit: int = 80) -> Dict[str, Any]:
    battle_state = ""
    battle_id = ""
    events: List[str] = []
    for line in lines[-limit:]:
        stripped = line.strip()
        if not stripped:
            continue
        if any(token in stripped for token in ("CreateBattle", "BattleResult", "BattleFinish", "Change battle state", "Round:", "First Team:", "Second Team:")):
            events.append(stripped)
        state_match = STATE_RE.search(stripped)
        if state_match:
            battle_state = state_match.group("right").strip()
        id_match = BATTLE_ID_RE.search(stripped)
        if id_match:
            battle_id = id_match.group("id")
    return {
        "recent_events": events[-40:],
        "battle_state": battle_state,
        "battle_id": battle_id,
    }


def file_probe(path: Path, preview_size: int = 48) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size": 0,
        "sha256": "",
        "hex_preview": "",
        "ascii_preview": "",
        "mtime": "",
    }
    if not path.exists():
        return summary

    stat = path.stat()
    payload = path.read_bytes()
    summary["size"] = len(payload)
    summary["sha256"] = hashlib.sha256(payload).hexdigest() if payload else ""
    summary["hex_preview"] = payload[:preview_size].hex()
    summary["ascii_preview"] = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in payload[:preview_size])
    summary["mtime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
    return summary


def decode_msgpack_best_effort(data: bytes, max_offset: int = 8) -> Any:
    best_payload: Any = None
    best_score: tuple[int, int, int] | None = None
    for offset in range(0, min(max_offset, max(0, len(data) - 1)) + 1):
        chunk = data[offset:]
        try:
            payload = msgpack.unpackb(chunk, raw=False, strict_map_key=False)
            remaining = 0
        except msgpack.ExtraData as exc:
            payload = exc.unpacked
            remaining = len(exc.extra)
        except Exception:
            continue
        score = (1 if isinstance(payload, dict) else 0, -remaining, -offset)
        if best_score is None or score > best_score:
            best_score = score
            best_payload = payload if offset == 0 and remaining == 0 else {
                "decode_offset": offset,
                "remaining_bytes": remaining,
                "decoded": payload,
            }
    return best_payload


def try_decompress_lz4_block_array(data: bytes) -> Dict[str, Any]:
    try:
        root = msgpack.unpackb(
            data,
            raw=False,
            strict_map_key=False,
            ext_hook=lambda code, payload: msgpack.ExtType(code, payload),
        )
    except Exception as exc:
        return {"debug": f"msgpack root read failed: {exc}"}

    if not isinstance(root, list) or len(root) < 2:
        return {"debug": "root is not lz4 block array"}

    extension = root[0]
    if not isinstance(extension, msgpack.ExtType) or extension.code != 98:
        return {"debug": f"extension type {getattr(extension, 'code', 'n/a')} is not Lz4BlockArray"}

    try:
        unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
        unpacker.feed(extension.data)
        block_lengths = [int(value) for value in unpacker]
    except Exception as exc:
        return {"debug": f"block length decode failed: {exc}"}

    if len(block_lengths) != len(root) - 1:
        return {"debug": f"block length count mismatch lengths={len(block_lengths)} items={len(root)}"}

    decoded_blocks: List[bytes] = []
    try:
        for block, length in zip(root[1:], block_lengths):
            if not isinstance(block, (bytes, bytearray)):
                return {"debug": "compressed block is not binary"}
            decoded_blocks.append(lz4.block.decompress(bytes(block), uncompressed_size=length))
    except Exception as exc:
        return {"debug": f"lz4 decode failed: {exc}"}

    return {"debug": "ok:" + ",".join(str(length) for length in block_lengths), "data": b"".join(decoded_blocks)}


def summarize_decoded_value(value: Any, max_chars: int = 600) -> Any:
    try:
        text = json.dumps(value, ensure_ascii=False, default=repr)
    except TypeError:
        text = repr(value)
    if len(text) <= max_chars:
        return value
    return text[:max_chars] + "..."


def decode_binary_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    payload = path.read_bytes()
    if not payload:
        return {"decoded": None, "lz4_debug": "empty"}

    summary: Dict[str, Any] = {"decoded": summarize_decoded_value(decode_msgpack_best_effort(payload))}
    decompressed = try_decompress_lz4_block_array(payload)
    summary["lz4_debug"] = decompressed.get("debug")
    if "data" in decompressed:
        decoded_uncompressed = decode_msgpack_best_effort(decompressed["data"])
        summary["lz4_uncompressed_size"] = len(decompressed["data"])
        summary["decoded_uncompressed"] = summarize_decoded_value(decoded_uncompressed)
    return summary


def build_probe_snapshot(
    log_path: Path = DEFAULT_LOG_PATH,
    battle_results_path: Path = DEFAULT_BATTLE_RESULTS_PATH,
    workers_serialization_path: Path = DEFAULT_WORKERS_SERIALIZATION_PATH,
    raw_account_path: Path = DEFAULT_RAW_ACCOUNT_PATH,
    normalized_account_path: Path = DEFAULT_NORMALIZED_ACCOUNT_PATH,
) -> Dict[str, Any]:
    lines = read_text_lines(log_path)
    name_map = load_champion_type_name_map(raw_account_path, normalized_account_path)
    latest_battle = parse_latest_battle_block(lines, name_map)
    signals = summarize_recent_log_signals(lines)
    return {
        "log_path": str(log_path),
        "log_exists": log_path.exists(),
        "log_line_count": len(lines),
        "latest_battle": latest_battle,
        "signals": signals,
        "battle_results_file": file_probe(battle_results_path),
        "battle_results_decode": decode_binary_payload(battle_results_path),
        "workers_serialization_file": file_probe(workers_serialization_path),
        "workers_serialization_decode": decode_binary_payload(workers_serialization_path),
    }


def print_snapshot(snapshot: Dict[str, Any]) -> None:
    latest = snapshot.get("latest_battle") or {}
    signals = snapshot.get("signals") or {}
    print("== Client Run Probe ==")
    print(f"log lines: {snapshot.get('log_line_count', 0)}")
    if latest:
        print(
            f"latest battle: id={latest.get('battle_id')} stage={latest.get('stage_id')} formation={latest.get('formation_index')}"
        )
        members = ", ".join(string_value(name) for name in latest.get("player_members") or [])
        if members:
            print(f"player team: {members}")
        enemy_rows = list_value(latest.get("enemy_rows"))
        if enemy_rows:
            print(f"enemy rows captured: {len(enemy_rows)}")
    else:
        print("latest battle: not found")
    if signals.get("battle_state") or signals.get("battle_id"):
        print(f"recent state: {signals.get('battle_state') or '-'} | recent battle id: {signals.get('battle_id') or '-'}")
    battle_file = snapshot.get("battle_results_file") or {}
    print(
        f"battleResults: size={battle_file.get('size', 0)} mtime={battle_file.get('mtime', '-')}"
    )
    workers_file = snapshot.get("workers_serialization_file") or {}
    print(
        f"workers-serialization: size={workers_file.get('size', 0)} mtime={workers_file.get('mtime', '-')}"
    )
    print("-- recent events --")
    for event in list_value(signals.get("recent_events"))[-20:]:
        print(event)
    print("-- battleResults decode --")
    print(json.dumps(snapshot.get("battle_results_decode") or {}, indent=2, ensure_ascii=False, default=repr))
    print("-- workers-serialization decode --")
    print(json.dumps(snapshot.get("workers_serialization_decode") or {}, indent=2, ensure_ascii=False, default=repr))


def watch_probe(interval_seconds: float, max_iterations: int = 0) -> None:
    previous_markers = {"log_size": -1, "battle_hex": "", "workers_hex": ""}
    iteration = 0
    while True:
        snapshot = build_probe_snapshot()
        battle_file = snapshot.get("battle_results_file") or {}
        workers_file = snapshot.get("workers_serialization_file") or {}
        current_markers = {
            "log_size": int_value(snapshot.get("log_line_count")),
            "battle_hex": string_value(battle_file.get("hex_preview")),
            "workers_hex": string_value(workers_file.get("hex_preview")),
        }
        if current_markers != previous_markers:
            print_snapshot(snapshot)
            print("")
            previous_markers = current_markers
        iteration += 1
        if max_iterations > 0 and iteration >= max_iterations:
            return
        time.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe locale per capire cosa espone il client RAID durante una run.")
    parser.add_argument("--watch", action="store_true", help="Resta in ascolto e ristampa quando cambiano log o cache.")
    parser.add_argument("--interval", type=float, default=1.0, help="Intervallo di polling in secondi per --watch.")
    parser.add_argument("--iterations", type=int, default=0, help="Numero massimo di iterazioni in watch mode. 0 = infinito.")
    parser.add_argument("--json", action="store_true", help="Stampa il payload completo in JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.watch:
        watch_probe(interval_seconds=max(args.interval, 0.2), max_iterations=max(args.iterations, 0))
        return
    snapshot = build_probe_snapshot()
    if args.json:
        print(json.dumps(snapshot, indent=2, ensure_ascii=False, default=repr))
        return
    print_snapshot(snapshot)


if __name__ == "__main__":
    main()
