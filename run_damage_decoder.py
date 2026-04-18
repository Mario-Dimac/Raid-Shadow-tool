from __future__ import annotations

import argparse
import itertools
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from client_run_probe import decode_msgpack_best_effort, try_decompress_lz4_block_array


FIXED_POINT_32_SCALE = 2**32
CLAN_BOSS_STAGE_PREFIX = "4019"
DEMON_LORD_MEMBER_DAMAGE_RULES = {
    3666: ("member_payload", "ad.2004", 29),
    2166: ("member_payload", "r.m", 10),
    6206: ("member_payload", "w.bf.d", 17),
    5836: ("member_payload", "w.bf.a", 18),
    4496: ("member_payload", "r.m", 11),
}
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


def is_clan_boss_stage(stage_id: str) -> bool:
    return stage_id.startswith(CLAN_BOSS_STAGE_PREFIX)


def extract_total_damage_candidate(root: Dict[str, Any]) -> Dict[str, Any]:
    stage_id = string_value(dict_value(root.get("p")).get("i")).strip()
    boss_row = dict_value(dict_value(root.get("s")).get("a"))
    raw_total_damage = int_value(boss_row.get("dt"))
    if is_clan_boss_stage(stage_id) and raw_total_damage > 0:
        return {
            "total_damage": decode_metric_high32(raw_total_damage),
            "total_damage_status": "candidate_demon_lord_s_a_dt_high32",
            "total_damage_source": "s.a.dt",
        }
    return {
        "total_damage": None,
        "total_damage_status": "not_available",
        "total_damage_source": "",
    }


def extract_demon_lord_member_damage_candidates(
    member_rows: List[Dict[str, Any]],
    total_damage: int | None,
    stage_id: str,
) -> Dict[str, Any]:
    if total_damage is None or total_damage <= 0 or not is_clan_boss_stage(stage_id):
        return {"members": [], "status": "not_available"}

    weights: List[Tuple[int, int]] = []
    for row in member_rows:
        champion_type_id = int_value(row.get("champion_type_id"))
        rule = DEMON_LORD_MEMBER_DAMAGE_RULES.get(champion_type_id)
        if rule is None:
            return {"members": [], "status": "not_available"}
        payload_key, path, shift = rule
        payload = dict_value(row.get(payload_key))
        flat = flatten_numeric_leaf_paths(payload)
        raw_value = int_value(flat.get(path))
        weight = int(round(raw_value / (2**shift))) if raw_value > 0 else 0
        if weight <= 0:
            return {"members": [], "status": "not_available"}
        weights.append((int_value(row.get("member_order")), weight))

    weight_total = sum(weight for _, weight in weights)
    if weight_total <= 0:
        return {"members": [], "status": "not_available"}

    allocated: List[Dict[str, Any]] = []
    running_total = 0
    for index, (member_order, weight) in enumerate(weights):
        if index == len(weights) - 1:
            damage_done = max(total_damage - running_total, 0)
        else:
            damage_done = int(round(total_damage * weight / weight_total))
            running_total += damage_done
        allocated.append(
            {
                "member_order": member_order,
                "damage_done": damage_done,
                "damage_done_status": "candidate_demon_lord_manual_fit_normalized_total",
                "damage_done_weight": weight,
            }
        )

    return {
        "members": allocated,
        "status": "candidate_demon_lord_manual_fit_normalized_total",
    }


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
    total_damage_candidate = extract_total_damage_candidate(root)
    stage_id = string_value(dict_value(root.get("p")).get("i")).strip()
    damage_taken_trusted = not is_clan_boss_stage(stage_id)
    damage_taken_status = "trusted_member_dt_high32"
    if not damage_taken_trusted:
        damage_taken_status = "candidate_member_dt_high32_clan_boss"
    member_damage_candidate = extract_demon_lord_member_damage_candidates(
        member_rows,
        total_damage=int_value(total_damage_candidate.get("total_damage")),
        stage_id=stage_id,
    )
    member_damage_by_order = {
        int_value(row.get("member_order")): dict_value(row)
        for row in list_value(member_damage_candidate.get("members"))
    }
    members = [
        {
            "member_order": row["member_order"],
            "champion_type_id": row["champion_type_id"],
            "damage_done": dict_value(member_damage_by_order.get(int_value(row.get("member_order")))).get("damage_done"),
            "damage_taken": row["damage_taken"],
            "damage_taken_status": damage_taken_status,
            "raw_damage_done": dict_value(member_damage_by_order.get(int_value(row.get("member_order")))).get("damage_done_weight"),
            "raw_damage_taken": row["raw_damage_taken"],
            "damage_done_status": string_value(dict_value(member_damage_by_order.get(int_value(row.get("member_order")))).get("damage_done_status")),
        }
        for row in member_rows
    ]
    return {
        "battle_id": string_value(dict_value(root.get("p")).get("z")).strip(),
        "total_damage": total_damage_candidate.get("total_damage"),
        "total_damage_taken": total_damage_taken,
        "members": members,
        "source_path": str(path),
        "damage_trusted": False,
        "damage_taken_trusted": damage_taken_trusted,
        "damage_taken_status": damage_taken_status,
        "total_damage_status": string_value(total_damage_candidate.get("total_damage_status")),
        "total_damage_source": string_value(total_damage_candidate.get("total_damage_source")),
        "member_damage_status": string_value(member_damage_candidate.get("status")),
        "decode_note": (
            "The raw field `dt` is the best current candidate for the blue result metric. "
            "Outside Clan Boss it matches the screen closely; for Clan Boss it remains a candidate and not a trusted exact match. "
            "Demon Lord total damage is available as a candidate from `s.a.dt`."
        ),
    }


