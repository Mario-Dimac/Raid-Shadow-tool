from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from enrichment_sources import ChampionSkillMatch, get_skill_enrichment_provider, register_skill_enrichment_provider
from forge_db import bootstrap_database, refresh_account_stat_models
from hellhades_enrich import HellHadesChampionMatch, enrich_registry_from_hellhades, enrich_registry_from_source
from providers.local_registry_provider import export_local_skill_registry


def test_bootstrap_database_builds_relational_tables(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 1,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack", "support"],
                "base_stats": {"hp": 20000, "def": 1200, "spd": 100},
                "total_stats": {"hp": 50000, "def": 3000, "spd": 210, "acc": 320},
                "equipped_item_ids": ["gear-1"],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "geo_a1",
                        "name": "Stone Hammer",
                        "cooldown": 0,
                        "effects": [{"type": "damage", "target": "enemy", "value": 1.0}],
                    },
                    {
                        "slot": "A3",
                        "skill_id": "geo_a3",
                        "name": "Burning Resolve",
                        "cooldown": 3,
                        "effects": [{"type": "hp_burn", "target": "enemy", "duration": 3, "chance": 100}],
                    },
                ],
            },
            {
                "champ_id": "champ-2",
                "name": "Coldheart",
                "rarity": "rare",
                "affinity": "void",
                "faction": "Dark Elves",
                "level": 50,
                "rank": 5,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": False,
                "role_tags": ["attack"],
                "base_stats": {"hp": 15000},
                "total_stats": {"hp": 32000},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "ch_a1",
                        "name": "Heartseeker Start",
                        "cooldown": None,
                        "effects": [],
                    }
                ],
            }
        ],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": True,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [{"type": "acc", "value": 20, "rolls": 2, "glyph_value": 0}],
            }
        ],
        "account_bonuses": [
            {
                "bonus_id": "great_hall_force_acc",
                "source": "great_hall",
                "scope": "global",
                "target": "force",
                "stat": "acc",
                "value": 10,
                "active": True,
            }
        ],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    assert summary["champion_catalog"] == 2
    assert summary["champion_roles"] == 3
    assert summary["champion_base_stats"] == 4
    assert summary["champion_skills"] == 3
    assert summary["champion_skill_effects"] == 2
    assert summary["account_champions"] == 2
    assert summary["account_champion_total_stats"] == 5
    assert summary["account_champion_imported_total_stats"] == 5
    assert summary["gear_items"] == 1
    assert summary["gear_substats"] == 1
    assert summary["account_bonuses"] == 1
    assert summary["set_definitions"] >= 1
    assert summary["registry_targets"] == 1
    assert summary["app_state"] >= 3
    assert summary["account_champion_stat_models"] == 2

    with sqlite3.connect(db_path) as conn:
        champion_catalog_columns = {row[1] for row in conn.execute("PRAGMA table_info(champion_catalog)").fetchall()}
        champion_skill_columns = {row[1] for row in conn.execute("PRAGMA table_info(champion_skills)").fetchall()}

    assert "hellhades_post_id" in champion_catalog_columns
    assert "skill_type" in champion_skill_columns
    assert "description_clean" in champion_skill_columns
    assert "source" in champion_skill_columns


