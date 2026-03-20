from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from forge_db import DB_PATH, ensure_schema, load_app_state


SKILL_DATA_EXPR = """
    cs.cooldown IS NOT NULL
    OR cs.booked_cooldown IS NOT NULL
    OR NULLIF(TRIM(COALESCE(cs.skill_type, '')), '') IS NOT NULL
    OR NULLIF(TRIM(COALESCE(cs.description_clean, cs.description, '')), '') IS NOT NULL
"""


def build_registry_report(db_path: Path = DB_PATH, limit: int = 25) -> Dict[str, Any]:
    ensure_schema(db_path)
    app_state = load_app_state(db_path)
    with sqlite3.connect(db_path) as conn:
        summary_row = conn.execute(
            f"""
            SELECT
                (SELECT COUNT(*) FROM champion_catalog),
                (
                    SELECT COUNT(*)
                    FROM champion_catalog
                    WHERE hellhades_post_id IS NOT NULL
                        OR NULLIF(TRIM(COALESCE(hellhades_url, '')), '') IS NOT NULL
                        OR NULLIF(TRIM(COALESCE(last_enriched_at, '')), '') IS NOT NULL
                ),
                (SELECT COUNT(*) FROM champion_skills),
                (SELECT COUNT(*) FROM champion_skills WHERE cooldown IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skills WHERE booked_cooldown IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skills WHERE NULLIF(TRIM(COALESCE(skill_type, '')), '') IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skills WHERE NULLIF(TRIM(COALESCE(description_clean, description, '')), '') IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skills WHERE NULLIF(TRIM(COALESCE(source, '')), '') IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skill_effects),
                (SELECT COUNT(*) FROM registry_targets),
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            rt.champion_name,
                            COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                            COUNT(DISTINCT CASE WHEN {SKILL_DATA_EXPR} THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_data
                        FROM registry_targets rt
                        LEFT JOIN champion_skills cs
                            ON cs.champion_name = rt.champion_name
                        GROUP BY rt.champion_name
                        HAVING skill_rows_with_data > 0
                    )
                ),
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            rt.champion_name,
                            COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                            COUNT(DISTINCT CASE WHEN {SKILL_DATA_EXPR} THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_data
                        FROM registry_targets rt
                        LEFT JOIN champion_skills cs
                            ON cs.champion_name = rt.champion_name
                        GROUP BY rt.champion_name
                        HAVING skill_rows > 0 AND skill_rows_with_data = skill_rows
                    )
                ),
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            rt.champion_name,
                            COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                            COUNT(DISTINCT CASE WHEN {SKILL_DATA_EXPR} THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_data,
                            COUNT(cse.effect_order) AS effect_rows
                        FROM registry_targets rt
                        LEFT JOIN champion_skills cs
                            ON cs.champion_name = rt.champion_name
                        LEFT JOIN champion_skill_effects cse
                            ON cse.champion_name = cs.champion_name
                            AND cse.slot = cs.slot
                        GROUP BY rt.champion_name
                        HAVING skill_rows > 0 AND skill_rows_with_data = skill_rows AND effect_rows > 0
                    )
                )
            """
        ).fetchone()
        missing_rows = conn.execute(
            f"""
            SELECT
                rt.champion_name,
                CASE
                    WHEN cc.hellhades_post_id IS NOT NULL
                        OR NULLIF(TRIM(COALESCE(cc.hellhades_url, '')), '') IS NOT NULL
                        OR NULLIF(TRIM(COALESCE(cc.last_enriched_at, '')), '') IS NOT NULL
                    THEN 1 ELSE 0
                END AS has_external_ref,
                COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                COUNT(DISTINCT CASE WHEN cs.cooldown IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS with_cooldown,
                COUNT(DISTINCT CASE WHEN cs.booked_cooldown IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS with_booked_cooldown,
                COUNT(DISTINCT CASE WHEN NULLIF(TRIM(COALESCE(cs.skill_type, '')), '') IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS with_skill_type,
                COUNT(DISTINCT CASE WHEN NULLIF(TRIM(COALESCE(cs.description_clean, cs.description, '')), '') IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS with_description,
                COUNT(DISTINCT CASE WHEN NULLIF(TRIM(COALESCE(cs.source, '')), '') IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS with_source,
                COUNT(DISTINCT CASE WHEN {SKILL_DATA_EXPR} THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_data,
                COUNT(cse.effect_order) AS effect_rows
            FROM registry_targets rt
            LEFT JOIN champion_catalog cc
                ON cc.champion_name = rt.champion_name
            LEFT JOIN champion_skills cs
                ON cs.champion_name = rt.champion_name
            LEFT JOIN champion_skill_effects cse
                ON cse.champion_name = cs.champion_name
                AND cse.slot = cs.slot
            GROUP BY rt.champion_name
            HAVING
                skill_rows = 0
                OR skill_rows_with_data < skill_rows
                OR effect_rows = 0
            ORDER BY
                skill_rows_with_data ASC,
                with_description ASC,
                with_skill_type ASC,
                with_cooldown ASC,
                effect_rows ASC,
                skill_rows DESC,
                rt.champion_name ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        source_rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(COALESCE(source, '')), ''), '(none)') AS source_name, COUNT(*)
            FROM champion_skills
            GROUP BY source_name
            ORDER BY COUNT(*) DESC, source_name ASC
            """
        ).fetchall()
        local_ready_row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT
                    rt.champion_name,
                    COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                    COUNT(DISTINCT CASE WHEN {SKILL_DATA_EXPR} THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_data,
                    COUNT(DISTINCT CASE WHEN cs.source = 'local_registry' THEN cs.slot || ':' || cs.skill_order END) AS local_skill_rows
                FROM registry_targets rt
                LEFT JOIN champion_skills cs
                    ON cs.champion_name = rt.champion_name
                GROUP BY rt.champion_name
                HAVING skill_rows > 0 AND skill_rows_with_data = skill_rows AND local_skill_rows = skill_rows
            )
            """
        ).fetchone()
        hellhades_ready_row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT
                    rt.champion_name,
                    COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                    COUNT(DISTINCT CASE WHEN {SKILL_DATA_EXPR} THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_data,
                    COUNT(DISTINCT CASE WHEN cs.source = 'hellhades' THEN cs.slot || ':' || cs.skill_order END) AS hellhades_skill_rows
                FROM registry_targets rt
                LEFT JOIN champion_skills cs
                    ON cs.champion_name = rt.champion_name
                GROUP BY rt.champion_name
                HAVING skill_rows > 0 AND skill_rows_with_data = skill_rows AND hellhades_skill_rows = skill_rows
            )
            """
        ).fetchone()

    summary = {
        "database": str(db_path),
        "champion_catalog": int(summary_row[0] if summary_row else 0),
        "champion_catalog_with_external_ref": int(summary_row[1] if summary_row else 0),
        "skill_rows": int(summary_row[2] if summary_row else 0),
        "skill_rows_with_cooldown": int(summary_row[3] if summary_row else 0),
        "skill_rows_with_booked_cooldown": int(summary_row[4] if summary_row else 0),
        "skill_rows_with_skill_type": int(summary_row[5] if summary_row else 0),
        "skill_rows_with_description": int(summary_row[6] if summary_row else 0),
        "skill_rows_with_source": int(summary_row[7] if summary_row else 0),
        "skill_effect_rows": int(summary_row[8] if summary_row else 0),
        "registry_targets": int(summary_row[9] if summary_row else 0),
        "registry_targets_with_skill_data": int(summary_row[10] if summary_row else 0),
        "registry_targets_with_complete_skill_data": int(summary_row[11] if summary_row else 0),
        "registry_targets_ready": int(summary_row[12] if summary_row else 0),
        "skill_rows_by_source": {str(row[0]): int(row[1] or 0) for row in source_rows},
        "skill_rows_from_local_registry": int(next((row[1] for row in source_rows if str(row[0]) == "local_registry"), 0)),
        "skill_rows_from_hellhades": int(next((row[1] for row in source_rows if str(row[0]) == "hellhades"), 0)),
        "registry_targets_ready_from_local_registry": int(local_ready_row[0] if local_ready_row else 0),
        "registry_targets_ready_from_hellhades": int(hellhades_ready_row[0] if hellhades_ready_row else 0),
        "registry_last_refresh_utc": app_state.get("registry_last_refresh_utc", ""),
        "registry_target_policy": app_state.get("registry_target_policy", ""),
        "external_sync_last_utc": app_state.get("hellhades_last_enrich_utc", ""),
        "skill_registry_last_sync_provider_order": app_state.get("skill_registry_last_sync_provider_order", []),
        "skill_registry_last_sync_provider_hits": app_state.get("skill_registry_last_sync_provider_hits", {}),
        "targets_needing_data": [
            {
                "champion_name": str(row[0]),
                "has_external_ref": bool(row[1]),
                "skill_rows": int(row[2] or 0),
                "with_cooldown": int(row[3] or 0),
                "with_booked_cooldown": int(row[4] or 0),
                "with_skill_type": int(row[5] or 0),
                "with_description": int(row[6] or 0),
                "with_source": int(row[7] or 0),
                "skill_rows_with_data": int(row[8] or 0),
                "effect_rows": int(row[9] or 0),
            }
            for row in missing_rows
        ],
    }

    # Temporary compatibility aliases while UI and callers migrate away from HellHades terminology.
    summary["champion_catalog_with_hellhades_match"] = summary["champion_catalog_with_external_ref"]
    summary["registry_targets_with_hellhades_match"] = summary["champion_catalog_with_external_ref"]
    summary["registry_targets_with_skill_types"] = summary["registry_targets_with_complete_skill_data"]
    summary["registry_targets_fully_enriched"] = summary["registry_targets_ready"]
    summary["hellhades_last_enrich_utc"] = summary["external_sync_last_utc"]
    summary["needs_enrichment"] = summary["targets_needing_data"]
    return summary


def main() -> None:
    report = build_registry_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