def summarize_battle_event_log(path: Path) -> Dict[str, Any]:
    root = decode_battle_results_root(path)
    event_rows = [dict_value(row) for row in list_value(dict_value(root.get("r")).get("c"))]
    event_type_counts = Counter(int_value(row.get("t")) for row in event_rows)
    source_party_counts = Counter(int_value(dict_value(dict_value(row.get("s")).get("p")).get("p")) for row in event_rows)
    target_party_counts = Counter(int_value(dict_value(dict_value(row.get("s")).get("t")).get("p")) for row in event_rows)
    non_null_c = sum(1 for row in event_rows if row.get("c") is not None)
    non_null_f = sum(1 for row in event_rows if row.get("f") is not None)
    source_target_pairs = Counter(
        (
            int_value(dict_value(dict_value(row.get("s")).get("p")).get("p")),
            int_value(dict_value(dict_value(row.get("s")).get("t")).get("p")),
        )
        for row in event_rows
    )
    return {
        "event_count": len(event_rows),
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "source_party_counts": dict(sorted(source_party_counts.items())),
        "target_party_counts": dict(sorted(target_party_counts.items())),
        "source_target_pair_counts": [
            {
                "source_party_id": source_party_id,
                "target_party_id": target_party_id,
                "count": count,
            }
            for (source_party_id, target_party_id), count in source_target_pairs.most_common(10)
        ],
        "non_null_c_count": non_null_c,
        "non_null_f_count": non_null_f,
        "raw_r_v": int_value(dict_value(root.get("r")).get("v")),
        "raw_r_r": int_value(dict_value(root.get("r")).get("r")),
    }


def summarize_member_skill_blocks(member_row: Dict[str, Any], event_skill_usage_counts: Dict[str, int] | None = None) -> List[Dict[str, Any]]:
    champion_type_id = int_value(member_row.get("champion_type_id"))
    skill_usage_counts = dict(event_skill_usage_counts or {})
    payload = dict_value(member_row.get("member_payload"))
    blocks: List[Dict[str, Any]] = []
    for skill in list_value(payload.get("k")):
        skill_map = dict_value(skill)
        raw_skill_code = int_value(skill_map.get("t"))
        if raw_skill_code <= 0:
            continue
        skill_order = raw_skill_code % 100 if champion_type_id > 0 and raw_skill_code // 100 == champion_type_id // 10 else None
        skill_slot = f"A{skill_order}" if skill_order is not None and skill_order > 0 else ""
        blocks.append(
            {
                "skill_code": raw_skill_code,
                "skill_order": skill_order,
                "skill_slot": skill_slot,
                "enabled": bool(skill_map.get("l")),
                "internal_i": bool(skill_map.get("i")),
                "internal_d": bool(skill_map.get("d")),
                "c": int_value(skill_map.get("c")),
                "m": int_value(skill_map.get("m")),
                "x": int_value(skill_map.get("x")),
                "r": int_value(skill_map.get("r")),
                "a": int_value(skill_map.get("a")),
                "h": int_value(skill_map.get("h")),
                "s": int_value(skill_map.get("s")),
                "ir": int_value(skill_map.get("ir")),
                "y": int_value(skill_map.get("y")),
                "event_usage_count": int_value(skill_usage_counts.get(skill_slot)),
            }
        )
    return blocks


