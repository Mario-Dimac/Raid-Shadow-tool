from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from forge_db import DB_PATH, ensure_schema, now_utc_iso, save_app_state
from run_damage_decoder import inspect_battle_results_payload


DATASET_KEY = "skill_usage_v1"
NORMALIZATION_SCOPE = "per_skill_code_minmax"
SKILL_SLOT_RE = re.compile(r"^A\d+$")
FEATURE_NAMES = (
    "enabled",
    "internal_i",
    "internal_d",
    "c",
    "m",
    "x",
    "r",
    "a",
    "h",
    "s",
    "ir",
    "y",
    "damage_taken",
    "incoming_target_events",
    "incoming_boss_target_events",
)


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


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def json_loads_dict(value: Any) -> Dict[str, Any]:
    text = string_value(value).strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return dict_value(payload)


def is_usable_skill_slot(skill_slot: Any) -> bool:
    return bool(SKILL_SLOT_RE.match(string_value(skill_slot).strip().upper()))


def extract_skill_feature_rows_from_report(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for member in list_value(report.get("members")):
        member_row = dict_value(member)
        member_order = int_value(member_row.get("member_order"))
        champion_type_id = int_value(member_row.get("champion_type_id"))
        for skill in list_value(member_row.get("skill_blocks")):
            skill_row = dict_value(skill)
            skill_order = int_value(skill_row.get("skill_order"))
            skill_slot = string_value(skill_row.get("skill_slot")).strip().upper()
            if skill_order <= 0 or not is_usable_skill_slot(skill_slot):
                continue
            rows.append(
                {
                    "member_order": member_order,
                    "champion_type_id": champion_type_id,
                    "skill_order": skill_order,
                    "skill_slot": skill_slot,
                    "skill_code": string_value(skill_row.get("skill_code")),
                    "enabled": 1 if bool(skill_row.get("enabled")) else 0,
                    "internal_i": 1 if bool(skill_row.get("internal_i")) else 0,
                    "internal_d": 1 if bool(skill_row.get("internal_d")) else 0,
                    "c": int_value(skill_row.get("c")),
                    "m": int_value(skill_row.get("m")),
                    "x": int_value(skill_row.get("x")),
                    "r": int_value(skill_row.get("r")),
                    "a": int_value(skill_row.get("a")),
                    "h": int_value(skill_row.get("h")),
                    "s": int_value(skill_row.get("s")),
                    "ir": int_value(skill_row.get("ir")),
                    "y": int_value(skill_row.get("y")),
                    "feature_payload_json": json_dumps(skill_row),
                }
            )
    return rows


def backfill_run_history_skill_features(db_path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    scanned_runs = 0
    updated_runs = 0
    inserted_feature_rows = 0
    updated_metric_rows = 0
    skipped_runs: List[Dict[str, Any]] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_rows = conn.execute(
            """
            SELECT r.run_id, r.battle_id, a.asset_path
            FROM run_history_runs r
            JOIN run_history_assets a
              ON a.run_id = r.run_id
            WHERE a.asset_kind = 'client_probe_battle_results_bin'
            ORDER BY r.run_id ASC
            """
        ).fetchall()

        for run_row in run_rows:
            run_id = int(run_row["run_id"])
            battle_id = string_value(run_row["battle_id"])
            raw_path = Path(string_value(run_row["asset_path"]))
            scanned_runs += 1

            if not raw_path.exists() or not raw_path.is_file():
                skipped_runs.append({"run_id": run_id, "battle_id": battle_id, "reason": "raw_asset_missing"})
                continue

            try:
                report = inspect_battle_results_payload(raw_path)
            except Exception:
                skipped_runs.append({"run_id": run_id, "battle_id": battle_id, "reason": "decode_failed"})
                continue

            feature_rows = extract_skill_feature_rows_from_report(report)
            member_rows = [dict_value(row) for row in list_value(report.get("members"))]
            if not feature_rows and not member_rows:
                skipped_runs.append({"run_id": run_id, "battle_id": battle_id, "reason": "no_report_rows"})
                continue

            conn.execute("DELETE FROM run_history_member_skill_features WHERE run_id = ?", (run_id,))
            for feature_row in feature_rows:
                conn.execute(
                    """
                    INSERT INTO run_history_member_skill_features (
                        run_id, member_order, skill_order, skill_slot, skill_code, champion_type_id,
                        enabled, internal_i, internal_d,
                        feature_c, feature_m, feature_x, feature_r, feature_a, feature_h, feature_s, feature_ir, feature_y,
                        feature_payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        int_value(feature_row.get("member_order")),
                        int_value(feature_row.get("skill_order")),
                        string_value(feature_row.get("skill_slot")),
                        string_value(feature_row.get("skill_code")),
                        int_value(feature_row.get("champion_type_id")) or None,
                        int_value(feature_row.get("enabled")),
                        int_value(feature_row.get("internal_i")),
                        int_value(feature_row.get("internal_d")),
                        int_value(feature_row.get("c")),
                        int_value(feature_row.get("m")),
                        int_value(feature_row.get("x")),
                        int_value(feature_row.get("r")),
                        int_value(feature_row.get("a")),
                        int_value(feature_row.get("h")),
                        int_value(feature_row.get("s")),
                        int_value(feature_row.get("ir")),
                        int_value(feature_row.get("y")),
                        string_value(feature_row.get("feature_payload_json")) or "{}",
                    ),
                )
            inserted_feature_rows += len(feature_rows)

            for member_row in member_rows:
                member_order = int_value(member_row.get("member_order"))
                metrics_payload = {
                    "incoming_target_events": int_value(member_row.get("incoming_target_events")),
                    "incoming_boss_target_events": int_value(member_row.get("incoming_boss_target_events")),
                    "incoming_boss_skill_codes": dict_value(member_row.get("incoming_boss_skill_codes")),
                    "damage_taken_status": string_value(member_row.get("damage_taken_status")),
                }
                existing_metric = conn.execute(
                    """
                    SELECT damage_done, damage_taken, healing_done, shields_done,
                           buffs_applied, debuffs_applied, deaths, revives, alive_at_end, metric_payload_json
                    FROM run_history_member_metrics
                    WHERE run_id = ? AND member_order = ?
                    """,
                    (run_id, member_order),
                ).fetchone()
                if existing_metric is None:
                    conn.execute(
                        """
                        INSERT INTO run_history_member_metrics (
                            run_id, member_order, damage_done, damage_taken, healing_done, shields_done,
                            buffs_applied, debuffs_applied, deaths, revives, alive_at_end, metric_payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            member_order,
                            0.0,
                            float_value(member_row.get("damage_taken")),
                            0.0,
                            0.0,
                            0,
                            0,
                            0,
                            0,
                            None,
                            json_dumps(metrics_payload),
                        ),
                    )
                    updated_metric_rows += 1
                    continue

                merged_payload = json_loads_dict(existing_metric["metric_payload_json"])
                merged_payload.update(metrics_payload)
                conn.execute(
                    """
                    UPDATE run_history_member_metrics
                    SET damage_taken = CASE WHEN COALESCE(damage_taken, 0) > 0 THEN damage_taken ELSE ? END,
                        metric_payload_json = ?
                    WHERE run_id = ? AND member_order = ?
                    """,
                    (
                        float_value(member_row.get("damage_taken")),
                        json_dumps(merged_payload),
                        run_id,
                        member_order,
                    ),
                )
                updated_metric_rows += 1

            updated_runs += 1

        conn.commit()

    return {
        "dataset_key": DATASET_KEY,
        "scanned_runs": scanned_runs,
        "updated_runs": updated_runs,
        "inserted_feature_rows": inserted_feature_rows,
        "updated_metric_rows": updated_metric_rows,
        "skipped_runs": len(skipped_runs),
        "skipped": skipped_runs[:25],
    }


def _load_materialization_rows(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            r.run_id,
            r.battle_id,
            r.encounter_key,
            r.encounter_name,
            r.stage_id,
            m.member_order,
            m.champion_name,
            m.champion_type_id,
            sf.skill_order,
            sf.skill_slot,
            sf.skill_code,
            sf.enabled,
            sf.internal_i,
            sf.internal_d,
            sf.feature_c,
            sf.feature_m,
            sf.feature_x,
            sf.feature_r,
            sf.feature_a,
            sf.feature_h,
            sf.feature_s,
            sf.feature_ir,
            sf.feature_y,
            su.usage_count,
            mm.damage_taken,
            mm.metric_payload_json,
            a.asset_path AS source_path
        FROM run_history_member_skill_features sf
        JOIN run_history_runs r
          ON r.run_id = sf.run_id
        JOIN run_history_members m
          ON m.run_id = sf.run_id
         AND m.member_order = sf.member_order
        LEFT JOIN run_history_member_skill_usage su
          ON su.run_id = sf.run_id
         AND su.member_order = sf.member_order
         AND su.skill_order = sf.skill_order
        LEFT JOIN run_history_member_metrics mm
          ON mm.run_id = sf.run_id
         AND mm.member_order = sf.member_order
        LEFT JOIN run_history_assets a
          ON a.run_id = sf.run_id
         AND a.asset_kind = 'client_probe_battle_results_bin'
        WHERE sf.skill_order > 0
          AND sf.skill_slot IS NOT NULL
          AND sf.skill_slot != ''
        ORDER BY sf.run_id ASC, sf.member_order ASC, sf.skill_order ASC
        """
    ).fetchall()

    payload: List[Dict[str, Any]] = []
    for row in rows:
        metric_payload = json_loads_dict(row["metric_payload_json"])
        payload.append(
            {
                "run_id": int_value(row["run_id"]),
                "battle_id": string_value(row["battle_id"]),
                "encounter_key": string_value(row["encounter_key"]),
                "encounter_name": string_value(row["encounter_name"]),
                "stage_id": string_value(row["stage_id"]),
                "member_order": int_value(row["member_order"]),
                "champion_name": string_value(row["champion_name"]),
                "champion_type_id": int_value(row["champion_type_id"]),
                "skill_order": int_value(row["skill_order"]),
                "skill_slot": string_value(row["skill_slot"]),
                "skill_code": string_value(row["skill_code"]),
                "target_value": int_value(row["usage_count"]),
                "source_path": string_value(row["source_path"]),
                "raw_features": {
                    "enabled": int_value(row["enabled"]),
                    "internal_i": int_value(row["internal_i"]),
                    "internal_d": int_value(row["internal_d"]),
                    "c": int_value(row["feature_c"]),
                    "m": int_value(row["feature_m"]),
                    "x": int_value(row["feature_x"]),
                    "r": int_value(row["feature_r"]),
                    "a": int_value(row["feature_a"]),
                    "h": int_value(row["feature_h"]),
                    "s": int_value(row["feature_s"]),
                    "ir": int_value(row["feature_ir"]),
                    "y": int_value(row["feature_y"]),
                    "damage_taken": float_value(row["damage_taken"]),
                    "incoming_target_events": int_value(metric_payload.get("incoming_target_events")),
                    "incoming_boss_target_events": int_value(metric_payload.get("incoming_boss_target_events")),
                },
            }
        )
    return payload


def _compute_feature_ranges(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[int, str], Dict[str, Tuple[float, float]]]:
    grouped: Dict[Tuple[int, str], Dict[str, List[float]]] = {}
    for row in rows:
        key = (int_value(row.get("champion_type_id")), string_value(row.get("skill_code")))
        feature_values = dict_value(row.get("raw_features"))
        bucket = grouped.setdefault(key, {name: [] for name in FEATURE_NAMES})
        for feature_name in FEATURE_NAMES:
            bucket[feature_name].append(float_value(feature_values.get(feature_name)))

    ranges: Dict[Tuple[int, str], Dict[str, Tuple[float, float]]] = {}
    for key, feature_map in grouped.items():
        ranges[key] = {}
        for feature_name, values in feature_map.items():
            if not values:
                ranges[key][feature_name] = (0.0, 0.0)
                continue
            ranges[key][feature_name] = (min(values), max(values))
    return ranges


def _normalize_feature_row(
    raw_features: Dict[str, Any],
    ranges: Dict[str, Tuple[float, float]],
) -> Tuple[Dict[str, Any], bool]:
    normalized: Dict[str, Any] = {}
    ready = False
    for feature_name in FEATURE_NAMES:
        value = float_value(raw_features.get(feature_name))
        low, high = ranges.get(feature_name, (0.0, 0.0))
        if high > low:
            normalized[feature_name] = (value - low) / (high - low)
            ready = True
        else:
            normalized[feature_name] = None
    return normalized, ready


def build_ai_training_skill_dataset_overview(
    db_path: Path = DB_PATH,
    dataset_key: str = DATASET_KEY,
) -> Dict[str, Any]:
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS sample_count,
                COUNT(DISTINCT run_id) AS run_count,
                COUNT(DISTINCT encounter_key) AS encounter_count,
                SUM(CASE WHEN normalization_ready = 1 THEN 1 ELSE 0 END) AS normalized_sample_count,
                MAX(updated_at) AS last_built_at
            FROM ai_training_skill_samples
            WHERE dataset_key = ?
            """,
            (dataset_key,),
        ).fetchone()
        top_rows = conn.execute(
            """
            SELECT encounter_key, encounter_name, COUNT(*) AS sample_count
            FROM ai_training_skill_samples
            WHERE dataset_key = ?
            GROUP BY encounter_key, encounter_name
            ORDER BY COUNT(*) DESC, encounter_key ASC
            LIMIT 5
            """,
            (dataset_key,),
        ).fetchall()

    return {
        "dataset_key": dataset_key,
        "sample_count": int_value(row["sample_count"]) if row is not None else 0,
        "run_count": int_value(row["run_count"]) if row is not None else 0,
        "encounter_count": int_value(row["encounter_count"]) if row is not None else 0,
        "normalized_sample_count": int_value(row["normalized_sample_count"]) if row is not None else 0,
        "last_built_at": string_value(row["last_built_at"]) if row is not None else "",
        "top_encounters": [
            {
                "encounter_key": string_value(top_row["encounter_key"]),
                "encounter_name": string_value(top_row["encounter_name"]),
                "sample_count": int_value(top_row["sample_count"]),
            }
            for top_row in top_rows
        ],
    }


def refresh_ai_training_skill_dataset(
    db_path: Path = DB_PATH,
    dataset_key: str = DATASET_KEY,
) -> Dict[str, Any]:
    ensure_schema(db_path)
    backfill_summary = backfill_run_history_skill_features(db_path=db_path)
    refreshed_at = now_utc_iso()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = _load_materialization_rows(conn)
        feature_ranges = _compute_feature_ranges(rows)
        conn.execute("DELETE FROM ai_training_skill_samples WHERE dataset_key = ?", (dataset_key,))

        inserted_rows = 0
        for row in rows:
            group_key = (int_value(row.get("champion_type_id")), string_value(row.get("skill_code")))
            normalized_features, normalization_ready = _normalize_feature_row(
                dict_value(row.get("raw_features")),
                feature_ranges.get(group_key, {}),
            )
            conn.execute(
                """
                INSERT INTO ai_training_skill_samples (
                    dataset_key, run_id, battle_id, encounter_key, encounter_name, stage_id,
                    member_order, champion_name, champion_type_id,
                    skill_order, skill_slot, skill_code,
                    target_label, target_value,
                    raw_features_json, normalized_features_json,
                    normalization_scope, normalization_ready,
                    source_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_key,
                    int_value(row.get("run_id")),
                    string_value(row.get("battle_id")),
                    string_value(row.get("encounter_key")),
                    string_value(row.get("encounter_name")),
                    string_value(row.get("stage_id")),
                    int_value(row.get("member_order")),
                    string_value(row.get("champion_name")),
                    int_value(row.get("champion_type_id")) or None,
                    int_value(row.get("skill_order")),
                    string_value(row.get("skill_slot")),
                    string_value(row.get("skill_code")),
                    "event_usage_count",
                    float_value(row.get("target_value")),
                    json_dumps(dict_value(row.get("raw_features"))),
                    json_dumps(normalized_features),
                    NORMALIZATION_SCOPE,
                    1 if normalization_ready else 0,
                    string_value(row.get("source_path")),
                    refreshed_at,
                    refreshed_at,
                ),
            )
            inserted_rows += 1

        conn.commit()

    overview = build_ai_training_skill_dataset_overview(db_path=db_path, dataset_key=dataset_key)
    summary = {
        "ok": True,
        "dataset_key": dataset_key,
        "refreshed_at": refreshed_at,
        "inserted_rows": inserted_rows,
        "backfill": backfill_summary,
        "overview": overview,
    }
    save_app_state(
        {
            "ai_training_skill_dataset_last_refresh_utc": refreshed_at,
            "ai_training_skill_dataset_summary": summary,
        },
        db_path=db_path,
    )
    return summary