def test_hellhades_enrichment_updates_skills_and_effects(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                    {"slot": "A2", "skill_id": "48802", "name": "48802", "effects": []},
                    {"slot": "A3", "skill_id": "48804", "name": "48804", "effects": []},
                    {"slot": "A4", "skill_id": "48805", "name": "48805", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    remote_skills = [
        {
            "name": "Tremor Staff",
            "type": "Basic",
            "cooldown": 0,
            "description": (
                "<p>Attacks 1 enemy. Has a 30% chance of placing a [Decrease ACC] debuff for 2 turns.<br />"
                "Level 2: Damage +5%</p>"
            ),
            "books": [],
        },
        {
            "name": "Creeping Petrify",
            "type": "Active",
            "cooldown": 4,
            "description": (
                "<p>Fully depletes the target's Turn Meter. Fills this Champion's Turn Meter by 25%.<br />"
                "Level 2: Cooldown -1</p>"
            ),
            "books": [],
        },
        {
            "name": "Quicksand Grasp",
            "type": "Active",
            "cooldown": 5,
            "description": (
                "<p>Places a [HP Burn] debuff for 3 turns and a [Weaken] debuff for 2 turns.<br />"
                "Level 2: Cooldown -1<br />"
                "Level 3: Cooldown -1</p>"
            ),
            "books": [],
        },
        {
            "name": "Stoneguard [P]",
            "type": "Passive",
            "cooldown": "",
            "description": "<p>Places a [Block Debuffs] buff on all allies for 1 turn.</p>",
            "books": [],
        },
    ]

    monkeypatch.setattr(
        "hellhades_enrich.resolve_champion_match",
        lambda champion_name: HellHadesChampionMatch(
            post_id=17837,
            title=champion_name,
            url="https://hellhades.com/raid/champions/geomancer/",
        ),
    )
    monkeypatch.setattr("hellhades_enrich.fetch_champion_skills", lambda post_id: remote_skills)

    summary = enrich_registry_from_hellhades(db_path=db_path)

    assert summary["requested"] == 1
    assert summary["matched"] == 1
    assert summary["updated"] == 1

    with sqlite3.connect(db_path) as conn:
        catalog_row = conn.execute(
            """
            SELECT hellhades_post_id, hellhades_url
            FROM champion_catalog
            WHERE champion_name = 'Geomancer'
            """
        ).fetchone()
        skill_rows = conn.execute(
            """
            SELECT slot, skill_name, cooldown, booked_cooldown, skill_type, description_clean, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()
        effect_types = {
            row[0]
            for row in conn.execute(
                """
                SELECT effect_type
                FROM champion_skill_effects
                WHERE champion_name = 'Geomancer'
                """
            ).fetchall()
        }

    assert catalog_row == (17837, "https://hellhades.com/raid/champions/geomancer/")
    assert skill_rows[0][0] == "A1"
    assert skill_rows[0][1] == "Tremor Staff"
    assert skill_rows[0][2] == 0
    assert skill_rows[0][4] == "Basic"
    assert "Level 2:" not in (skill_rows[0][5] or "")
    assert skill_rows[0][6] == "hellhades"
    assert skill_rows[2][1] == "Quicksand Grasp"
    assert skill_rows[2][2] == 5
    assert skill_rows[2][3] == 3
    assert skill_rows[3][4] == "Passive"
    assert "decrease_acc" in effect_types
    assert "turn_meter_reduce" in effect_types
    assert "turn_meter_fill" in effect_types
    assert "hp_burn" in effect_types
    assert "weaken" in effect_types
    assert "block_debuffs" in effect_types


def test_enrichment_can_run_through_generic_provider_layer(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                    {"slot": "A2", "skill_id": "48802", "name": "48802", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    class FakeProvider:
        source_name = "fake-provider"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(
                source_name=self.source_name,
                source_ref="9001",
                title=champion_name,
                url="https://example.invalid/champions/geomancer",
            )

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {
                    "name": "Provider A1",
                    "type": "Basic",
                    "cooldown": 0,
                    "description": "<p>Places a [Decrease DEF] debuff for 2 turns.</p>",
                    "books": [],
                },
                {
                    "name": "Provider A2",
                    "type": "Active",
                    "cooldown": 4,
                    "description": "<p>Places a [HP Burn] debuff for 3 turns.</p>",
                    "books": [],
                },
            ]

    register_skill_enrichment_provider(FakeProvider())

    summary = enrich_registry_from_source("fake-provider", db_path=db_path)

    assert summary["provider"] == "fake-provider"
    assert summary["updated"] == 1

    with sqlite3.connect(db_path) as conn:
        skill_rows = conn.execute(
            """
            SELECT skill_name, skill_type, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()
        effect_types = {
            row[0]
            for row in conn.execute(
                """
                SELECT effect_type
                FROM champion_skill_effects
                WHERE champion_name = 'Geomancer'
                """
            ).fetchall()
        }

    assert skill_rows == [
        ("Provider A1", "Basic", "fake-provider"),
        ("Provider A2", "Active", "fake-provider"),
    ]
    assert "decrease_def" in effect_types
    assert "hp_burn" in effect_types


def test_local_skill_registry_export_roundtrips_db_skill_data(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    registry_path = tmp_path / "local_skill_registry.json"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {
                        "slot": "A1",
                        "skill_id": "geo_a1",
                        "name": "Stone Hammer",
                        "cooldown": 0,
                        "description": "Places [HP Burn].",
                        "effects": [{"type": "hp_burn", "target": "enemy", "duration": 2}],
                    }
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    summary = export_local_skill_registry(db_path=db_path, output_path=registry_path)

    exported = json.loads(registry_path.read_text(encoding="utf-8"))
    assert summary["champion_count"] == 1
    assert summary["skill_count"] == 1
    assert exported["champions"][0]["champion_name"] == "Geomancer"
    assert exported["champions"][0]["skills"][0]["name"] == "Stone Hammer"
    assert exported["champions"][0]["skills"][0]["effects"][0]["effect_type"] == "hp_burn"


def test_auto_provider_prefers_local_registry_before_hellhades(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                    {"slot": "A2", "skill_id": "48802", "name": "48802", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    original_local = get_skill_enrichment_provider("local_registry")
    original_ayumi = get_skill_enrichment_provider("ayumilove")
    original_hh = get_skill_enrichment_provider("hellhades")

    class LocalProvider:
        source_name = "local_registry"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, champion_name, champion_name, "")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "Local A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Decrease ATK] debuff.</p>", "effects": []},
                {"name": "Local A2", "type": "Active", "cooldown": 4, "description": "<p>Places a [HP Burn] debuff.</p>", "effects": []},
            ]

    class HellHadesProvider:
        source_name = "hellhades"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, "17837", champion_name, "https://example.invalid/hh")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "HH A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Decrease DEF] debuff.</p>", "effects": []},
                {"name": "HH A2", "type": "Active", "cooldown": 4, "description": "<p>Places a [Weaken] debuff.</p>", "effects": []},
            ]

    class AyumiLoveProvider:
        source_name = "ayumilove"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, champion_name, champion_name, "https://example.invalid/ayumi")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "Ayumi A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Leech] debuff.</p>", "effects": []},
                {"name": "Ayumi A2", "type": "Active", "cooldown": 4, "description": "<p>Places a [Fear] debuff.</p>", "effects": []},
            ]

    register_skill_enrichment_provider(LocalProvider())
    register_skill_enrichment_provider(AyumiLoveProvider())
    register_skill_enrichment_provider(HellHadesProvider())
    try:
        summary = enrich_registry_from_source("auto", db_path=db_path)
    finally:
        register_skill_enrichment_provider(original_local)
        register_skill_enrichment_provider(original_ayumi)
        register_skill_enrichment_provider(original_hh)

    assert summary["provider"] == "auto"
    assert summary["provider_hits"]["local_registry"] == 1
    assert summary["provider_hits"]["ayumilove"] == 0
    assert summary["provider_hits"]["hellhades"] == 0

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT skill_name, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()

    assert rows == [("Local A1", "local_registry"), ("Local A2", "local_registry")]


