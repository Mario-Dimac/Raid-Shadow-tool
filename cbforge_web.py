from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse

from account_stats import materialize_base_totals
from build_planner import build_champion_plan, list_build_profiles
from forge_db import DB_PATH, NORMALIZED_SOURCE_PATH, bootstrap_database, ensure_schema, refresh_account_stats_from_source
from gear_advisor import evaluate_gear_item, summarize_gear_verdicts
import hellhades_live
from hellhades_enrich import enrich_registry_from_source
from registry_report import build_registry_report


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
LEGACY_DIR = BASE_DIR / "old" / "legacy_20260318"
LEGACY_INPUT_DIR = LEGACY_DIR / "input"
GEAR_SLOT_ORDER = {
    "weapon": 1,
    "helmet": 2,
    "shield": 3,
    "gloves": 4,
    "chest": 5,
    "boots": 6,
    "ring": 7,
    "amulet": 8,
    "banner": 9,
}
SELL_QUEUE_PAGES = {
    "artifact": {"item_class": "artifact", "label": "Artifact (6 slot)"},
    "accessory": {"item_class": "accessory", "label": "Accessori (ring, amulet, banner)"},
}
SELL_QUEUE_VERDICTS = {"sell_now", "sell_after_12"}
SELL_QUEUE_MAIN_TIER_ORDER = {"weak": 0, "medium": 1, "strong": 2}


def open_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def build_web_summary(db_path: Path = DB_PATH) -> Dict[str, Any]:
    report = build_registry_report(db_path)
    with open_db(db_path) as conn:
        owned_row = conn.execute("SELECT COUNT(*) FROM account_champions").fetchone()
        report["owned_champions"] = int(owned_row[0] if owned_row else 0)
    return report


