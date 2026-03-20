from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from account_stats import build_stat_computation


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "cbforge.sqlite3"
NORMALIZED_SOURCE_PATH = INPUT_DIR / "normalized_account.json"


DEFAULT_SET_RULES: Dict[str, Dict[str, Any]] = {
    "Attack Speed": {"pieces_required": 2, "stats": [("spd", 12.0)]},
    "Accuracy": {"pieces_required": 2, "stats": [("acc", 40.0)]},
    "Accuracy And Speed": {"pieces_required": 2, "stats": [("acc", 40.0), ("spd", 12.0)]},
    "HP And Heal": {"pieces_required": 2, "stats": [("hp_pct", 15.0)], "heal_each_turn_pct": 3.0},
    "HP And Defence": {"pieces_required": 2, "stats": [("hp_pct", 15.0), ("def_pct", 15.0)]},
    "Attack Power And Ignore Defense": {"pieces_required": 2, "stats": [("atk_pct", 15.0)]},
    "Shield And Speed": {"pieces_required": 2, "stats": [("spd", 12.0)]},
    "Shield And HP": {"pieces_required": 2, "stats": [("hp_pct", 15.0)]},
    "Shield And Attack Power": {"pieces_required": 2, "stats": [("atk_pct", 15.0)]},
    "Shield And Critical Chance": {"pieces_required": 2, "stats": [("crit_rate", 12.0)]},
}