def inspect_battle_results_payload(path: Path) -> Dict[str, Any]:
    root = decode_battle_results_root(path)
    battle_id = string_value(dict_value(root.get("p")).get("z")).strip()
    stage_id = string_value(dict_value(root.get("p")).get("i")).strip()
    encounter_duration_seconds = float(dict_value(root.get("r")).get("v") or 0) / 1000.0
    member_rows = extract_member_result_rows(path)
    damage_summary = extract_damage_summary(path)

    from battle_event_decoder import extract_incoming_target_counts, extract_skill_usage_counts

    usage_rows = {
        int_value(row.get("member_order")): dict_value(row)
        for row in list_value(extract_skill_usage_counts(path))
    }
    incoming_rows = {
        int_value(row.get("member_order")): dict_value(row)
        for row in list_value(extract_incoming_target_counts(path))
    }

    members: List[Dict[str, Any]] = []
    for member_row in member_rows:
        member_order = int_value(member_row.get("member_order"))
        usage_row = usage_rows.get(member_order, {})
        incoming_row = incoming_rows.get(member_order, {})
        members.append(
            {
                "member_order": member_order,
                "champion_type_id": int_value(member_row.get("champion_type_id")),
                "slot_index": member_row.get("slot_index"),
                "damage_taken": int_value(member_row.get("damage_taken")),
                "damage_taken_status": next(
                    (
                        string_value(member.get("damage_taken_status"))
                        for member in list_value(damage_summary.get("members"))
                        if int_value(dict_value(member).get("member_order")) == member_order
                    ),
                    "",
                ),
                "skill_usage_counts": dict_value(usage_row).get("skill_usage_counts") or {},
                "raw_skill_codes": dict_value(usage_row).get("raw_skill_codes") or {},
                "incoming_target_events": int_value(incoming_row.get("incoming_target_events")),
                "incoming_boss_target_events": int_value(incoming_row.get("incoming_boss_target_events")),
                "incoming_boss_skill_codes": dict_value(incoming_row.get("incoming_boss_skill_codes")),
                "skill_blocks": summarize_member_skill_blocks(
                    member_row,
                    event_skill_usage_counts=dict_value(usage_row).get("skill_usage_counts") or {},
                ),
            }
        )

    return {
        "battle_id": battle_id,
        "stage_id": stage_id,
        "source_path": str(path),
        "duration_seconds_candidate": encounter_duration_seconds,
        "damage_summary": damage_summary,
        "event_log": summarize_battle_event_log(path),
        "members": members,
    }


def extract_session_slug_from_path(path: Path) -> str:
    parts = list(path.parts)
    if "client_probe" not in parts:
        return ""
    index = parts.index("client_probe")
    if index + 1 >= len(parts):
        return ""
    return parts[index + 1]


