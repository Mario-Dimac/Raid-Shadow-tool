from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import lz4.block
import msgpack

from cbforge_extractor.paths import BASE_DIR, INPUT_DIR, RAID_LOCALLOW


BATTLE_RESULTS_PATH = RAID_LOCALLOW / "battle-results" / "battleResults"
BATTLE_CAPTURE_DIR = INPUT_DIR / "battle_result_captures"
BATTLE_PROBE_PROJECT = BASE_DIR / "hh_battle_probe" / "hh_battle_probe.csproj"
RAW_ACCOUNT_PATH = INPUT_DIR / "raw_account.json"
MIN_USEFUL_BATTLE_RESULT_SIZE = 12
FIXED_32_SCALE = 2**32


def capture_battle_result_snapshot(
    battle_id: str = "",
    preferred_names: List[str] | None = None,
    path: Path = BATTLE_RESULTS_PATH,
) -> Dict[str, Any]:
    if not path.exists():
        return {}

    payload = path.read_bytes()
    if not payload:
        return {}

    BATTLE_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    digest = hashlib.sha256(payload).hexdigest()
    stem = f"{captured_at.replace(':', '-').replace('+00:00', 'Z')}_{battle_id or 'battle'}_{digest[:10]}"
    binary_path = BATTLE_CAPTURE_DIR / f"{stem}.bin"
    if not binary_path.exists():
        binary_path.write_bytes(payload)

    metadata = {
        "battle_id": battle_id,
        "captured_at": captured_at,
        "size": len(payload),
        "sha256": digest,
        "snapshot_path": str(binary_path),
        "decoded_path": "",
        "damage_summary": {
            "total_damage": 0.0,
            "damage_by_champion": [],
            "candidate_damage_fields": [],
        },
    }
    try:
        decoded = decode_battle_result(binary_path)
        extracted = extract_damage_summary(decoded, preferred_names or [])
        metadata["damage_summary"] = extracted
        if decoded:
            decoded_path = BATTLE_CAPTURE_DIR / f"{stem}.json"
            decoded_path.write_text(
                json.dumps(decoded, indent=2, ensure_ascii=False, default=json_safe_default),
                encoding="utf-8",
            )
            metadata["decoded_path"] = str(decoded_path)
    except Exception as exc:
        metadata["error"] = str(exc)

    metadata_path = BATTLE_CAPTURE_DIR / f"{stem}.meta.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    metadata["metadata_path"] = str(metadata_path)
    return metadata


def read_battle_result_payload(path: Path = BATTLE_RESULTS_PATH, include_payload: bool = False) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "size": 0, "sha256": "", "payload": b"" if include_payload else None}
    payload = path.read_bytes()
    metadata = {
        "exists": True,
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest() if payload else "",
        "payload": None,
    }
    if include_payload:
        metadata["payload"] = payload
    return metadata