SCHEMA_STATEMENTS: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS champion_catalog (
        champion_name TEXT PRIMARY KEY,
        rarity TEXT,
        affinity TEXT,
        faction TEXT,
        hellhades_post_id INTEGER,
        hellhades_url TEXT,
        last_enriched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champion_roles (
        champion_name TEXT NOT NULL,
        role_tag TEXT NOT NULL,
        PRIMARY KEY (champion_name, role_tag)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champion_base_stats (
        champion_name TEXT NOT NULL,
        stat_name TEXT NOT NULL,
        stat_value REAL NOT NULL,
        PRIMARY KEY (champion_name, stat_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champion_skills (
        champion_name TEXT NOT NULL,
        slot TEXT NOT NULL,
        skill_order INTEGER NOT NULL,
        skill_id TEXT,
        skill_name TEXT,
        cooldown INTEGER,
        booked_cooldown INTEGER,
        description TEXT,
        skill_type TEXT,
        description_clean TEXT,
        source TEXT,
        PRIMARY KEY (champion_name, slot, skill_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS champion_skill_effects (
        champion_name TEXT NOT NULL,
        slot TEXT NOT NULL,
        effect_order INTEGER NOT NULL,
        effect_type TEXT,
        target TEXT,
        effect_value REAL,
        duration INTEGER,
        chance REAL,
        condition_text TEXT,
        PRIMARY KEY (champion_name, slot, effect_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS registry_targets (
        champion_name TEXT PRIMARY KEY,
        target_reason TEXT NOT NULL,
        priority INTEGER NOT NULL,
        last_imported_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_champions (
        champ_id TEXT PRIMARY KEY,
        champion_name TEXT NOT NULL,
        rarity TEXT,
        affinity TEXT,
        faction TEXT,
        level INTEGER NOT NULL,
        rank INTEGER NOT NULL,
        awakening_level INTEGER NOT NULL,
        empowerment_level INTEGER NOT NULL,
        booked INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_champion_total_stats (
        champ_id TEXT NOT NULL,
        stat_name TEXT NOT NULL,
        stat_value REAL NOT NULL,
        PRIMARY KEY (champ_id, stat_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_champion_imported_total_stats (
        champ_id TEXT NOT NULL,
        stat_name TEXT NOT NULL,
        stat_value REAL NOT NULL,
        PRIMARY KEY (champ_id, stat_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_champion_stat_models (
        champ_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        completeness TEXT NOT NULL,
        unsupported_sets_json TEXT NOT NULL,
        applied_sets_json TEXT NOT NULL,
        computed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gear_items (
        item_id TEXT PRIMARY KEY,
        item_class TEXT,
        slot TEXT,
        set_name TEXT,
        rarity TEXT,
        rank INTEGER NOT NULL,
        level INTEGER NOT NULL,
        ascension_level INTEGER NOT NULL,
        required_faction TEXT,
        required_faction_id INTEGER NOT NULL,
        equipped_by TEXT,
        locked INTEGER NOT NULL,
        main_stat_type TEXT,
        main_stat_value REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gear_substats (
        item_id TEXT NOT NULL,
        substat_order INTEGER NOT NULL,
        stat_type TEXT,
        stat_value REAL NOT NULL,
        rolls INTEGER NOT NULL,
        glyph_value REAL NOT NULL,
        PRIMARY KEY (item_id, substat_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_bonuses (
        bonus_id TEXT PRIMARY KEY,
        source TEXT,
        scope TEXT,
        target TEXT,
        stat TEXT,
        value REAL NOT NULL,
        active INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS set_definitions (
        set_name TEXT PRIMARY KEY,
        pieces_required INTEGER NOT NULL,
        heal_each_turn_pct REAL NOT NULL,
        source TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS set_definition_stats (
        set_name TEXT NOT NULL,
        stat_order INTEGER NOT NULL,
        stat_type TEXT NOT NULL,
        stat_value REAL NOT NULL,
        PRIMARY KEY (set_name, stat_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS combat_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        saved_at TEXT NOT NULL,
        team_name TEXT NOT NULL,
        difficulty TEXT,
        affinity TEXT,
        boss_turn INTEGER NOT NULL,
        damage REAL NOT NULL,
        source TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS combat_run_members (
        run_id INTEGER NOT NULL,
        member_order INTEGER NOT NULL,
        champ_id TEXT,
        champion_name TEXT,
        PRIMARY KEY (run_id, member_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS combat_sessions (
        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT,
        ended_at TEXT,
        team_name TEXT,
        difficulty TEXT,
        affinity TEXT,
        source TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_state (
        state_key TEXT PRIMARY KEY,
        state_value TEXT
    )
    """,
)


def ensure_schema(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        ensure_schema_columns(conn)
        conn.commit()


def ensure_schema_columns(conn: sqlite3.Connection) -> None:
    ensure_column(
        conn,
        table_name="champion_catalog",
        column_name="hellhades_post_id",
        column_sql="INTEGER",
    )
    ensure_column(
        conn,
        table_name="champion_catalog",
        column_name="hellhades_url",
        column_sql="TEXT",
    )
    ensure_column(
        conn,
        table_name="champion_catalog",
        column_name="last_enriched_at",
        column_sql="TEXT",
    )
    ensure_column(
        conn,
        table_name="champion_skills",
        column_name="skill_type",
        column_sql="TEXT",
    )
    ensure_column(
        conn,
        table_name="champion_skills",
        column_name="description_clean",
        column_sql="TEXT",
    )
    ensure_column(
        conn,
        table_name="champion_skills",
        column_name="source",
        column_sql="TEXT",
    )


def ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing_columns = {str(row[1]) for row in rows}
    if column_name not in existing_columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def reset_database(path: Path = DB_PATH) -> None:
    if path.exists():
        path.unlink()
    ensure_schema(path)


def load_source_account(source_path: Path = NORMALIZED_SOURCE_PATH) -> Dict[str, Any]:
    account = json.loads(source_path.read_text(encoding="utf-8-sig"))
    reconcile_loaded_account_ownership(account)
    return account if isinstance(account, dict) else {}


def bootstrap_database(
    source_path: Path = NORMALIZED_SOURCE_PATH,
    db_path: Path = DB_PATH,
    rebuild: bool = True,
) -> Dict[str, Any]:
    account = load_source_account(source_path)
    if rebuild:
        reset_database(db_path)
    else:
        ensure_schema(db_path)

    champions = list_value(account.get("champions"))
    gear = list_value(account.get("gear"))
    bonuses = list_value(account.get("account_bonuses"))
    templates = select_best_template_rows(champions)
    observed_sets = collect_observed_sets(gear)

    with sqlite3.connect(db_path) as conn:
        if not rebuild:
            clear_runtime_tables(conn)

        for champion_name, champion in templates.items():
            conn.execute(
                """
                INSERT INTO champion_catalog (champion_name, rarity, affinity, faction)
                VALUES (?, ?, ?, ?)
                """,
                (
                    champion_name,
                    string_value(champion.get("rarity")),
                    string_value(champion.get("affinity")),
                    string_value(champion.get("faction")),
                ),
            )
            for role_tag in sorted({string_value(role) for role in list_value(champion.get("role_tags")) if string_value(role)}):
                conn.execute(
                    "INSERT INTO champion_roles (champion_name, role_tag) VALUES (?, ?)",
                    (champion_name, role_tag),
                )
            for stat_name, stat_value in sorted(dict_value(champion.get("base_stats")).items()):
                conn.execute(
                    "INSERT INTO champion_base_stats (champion_name, stat_name, stat_value) VALUES (?, ?, ?)",
                    (champion_name, string_value(stat_name), float_value(stat_value)),
                )
            for skill_order, skill in enumerate(list_value(champion.get("skills")), start=1):
                slot = normalize_skill_slot(skill, skill_order)
                conn.execute(
                    """
                    INSERT INTO champion_skills (
                        champion_name, slot, skill_order, skill_id, skill_name,
                        cooldown, booked_cooldown, description, skill_type, description_clean, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        champion_name,
                        slot,
                        skill_order,
                        optional_string(skill.get("skill_id")),
                        first_non_empty(
                            skill.get("name"),
                            skill.get("skill_name"),
                            skill.get("label"),
                            skill.get("title"),
                        ),
                        nullable_int(
                            first_non_empty(
                                skill.get("cooldown"),
                                skill.get("cooldown_base"),
                                skill.get("cooldown_value"),
                            )
                        ),
                        nullable_int(
                            first_non_empty(
                                skill.get("cooldown_booked"),
                                skill.get("cooldown_after_books"),
                                skill.get("booked_cooldown"),
                            )
                        ),
                        optional_string(first_non_empty(skill.get("description"), skill.get("text"))),
                        optional_string(first_non_empty(skill.get("skill_type"), skill.get("type"))),
                        optional_string(first_non_empty(skill.get("description_clean"), skill.get("description"), skill.get("text"))),
                        optional_string(first_non_empty(skill.get("source"), "import")),
                    ),
                )
                for effect_order, effect in enumerate(list_value(skill.get("effects")), start=1):
                    effect_map = dict_value(effect)
                    conn.execute(
                        """
                        INSERT INTO champion_skill_effects (
                            champion_name, slot, effect_order, effect_type, target,
                            effect_value, duration, chance, condition_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            champion_name,
                            slot,
                            effect_order,
                            optional_string(first_non_empty(effect_map.get("type"), effect_map.get("effect_type"))),
                            optional_string(effect_map.get("target")),
                            nullable_float(first_non_empty(effect_map.get("value"), effect_map.get("amount"))),
                            nullable_int(effect_map.get("duration")),
                            nullable_float(effect_map.get("chance")),
                            optional_string(first_non_empty(effect_map.get("condition"), effect_map.get("notes"))),
                        ),
                    )

        level_60_targets = sorted(
            {
                string_value(champion.get("name"))
                for champion in champions
                if int_value(champion.get("level")) == 60 and string_value(champion.get("name"))
            }
        )
        imported_at = now_utc_iso()
        for champion_name in level_60_targets:
            conn.execute(
                """
                INSERT INTO registry_targets (champion_name, target_reason, priority, last_imported_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    champion_name,
                    "owned_level_60",
                    100,
                    imported_at,
                ),
            )

        for champion in champions:
            champ_id = string_value(champion.get("champ_id"))
            conn.execute(
                """
                INSERT INTO account_champions (
                    champ_id, champion_name, rarity, affinity, faction,
                    level, rank, awakening_level, empowerment_level, booked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    champ_id,
                    string_value(champion.get("name")),
                    string_value(champion.get("rarity")),
                    string_value(champion.get("affinity")),
                    string_value(champion.get("faction")),
                    int_value(champion.get("level")),
                    int_value(champion.get("rank")),
                    int_value(champion.get("awakening_level")),
                    int_value(champion.get("empowerment_level")),
                    1 if bool(champion.get("booked")) else 0,
                ),
            )
            for stat_name, stat_value in sorted(dict_value(champion.get("total_stats")).items()):
                conn.execute(
                    """
                    INSERT INTO account_champion_imported_total_stats (champ_id, stat_name, stat_value)
                    VALUES (?, ?, ?)
                    """,
                    (champ_id, string_value(stat_name), float_value(stat_value)),
                )

        for item in gear:
            main_stat = dict_value(item.get("main_stat"))
            item_id = string_value(item.get("item_id"))
            conn.execute(
                """
                INSERT INTO gear_items (
                    item_id, item_class, slot, set_name, rarity, rank, level,
                    ascension_level, required_faction, required_faction_id,
                    equipped_by, locked, main_stat_type, main_stat_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    string_value(item.get("item_class")),
                    string_value(item.get("slot")),
                    string_value(item.get("set_name")),
                    string_value(item.get("rarity")),
                    int_value(item.get("rank")),
                    int_value(item.get("level")),
                    int_value(item.get("ascension_level")),
                    string_value(item.get("required_faction")),
                    int_value(item.get("required_faction_id")),
                    optional_string(item.get("equipped_by")),
                    1 if bool(item.get("locked")) else 0,
                    string_value(main_stat.get("type")),
                    float_value(main_stat.get("value")),
                ),
            )
            for substat_order, substat in enumerate(list_value(item.get("substats")), start=1):
                substat_map = dict_value(substat)
                conn.execute(
                    """
                    INSERT INTO gear_substats (
                        item_id, substat_order, stat_type, stat_value, rolls, glyph_value
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        substat_order,
                        string_value(substat_map.get("type")),
                        float_value(substat_map.get("value")),
                        int_value(substat_map.get("rolls")),
                        float_value(substat_map.get("glyph_value")),
                    ),
                )

        for bonus in bonuses:
            conn.execute(
                """
                INSERT INTO account_bonuses (
                    bonus_id, source, scope, target, stat, value, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    string_value(bonus.get("bonus_id")),
                    string_value(bonus.get("source")),
                    string_value(bonus.get("scope")),
                    string_value(bonus.get("target")),
                    string_value(bonus.get("stat")),
                    float_value(bonus.get("value")),
                    1 if bool(bonus.get("active")) else 0,
                ),
            )

        for set_name in sorted(observed_sets | set(DEFAULT_SET_RULES)):
            rule = dict_value(DEFAULT_SET_RULES.get(set_name))
            conn.execute(
                """
                INSERT INTO set_definitions (set_name, pieces_required, heal_each_turn_pct, source)
                VALUES (?, ?, ?, ?)
                """,
                (
                    set_name,
                    int_value(rule.get("pieces_required")),
                    float_value(rule.get("heal_each_turn_pct")),
                    "bootstrap_rules" if rule else "observed_gear",
                ),
            )
            for stat_order, stat_row in enumerate(list_value(rule.get("stats")), start=1):
                stat_type, stat_value = normalize_set_stat(stat_row)
                conn.execute(
                    """
                    INSERT INTO set_definition_stats (set_name, stat_order, stat_type, stat_value)
                    VALUES (?, ?, ?, ?)
                    """,
                    (set_name, stat_order, stat_type, stat_value),
                )

        stats_summary = refresh_account_stat_models_in_conn(conn)
        conn.commit()

    save_app_state(
        {
            "account_stats_last_refresh_utc": stats_summary["computed_at"],
            "account_stats_summary": stats_summary,
            "registry_last_refresh_utc": imported_at,
            "registry_target_policy": "owned_level_60_only",
            "registry_target_count": len(level_60_targets),
        },
        db_path,
    )

    return database_status(db_path)


def database_status(path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(path)
    status: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
    }
    tables = (
        "champion_catalog",
        "champion_roles",
        "champion_base_stats",
        "champion_skills",
        "champion_skill_effects",
        "registry_targets",
        "account_champions",
        "account_champion_total_stats",
        "account_champion_imported_total_stats",
        "account_champion_stat_models",
        "gear_items",
        "gear_substats",
        "account_bonuses",
        "set_definitions",
        "set_definition_stats",
        "combat_runs",
        "combat_run_members",
        "combat_sessions",
        "app_state",
    )
    with sqlite3.connect(path) as conn:
        for table in tables:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            status[table] = int(row[0] if row else 0)
    return status


def clear_runtime_tables(conn: sqlite3.Connection) -> None:
    for table in (
        "champion_catalog",
        "champion_roles",
        "champion_base_stats",
        "champion_skills",
        "champion_skill_effects",
        "registry_targets",
        "account_champions",
        "account_champion_total_stats",
        "account_champion_imported_total_stats",
        "account_champion_stat_models",
        "gear_items",
        "gear_substats",
        "account_bonuses",
        "set_definitions",
        "set_definition_stats",
    ):
        conn.execute(f"DELETE FROM {table}")


def refresh_account_stat_models(db_path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        summary = refresh_account_stat_models_in_conn(conn)
        conn.commit()
    save_app_state(
        {
            "account_stats_last_refresh_utc": summary["computed_at"],
            "account_stats_summary": summary,
        },
        db_path,
    )
    return summary


def refresh_account_stats_from_source(
    source_path: Path = NORMALIZED_SOURCE_PATH,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    account = load_source_account(source_path)
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        sync_imported_total_stats_in_conn(conn, list_value(account.get("champions")))
        summary = refresh_account_stat_models_in_conn(conn)
        conn.commit()
    save_app_state(
        {
            "account_stats_last_refresh_utc": summary["computed_at"],
            "account_stats_summary": summary,
        },
        db_path,
    )
    return summary


def refresh_account_stat_models_in_conn(conn: sqlite3.Connection) -> Dict[str, Any]:
    set_rules = load_set_rules(conn)
    bonuses = load_account_bonuses(conn)
    gear_by_owner = load_equipped_gear_by_owner(conn)
    base_stats_by_name = load_base_stats_by_champion(conn)
    raw_totals_by_champ = load_imported_total_stats_by_champion(conn)

    champion_rows = conn.execute(
        """
        SELECT champ_id, champion_name, affinity
        FROM account_champions
        ORDER BY champion_name ASC, champ_id ASC
        """
    ).fetchall()

    conn.execute("DELETE FROM account_champion_total_stats")
    conn.execute("DELETE FROM account_champion_stat_models")

    source_counts = {"raw": 0, "derived": 0, "missing": 0}
    partial_count = 0
    computed_at = now_utc_iso()

    for champ_id, champion_name, affinity in champion_rows:
        stat_result = build_stat_computation(
            base_stats=base_stats_by_name.get(string_value(champion_name), {}),
            raw_total_stats=raw_totals_by_champ.get(string_value(champ_id), {}),
            equipped_items=gear_by_owner.get(string_value(champ_id), []),
            bonuses=bonuses,
            set_rules=set_rules,
            affinity=string_value(affinity),
        )

        for stat_name, stat_value in sorted(stat_result.total_stats.items()):
            conn.execute(
                """
                INSERT INTO account_champion_total_stats (champ_id, stat_name, stat_value)
                VALUES (?, ?, ?)
                """,
                (string_value(champ_id), string_value(stat_name), float_value(stat_value)),
            )

        conn.execute(
            """
            INSERT INTO account_champion_stat_models (
                champ_id, source, completeness, unsupported_sets_json, applied_sets_json, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                string_value(champ_id),
                stat_result.source,
                stat_result.completeness,
                json.dumps(stat_result.unsupported_sets, ensure_ascii=False),
                json.dumps(stat_result.applied_sets, ensure_ascii=False),
                computed_at,
            ),
        )

        source_counts[stat_result.source] = source_counts.get(stat_result.source, 0) + 1
        if stat_result.completeness == "partial":
            partial_count += 1

    return {
        "updated_champions": len(champion_rows),
        "raw_champions": source_counts.get("raw", 0),
        "derived_champions": source_counts.get("derived", 0),
        "missing_champions": source_counts.get("missing", 0),
        "partial_champions": partial_count,
        "computed_at": computed_at,
    }


def load_set_rules(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT sd.set_name, sd.pieces_required, sd.heal_each_turn_pct, sds.stat_type, sds.stat_value
        FROM set_definitions sd
        LEFT JOIN set_definition_stats sds
            ON sds.set_name = sd.set_name
        ORDER BY sd.set_name ASC, sds.stat_order ASC
        """
    ).fetchall()
    rules: Dict[str, Dict[str, Any]] = {}
    for set_name, pieces_required, heal_each_turn_pct, stat_type, stat_value in rows:
        rule = rules.setdefault(
            string_value(set_name),
            {
                "pieces_required": int_value(pieces_required),
                "heal_each_turn_pct": float_value(heal_each_turn_pct),
                "stats": [],
            },
        )
        if stat_type is not None:
            rule["stats"].append((string_value(stat_type), float_value(stat_value)))
    return rules


def load_account_bonuses(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT source, scope, target, stat, value, active
        FROM account_bonuses
        ORDER BY bonus_id ASC
        """
    ).fetchall()
    return [
        {
            "source": string_value(source),
            "scope": string_value(scope),
            "target": string_value(target),
            "stat": string_value(stat),
            "value": float_value(value),
            "active": bool(active),
        }
        for source, scope, target, stat, value, active in rows
    ]


def load_equipped_gear_by_owner(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
    substat_rows = conn.execute(
        """
        SELECT item_id, substat_order, stat_type, stat_value, rolls, glyph_value
        FROM gear_substats
        ORDER BY item_id ASC, substat_order ASC
        """
    ).fetchall()
    substats_by_item: Dict[str, List[Dict[str, Any]]] = {}
    for item_id, substat_order, stat_type, stat_value, rolls, glyph_value in substat_rows:
        substats_by_item.setdefault(string_value(item_id), []).append(
            {
                "substat_order": int_value(substat_order),
                "type": string_value(stat_type),
                "value": float_value(stat_value),
                "rolls": int_value(rolls),
                "glyph_value": float_value(glyph_value),
            }
        )

    item_rows = conn.execute(
        """
        SELECT item_id, slot, set_name, equipped_by, main_stat_type, main_stat_value
        FROM gear_items
        WHERE equipped_by IS NOT NULL AND equipped_by != ''
        ORDER BY equipped_by ASC, item_id ASC
        """
    ).fetchall()
    gear_by_owner: Dict[str, List[Dict[str, Any]]] = {}
    for item_id, slot, set_name, equipped_by, main_stat_type, main_stat_value in item_rows:
        gear_by_owner.setdefault(string_value(equipped_by), []).append(
            {
                "item_id": string_value(item_id),
                "slot": string_value(slot),
                "set_name": string_value(set_name),
                "main_stat": {
                    "type": string_value(main_stat_type),
                    "value": float_value(main_stat_value),
                },
                "substats": substats_by_item.get(string_value(item_id), []),
            }
        )
    return gear_by_owner


def load_base_stats_by_champion(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    rows = conn.execute(
        """
        SELECT champion_name, stat_name, stat_value
        FROM champion_base_stats
        ORDER BY champion_name ASC, stat_name ASC
        """
    ).fetchall()
    payload: Dict[str, Dict[str, float]] = {}
    for champion_name, stat_name, stat_value in rows:
        payload.setdefault(string_value(champion_name), {})[string_value(stat_name)] = float_value(stat_value)
    return payload


def load_total_stats_by_champion(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    rows = conn.execute(
        """
        SELECT champ_id, stat_name, stat_value
        FROM account_champion_total_stats
        ORDER BY champ_id ASC, stat_name ASC
        """
    ).fetchall()
    payload: Dict[str, Dict[str, float]] = {}
    for champ_id, stat_name, stat_value in rows:
        payload.setdefault(string_value(champ_id), {})[string_value(stat_name)] = float_value(stat_value)
    return payload


def load_imported_total_stats_by_champion(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    rows = conn.execute(
        """
        SELECT champ_id, stat_name, stat_value
        FROM account_champion_imported_total_stats
        ORDER BY champ_id ASC, stat_name ASC
        """
    ).fetchall()
    payload: Dict[str, Dict[str, float]] = {}
    for champ_id, stat_name, stat_value in rows:
        payload.setdefault(string_value(champ_id), {})[string_value(stat_name)] = float_value(stat_value)
    return payload


def sync_imported_total_stats_in_conn(conn: sqlite3.Connection, champions: Iterable[Dict[str, Any]]) -> None:
    conn.execute("DELETE FROM account_champion_imported_total_stats")
    for champion in champions:
        champ_id = string_value(champion.get("champ_id"))
        for stat_name, stat_value in sorted(dict_value(champion.get("total_stats")).items()):
            conn.execute(
                """
                INSERT INTO account_champion_imported_total_stats (champ_id, stat_name, stat_value)
                VALUES (?, ?, ?)
                """,
                (champ_id, string_value(stat_name), float_value(stat_value)),
            )


def save_app_state(entries: Dict[str, Any], db_path: Path = DB_PATH) -> None:
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        for key, value in entries.items():
            conn.execute(
                """
                INSERT INTO app_state (state_key, state_value)
                VALUES (?, ?)
                ON CONFLICT(state_key) DO UPDATE SET state_value = excluded.state_value
                """,
                (string_value(key), json.dumps(value, ensure_ascii=False)),
            )
        conn.commit()


def load_app_state(db_path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT state_key, state_value FROM app_state ORDER BY state_key ASC").fetchall()
    payload: Dict[str, Any] = {}
    for key, value in rows:
        try:
            payload[str(key)] = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            payload[str(key)] = value
    return payload


def select_best_template_rows(champions: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    selected: Dict[str, Dict[str, Any]] = {}
    for champion in champions:
        champion_name = string_value(champion.get("name"))
        if not champion_name:
            continue
        current = selected.get(champion_name)
        if current is None or champion_sort_tuple(champion) > champion_sort_tuple(current):
            selected[champion_name] = champion
    return selected


def collect_observed_sets(gear: Iterable[Dict[str, Any]]) -> set[str]:
    observed: set[str] = set()
    for item in gear:
        set_name = string_value(item.get("set_name")).strip()
        if set_name:
            observed.add(set_name)
    return observed


def reconcile_loaded_account_ownership(account: Dict[str, Any]) -> None:
    champions = list_value(account.get("champions"))
    gear = list_value(account.get("gear"))
    owner_by_item_id: Dict[str, str] = {}
    for champion in champions:
        champ_id = string_value(champion.get("champ_id"))
        for item_id in list_value(champion.get("equipped_item_ids")):
            normalized_item_id = string_value(item_id)
            if normalized_item_id:
                owner_by_item_id[normalized_item_id] = champ_id
    for item in gear:
        item_id = string_value(item.get("item_id"))
        owner_id = owner_by_item_id.get(item_id)
        if owner_id:
            item["equipped_by"] = owner_id


def champion_sort_tuple(champion: Dict[str, Any]) -> Tuple[int, int, int, int]:
    return (
        int_value(champion.get("level")),
        int_value(champion.get("rank")),
        int_value(champion.get("awakening_level")),
        len(list_value(champion.get("equipped_item_ids"))),
    )


def normalize_skill_slot(skill: Dict[str, Any], skill_order: int) -> str:
    raw_slot = string_value(first_non_empty(skill.get("slot"), skill.get("skill_slot"))).upper()
    if raw_slot.startswith("A") and raw_slot[1:].isdigit():
        return raw_slot
    if raw_slot.isdigit():
        return f"A{raw_slot}"
    return f"A{skill_order}"


def normalize_set_stat(value: Any) -> Tuple[str, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return string_value(value[0]), float_value(value[1])
    if isinstance(value, dict):
        return string_value(value.get("type")), float_value(value.get("value"))
    return "", 0.0


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def optional_string(value: Any) -> Optional[str]:
    text = string_value(value).strip()
    return text or None


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def nullable_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def nullable_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> None:
    summary = bootstrap_database()
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