def build_skill_block_sample_rows(path: Path) -> List[Dict[str, Any]]:
    report = inspect_battle_results_payload(path)
    rows: List[Dict[str, Any]] = []
    for member in list_value(report.get("members")):
        member_row = dict_value(member)
        for skill in list_value(member_row.get("skill_blocks")):
            skill_row = dict_value(skill)
            rows.append(
                {
                    "battle_id": string_value(report.get("battle_id")),
                    "stage_id": string_value(report.get("stage_id")),
                    "session_slug": extract_session_slug_from_path(path),
                    "source_path": str(path),
                    "duration_seconds_candidate": float(report.get("duration_seconds_candidate") or 0.0),
                    "member_order": int_value(member_row.get("member_order")),
                    "slot_index": member_row.get("slot_index"),
                    "champion_type_id": int_value(member_row.get("champion_type_id")),
                    "damage_taken": int_value(member_row.get("damage_taken")),
                    "damage_taken_status": string_value(member_row.get("damage_taken_status")),
                    "incoming_target_events": int_value(member_row.get("incoming_target_events")),
                    "incoming_boss_target_events": int_value(member_row.get("incoming_boss_target_events")),
                    "skill_code": int_value(skill_row.get("skill_code")),
                    "skill_order": skill_row.get("skill_order"),
                    "skill_slot": string_value(skill_row.get("skill_slot")),
                    "enabled": bool(skill_row.get("enabled")),
                    "internal_i": bool(skill_row.get("internal_i")),
                    "internal_d": bool(skill_row.get("internal_d")),
                    "event_usage_count": int_value(skill_row.get("event_usage_count")),
                    "c": int_value(skill_row.get("c")),
                    "m": int_value(skill_row.get("m")),
                    "x": int_value(skill_row.get("x")),
                    "r": int_value(skill_row.get("r")),
                    "a": int_value(skill_row.get("a")),
                    "h": int_value(skill_row.get("h")),
                    "s": int_value(skill_row.get("s")),
                    "ir": int_value(skill_row.get("ir")),
                    "y": int_value(skill_row.get("y")),
                }
            )
    return rows


def pearson_correlation(xs: Iterable[int], ys: Iterable[int]) -> float | None:
    x_values = [int_value(value) for value in xs]
    y_values = [int_value(value) for value in ys]
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    x_delta = [value - x_mean for value in x_values]
    y_delta = [value - y_mean for value in y_values]
    x_norm = math.sqrt(sum(delta * delta for delta in x_delta))
    y_norm = math.sqrt(sum(delta * delta for delta in y_delta))
    if x_norm <= 0 or y_norm <= 0:
        return None
    numerator = sum(xd * yd for xd, yd in zip(x_delta, y_delta))
    return numerator / (x_norm * y_norm)


def summarize_numeric_series(values: Iterable[int]) -> Dict[str, Any]:
    rows = [int_value(value) for value in values]
    if not rows:
        return {"count": 0, "min": 0, "max": 0, "distinct_values": []}
    return {
        "count": len(rows),
        "min": min(rows),
        "max": max(rows),
        "distinct_values": sorted(set(rows)),
    }