def refresh_gear_from_game(
    db_path: Path = DB_PATH,
    source_path: Path = NORMALIZED_SOURCE_PATH,
) -> Dict[str, Any]:
    if not LEGACY_DIR.exists():
        raise FileNotFoundError(f"Pipeline legacy non trovata: {LEGACY_DIR}")

    commands = [
        ["python", "extract_local.py"],
        ["python", "normalize.py"],
    ]
    results: List[Dict[str, Any]] = []
    combined_output: List[str] = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=LEGACY_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (completed.stdout + completed.stderr).strip()
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "output": output,
            }
        )
        if output:
            combined_output.append(output)
        if completed.returncode != 0:
            raise RuntimeError(output or f"Command failed: {' '.join(command)}")

    copied_files: List[str] = []
    for file_name in ("raw_account.json", "normalized_account.json"):
        legacy_path = LEGACY_INPUT_DIR / file_name
        target_path = BASE_DIR / "input" / file_name
        if not legacy_path.exists():
            raise FileNotFoundError(f"Output pipeline mancante: {legacy_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, target_path)
        copied_files.append(str(target_path))

    rebuild_summary = bootstrap_database(
        source_path=source_path,
        db_path=db_path,
        rebuild=False,
    )
    return {
        "ok": True,
        "results": results,
        "copied_files": copied_files,
        "summary": rebuild_summary,
        "output": "\n\n".join(chunk for chunk in combined_output if chunk),
    }


def build_gear_summary(db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        total_items = int(conn.execute("SELECT COUNT(*) FROM gear_items").fetchone()[0])
        equipped_items = int(
            conn.execute(
                "SELECT COUNT(*) FROM gear_items WHERE equipped_by IS NOT NULL AND equipped_by != ''"
            ).fetchone()[0]
        )
        locked_items = int(conn.execute("SELECT COUNT(*) FROM gear_items WHERE locked = 1").fetchone()[0])
        unique_sets = int(
            conn.execute(
                "SELECT COUNT(DISTINCT set_name) FROM gear_items WHERE set_name IS NOT NULL AND set_name != ''"
            ).fetchone()[0]
        )
        top_sets = [
            {"set_name": str(row["set_name"] or "(none)"), "count": int(row["item_count"] or 0)}
            for row in conn.execute(
                """
                SELECT set_name, COUNT(*) AS item_count
                FROM gear_items
                GROUP BY set_name
                ORDER BY item_count DESC, set_name ASC
                LIMIT 8
                """
            ).fetchall()
        ]
        slots = [
            {"slot": str(row["slot"] or ""), "count": int(row["item_count"] or 0)}
            for row in conn.execute(
                """
                SELECT slot, COUNT(*) AS item_count
                FROM gear_items
                GROUP BY slot
                ORDER BY item_count DESC, slot ASC
                """
            ).fetchall()
        ]
        item_rows = conn.execute(
            """
            SELECT
                gi.item_id,
                gi.slot,
                gi.set_name,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.main_stat_type,
                gi.equipped_by,
                ac.champion_name AS owner_name
            FROM gear_items gi
            LEFT JOIN account_champions ac
                ON ac.champ_id = gi.equipped_by
            """
        ).fetchall()
        substats_by_item = load_gear_substats_map(conn)

    evaluated_items: List[Dict[str, Any]] = []
    for row in item_rows:
        item = {
            "item_id": str(row["item_id"]),
            "slot": str(row["slot"] or ""),
            "set_name": str(row["set_name"] or ""),
            "rarity": str(row["rarity"] or ""),
            "rank": int(row["rank"] or 0),
            "level": int(row["level"] or 0),
            "main_stat_type": str(row["main_stat_type"] or ""),
            "equipped": bool(row["equipped_by"]),
            "owner_name": str(row["owner_name"] or ""),
        }
        item["advice_verdict"] = evaluate_gear_item(item, substats_by_item.get(item["item_id"], []))["verdict"]
        evaluated_items.append(item)

    return {
        "total_items": total_items,
        "equipped_items": equipped_items,
        "inventory_items": total_items - equipped_items,
        "locked_items": locked_items,
        "unique_sets": unique_sets,
        "verdict_counts": summarize_gear_verdicts(evaluated_items),
        "top_sets": top_sets,
        "slots": slots,
    }


def list_owned_champions(
    db_path: Path = DB_PATH,
    search: str = "",
    scope: str = "all",
    sort: str = "power",
) -> Dict[str, Any]:
    search_text = search.strip().lower()
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                ac.champ_id,
                ac.champion_name,
                ac.level,
                ac.rank,
                ac.booked,
                ac.rarity,
                ac.affinity,
                ac.faction,
                CASE WHEN rt.champion_name IS NOT NULL THEN 1 ELSE 0 END AS is_registry_target,
                cc.hellhades_post_id,
                COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                COUNT(DISTINCT CASE WHEN (
                    cs.cooldown IS NOT NULL
                    OR cs.booked_cooldown IS NOT NULL
                    OR NULLIF(TRIM(COALESCE(cs.skill_type, '')), '') IS NOT NULL
                    OR NULLIF(TRIM(COALESCE(cs.description_clean, cs.description, '')), '') IS NOT NULL
                ) THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_data,
                COUNT(DISTINCT CASE WHEN cse.effect_order IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_effects
            FROM account_champions ac
            LEFT JOIN registry_targets rt
                ON rt.champion_name = ac.champion_name
            LEFT JOIN champion_catalog cc
                ON cc.champion_name = ac.champion_name
            LEFT JOIN champion_skills cs
                ON cs.champion_name = ac.champion_name
            LEFT JOIN champion_skill_effects cse
                ON cse.champion_name = cs.champion_name
                AND cse.slot = cs.slot
            GROUP BY
                ac.champ_id,
                ac.champion_name,
                ac.level,
                ac.rank,
                ac.booked,
                ac.rarity,
                ac.affinity,
                ac.faction,
                is_registry_target,
                cc.hellhades_post_id
            """
        ).fetchall()

    champions_by_name: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        champion = {
            "champ_id": str(row["champ_id"]),
            "champion_name": str(row["champion_name"]),
            "level": int(row["level"] or 0),
            "rank": int(row["rank"] or 0),
            "booked": bool(row["booked"]),
            "rarity": str(row["rarity"] or ""),
            "affinity": str(row["affinity"] or ""),
            "faction": str(row["faction"] or ""),
            "is_registry_target": bool(row["is_registry_target"]),
            "hellhades_post_id": row["hellhades_post_id"],
            "skill_rows": int(row["skill_rows"] or 0),
            "skill_rows_with_data": int(row["skill_rows_with_data"] or 0),
            "skill_rows_with_effects": int(row["skill_rows_with_effects"] or 0),
        }
        champion["data_status"] = classify_skill_data_status(
            champion["skill_rows"],
            champion["skill_rows_with_data"],
        )
        champion["enriched"] = champion["data_status"] == "complete"
        if search_text and search_text not in champion["champion_name"].lower():
            continue
        if scope == "target" and not champion["is_registry_target"]:
            continue
        if scope == "missing" and champion["data_status"] == "complete":
            continue
        current = champions_by_name.get(champion["champion_name"])
        if current is None or champion_sort_key(champion) > champion_sort_key(current):
            champions_by_name[champion["champion_name"]] = champion

    champions = list(champions_by_name.values())

    if sort == "name":
        champions.sort(key=lambda item: (item["champion_name"].lower(), -item["level"], -item["rank"]))
    else:
        champions.sort(
            key=lambda item: (
                -item["level"],
                -item["rank"],
                0 if item["is_registry_target"] else 1,
                item["champion_name"].lower(),
            )
        )

    return {"champions": champions}


def champion_sort_key(champion: Dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(champion["level"]),
        int(champion["rank"]),
        1 if champion["booked"] else 0,
        1 if champion["enriched"] else 0,
    )


def classify_skill_data_status(skill_rows: int, skill_rows_with_data: int) -> str:
    if skill_rows <= 0 or skill_rows_with_data <= 0:
        return "missing"
    if skill_rows_with_data < skill_rows:
        return "partial"
    return "complete"


def list_gear_items(
    db_path: Path = DB_PATH,
    search: str = "",
    ownership: str = "all",
    item_class: str = "",
    slot: str = "",
    set_name: str = "",
    advice: str = "",
    sort: str = "rank",
) -> Dict[str, Any]:
    search_text = search.strip().lower()
    selected_item_class = item_class.strip().lower()
    selected_slot = slot.strip().lower()
    selected_set = set_name.strip().lower()
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                gi.item_id,
                gi.item_class,
                gi.slot,
                gi.set_name,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.ascension_level,
                gi.required_faction,
                gi.equipped_by,
                gi.locked,
                gi.main_stat_type,
                gi.main_stat_value,
                ac.champion_name AS owner_name,
                COUNT(gs.substat_order) AS substat_count,
                COALESCE(SUM(gs.glyph_value), 0) AS glyph_total
            FROM gear_items gi
            LEFT JOIN account_champions ac
                ON ac.champ_id = gi.equipped_by
            LEFT JOIN gear_substats gs
                ON gs.item_id = gi.item_id
            GROUP BY
                gi.item_id,
                gi.item_class,
                gi.slot,
                gi.set_name,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.ascension_level,
                gi.required_faction,
                gi.equipped_by,
                gi.locked,
                gi.main_stat_type,
                gi.main_stat_value,
                owner_name
            """
        ).fetchall()
        substats_by_item = load_gear_substats_map(conn)

    items: List[Dict[str, Any]] = []
    item_classes = sorted({str(row["item_class"] or "") for row in rows if str(row["item_class"] or "")}, key=lambda value: value.lower())
    slots = sorted({str(row["slot"] or "") for row in rows if str(row["slot"] or "")}, key=gear_slot_sort_key)
    sets = sorted({str(row["set_name"] or "") for row in rows if str(row["set_name"] or "")}, key=lambda value: value.lower())
    owners = sorted({str(row["owner_name"] or "") for row in rows if str(row["owner_name"] or "")}, key=lambda value: value.lower())

    for row in rows:
        item = {
            "item_id": str(row["item_id"]),
            "item_class": str(row["item_class"] or ""),
            "slot": str(row["slot"] or ""),
            "set_name": str(row["set_name"] or ""),
            "rarity": str(row["rarity"] or ""),
            "rank": int(row["rank"] or 0),
            "level": int(row["level"] or 0),
            "ascension_level": int(row["ascension_level"] or 0),
            "required_faction": str(row["required_faction"] or ""),
            "equipped_by": str(row["equipped_by"] or ""),
            "owner_name": str(row["owner_name"] or ""),
            "locked": bool(row["locked"]),
            "main_stat_type": str(row["main_stat_type"] or ""),
            "main_stat_value": row["main_stat_value"],
            "substat_count": int(row["substat_count"] or 0),
            "glyph_total": float(row["glyph_total"] or 0.0),
        }
        item["equipped"] = bool(item["equipped_by"])
        advice_payload = evaluate_gear_item(item, substats_by_item.get(item["item_id"], []))
        item["advice_verdict"] = advice_payload["verdict"]
        item["advice_reasons"] = advice_payload["reasons"]
        item["pre12_score"] = advice_payload["pre12_score"]
        item["realized_score"] = advice_payload["realized_score"]
        item["premium_rolls"] = advice_payload["premium_rolls"]
        item["good_rolls"] = advice_payload["good_rolls"]
        item["main_tier"] = advice_payload["main_tier"]
        haystack = " ".join(
            [
                item["item_id"],
                item["slot"],
                item["set_name"],
                item["owner_name"],
                item["main_stat_type"],
                item["rarity"],
                item["required_faction"],
                item["advice_verdict"],
                " ".join(item["advice_reasons"]),
            ]
        ).lower()
        if search_text and search_text not in haystack:
            continue
        if ownership == "equipped" and not item["equipped"]:
            continue
        if ownership == "inventory" and item["equipped"]:
            continue
        if selected_item_class and item["item_class"].lower() != selected_item_class:
            continue
        if selected_slot and item["slot"].lower() != selected_slot:
            continue
        if selected_set and item["set_name"].lower() != selected_set:
            continue
        if advice and item["advice_verdict"] != advice:
            continue
        items.append(item)

    if sort == "advice":
        advice_order = {
            "push_16": 0,
            "keep_16": 1,
            "keep_after_12": 2,
            "push_12": 3,
            "review_pre12": 4,
            "review_16": 5,
            "review_equipped": 6,
            "sell_after_12": 7,
            "sell_now": 8,
        }
        items.sort(
            key=lambda item: (
                advice_order.get(item["advice_verdict"], 99),
                -float(item["realized_score"]),
                -float(item["pre12_score"]),
                gear_slot_sort_key(item["slot"]),
                item["item_id"],
            )
        )
    elif sort == "slot":
        items.sort(key=lambda item: (gear_slot_sort_key(item["slot"]), item["set_name"].lower(), -item["rank"], -item["level"], item["item_id"]))
    elif sort == "set":
        items.sort(key=lambda item: (item["set_name"].lower(), gear_slot_sort_key(item["slot"]), -item["rank"], -item["level"], item["item_id"]))
    elif sort == "owner":
        items.sort(key=lambda item: (0 if item["equipped"] else 1, item["owner_name"].lower(), gear_slot_sort_key(item["slot"]), item["set_name"].lower(), item["item_id"]))
    else:
        items.sort(
            key=lambda item: (
                0 if item["equipped"] else 1,
                -item["rank"],
                -item["level"],
                -item["ascension_level"],
                gear_slot_sort_key(item["slot"]),
                item["set_name"].lower(),
                item["item_id"],
            )
        )

    return {
        "items": items,
        "filters": {
            "item_classes": item_classes,
            "slots": slots,
            "sets": sets,
            "owners": owners,
            "advice": sorted({item["advice_verdict"] for item in items}, key=lambda value: value.lower()),
        },
    }


def build_sell_queue_summary(
    db_path: Path = DB_PATH,
    limit_per_page: int = 50,
    exclude_ids: List[str] | None = None,
) -> Dict[str, Any]:
    candidates_by_page = collect_sell_queue_candidates(db_path, exclude_ids=exclude_ids)
    pages_payload: List[Dict[str, Any]] = []
    for page, page_meta in sorted(SELL_QUEUE_PAGES.items()):
        candidates = candidates_by_page[page]
        pages_payload.append(
            {
                "page": page,
                "label": page_meta["label"],
                "item_class": page_meta["item_class"],
                "candidate_count": len(candidates),
                "visible_candidates": candidates[:limit_per_page],
            }
        )
    return {"pages": pages_payload}


def collect_sell_queue_candidates(
    db_path: Path = DB_PATH,
    exclude_ids: List[str] | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    excluded = {str(item_id).strip() for item_id in (exclude_ids or []) if str(item_id).strip()}
    pages_payload: Dict[str, List[Dict[str, Any]]] = {}
    for page, page_meta in sorted(SELL_QUEUE_PAGES.items()):
        page_items = list_gear_items(
            db_path=db_path,
            ownership="inventory",
            item_class=page_meta["item_class"],
            sort="advice",
        )["items"]
        pages_payload[page] = [
            item
            for item in page_items
            if (
                str(item.get("advice_verdict") or "") in SELL_QUEUE_VERDICTS
                and not bool(item.get("locked"))
                and str(item.get("item_id") or "") not in excluded
            )
        ]
        pages_payload[page].sort(key=sell_queue_sort_key)
    return pages_payload


def sell_queue_sort_key(item: Dict[str, Any]) -> tuple[Any, ...]:
    main_tier = str(item.get("main_tier") or "")
    level = int(item.get("level") or 0)
    verdict = str(item.get("advice_verdict") or "")
    realized_score = float(item.get("realized_score") or 0.0)
    pre12_score = float(item.get("pre12_score") or 0.0)
    rank = int(item.get("rank") or 0)

    if main_tier == "weak" and level < 12:
        bucket = 0
    elif main_tier == "weak":
        bucket = 1
    elif verdict == "sell_now":
        bucket = 2
    else:
        bucket = 3

    return (
        bucket,
        level,
        SELL_QUEUE_MAIN_TIER_ORDER.get(main_tier, 99),
        pre12_score,
        realized_score,
        rank,
        gear_slot_sort_key(str(item.get("slot") or "")),
        str(item.get("item_id") or ""),
    )


def sell_artifacts_from_queue(
    artifact_ids: List[Any],
    db_path: Path = DB_PATH,
    access_token: str | None = None,
) -> Dict[str, Any]:
    requested_ids: List[str] = []
    seen_ids = set()
    for raw_value in artifact_ids:
        item_id = str(raw_value or "").strip()
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        requested_ids.append(item_id)

    if not requested_ids:
        raise ValueError("artifact_ids mancanti.")

    candidates_by_id: Dict[str, Dict[str, Any]] = {}
    for page_candidates in collect_sell_queue_candidates(db_path).values():
        for item in page_candidates:
            candidates_by_id[str(item["item_id"])] = item

    approved_ids = [item_id for item_id in requested_ids if item_id in candidates_by_id]
    rejected_ids = [item_id for item_id in requested_ids if item_id not in candidates_by_id]
    if not approved_ids:
        raise ValueError("Nessun ID vendibile trovato nella coda corrente.")

    result = hellhades_live.sell_artifacts_live(approved_ids, access_token=access_token)
    approved_items = [candidates_by_id[item_id] for item_id in approved_ids]
    message = str(result.get("message") or "")
    if rejected_ids:
        message = f"{message} Ignorati {len(rejected_ids)} ID fuori coda o non vendibili."
    result.update(
        {
            "requested_ids": requested_ids,
            "approved_ids": approved_ids,
            "rejected_ids": rejected_ids,
            "approved_items": approved_items,
            "message": message.strip(),
        }
    )
    return result


def gear_item_detail(item_id: str, db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        item_row = conn.execute(
            """
            SELECT
                gi.item_id,
                gi.item_class,
                gi.slot,
                gi.set_name,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.ascension_level,
                gi.required_faction,
                gi.required_faction_id,
                gi.equipped_by,
                gi.locked,
                gi.main_stat_type,
                gi.main_stat_value,
                ac.champion_name AS owner_name
            FROM gear_items gi
            LEFT JOIN account_champions ac
                ON ac.champ_id = gi.equipped_by
            WHERE gi.item_id = ?
            """,
            (item_id,),
        ).fetchone()
        if item_row is None:
            raise KeyError(f"Equip non trovato: {item_id}")
        substat_rows = conn.execute(
            """
            SELECT substat_order, stat_type, stat_value, rolls, glyph_value
            FROM gear_substats
            WHERE item_id = ?
            ORDER BY substat_order ASC
            """,
            (item_id,),
        ).fetchall()

    substats = [
        {
            "substat_order": int(row["substat_order"] or 0),
            "stat_type": str(row["stat_type"] or ""),
            "stat_value": row["stat_value"],
            "rolls": int(row["rolls"] or 0),
            "glyph_value": row["glyph_value"],
        }
        for row in substat_rows
    ]
    item = {
        "item_id": str(item_row["item_id"]),
        "item_class": str(item_row["item_class"] or ""),
        "slot": str(item_row["slot"] or ""),
        "set_name": str(item_row["set_name"] or ""),
        "rarity": str(item_row["rarity"] or ""),
        "rank": int(item_row["rank"] or 0),
        "level": int(item_row["level"] or 0),
        "ascension_level": int(item_row["ascension_level"] or 0),
        "required_faction": str(item_row["required_faction"] or ""),
        "required_faction_id": int(item_row["required_faction_id"] or 0),
        "equipped_by": str(item_row["equipped_by"] or ""),
        "owner_name": str(item_row["owner_name"] or ""),
        "equipped": bool(item_row["equipped_by"]),
        "locked": bool(item_row["locked"]),
        "main_stat_type": str(item_row["main_stat_type"] or ""),
        "main_stat_value": item_row["main_stat_value"],
    }
    return {
        "item": item,
        "substats": substats,
        "advice": evaluate_gear_item(item, substats),
    }


def gear_slot_sort_key(slot: str) -> tuple[int, str]:
    normalized = str(slot or "").strip().lower()
    return (GEAR_SLOT_ORDER.get(normalized, 99), normalized)


def load_gear_substats_map(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT item_id, substat_order, stat_type, stat_value, rolls, glyph_value
        FROM gear_substats
        ORDER BY item_id ASC, substat_order ASC
        """
    ).fetchall()
    substats_by_item: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        substats_by_item.setdefault(str(row["item_id"]), []).append(
            {
                "substat_order": int(row["substat_order"] or 0),
                "stat_type": str(row["stat_type"] or ""),
                "stat_value": row["stat_value"],
                "rolls": int(row["rolls"] or 0),
                "glyph_value": row["glyph_value"],
            }
        )
    return substats_by_item


def champion_detail(champion_name: str, db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        account_row = conn.execute(
            """
            SELECT champ_id, champion_name, rarity, affinity, faction, level, rank, awakening_level, empowerment_level, booked
            FROM account_champions
            WHERE champion_name = ?
            ORDER BY level DESC, rank DESC, awakening_level DESC, empowerment_level DESC
            LIMIT 1
            """,
            (champion_name,),
        ).fetchone()
        if account_row is None:
            raise KeyError(f"Campione non trovato: {champion_name}")

        catalog_row = conn.execute(
            """
            SELECT champion_name, hellhades_post_id, hellhades_url, last_enriched_at
            FROM champion_catalog
            WHERE champion_name = ?
            """,
            (champion_name,),
        ).fetchone()
        role_rows = conn.execute(
            "SELECT role_tag FROM champion_roles WHERE champion_name = ? ORDER BY role_tag ASC",
            (champion_name,),
        ).fetchall()
        base_stat_rows = conn.execute(
            "SELECT stat_name, stat_value FROM champion_base_stats WHERE champion_name = ? ORDER BY stat_name ASC",
            (champion_name,),
        ).fetchall()
        total_stat_rows = conn.execute(
            """
            SELECT stat_name, stat_value
            FROM account_champion_total_stats
            WHERE champ_id = ?
            ORDER BY stat_name ASC
            """,
            (account_row["champ_id"],),
        ).fetchall()
        stat_model_row = conn.execute(
            """
            SELECT source, completeness, unsupported_sets_json, applied_sets_json, computed_at
            FROM account_champion_stat_models
            WHERE champ_id = ?
            """,
            (account_row["champ_id"],),
        ).fetchone()
        skill_rows = conn.execute(
            """
            SELECT slot, skill_order, skill_id, skill_name, cooldown, booked_cooldown, description, skill_type, description_clean, source
            FROM champion_skills
            WHERE champion_name = ?
            ORDER BY skill_order ASC
            """,
            (champion_name,),
        ).fetchall()
        effect_rows = conn.execute(
            """
            SELECT slot, effect_order, effect_type, target, effect_value, duration, chance, condition_text
            FROM champion_skill_effects
            WHERE champion_name = ?
            ORDER BY slot ASC, effect_order ASC
            """,
            (champion_name,),
        ).fetchall()

    unsupported_sets: List[str] = []
    applied_sets: List[Dict[str, Any]] = []
    if stat_model_row is not None:
        try:
            unsupported_sets = json.loads(stat_model_row["unsupported_sets_json"] or "[]")
        except json.JSONDecodeError:
            unsupported_sets = []
        try:
            applied_sets = json.loads(stat_model_row["applied_sets_json"] or "[]")
        except json.JSONDecodeError:
            applied_sets = []

    base_stats = {str(row["stat_name"]): row["stat_value"] for row in base_stat_rows}
    effects_by_slot: Dict[str, List[Dict[str, Any]]] = {}
    for row in effect_rows:
        effects_by_slot.setdefault(str(row["slot"]), []).append(
            {
                "effect_order": int(row["effect_order"] or 0),
                "effect_type": str(row["effect_type"] or ""),
                "target": str(row["target"] or ""),
                "effect_value": row["effect_value"],
                "duration": row["duration"],
                "chance": row["chance"],
                "condition_text": str(row["condition_text"] or ""),
            }
        )
    skill_rows_with_data = 0
    skill_sources = sorted({str(row["source"] or "").strip() for row in skill_rows if str(row["source"] or "").strip()})
    for row in skill_rows:
        slot_key = str(row["slot"])
        has_data = (
            row["cooldown"] is not None
            or row["booked_cooldown"] is not None
            or bool(str(row["skill_type"] or "").strip())
            or bool(str(row["description_clean"] or row["description"] or "").strip())
            or bool(effects_by_slot.get(slot_key))
        )
        if has_data:
            skill_rows_with_data += 1
    skill_data_status = classify_skill_data_status(len(skill_rows), skill_rows_with_data)
    external_provider = skill_sources[0] if len(skill_sources) == 1 else ""
    if not external_provider and catalog_row and (
        catalog_row["hellhades_post_id"] is not None
        or str(catalog_row["hellhades_url"] or "").strip()
        or str(catalog_row["last_enriched_at"] or "").strip()
    ):
        external_provider = "hellhades"

    return {
        "account": {
            "champ_id": str(account_row["champ_id"]),
            "champion_name": str(account_row["champion_name"]),
            "rarity": str(account_row["rarity"] or ""),
            "affinity": str(account_row["affinity"] or ""),
            "faction": str(account_row["faction"] or ""),
            "level": int(account_row["level"] or 0),
            "rank": int(account_row["rank"] or 0),
            "awakening_level": int(account_row["awakening_level"] or 0),
            "empowerment_level": int(account_row["empowerment_level"] or 0),
            "booked": bool(account_row["booked"]),
        },
        "catalog": {
            "external_provider": external_provider,
            "external_ref_id": int(catalog_row["hellhades_post_id"]) if catalog_row and catalog_row["hellhades_post_id"] is not None else None,
            "external_url": str(catalog_row["hellhades_url"] or "") if catalog_row else "",
            "external_synced_at": str(catalog_row["last_enriched_at"] or "") if catalog_row else "",
            "hellhades_post_id": int(catalog_row["hellhades_post_id"]) if catalog_row and catalog_row["hellhades_post_id"] is not None else None,
            "hellhades_url": str(catalog_row["hellhades_url"] or "") if catalog_row else "",
            "last_enriched_at": str(catalog_row["last_enriched_at"] or "") if catalog_row else "",
        },
        "roles": [str(row["role_tag"]) for row in role_rows],
        "base_stats": base_stats,
        "base_totals": materialize_base_totals(base_stats),
        "total_stats": {str(row["stat_name"]): row["stat_value"] for row in total_stat_rows},
        "stat_model": {
            "source": str(stat_model_row["source"] or "") if stat_model_row else "",
            "completeness": str(stat_model_row["completeness"] or "") if stat_model_row else "",
            "unsupported_sets": unsupported_sets if isinstance(unsupported_sets, list) else [],
            "applied_sets": applied_sets if isinstance(applied_sets, list) else [],
            "computed_at": str(stat_model_row["computed_at"] or "") if stat_model_row else "",
        },
        "skills": [
            {
                "slot": str(row["slot"]),
                "skill_order": int(row["skill_order"] or 0),
                "skill_id": str(row["skill_id"] or ""),
                "skill_name": str(row["skill_name"] or ""),
                "cooldown": row["cooldown"],
                "booked_cooldown": row["booked_cooldown"],
                "description": str(row["description"] or ""),
                "skill_type": str(row["skill_type"] or ""),
                "description_clean": str(row["description_clean"] or ""),
                "source": str(row["source"] or ""),
                "effects": effects_by_slot.get(str(row["slot"]), []),
            }
            for row in skill_rows
        ],
        "skill_data": {
            "skill_rows": len(skill_rows),
            "skill_rows_with_data": skill_rows_with_data,
            "skill_rows_with_effects": sum(1 for effects in effects_by_slot.values() if effects),
            "data_status": skill_data_status,
            "sources": skill_sources,
            "primary_source": skill_sources[0] if len(skill_sources) == 1 else "",
        },
    }


def first_query_value(query: Dict[str, List[str]], key: str) -> str:
    values = query.get(key) or [""]
    return values[0]


class CBForgeHandler(BaseHTTPRequestHandler):
    server_version = "CBForgeWeb/0.1"

    @property
    def app(self) -> "CBForgeWebServer":
        return self.server  # type: ignore[return-value]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/gear":
            self._send_file(WEB_DIR / "gear.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/build":
            self._send_file(WEB_DIR / "build.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_file(WEB_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/gear.js":
            self._send_file(WEB_DIR / "gear.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/build.js":
            self._send_file(WEB_DIR / "build.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/style.css":
            self._send_file(WEB_DIR / "style.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/summary":
            self._send_json(build_web_summary(self.app.db_path))
            return
        if parsed.path == "/api/gear-summary":
            self._send_json(build_gear_summary(self.app.db_path))
            return
        if parsed.path == "/api/champions":
            query = parse_qs(parsed.query)
            self._send_json(
                list_owned_champions(
                    db_path=self.app.db_path,
                    search=first_query_value(query, "search"),
                    scope=first_query_value(query, "scope") or "all",
                    sort=first_query_value(query, "sort") or "power",
                )
            )
            return
        if parsed.path == "/api/build-profiles":
            self._send_json({"profiles": list_build_profiles()})
            return
        if parsed.path == "/api/build-plan":
            query = parse_qs(parsed.query)
            name = first_query_value(query, "name")
            profile = first_query_value(query, "profile") or "arena_speed_lead"
            if not name:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'name' mancante.")
                return
            try:
                payload = build_champion_plan(unquote(name), profile_key=profile, db_path=self.app.db_path)
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/gear-items":
            query = parse_qs(parsed.query)
            self._send_json(
                list_gear_items(
                    db_path=self.app.db_path,
                    search=first_query_value(query, "search"),
                    ownership=first_query_value(query, "ownership") or "all",
                    item_class=first_query_value(query, "item_class"),
                    slot=first_query_value(query, "slot"),
                    set_name=first_query_value(query, "set"),
                    advice=first_query_value(query, "advice"),
                    sort=first_query_value(query, "sort") or "rank",
                )
            )
            return
        if parsed.path == "/api/sell-queue":
            query = parse_qs(parsed.query)
            exclude_ids = query.get("exclude_id") or []
            self._send_json(build_sell_queue_summary(self.app.db_path, exclude_ids=exclude_ids))
            return
        if parsed.path == "/api/champion":
            query = parse_qs(parsed.query)
            name = first_query_value(query, "name")
            if not name:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'name' mancante.")
                return
            try:
                payload = champion_detail(unquote(name), self.app.db_path)
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/gear-item":
            query = parse_qs(parsed.query)
            item_id = first_query_value(query, "id")
            if not item_id:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'id' mancante.")
                return
            try:
                payload = gear_item_detail(unquote(item_id), self.app.db_path)
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(payload)
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "Endpoint non trovato.")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json_body()
        try:
            if parsed.path == "/api/rebuild-db":
                summary = bootstrap_database(
                    source_path=self.app.source_path,
                    db_path=self.app.db_path,
                    rebuild=True,
                )
                self._send_json({"ok": True, "summary": summary})
                return
            if parsed.path == "/api/update-targets":
                summary = enrich_registry_from_source("auto", db_path=self.app.db_path)
                self._send_json({"ok": True, "summary": summary})
                return
            if parsed.path == "/api/recompute-stats":
                summary = refresh_account_stats_from_source(
                    source_path=self.app.source_path,
                    db_path=self.app.db_path,
                )
                self._send_json({"ok": True, "summary": summary})
                return
            if parsed.path == "/api/refresh-gear":
                payload = refresh_gear_from_game(
                    db_path=self.app.db_path,
                    source_path=self.app.source_path,
                )
                self._send_json(payload)
                return
            if parsed.path == "/api/update-champion":
                champion_name = str(payload.get("champion_name") or "").strip()
                if not champion_name:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "champion_name mancante.")
                    return
                summary = enrich_registry_from_source(
                    "auto",
                    db_path=self.app.db_path,
                    champion_names=[champion_name],
                )
                self._send_json({"ok": True, "summary": summary})
                return
            if parsed.path == "/api/live-sell-artifacts":
                result = sell_artifacts_from_queue(
                    artifact_ids=list(payload.get("artifact_ids") or []),
                    db_path=self.app.db_path,
                    access_token=str(payload.get("access_token") or "").strip() or None,
                )
                self._send_json({"ok": True, "result": result})
                return
        except Exception as exc:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "Endpoint non trovato.")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_file(self, path: Path, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        if not path.exists():
            self._send_error_json(HTTPStatus.NOT_FOUND, f"Asset mancante: {path.name}")
            return
        encoded = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}


class CBForgeWebServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], db_path: Path, source_path: Path):
        super().__init__(server_address, handler_cls)
        self.db_path = db_path
        self.source_path = source_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CB Forge web interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--source-path", type=Path, default=NORMALIZED_SOURCE_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_schema(args.db_path)
    server = CBForgeWebServer((args.host, args.port), CBForgeHandler, db_path=args.db_path, source_path=args.source_path)
    print(f"CB Forge web listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