def test_auto_provider_falls_back_to_hellhades_when_local_registry_missing(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    original_local = get_skill_enrichment_provider("local_registry")
    original_ayumi = get_skill_enrichment_provider("ayumilove")
    original_hh = get_skill_enrichment_provider("hellhades")

    class EmptyLocalProvider:
        source_name = "local_registry"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return None

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return []

    class HellHadesProvider:
        source_name = "hellhades"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, "17837", champion_name, "https://example.invalid/hh")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "HH A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Decrease DEF] debuff.</p>", "effects": []},
            ]

    class AyumiLoveProvider:
        source_name = "ayumilove"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, champion_name, champion_name, "https://example.invalid/ayumi")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "Ayumi A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Leech] debuff.</p>", "effects": []},
            ]

    register_skill_enrichment_provider(EmptyLocalProvider())
    register_skill_enrichment_provider(AyumiLoveProvider())
    register_skill_enrichment_provider(HellHadesProvider())
    try:
        summary = enrich_registry_from_source("auto", db_path=db_path)
    finally:
        register_skill_enrichment_provider(original_local)
        register_skill_enrichment_provider(original_ayumi)
        register_skill_enrichment_provider(original_hh)

    assert summary["provider_hits"]["local_registry"] == 0
    assert summary["provider_hits"]["ayumilove"] == 1
    assert summary["provider_hits"]["hellhades"] == 0

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT skill_name, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()

    assert rows == [("Ayumi A1", "ayumilove")]