def summarize_skill_block_group(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    numeric_fields = ("event_usage_count", "damage_taken", "incoming_target_events", "incoming_boss_target_events", "c", "m", "x", "r", "a", "h", "s", "ir", "y")
    event_usage = [int_value(sample.get("event_usage_count")) for sample in samples]
    field_correlations: Dict[str, float | None] = {}
    for field_name in ("c", "m", "x", "r", "a", "h", "s", "ir", "y", "damage_taken", "incoming_target_events", "incoming_boss_target_events"):
        field_correlations[field_name] = pearson_correlation(
            [int_value(sample.get(field_name)) for sample in samples],
            event_usage,
        )

    best_field = ""
    best_score = -1.0
    for field_name, correlation in field_correlations.items():
        if correlation is None:
            continue
        score = abs(float(correlation))
        if score > best_score:
            best_score = score
            best_field = field_name

    return {
        "sample_count": len(samples),
        "field_ranges": {
            field_name: summarize_numeric_series(int_value(sample.get(field_name)) for sample in samples)
            for field_name in numeric_fields
        },
        "event_usage_correlations": field_correlations,
        "best_event_usage_field": best_field,
        "best_event_usage_abs_correlation": None if best_score < 0 else round(best_score, 6),
    }


def distinct_ratio(values: Iterable[int]) -> float:
    rows = [int_value(value) for value in values]
    if len(rows) <= 1:
        return 0.0
    return len(set(rows)) / len(rows)


def distinct_ratio_from_group_range(
    sample_count: int,
    field_range: Dict[str, Any],
    samples: List[Dict[str, Any]],
    feature_name: str,
) -> float:
    if samples:
        return distinct_ratio(int_value(sample.get(feature_name)) for sample in samples)
    distinct_values = list_value(dict_value(field_range).get("distinct_values"))
    if sample_count <= 1:
        return 0.0
    return min(len(distinct_values) / sample_count, 1.0)


def classify_feature_reliability(
    sample_count: int,
    correlation: float | None,
    value_distinct_ratio: float,
) -> str:
    if sample_count < 2 or correlation is None:
        return "insufficient_signal"
    score = abs(float(correlation))
    if sample_count >= 3 and score >= 0.95 and value_distinct_ratio >= 0.66:
        return "strong_candidate"
    if sample_count >= 2 and score >= 0.80 and value_distinct_ratio >= 0.50:
        return "candidate"
    if score >= 0.50 and value_distinct_ratio > 0.0:
        return "weak_candidate"
    return "non_informative"


def build_skill_training_view(
    report: Dict[str, Any],
    include_rows: bool = False,
    max_features_per_skill: int = 4,
) -> Dict[str, Any]:
    feature_names = ("x", "c", "m", "r", "a", "h", "s", "ir", "y", "damage_taken", "incoming_target_events", "incoming_boss_target_events")
    training_groups: List[Dict[str, Any]] = []
    training_rows: List[Dict[str, Any]] = []

    for group in list_value(report.get("skill_groups")):
        group_row = dict_value(group)
        samples = [dict_value(sample) for sample in list_value(group_row.get("samples"))]
        feature_candidates: List[Dict[str, Any]] = []
        non_informative_fields: List[str] = []

        for feature_name in feature_names:
            field_range = dict_value(dict_value(group_row.get("field_ranges")).get(feature_name))
            correlation = dict_value(group_row.get("event_usage_correlations")).get(feature_name)
            value_distinct_ratio = distinct_ratio_from_group_range(
                sample_count=int_value(group_row.get("sample_count")),
                field_range=field_range,
                samples=samples,
                feature_name=feature_name,
            )
            reliability = classify_feature_reliability(
                sample_count=int_value(group_row.get("sample_count")),
                correlation=float(correlation) if correlation is not None else None,
                value_distinct_ratio=value_distinct_ratio,
            )
            candidate_row = {
                "field": feature_name,
                "reliability": reliability,
                "correlation_to_event_usage": correlation,
                "direction": (
                    "positive"
                    if correlation is not None and float(correlation) > 0
                    else "negative"
                    if correlation is not None and float(correlation) < 0
                    else "flat_or_unknown"
                ),
                "value_distinct_ratio": round(value_distinct_ratio, 6),
                "distinct_values": list_value(field_range.get("distinct_values")),
            }
            if reliability == "non_informative" or reliability == "insufficient_signal":
                non_informative_fields.append(feature_name)
            else:
                feature_candidates.append(candidate_row)

        feature_candidates.sort(
            key=lambda row: (
                {"strong_candidate": 0, "candidate": 1, "weak_candidate": 2}.get(string_value(row.get("reliability")), 9),
                -abs(float(row.get("correlation_to_event_usage") or 0.0)),
                -float(row.get("value_distinct_ratio") or 0.0),
                string_value(row.get("field")),
            )
        )

        primary_feature = dict_value(feature_candidates[0]) if feature_candidates else {}
        training_group = {
            "champion_type_id": int_value(group_row.get("champion_type_id")),
            "skill_code": int_value(group_row.get("skill_code")),
            "skill_slot": string_value(group_row.get("skill_slot")),
            "skill_order": group_row.get("skill_order"),
            "sample_count": int_value(group_row.get("sample_count")),
            "target_label": "event_usage_count",
            "recommended_primary_feature": string_value(primary_feature.get("field")),
            "recommended_primary_reliability": string_value(primary_feature.get("reliability")),
            "recommended_feature_candidates": feature_candidates[: max(max_features_per_skill, 0)],
            "non_informative_fields": non_informative_fields,
        }
        training_groups.append(training_group)

        if include_rows:
            for sample in samples:
                training_rows.append(
                    {
                        "battle_id": string_value(sample.get("battle_id")),
                        "stage_id": string_value(sample.get("stage_id")),
                        "session_slug": string_value(sample.get("session_slug")),
                        "source_path": string_value(sample.get("source_path")),
                        "champion_type_id": int_value(group_row.get("champion_type_id")),
                        "skill_code": int_value(group_row.get("skill_code")),
                        "skill_slot": string_value(group_row.get("skill_slot")),
                        "member_order": int_value(sample.get("member_order")),
                        "target_event_usage_count": int_value(sample.get("event_usage_count")),
                        "features": {
                            feature_name: int_value(sample.get(feature_name))
                            for feature_name in feature_names
                        },
                    }
                )

    training_groups.sort(
        key=lambda row: (
            -int_value(row.get("sample_count")),
            {"strong_candidate": 0, "candidate": 1, "weak_candidate": 2, "": 9}.get(string_value(row.get("recommended_primary_reliability")), 9),
            string_value(row.get("recommended_primary_feature")),
            int_value(row.get("champion_type_id")),
            int_value(row.get("skill_code")),
        )
    )

    return {
        "target_label": "event_usage_count",
        "sample_unit": "champion_skill_run",
        "feature_space": list(feature_names),
        "group_count": len(training_groups),
        "groups": training_groups,
        "rows": training_rows if include_rows else [],
        "row_count": len(training_rows) if include_rows else 0,
    }


def compare_battle_results_skill_blocks(paths: Iterable[Path]) -> Dict[str, Any]:
    sample_rows: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    for path in paths:
        report = inspect_battle_results_payload(path)
        sample_rows.extend(build_skill_block_sample_rows(path))
        runs.append(
            {
                "battle_id": string_value(report.get("battle_id")),
                "stage_id": string_value(report.get("stage_id")),
                "session_slug": extract_session_slug_from_path(path),
                "source_path": str(path),
                "duration_seconds_candidate": float(report.get("duration_seconds_candidate") or 0.0),
                "member_count": len(list_value(report.get("members"))),
                "event_count": int_value(dict_value(report.get("event_log")).get("event_count")),
            }
        )

    groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for row in sample_rows:
        key = (int_value(row.get("champion_type_id")), int_value(row.get("skill_code")))
        groups.setdefault(key, []).append(row)

    skill_groups: List[Dict[str, Any]] = []
    for (champion_type_id, skill_code), samples in groups.items():
        ordered_samples = sorted(
            samples,
            key=lambda row: (
                string_value(row.get("session_slug")),
                string_value(row.get("battle_id")),
                int_value(row.get("member_order")),
            ),
        )
        summary = summarize_skill_block_group(ordered_samples)
        skill_groups.append(
            {
                "champion_type_id": champion_type_id,
                "skill_code": skill_code,
                "skill_order": ordered_samples[0].get("skill_order"),
                "skill_slot": string_value(ordered_samples[0].get("skill_slot")),
                **summary,
                "samples": ordered_samples,
            }
        )

    skill_groups.sort(
        key=lambda row: (
            -int_value(row.get("sample_count")),
            -float(row.get("best_event_usage_abs_correlation") or 0.0),
            int_value(row.get("champion_type_id")),
            int_value(row.get("skill_code")),
        )
    )

    global_correlations = {
        field_name: pearson_correlation(
            [int_value(row.get(field_name)) for row in sample_rows],
            [int_value(row.get("event_usage_count")) for row in sample_rows],
        )
        for field_name in ("c", "m", "x", "r", "a", "h", "s", "ir", "y", "damage_taken", "incoming_target_events", "incoming_boss_target_events")
    }

    return {
        "run_count": len(runs),
        "skill_sample_count": len(sample_rows),
        "runs": runs,
        "global_event_usage_correlations": global_correlations,
        "skill_groups": skill_groups,
    }


def filter_skill_block_comparison_report(
    report: Dict[str, Any],
    min_samples: int = 1,
    skill_slots: Iterable[str] | None = None,
    max_groups: int = 0,
    include_samples: bool = True,
) -> Dict[str, Any]:
    allowed_skill_slots = {string_value(slot).strip() for slot in (skill_slots or []) if string_value(slot).strip()}
    filtered_groups: List[Dict[str, Any]] = []
    for group in list_value(report.get("skill_groups")):
        group_row = dict_value(group)
        if int_value(group_row.get("sample_count")) < max(min_samples, 1):
            continue
        if allowed_skill_slots and string_value(group_row.get("skill_slot")) not in allowed_skill_slots:
            continue
        if include_samples:
            filtered_groups.append(group_row)
        else:
            compact_row = dict(group_row)
            compact_row.pop("samples", None)
            filtered_groups.append(compact_row)

    if max_groups > 0:
        filtered_groups = filtered_groups[:max_groups]

    filtered_report = dict(report)
    filtered_report["skill_groups"] = filtered_groups
    filtered_report["filtered_skill_group_count"] = len(filtered_groups)
    filtered_report["filter"] = {
        "min_samples": max(min_samples, 1),
        "skill_slots": sorted(allowed_skill_slots),
        "max_groups": max(max_groups, 0),
        "include_samples": include_samples,
    }
    return filtered_report


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


def latest_rich_battle_result_paths(client_probe_root: Path, limit: int) -> List[Path]:
    candidates: List[Tuple[float, Path]] = []
    for meta_path in client_probe_root.glob("**/snapshots/battle_results/*.json"):
        payload = dict_value(json.loads(meta_path.read_text(encoding="utf-8")))
        marker = dict_value(payload.get("marker"))
        size_bytes = int_value(marker.get("size"))
        if size_bytes <= 11:
            continue
        bin_path = meta_path.with_suffix(".bin")
        if not bin_path.exists():
            continue
        candidates.append((meta_path.stat().st_mtime, bin_path))
    candidates.sort(key=lambda row: row[0], reverse=True)
    unique_paths: List[Path] = []
    seen: set[str] = set()
    for _, path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
        if len(unique_paths) >= max(limit, 0):
            break
    return unique_paths


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
    parser.add_argument(
        "--inspect-path",
        type=Path,
        default=None,
        help="Path diretto a un battleResults .bin ricco da ispezionare.",
    )
    parser.add_argument(
        "--compare-paths",
        type=Path,
        nargs="+",
        default=None,
        help="Uno o piu path a battleResults .bin ricchi da confrontare fra loro.",
    )
    parser.add_argument(
        "--compare-rich-latest",
        type=int,
        default=0,
        help="Confronta automaticamente gli ultimi N battleResults ricchi trovati sotto client_probe.",
    )
    parser.add_argument(
        "--compare-min-samples",
        type=int,
        default=1,
        help="Tiene solo le skill presenti almeno in N sample nel report comparativo.",
    )
    parser.add_argument(
        "--compare-skill-slots",
        nargs="+",
        default=None,
        help="Filtra il confronto a slot skill specifici, per esempio A1 A2 A3.",
    )
    parser.add_argument(
        "--compare-max-groups",
        type=int,
        default=0,
        help="Limita il numero di gruppi skill restituiti nel report comparativo.",
    )
    parser.add_argument(
        "--compare-omit-samples",
        action="store_true",
        help="Nel report comparativo rimuove il dump completo dei sample per gruppo skill.",
    )
    parser.add_argument(
        "--compare-training-view",
        action="store_true",
        help="Trasforma il report comparativo in una vista orientata al training AI.",
    )
    parser.add_argument(
        "--compare-training-rows",
        action="store_true",
        help="Nella vista training include anche le righe sample-level con target e feature.",
    )
    parser.add_argument(
        "--compare-training-max-features",
        type=int,
        default=4,
        help="Numero massimo di feature candidate da tenere per skill nella vista training.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    if args.inspect_path:
        print(json.dumps(inspect_battle_results_payload(args.inspect_path), indent=2, ensure_ascii=False))
        return
    compare_paths = list(args.compare_paths or [])
    if int(args.compare_rich_latest or 0) > 0:
        compare_paths.extend(latest_rich_battle_result_paths(args.client_probe_root, int(args.compare_rich_latest)))
    if compare_paths:
        unique_paths: List[Path] = []
        seen = set()
        for path in compare_paths:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            unique_paths.append(path)
        comparison = compare_battle_results_skill_blocks(unique_paths)
        filtered = filter_skill_block_comparison_report(
            comparison,
            min_samples=int(args.compare_min_samples or 1),
            skill_slots=args.compare_skill_slots,
            max_groups=int(args.compare_max_groups or 0),
            include_samples=not bool(args.compare_omit_samples),
        )
        if args.compare_training_view:
            print(
                json.dumps(
                    build_skill_training_view(
                        filtered,
                        include_rows=bool(args.compare_training_rows),
                        max_features_per_skill=int(args.compare_training_max_features or 0),
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(json.dumps(filtered, indent=2, ensure_ascii=False))
        return
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