def decode_battle_result(path: Path) -> Dict[str, Any]:
    python_decoded = decode_battle_result_python(path)
    if python_decoded:
        return python_decoded

    if not BATTLE_PROBE_PROJECT.exists():
        return {}

    try:
        completed = subprocess.run(
            ["dotnet", "run", "--no-build", "--project", str(BATTLE_PROBE_PROJECT), "--summary", str(path)],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {
            "error": "hh_battle_probe timeout",
        }
    if completed.returncode != 0:
        return {
            "error": completed.stderr.strip() or completed.stdout.strip() or "hh_battle_probe failed",
        }
    stdout = completed.stdout
    json_start = stdout.find("{")
    if json_start < 0:
        return {}
    try:
        return json.loads(stdout[json_start:])
    except json.JSONDecodeError:
        return {}


def decode_battle_result_python(path: Path) -> Dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError:
        return {}
    if not data:
        return {}

    payload: Dict[str, Any] = {
        "path": str(path),
        "size": len(data),
    }
    decoded = decode_msgpack_best_effort(data)
    if decoded is not None:
        payload["decoded"] = summarize_decoded_payload(decoded)

    decompressed = try_decompress_lz4_block_array(data)
    if not decompressed:
        return payload

    payload["lz4_debug"] = decompressed["debug"]
    uncompressed = decompressed["data"]
    payload["lz4_uncompressed_size"] = len(uncompressed)
    decoded_uncompressed = decode_msgpack_best_effort(uncompressed)
    if decoded_uncompressed is not None:
        payload["decoded_uncompressed"] = summarize_decoded_payload(decoded_uncompressed)
    return payload


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

        score = (
            1 if isinstance(payload, dict) else 0,
            -remaining,
            -offset,
        )
        if best_score is None or score > best_score:
            best_score = score
            if offset == 0 and remaining == 0:
                best_payload = payload
            else:
                best_payload = {
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

    return {
        "debug": "ok:" + ",".join(str(length) for length in block_lengths),
        "data": b"".join(decoded_blocks),
    }


def summarize_decoded_payload(payload: Any) -> Any:
    unwrapped = unwrap_decoded_value(payload)
    if not isinstance(unwrapped, dict):
        return payload

    summary: Dict[str, Any] = {}
    for key in ("i", "c"):
        if key in unwrapped:
            summary[key] = unwrapped[key]

    setup_rows = list_value(path_get(unwrapped, "p", "f", "h"))
    if setup_rows:
        summary["p"] = {
            "f": {
                "h": [
                    compact_dict(row, ("d", "t", "u", "i", "h", "g", "l"))
                    for row in setup_rows
                    if isinstance(row, dict)
                ]
            }
        }

    result_rows = list_value(path_get(unwrapped, "s", "f", "h"))
    if result_rows:
        compact_rows = []
        for row in result_rows:
            if not isinstance(row, dict):
                continue
            compact_row = compact_dict(row, ("i", "d", "t", "u", "h", "dt", "s", "da"))
            additional_damage = row.get("ad") if isinstance(row.get("ad"), dict) else {}
            if "2004" in additional_damage:
                compact_row["ad"] = {"2004": additional_damage.get("2004")}
            compact_rows.append(compact_row)
        summary["s"] = {"f": {"h": compact_rows}}

    return summary or payload


def compact_dict(row: Dict[str, Any], keys: tuple[str, ...] | tuple[str, ...]) -> Dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}


def json_safe_default(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        preview = bytes(value[:32]).hex()
        return {
            "binary_length": len(value),
            "hex_preview": preview,
        }
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def extract_damage_summary(decoded: Any, preferred_names: List[str]) -> Dict[str, Any]:
    summary = {
        "total_damage": 0.0,
        "damage_by_champion": [],
        "candidate_damage_fields": [],
    }
    payload = best_decoded_payload(decoded)
    structured = extract_structured_damage_summary(payload, preferred_names)
    if structured:
        return structured

    numeric_hits: List[Dict[str, Any]] = []
    champion_hits: List[Dict[str, Any]] = []
    walk_damage_candidates(payload, "$", numeric_hits, champion_hits)

    if champion_hits:
        summary["damage_by_champion"] = champion_hits[:20]

    if preferred_names:
        normalized = {normalize_name(name): name for name in preferred_names}
        filtered = [
            item
            for item in champion_hits
            if normalize_name(string_value(item.get("name"))) in normalized
        ]
        if filtered:
            summary["damage_by_champion"] = filtered
            summary["total_damage"] = round(sum(float_value(item.get("damage")) for item in filtered), 1)

    if summary["total_damage"] <= 0 and numeric_hits:
        largest = max(numeric_hits, key=lambda item: float_value(item.get("value")))
        summary["total_damage"] = round(float_value(largest.get("value")), 1)

    summary["candidate_damage_fields"] = numeric_hits[:25]
    return summary


def best_decoded_payload(decoded: Any) -> Any:
    if not isinstance(decoded, dict):
        return unwrap_decoded_value(decoded)

    uncompressed = decoded.get("decoded_uncompressed")
    if uncompressed is not None:
        return unwrap_decoded_value(uncompressed)

    probe_decoded = decoded.get("decoded")
    if probe_decoded is not None:
        return unwrap_decoded_value(probe_decoded)

    return unwrap_decoded_value(decoded)


def unwrap_decoded_value(value: Any) -> Any:
    current = value
    while (
        isinstance(current, dict)
        and "decoded" in current
        and set(current.keys()).issubset({"decode_offset", "remaining_bytes", "decoded"})
    ):
        current = current.get("decoded")
    return current


def extract_structured_damage_summary(decoded: Any, preferred_names: List[str]) -> Dict[str, Any]:
    result_rows = list_value(path_get(decoded, "s", "f", "h"))
    if not result_rows:
        return {}

    setup_rows = list_value(path_get(decoded, "p", "f", "h"))
    name_by_result_key = build_result_name_map(setup_rows, result_rows, preferred_names)
    source_field = choose_structured_damage_field(result_rows)
    if not source_field:
        return {}
    champion_hits: List[Dict[str, Any]] = []
    candidate_fields: List[Dict[str, Any]] = []

    for index, row in enumerate(result_rows):
        if not isinstance(row, dict):
            continue
        result_key = result_identity(row, index)
        champion_name = (
            name_by_result_key.get(result_key)
            or preferred_names[index]
            if index < len(preferred_names)
            else ""
        )
        raw_damage = int_value(read_structured_damage_field(row, source_field))
        scaled_damage = round(fixed_32_to_float(raw_damage), 1) if raw_damage > 0 else 0.0
        candidate_fields.extend(structured_candidate_fields(row, index))
        champion_hits.append(
            {
                "path": f"$.s.f.h[{index}].{source_field}",
                "name": champion_name or fallback_champion_name(index, row),
                "damage": scaled_damage,
                "raw_value": raw_damage,
                "source_field": source_field,
                "confidence": "heuristic" if source_field != "ad.2004" else "medium",
            }
        )

    if not champion_hits:
        return {}

    non_zero_hits = [item for item in champion_hits if float_value(item.get("damage")) > 0]
    total_damage = round(sum(float_value(item.get("damage")) for item in champion_hits), 1)
    if total_damage <= 0 and not non_zero_hits:
        return {}

    return {
        "total_damage": total_damage,
        "damage_by_champion": champion_hits,
        "candidate_damage_fields": candidate_fields[:25],
        "source": "structured_battle_result",
        "confidence": "heuristic" if source_field != "ad.2004" else "medium",
    }


def build_result_name_map(
    setup_rows: List[Any],
    result_rows: List[Any],
    preferred_names: List[str],
) -> Dict[str, str]:
    names_by_key: Dict[str, str] = {}
    setup_name_map: Dict[tuple[int, int], str] = {}
    type_name_map = load_champion_type_name_map()

    for index, row in enumerate(setup_rows):
        if not isinstance(row, dict):
            continue
        name = preferred_names[index] if index < len(preferred_names) else ""
        if not name:
            name = type_name_map.get(int_value(row.get("i")), "")
        if not name:
            continue
        setup_name_map[(int_value(row.get("i")), int_value(row.get("h")))] = name

    for index, row in enumerate(result_rows):
        if not isinstance(row, dict):
            continue
        result_key = result_identity(row, index)
        setup_key = (int_value(row.get("t")), int_value(row.get("u")))
        if setup_key in setup_name_map:
            names_by_key[result_key] = setup_name_map[setup_key]
        elif index < len(preferred_names) and preferred_names[index]:
            names_by_key[result_key] = preferred_names[index]
    return names_by_key


def result_identity(row: Dict[str, Any], index: int) -> str:
    return f"{int_value(row.get('t'))}:{int_value(row.get('u'))}:{index}"


def structured_candidate_fields(row: Dict[str, Any], index: int) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for field_path, raw_value in (
        (f"$.s.f.h[{index}].ad.2004", int_value(path_get(row, "ad", "2004"))),
        (f"$.s.f.h[{index}].h", int_value(row.get("h"))),
        (f"$.s.f.h[{index}].dt", int_value(row.get("dt"))),
        (f"$.s.f.h[{index}].s", int_value(row.get("s"))),
    ):
        if raw_value <= 0:
            continue
        candidates.append(
            {
                "path": field_path,
                "value": round(fixed_32_to_float(raw_value), 1),
                "raw_value": raw_value,
            }
        )
    return candidates


def choose_structured_damage_field(rows: List[Any]) -> str:
    primary_values = [
        int_value(read_structured_damage_field(row, "ad.2004"))
        for row in rows
        if isinstance(row, dict)
    ]
    if any(value > 0 for value in primary_values):
        return "ad.2004"

    for field in ("h", "dt", "s"):
        values = [int_value(read_structured_damage_field(row, field)) for row in rows if isinstance(row, dict)]
        if any(value > 0 for value in values):
            return field
    return ""


def read_structured_damage_field(row: Dict[str, Any], field: str) -> Any:
    if field == "ad.2004":
        return path_get(row, "ad", "2004")
    return row.get(field)


def path_get(value: Any, *parts: str) -> Any:
    current = value
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def fixed_32_to_float(value: Any) -> float:
    raw = float_value(value)
    if raw <= 0:
        return 0.0
    return raw / FIXED_32_SCALE


def fallback_champion_name(index: int, row: Dict[str, Any]) -> str:
    champion_id = int_value(row.get("u"))
    type_id = int_value(row.get("t"))
    type_name = load_champion_type_name_map().get(type_id, "")
    if type_name:
        return type_name
    if champion_id > 0:
        return f"champion_{champion_id}"
    if type_id > 0:
        return f"type_{type_id}"
    return f"slot_{index + 1}"


def walk_damage_candidates(
    value: Any,
    path: str,
    numeric_hits: List[Dict[str, Any]],
    champion_hits: List[Dict[str, Any]],
) -> None:
    if isinstance(value, dict):
        maybe_name = first_text(value, ("name", "championName", "heroName", "unitName", "displayName"))
        maybe_damage = first_number(
            value,
            (
                "damage",
                "totalDamage",
                "damageDone",
                "damageDealt",
                "dealtDamage",
                "teamDamage",
            ),
        )
        if maybe_name and maybe_damage > 0:
            champion_hits.append(
                {
                    "path": path,
                    "name": maybe_name,
                    "damage": round(maybe_damage, 1),
                }
            )
        for key, item in value.items():
            key_text = string_value(key)
            child_path = f"{path}.{key_text}"
            if "damage" in key_text.lower() and isinstance(item, (int, float)):
                numeric_hits.append({"path": child_path, "value": float(item)})
            walk_damage_candidates(item, child_path, numeric_hits, champion_hits)
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            walk_damage_candidates(item, f"{path}[{index}]", numeric_hits, champion_hits)


def first_text(payload: Dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = string_value(payload.get(key)).strip()
        if value:
            return value
    return ""


def first_number(payload: Dict[str, Any], keys: tuple[str, ...]) -> float:
    for key in keys:
        value = float_value(payload.get(key))
        if value > 0:
            return value
    return 0.0


def normalize_name(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


_TYPE_NAME_MAP_CACHE: Dict[int, str] | None = None


def load_champion_type_name_map(path: Path = RAW_ACCOUNT_PATH) -> Dict[int, str]:
    global _TYPE_NAME_MAP_CACHE
    if _TYPE_NAME_MAP_CACHE is not None and path == RAW_ACCOUNT_PATH:
        return _TYPE_NAME_MAP_CACHE

    mapping: Dict[int, str] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        roster = payload.get("roster") or payload.get("champions") or []
        if isinstance(roster, list):
            for item in roster:
                if not isinstance(item, dict):
                    continue
                type_id = int_value(item.get("type_id"))
                name = string_value(item.get("name")).strip()
                if type_id > 0 and name and type_id not in mapping:
                    mapping[type_id] = name

    if path == RAW_ACCOUNT_PATH:
        _TYPE_NAME_MAP_CACHE = mapping
    return mapping
