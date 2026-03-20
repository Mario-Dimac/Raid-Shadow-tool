from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from forge_db import DB_PATH, ensure_schema, load_app_state


def build_registry_report(db_path: Path = DB_PATH, limit: int = 25) -> Dict[str, Any]:
    ensure_schema(db_path)
    app_state = load_app_state(db_path)
    with sqlite3.connect(db_path) as conn:
        summary_row = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM champion_catalog),
                (SELECT COUNT(*) FROM champion_catalog WHERE hellhades_post_id IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skills),
                (SELECT COUNT(*) FROM champion_skills WHERE cooldown IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skills WHERE booked_cooldown IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skills WHERE skill_type IS NOT NULL),
                (SELECT COUNT(*) FROM champion_skill_effects),
                (SELECT COUNT(*) FROM registry_targets),
                (
                    SELECT COUNT(*)
                    FROM registry_targets rt
                    JOIN champion_catalog cc
                        ON cc.champion_name = rt.champion_name
                    WHERE cc.hellhades_post_id IS NOT NULL
                ),
                (
                    SELECT COUNT(DISTINCT rt.champion_name)
                    FROM registry_targets rt
                    JOIN champion_skills cs
                        ON cs.champion_name = rt.champion_name
                    WHERE cs.skill_type IS NOT NULL
                ),
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            rt.champion_name,
                            CASE WHEN cc.hellhades_post_id IS NOT NULL THEN 1 ELSE 0 END AS matched_post_id,
                            COUNT(cs.slot) AS skill_rows,
                            SUM(CASE WHEN cs.skill_type IS NOT NULL THEN 1 ELSE 0 END) AS with_skill_type,
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
                            matched_post_id = 1
                            AND with_skill_type = skill_rows
                            AND effect_rows > 0
                    )
                )
            """
        ).fetchone()
        missing_rows = conn.execute(
            """
            SELECT
                rt.champion_name,
                CASE WHEN cc.hellhades_post_id IS NOT NULL THEN 1 ELSE 0 END AS matched_post_id,
                COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                COUNT(DISTINCT CASE WHEN cs.cooldown IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS with_cooldown,
                COUNT(DISTINCT CASE WHEN cs.booked_cooldown IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS with_booked_cooldown,
                COUNT(DISTINCT CASE WHEN cs.skill_type IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS with_skill_type,
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
                matched_post_id = 0
                OR with_skill_type < skill_rows
                OR effect_rows = 0
            ORDER BY
                matched_post_id ASC,
                with_skill_type ASC,
                with_cooldown ASC,
                with_booked_cooldown ASC,
                effect_rows ASC,
                skill_rows DESC,
                rt.champion_name ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    return {
        "database": str(db_path),
        "champion_catalog": int(summary_row[0] if summary_row else 0),
        "champion_catalog_with_hellhades_match": int(summary_row[1] if summary_row else 0),
        "skill_rows": int(summary_row[2] if summary_row else 0),
        "skill_rows_with_cooldown": int(summary_row[3] if summary_row else 0),
        "skill_rows_with_booked_cooldown": int(summary_row[4] if summary_row else 0),
        "skill_rows_with_skill_type": int(summary_row[5] if summary_row else 0),
        "skill_effect_rows": int(summary_row[6] if summary_row else 0),
        "registry_targets": int(summary_row[7] if summary_row else 0),
        "registry_targets_with_hellhades_match": int(summary_row[8] if summary_row else 0),
        "registry_targets_with_skill_types": int(summary_row[9] if summary_row else 0),
        "registry_targets_fully_enriched": int(summary_row[10] if summary_row else 0),
        "registry_last_refresh_utc": app_state.get("registry_last_refresh_utc", ""),
        "registry_target_policy": app_state.get("registry_target_policy", ""),
        "hellhades_last_enrich_utc": app_state.get("hellhades_last_enrich_utc", ""),
        "needs_enrichment": [
            {
                "champion_name": str(row[0]),
                "matched_post_id": bool(row[1]),
                "skill_rows": int(row[2] or 0),
                "with_cooldown": int(row[3] or 0),
                "with_booked_cooldown": int(row[4] or 0),
                "with_skill_type": int(row[5] or 0),
                "effect_rows": int(row[6] or 0),
            }
            for row in missing_rows
        ],
    }


def main() -> None:
    report = build_registry_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