def test_auto_provider_falls_back_to_hellhades_when_ayumilove_missing(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Geomancer",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Dwarves",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": ["attack"],
                "base_stats": {"hp": 20000},
                "total_stats": {"hp": 50000},
                "equipped_item_ids": [],
                "skills": [
                    {"slot": "A1", "skill_id": "48801", "name": "48801", "effects": []},
                ],
            }
        ],
        "gear": [],
        "account_bonuses": [],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    original_local = get_skill_enrichment_provider("local_registry")
    original_ayumi = get_skill_enrichment_provider("ayumilove")
    original_hh = get_skill_enrichment_provider("hellhades")

    class EmptyLocalProvider:
        source_name = "local_registry"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return None

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return []

    class EmptyAyumiLoveProvider:
        source_name = "ayumilove"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return None

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return []

    class HellHadesProvider:
        source_name = "hellhades"

        def resolve_champion_match(self, champion_name: str) -> ChampionSkillMatch | None:
            return ChampionSkillMatch(self.source_name, "17837", champion_name, "https://example.invalid/hh")

        def fetch_champion_skills(self, match: ChampionSkillMatch) -> list[dict[str, object]]:
            return [
                {"name": "HH A1", "type": "Basic", "cooldown": 0, "description": "<p>Places a [Decrease DEF] debuff.</p>", "effects": []},
            ]

    register_skill_enrichment_provider(EmptyLocalProvider())
    register_skill_enrichment_provider(EmptyAyumiLoveProvider())
    register_skill_enrichment_provider(HellHadesProvider())
    try:
        summary = enrich_registry_from_source("auto", db_path=db_path)
    finally:
        register_skill_enrichment_provider(original_local)
        register_skill_enrichment_provider(original_ayumi)
        register_skill_enrichment_provider(original_hh)

    assert summary["provider_hits"]["local_registry"] == 0
    assert summary["provider_hits"]["ayumilove"] == 0
    assert summary["provider_hits"]["hellhades"] == 1

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT skill_name, source
            FROM champion_skills
            WHERE champion_name = 'Geomancer'
            ORDER BY skill_order ASC
            """
        ).fetchall()

    assert rows == [("HH A1", "hellhades")]


def test_bootstrap_derives_total_stats_when_raw_dump_is_empty(tmp_path: Path) -> None:
    source_path = tmp_path / "normalized_account.json"
    db_path = tmp_path / "cbforge.sqlite3"
    payload = {
        "champions": [
            {
                "champ_id": "champ-1",
                "name": "Seeker",
                "rarity": "epic",
                "affinity": "force",
                "faction": "Barbarians",
                "level": 60,
                "rank": 6,
                "awakening_level": 0,
                "empowerment_level": 0,
                "booked": True,
                "role_tags": [],
                "base_stats": {
                    "hp": 100,
                    "atk": 100,
                    "def": 100,
                    "spd": 100,
                    "crit_rate": 15,
                    "crit_dmg": 50,
                    "acc": 0,
                    "res": 30,
                },
                "total_stats": {
                    "hp": 0,
                    "atk": 0,
                    "def": 0,
                    "spd": 0,
                    "crit_rate": 0,
                    "crit_dmg": 0,
                    "acc": 0,
                    "res": 0,
                },
                "equipped_item_ids": ["gear-1", "gear-2"],
                "skills": [],
            }
        ],
        "gear": [
            {
                "item_id": "gear-1",
                "item_class": "artifact",
                "slot": "boots",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "spd", "value": 45},
                "substats": [{"type": "acc", "value": 0.2, "rolls": 0, "glyph_value": 0}],
            },
            {
                "item_id": "gear-2",
                "item_class": "artifact",
                "slot": "weapon",
                "set_name": "Attack Speed",
                "rarity": "legendary",
                "rank": 6,
                "level": 16,
                "ascension_level": 0,
                "required_faction": "",
                "required_faction_id": 0,
                "equipped_by": "champ-1",
                "locked": False,
                "main_stat": {"type": "atk", "value": 265},
                "substats": [{"type": "hp_pct", "value": 0.1, "rolls": 0, "glyph_value": 0}],
            },
        ],
        "account_bonuses": [
            {
                "bonus_id": "great_hall_force_acc",
                "source": "great_hall",
                "scope": "global",
                "target": "force",
                "stat": "acc",
                "value": 10,
                "active": True,
            }
        ],
    }
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    bootstrap_database(source_path=source_path, db_path=db_path, rebuild=True)

    with sqlite3.connect(db_path) as conn:
        total_stats = dict(
            conn.execute(
                """
                SELECT stat_name, stat_value
                FROM account_champion_total_stats
                WHERE champ_id = 'champ-1'
                """
            ).fetchall()
        )
        stat_model = conn.execute(
            """
            SELECT source, completeness
            FROM account_champion_stat_models
            WHERE champ_id = 'champ-1'
            """
        ).fetchone()

    assert total_stats["hp"] == 26400.0
    assert total_stats["atk"] == 1165.0
    assert total_stats["spd"] == 157.0
    assert total_stats["acc"] == 30.0
    assert stat_model == ("derived", "derived")

    refresh_summary = refresh_account_stat_models(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        refreshed_stats = dict(
            conn.execute(
                """
                SELECT stat_name, stat_value
                FROM account_champion_total_stats
                WHERE champ_id = 'champ-1'
                """
            ).fetchall()
        )
        refreshed_model = conn.execute(
            """
            SELECT source, completeness
            FROM account_champion_stat_models
            WHERE champ_id = 'champ-1'
            """
        ).fetchone()

    assert refresh_summary["derived_champions"] == 1
    assert refreshed_stats == total_stats
    assert refreshed_model == ("derived", "derived")
