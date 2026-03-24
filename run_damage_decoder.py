from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from client_run_probe import decode_msgpack_best_effort, try_decompress_lz4_block_array


FIXED_POINT_32_SCALE = 2**32
BATTLE_HEADER_RE = re.compile(r"^## Battaglia `([^`]+)`$")
SESSION_RE = re.compile(r"^Sessione probe: `([^`]+)`\.$")
STAGE_RE = re.compile(r"^Stage ID probe: `([^`]+)`\.$")
CONTENT_RE = re.compile(r"^Contenuto osservato a schermo: `([^`]+)`\.$")
ENCOUNTER_RE = re.compile(r"^Encounter ricostruito dal recorder: `([^`]+)`(?: \(`([^`]+)`\))?\.$")
DAMAGE_LINE_RE = re.compile(r"^Nella battaglia `([^`]+)`, `([^`]+)` ha fatto `([\d,]+)` danni\.$")
BATTLE_ID_IN_REASON_RE = re.compile(r"Id=([^\]]+)")


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_display_int(value: str) -> int:
    return int_value(value.replace(",", "").strip())


def decode_battle_results_root(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    payload = path.read_bytes()
    if not payload:
        return {}
    decompressed = try_decompress_lz4_block_array(payload)
    raw_data = decompressed.get("data")
    if not isinstance(raw_data, (bytes, bytearray)):
        return {}
    decoded = decode_msgpack_best_effort(bytes(raw_data))
    if isinstance(decoded, dict) and "decoded" in decoded:
        root = decoded.get("decoded")
        return dict_value(root)
    return dict_value(decoded)


def decode_metric_high32(raw_metric: Any) -> int:
    value = int_value(raw_metric)
    if value <= 0:
        return 0
    return int(round(value / FIXED_POINT_32_SCALE))


def extract_member_result_rows(path: Path) -> List[Dict[str, Any]]:
    root = decode_battle_results_root(path)
    result_members = list_value(dict_value(dict_value(root.get("s")).get("f")).get("h"))
    profile_members = list_value(dict_value(dict_value(root.get("p")).get("f")).get("h"))
    rows: List[Dict[str, Any]] = []
    for member_order, member in enumerate(result_members, start=1):
        row = dict_value(member)
        profile_row = dict_value(profile_members[member_order - 1]) if member_order - 1 < len(profile_members) else {}
        raw_slot_index = row.get("i")
        slot_index = int_value(raw_slot_index) if raw_slot_index is not None else None
        rows.append(
            {
                "member_order": member_order,
                "champion_type_id": int_value(row.get("t")) or None,
                "slot_index": slot_index,
                # This is the blue line shown in the result screen, not damage dealt.
                "damage_taken": decode_metric_high32(row.get("dt")),
                "raw_damage_taken": int_value(row.get("dt")),
                "member_payload": row,
                "profile_payload": profile_row,
            }
        )
    return rows


def extract_damage_summary(path: Path) -> Dict[str, Any]:
    root = decode_battle_results_root(path)
    member_rows = extract_member_result_rows(path)
    total_damage_taken = sum(int_value(row.get("damage_taken")) for row in member_rows)
    members = [
        {
            "member_order": row["member_order"],
            "champion_type_id": row["champion_type_id"],
            "damage_done": None,
            "damage_taken": row["damage_taken"],
            "raw_damage_done": None,
            "raw_damage_taken": row["raw_damage_taken"],
        }
        for row in member_rows
    ]
    return {
        "battle_id": string_value(dict_value(root.get("p")).get("z")).strip(),
        "total_damage": None,
        "total_damage_taken": total_damage_taken,
        "members": members,
        "source_path": str(path),
        "damage_trusted": False,
        "damage_taken_trusted": True,
        "decode_note": "The raw field `dt` matches the blue result metric, not the red damage-dealt line.",
    }


def parse_manual_battle_damage_notes(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    notes: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        battle_match = BATTLE_HEADER_RE.match(line)
        if battle_match:
            if current:
                notes.append(current)
            current = {
                "battle_id": battle_match.group(1),
                "session_slug": "",
                "stage_id": "",
                "encounter_name": "",
                "encounter_affinity": "",
                "content_label": "",
                "member_damage": [],
            }
            continue

        if not current:
            continue

        session_match = SESSION_RE.match(line)
        if session_match:
            current["session_slug"] = session_match.group(1)
            continue

        stage_match = STAGE_RE.match(line)
        if stage_match:
            current["stage_id"] = stage_match.group(1)
            continue

        encounter_match = ENCOUNTER_RE.match(line)
        if encounter_match:
            current["encounter_name"] = encounter_match.group(1)
            current["encounter_affinity"] = encounter_match.group(2) or ""
            continue

        content_match = CONTENT_RE.match(line)
        if content_match:
            current["content_label"] = content_match.group(1)
            continue

        damage_match = DAMAGE_LINE_RE.match(line)
        if damage_match:
            current["member_damage"].append(
                {
                    "battle_id": damage_match.group(1),
                    "champion_name": damage_match.group(2),
                    "damage_done": parse_display_int(damage_match.group(3)),
                }
            )

    if current:
        notes.append(current)
    return notes


def detect_battle_id_from_meta_payload(meta_payload: Dict[str, Any], meta_path: Path) -> str:
    battle_context = dict_value(meta_payload.get("battle_context"))
    battle_id = string_value(battle_context.get("battle_id")).strip()
    if battle_id:
        reason = string_value(meta_payload.get("reason")).strip()
        reason_match = BATTLE_ID_IN_REASON_RE.search(reason)
        if reason_match and reason_match.group(1).strip() != battle_id:
            battle_id = reason_match.group(1).strip()
    else:
        reason = string_value(meta_payload.get("reason")).strip()
        reason_match = BATTLE_ID_IN_REASON_RE.search(reason)
        if reason_match:
            battle_id = reason_match.group(1).strip()
    if battle_id:
        return battle_id
    bin_path = meta_path.with_suffix(".bin")
    return string_value(dict_value(decode_battle_results_root(bin_path).get("p")).get("z")).strip()


def index_rich_battle_result_assets(client_probe_root: Path) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for meta_path in client_probe_root.glob("**/snapshots/battle_results/*.json"):
        payload = dict_value(json.loads(meta_path.read_text(encoding="utf-8")))
        marker = dict_value(payload.get("marker"))
        size_bytes = int_value(marker.get("size"))
        if size_bytes <= 11:
            continue
        battle_id = detect_battle_id_from_meta_payload(payload, meta_path=meta_path)
        if not battle_id:
            continue
        bin_path = meta_path.with_suffix(".bin")
        candidate = {
            "battle_id": battle_id,
            "session_slug": meta_path.parents[2].name,
            "size_bytes": size_bytes,
            "meta_path": str(meta_path),
            "bin_path": str(bin_path),
        }
        current = index.get(battle_id)
        if current is None or size_bytes >= int_value(current.get("size_bytes")):
            index[battle_id] = candidate
    return index


def flatten_numeric_leaf_paths(value: Any, prefix: str = "") -> Dict[str, int]:
    rows: Dict[str, int] = {}
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.update(flatten_numeric_leaf_paths(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            child = f"{prefix}[{index}]"
            rows.update(flatten_numeric_leaf_paths(nested, child))
    elif isinstance(value, int) and not isinstance(value, bool):
        rows[prefix] = value
    return rows


def flatten_numeric_direct_blocks(value: Any, prefix: str = "") -> Dict[str, Dict[str, int]]:
    rows: Dict[str, Dict[str, int]] = {}
    if isinstance(value, dict):
        direct_numeric = {
            str(key): nested
            for key, nested in value.items()
            if isinstance(nested, int) and not isinstance(nested, bool)
        }
        if direct_numeric:
            rows[prefix] = direct_numeric
        for key, nested in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.update(flatten_numeric_direct_blocks(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            child = f"{prefix}[{index}]"
            rows.update(flatten_numeric_direct_blocks(nested, child))
    return rows


def transform_metric_candidates(raw_value: int) -> Dict[str, int]:
    return {
        "raw": raw_value,
        "high32": raw_value // FIXED_POINT_32_SCALE,
        "low32": raw_value % FIXED_POINT_32_SCALE,
        "round_2^16": int(round(raw_value / (2**16))),
        "round_2^24": int(round(raw_value / (2**24))),
        "round_2^28": int(round(raw_value / (2**28))),
        "round_2^32": int(round(raw_value / (2**32))),
    }


def transform_sort_priority(transform_name: str) -> int:
    order = {
        "raw": 0,
        "high32": 1,
        "round_2^32": 2,
        "low32": 3,
        "round_2^28": 4,
        "round_2^24": 5,
        "round_2^16": 6,
    }
    return order.get(transform_name, 99)


def relative_error(observed: int, expected: int) -> float:
    if expected <= 0:
        return 0.0 if observed == expected else float("inf")
    return abs(observed - expected) / expected


def rank_member_metric_candidates(
    samples: Iterable[Tuple[Dict[str, Any], int]],
    tolerance_ratio: float = 0.01,
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}

    sample_list = list(samples)
    for member_payload, target_value in sample_list:
        flat = flatten_numeric_leaf_paths(member_payload)
        for path, raw_value in flat.items():
            for transform_name, observed in transform_metric_candidates(raw_value).items():
                grouped.setdefault((path, transform_name), []).append((observed, target_value))

    ranked: List[Dict[str, Any]] = []
    for (path, transform_name), rows in grouped.items():
        matches = 0
        total_error = 0.0
        for observed, expected in rows:
            error = relative_error(observed, expected)
            total_error += error
            if error <= tolerance_ratio:
                matches += 1
        ranked.append(
            {
                "path": path,
                "transform": transform_name,
                "samples": len(rows),
                "matches": matches,
                "mean_relative_error": total_error / len(rows) if rows else float("inf"),
            }
        )

    ranked.sort(
        key=lambda row: (
            -int_value(row.get("matches")),
            float(row.get("mean_relative_error") or 0.0),
            str(row.get("path") or ""),
            transform_sort_priority(str(row.get("transform") or "")),
            str(row.get("transform") or ""),
        )
    )
    return ranked


def rank_member_composite_metric_candidates(
    samples: Iterable[Tuple[Dict[str, Any], int]],
    tolerance_ratio: float = 0.01,
    max_terms: int = 3,
    max_children_per_block: int = 12,
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}

    sample_list = list(samples)
    for payload, target_value in sample_list:
        flat_blocks = flatten_numeric_direct_blocks(payload)
        for block_path, numeric_children in flat_blocks.items():
            child_items = sorted(numeric_children.items())
            if len(child_items) < 2:
                continue
            child_items = child_items[:max_children_per_block]
            max_size = min(max_terms, len(child_items))
            for term_count in range(2, max_size + 1):
                for combo in itertools.combinations(child_items, term_count):
                    combo_keys = "+".join(key for key, _ in combo)
                    raw_value = sum(raw for _, raw in combo)
                    candidate_path = f"{block_path}[{combo_keys}]" if block_path else f"[{combo_keys}]"
                    for transform_name, observed in transform_metric_candidates(raw_value).items():
                        transformed_terms = [transform_metric_candidates(raw).get(transform_name, 0) for _, raw in combo]
                        non_zero_terms = sum(1 for value in transformed_terms if int_value(value) != 0)
                        if non_zero_terms < 2:
                            continue
                        grouped.setdefault((candidate_path, transform_name), []).append((observed, target_value))

    ranked: List[Dict[str, Any]] = []
    for (path, transform_name), rows in grouped.items():
        matches = 0
        total_error = 0.0
        for observed, expected in rows:
            error = relative_error(observed, expected)
            total_error += error
            if error <= tolerance_ratio:
                matches += 1
        ranked.append(
            {
                "path": path,
                "transform": transform_name,
                "samples": len(rows),
                "matches": matches,
                "mean_relative_error": total_error / len(rows) if rows else float("inf"),
            }
        )

    ranked.sort(
        key=lambda row: (
            -int_value(row.get("matches")),
            float(row.get("mean_relative_error") or 0.0),
            str(row.get("path") or ""),
            transform_sort_priority(str(row.get("transform") or "")),
            str(row.get("transform") or ""),
        )
    )
    return ranked


def build_manual_damage_dataset(
    notes_path: Path,
    client_probe_root: Path,
) -> List[Dict[str, Any]]:
    notes = parse_manual_battle_damage_notes(notes_path)
    asset_index = index_rich_battle_result_assets(client_probe_root)
    dataset: List[Dict[str, Any]] = []

    for note in notes:
        battle_id = string_value(note.get("battle_id")).strip()
        asset = dict_value(asset_index.get(battle_id))
        if not battle_id or not asset:
            continue
        asset_path = Path(string_value(asset.get("bin_path")))
        member_rows = extract_member_result_rows(asset_path)
        manual_rows = list_value(note.get("member_damage"))
        if len(member_rows) != len(manual_rows):
            continue
        dataset.append(
            {
                "battle_id": battle_id,
                "session_slug": string_value(note.get("session_slug")),
                "stage_id": string_value(note.get("stage_id")),
                "asset_path": str(asset_path),
                "member_rows": member_rows,
                "manual_rows": manual_rows,
            }
        )
    return dataset


def read_manual_result_metrics(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    payload = dict_value(json.loads(path.read_text(encoding="utf-8")))
    return [dict_value(row) for row in list_value(payload.get("battles"))]


def build_manual_result_metrics_dataset(
    metrics_path: Path,
    client_probe_root: Path,
) -> List[Dict[str, Any]]:
    notes = read_manual_result_metrics(metrics_path)
    asset_index = index_rich_battle_result_assets(client_probe_root)
    dataset: List[Dict[str, Any]] = []

    for note in notes:
        battle_id = string_value(note.get("battle_id")).strip()
        asset = dict_value(asset_index.get(battle_id))
        if not battle_id or not asset:
            continue
        asset_path = Path(string_value(asset.get("bin_path")))
        member_rows = extract_member_result_rows(asset_path)
        manual_rows = [dict_value(row) for row in list_value(note.get("members"))]
        if len(member_rows) != len(manual_rows):
            continue
        dataset.append(
            {
                "battle_id": battle_id,
                "session_slug": string_value(note.get("session_slug")),
                "stage_id": string_value(note.get("stage_id")),
                "asset_path": str(asset_path),
                "member_rows": member_rows,
                "manual_rows": manual_rows,
            }
        )
    return dataset


def analyze_manual_damage_notes(
    notes_path: Path,
    client_probe_root: Path,
    top: int = 20,
) -> Dict[str, Any]:
    dataset = build_manual_damage_dataset(notes_path=notes_path, client_probe_root=client_probe_root)
    samples: List[Tuple[Dict[str, Any], int]] = []
    for battle in dataset:
        for member_row, manual_row in zip(list_value(battle.get("member_rows")), list_value(battle.get("manual_rows"))):
            samples.append((dict_value(member_row.get("member_payload")), int_value(dict_value(manual_row).get("damage_done"))))

    ranked = rank_member_metric_candidates(samples)
    return {
        "battles": len(dataset),
        "samples": len(samples),
        "top_candidates": ranked[:top],
        "notes_path": str(notes_path),
        "client_probe_root": str(client_probe_root),
    }


def analyze_manual_result_metrics(
    metrics_path: Path,
    client_probe_root: Path,
    top: int = 10,
) -> Dict[str, Any]:
    dataset = build_manual_result_metrics_dataset(metrics_path=metrics_path, client_probe_root=client_probe_root)
    metric_keys = ("damage_done", "damage_taken", "healing_done")
    payload_keys = ("member_payload", "profile_payload")
    ranked_by_metric: Dict[str, Dict[str, Any]] = {}

    for metric_key in metric_keys:
        ranked_by_metric[metric_key] = {}
        for payload_key in payload_keys:
            samples: List[Tuple[Dict[str, Any], int]] = []
            for battle in dataset:
                for member_row, manual_row in zip(list_value(battle.get("member_rows")), list_value(battle.get("manual_rows"))):
                    payload = dict_value(dict_value(member_row).get(payload_key))
                    target = int_value(dict_value(manual_row).get(metric_key))
                    if not payload or target <= 0:
                        continue
                    samples.append((payload, target))
            ranked = rank_member_metric_candidates(samples)
            composite_ranked = rank_member_composite_metric_candidates(samples)
            ranked_by_metric[metric_key][payload_key] = {
                "samples": len(samples),
                "top_candidates": ranked[:top],
                "top_composite_candidates": composite_ranked[:top],
            }

    return {
        "battles": len(dataset),
        "metrics_path": str(metrics_path),
        "client_probe_root": str(client_probe_root),
        "ranked_by_metric": ranked_by_metric,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analizza i payload battleResults contro il foglio manuale di danno.")
    parser.add_argument(
        "--notes",
        type=Path,
        default=Path("data_sources") / "manual_battle_damage_notes.md",
        help="Foglio manuale con i danni per campione.",
    )
    parser.add_argument(
        "--client-probe-root",
        type=Path,
        default=Path("input") / "client_probe",
        help="Root delle sessioni client_probe.",
    )
    parser.add_argument("--top", type=int, default=20, help="Numero di candidati da mostrare.")
    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("data_sources") / "manual_battle_result_metrics.json",
        help="Dataset JSON con danno/cure/subito manuali.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    summary = analyze_manual_damage_notes(
        notes_path=args.notes,
        client_probe_root=args.client_probe_root,
        top=max(int(args.top or 0), 1),
    )
    metric_summary = analyze_manual_result_metrics(
        metrics_path=args.metrics,
        client_probe_root=args.client_probe_root,
        top=max(int(args.top or 0), 1),
    )
    print(json.dumps({"damage_notes": summary, "result_metrics": metric_summary}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
