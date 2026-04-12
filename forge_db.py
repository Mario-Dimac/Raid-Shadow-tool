from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from account_stats import build_stat_computation
from set_curation import load_local_set_rules


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "cbforge.sqlite3"
NORMALIZED_SOURCE_PATH = INPUT_DIR / "normalized_account.json"
RAW_SOURCE_PATH = INPUT_DIR / "raw_account.json"


DEFAULT_SET_RULES: Dict[str, Dict[str, Any]] = {
    "Attack Speed": {"set_kind": "fixed", "pieces_required": 2, "max_pieces": 6, "counts_accessories": False, "stats": [("spd", 12.0)]},
    "Accuracy": {"set_kind": "fixed", "pieces_required": 2, "max_pieces": 6, "counts_accessories": False, "stats": [("acc", 40.0)]},
    "Accuracy And Speed": {
        "set_kind": "fixed",
        "pieces_required": 2,
        "max_pieces": 6,
        "counts_accessories": False,
        "stats": [("acc", 40.0), ("spd", 12.0)],
    },
    "HP And Heal": {
        "set_kind": "fixed",
        "pieces_required": 2,
        "max_pieces": 6,
        "counts_accessories": False,
        "stats": [("hp_pct", 15.0)],
        "heal_each_turn_pct": 3.0,
    },
    "HP And Defence": {
        "set_kind": "fixed",
        "pieces_required": 2,
        "max_pieces": 6,
        "counts_accessories": False,
        "stats": [("hp_pct", 10.0), ("def_pct", 10.0)],
    },
    "Attack Power And Ignore Defense": {
        "set_kind": "fixed",
        "pieces_required": 2,
        "max_pieces": 6,
        "counts_accessories": False,
        "stats": [("atk_pct", 15.0)],
    },
    "Shield And Speed": {"set_kind": "fixed", "pieces_required": 2, "max_pieces": 6, "counts_accessories": False, "stats": [("spd", 12.0)]},
    "Shield And HP": {"set_kind": "fixed", "pieces_required": 2, "max_pieces": 6, "counts_accessories": False, "stats": [("hp_pct", 15.0)]},
    "Shield And Attack Power": {
        "set_kind": "fixed",
        "pieces_required": 2,
        "max_pieces": 6,
        "counts_accessories": False,
        "stats": [("atk_pct", 15.0)],
    },
    "Shield And Critical Chance": {
        "set_kind": "fixed",
        "pieces_required": 2,
        "max_pieces": 6,
        "counts_accessories": False,
        "stats": [("crit_rate", 12.0)],
    },
    "Stone Skin": {
        "set_kind": "variable",
        "pieces_required": 1,
        "max_pieces": 9,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "stats": [("hp_pct", 8.0)]},
            {"pieces_required": 2, "stats": [("res", 40.0)]},
            {"pieces_required": 3, "stats": [("def_pct", 15.0)]},
            {"pieces_required": 4, "effect_text": "Stone Skin for 1 turn at battle start"},
            {"pieces_required": 5, "stats": [("def_pct", 15.0)]},
            {"pieces_required": 6, "effect_text": "Stone Skin for 2 turns at battle start"},
            {"pieces_required": 7, "stats": [("hp_pct", 8.0)]},
            {"pieces_required": 8, "stats": [("res", 40.0)]},
            {"pieces_required": 9, "effect_text": "Stone Skin shield upgraded to 75% HP"},
        ],
    },
    "Protection": {
        "set_kind": "variable",
        "pieces_required": 1,
        "max_pieces": 9,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "stats": [("res", 20.0)]},
            {"pieces_required": 2, "stats": [("hp_pct", 15.0)]},
            {"pieces_required": 3, "stats": [("spd", 12.0)]},
            {"pieces_required": 4, "effect_text": "25% chance to place Protected buffs"},
            {"pieces_required": 5, "stats": [("spd", 12.0)]},
            {"pieces_required": 6, "effect_text": "50% chance to place Protected buffs"},
            {"pieces_required": 7, "stats": [("res", 20.0)]},
            {"pieces_required": 8, "stats": [("spd", 8.0)]},
            {"pieces_required": 9, "effect_text": "75% chance to place Protected buffs and allies deal 5% more damage per wearer buff"},
        ],
    },
    "Supersonic": {
        "set_kind": "variable",
        "pieces_required": 1,
        "max_pieces": 9,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "stats": [("res", 20.0)]},
            {"pieces_required": 2, "stats": [("hp_pct", 15.0)]},
            {"pieces_required": 3, "stats": [("spd", 10.0)]},
            {"pieces_required": 4, "effect_text": "Turn Meter increases by 2% per enemy buff"},
            {"pieces_required": 5, "stats": [("spd", 10.0)]},
            {"pieces_required": 6, "effect_text": "Reduces Turn Meter reduction effects by 30%"},
            {"pieces_required": 7, "stats": [("res", 20.0)]},
            {"pieces_required": 8, "stats": [("spd", 12.0)]},
            {"pieces_required": 9, "effect_text": "Increases Turn Meter boost effects by 30%"},
        ],
    },
    "Pinpoint": {
        "set_kind": "variable",
        "pieces_required": 1,
        "max_pieces": 9,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "stats": [("acc", 20.0)]},
            {"pieces_required": 2, "stats": [("spd", 10.0)]},
            {"pieces_required": 3, "stats": [("acc", 20.0)]},
            {"pieces_required": 4, "effect_text": "Block Debuffs for 2 turns at the start of each round"},
            {"pieces_required": 5, "stats": [("spd", 10.0)]},
            {"pieces_required": 6, "effect_text": "50% chance to block Sheep from Polymorph"},
            {"pieces_required": 7, "stats": [("acc", 20.0)]},
            {"pieces_required": 8, "stats": [("spd", 10.0)]},
            {"pieces_required": 9, "effect_text": "Allies deal 5% more damage per wearer debuff"},
        ],
    },
    "Stonecleaver": {
        "set_kind": "variable",
        "pieces_required": 1,
        "max_pieces": 9,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "stats": [("atk_pct", 10.0)]},
            {"pieces_required": 2, "stats": [("crit_dmg", 15.0)]},
            {"pieces_required": 3, "stats": [("spd", 5.0)]},
            {"pieces_required": 4, "effect_text": "+30% damage to Stone Skin shields"},
            {"pieces_required": 5, "stats": [("atk_pct", 15.0)]},
            {"pieces_required": 6, "effect_text": "Ignores 20% DEF"},
            {"pieces_required": 7, "stats": [("spd", 5.0)]},
            {"pieces_required": 8, "stats": [("crit_dmg", 15.0)]},
            {"pieces_required": 9, "effect_text": "+70% damage to Stone Skin shields"},
        ],
    },
    "Rebirth": {
        "set_kind": "variable",
        "pieces_required": 1,
        "max_pieces": 9,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "stats": [("res", 20.0)]},
            {"pieces_required": 2, "stats": [("spd", 10.0)]},
            {"pieces_required": 3, "stats": [("res", 20.0)]},
            {"pieces_required": 4, "effect_text": "Revived allies gain +10% HP and +10% Turn Meter"},
            {"pieces_required": 5, "stats": [("spd", 10.0)]},
            {"pieces_required": 6, "effect_text": "Places Block Damage when an ally is killed once per round"},
            {"pieces_required": 7, "stats": [("res", 20.0)]},
            {"pieces_required": 8, "stats": [("spd", 12.0)]},
            {"pieces_required": 9, "effect_text": "Revived allies have skill cooldowns reduced by 1"},
        ],
    },
    "Chronophage": {
        "set_kind": "variable",
        "pieces_required": 1,
        "max_pieces": 9,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "stats": [("res", 20.0)]},
            {"pieces_required": 2, "stats": [("spd", 10.0)]},
            {"pieces_required": 3, "stats": [("res", 20.0)]},
            {"pieces_required": 4, "effect_text": "Starts the round with 1 Immutable stack"},
            {"pieces_required": 5, "stats": [("spd", 10.0)]},
            {"pieces_required": 6, "effect_text": "Starts the round with 2 Immutable stacks"},
            {"pieces_required": 7, "stats": [("res", 20.0)]},
            {"pieces_required": 8, "stats": [("spd", 12.0)]},
            {"pieces_required": 9, "effect_text": "Starts the round with 3 Immutable stacks"},
        ],
    },
    "Mercurial": {
        "set_kind": "variable",
        "pieces_required": 1,
        "max_pieces": 9,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "stats": [("res", 20.0)]},
            {"pieces_required": 2, "stats": [("hp_pct", 15.0)]},
            {"pieces_required": 3, "stats": [("spd", 8.0)]},
            {"pieces_required": 4, "effect_text": "Grants 1 Total Guard stack at the start of the round"},
            {"pieces_required": 5, "stats": [("spd", 12.0)]},
            {"pieces_required": 6, "effect_text": "Grants 2 Total Guard stacks at the start of the round"},
            {"pieces_required": 7, "stats": [("res", 20.0)]},
            {"pieces_required": 8, "stats": [("spd", 12.0)]},
            {"pieces_required": 9, "effect_text": "Grants 3 Total Guard stacks and refreshes 1 stack at turn start if none remain"},
        ],
    },
    "Counterattack Accessory": {
        "set_kind": "accessory",
        "pieces_required": 1,
        "max_pieces": 3,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "effect_text": "5% chance to counterattack when hit"},
            {"pieces_required": 2, "effect_text": "10% chance to counterattack when hit"},
            {"pieces_required": 3, "effect_text": "15% chance to counterattack when hit"},
        ],
    },
    "Shield Accessory": {
        "set_kind": "accessory",
        "pieces_required": 1,
        "max_pieces": 3,
        "counts_accessories": True,
        "piece_bonuses": [
            {"pieces_required": 1, "effect_text": "Shield worth 5% of damage dealt after attacking"},
            {"pieces_required": 2, "effect_text": "Shield worth 10% of damage dealt after attacking"},
            {"pieces_required": 3, "effect_text": "Shield worth 15% of damage dealt after attacking"},
        ],
    },
}

DEFAULT_SET_RULES["Pinpoint"] = {
    "set_kind": "variable",
    "pieces_required": 1,
    "max_pieces": 9,
    "counts_accessories": True,
    "piece_bonuses": [
        {"pieces_required": 1, "stats": [("acc", 20.0)]},
        {"pieces_required": 2, "stats": [("spd", 10.0)]},
        {"pieces_required": 3, "stats": [("acc", 20.0)]},
        {"pieces_required": 4, "effect_text": "Grants 1 Intercept Stack at the start of each round"},
        {"pieces_required": 5, "stats": [("spd", 10.0)]},
        {"pieces_required": 6, "effect_text": "Grants 2 Intercept Stacks at the start of each round"},
        {"pieces_required": 7, "stats": [("acc", 20.0)]},
        {"pieces_required": 8, "stats": [("spd", 12.0)]},
        {"pieces_required": 9, "effect_text": "Grants 4 Intercept Stacks at the start of each round"},
    ],
}

DEFAULT_SET_RULES["Merciless"] = {
    "set_kind": "variable",
    "pieces_required": 1,
    "max_pieces": 9,
    "counts_accessories": True,
    "piece_bonuses": [
        {"pieces_required": 1, "stats": [("atk_pct", 10.0)]},
        {"pieces_required": 2, "stats": [("crit_dmg", 15.0)]},
        {"pieces_required": 3, "stats": [("spd", 5.0)]},
        {"pieces_required": 4, "effect_text": "30% chance to reduce a random skill cooldown by 1"},
        {"pieces_required": 5, "stats": [("atk_pct", 15.0)]},
        {"pieces_required": 6, "effect_text": "Ignores 35% of enemy DEF"},
        {"pieces_required": 7, "stats": [("spd", 5.0)]},
        {"pieces_required": 8, "stats": [("crit_dmg", 15.0)]},
        {"pieces_required": 9, "effect_text": "15% chance to gain an Extra Turn upon dealing damage"},
    ],
}

GEAR_ALLOWED_MAIN_STATS: Dict[str, Dict[str, set[str]]] = {
    "artifact": {
        "weapon": {"atk"},
        "helmet": {"hp"},
        "shield": {"def"},
        "gloves": {"hp_pct", "atk_pct", "def_pct", "crit_rate", "crit_dmg", "hp", "atk", "def"},
        "chest": {"hp_pct", "atk_pct", "def_pct", "acc", "res", "hp", "atk", "def"},
        "boots": {"spd", "hp_pct", "atk_pct", "def_pct", "hp", "atk", "def"},
    },
    "accessory": {
        "ring": {"hp", "atk", "def"},
        "amulet": {"hp", "atk", "def", "crit_dmg", "res"},
        "banner": {"hp", "atk", "def", "acc", "res"},
    },
}

GEAR_ALLOWED_SUBSTATS: Dict[str, Dict[str, set[str]]] = {
    "accessory": {
        "ring": {"hp", "atk", "def", "hp_pct", "atk_pct", "def_pct"},
        "amulet": {"hp", "atk", "def", "acc", "res", "crit_dmg"},
        "banner": {"hp", "atk", "def", "hp_pct", "atk_pct", "def_pct", "spd"},
    },
}

LEGACY_KIND_SLOT_MAP: Dict[int, Tuple[str, str]] = {
    1: ("artifact", "helmet"),
    2: ("artifact", "gloves"),
    3: ("artifact", "chest"),
    4: ("artifact", "boots"),
    5: ("artifact", "weapon"),
    6: ("artifact", "shield"),
    7: ("accessory", "ring"),
    8: ("accessory", "amulet"),
    9: ("accessory", "banner"),
}

DEFAULT_SET_RULES["Feral"] = {
    "set_kind": "variable",
    "pieces_required": 1,
    "max_pieces": 9,
    "counts_accessories": True,
    "piece_bonuses": [
        {"pieces_required": 1, "stats": [("acc", 40.0)]},
        {"pieces_required": 2, "stats": [("spd", 5.0)]},
        {"pieces_required": 3, "stats": [("acc", 40.0)]},
        {"pieces_required": 4, "effect_text": "Places Block Debuffs on the wearer for 2 turns at the start of each round"},
        {"pieces_required": 5, "stats": [("spd", 5.0)]},
        {"pieces_required": 6, "effect_text": "50% chance to block the Sheep debuff from Polymorph"},
        {"pieces_required": 7, "stats": [("acc", 40.0)]},
        {"pieces_required": 8, "stats": [("spd", 5.0)]},
        {"pieces_required": 9, "effect_text": "Allies deal 5% more damage per debuff inflicted by the wearer"},
    ],
}

DEFAULT_SET_RULES["Righteous"] = {
    "set_kind": "fixed",
    "pieces_required": 2,
    "max_pieces": 6,
    "counts_accessories": False,
    "stats": [("spd", 10.0), ("res", 40.0)],
}

DEFAULT_SET_RULES["Instinct"] = {
    "set_kind": "fixed",
    "pieces_required": 4,
    "max_pieces": 6,
    "counts_accessories": False,
    "stats": [("spd", 12.0)],
    "piece_bonuses": [
        {"pieces_required": 4, "effect_text": "Ignores 20% of enemy DEF"},
    ],
}

DEFAULT_SET_RULES["Killstroke"] = {
    "set_kind": "fixed",
    "pieces_required": 2,
    "max_pieces": 6,
    "counts_accessories": False,
    "stats": [("crit_dmg", 20.0), ("spd", 5.0)],
}

DEFAULT_SET_RULES.update(
    {
        "Life Drain": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Heals by 30% of damage dealt"}],
        },
        "Counterattack On Crit": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "45% chance to counterattack when a debuff is placed on the wearer"}],
        },
        "Dot Rate": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "75% chance to place a 2.5% Poison debuff for 2 turns when attacking"}],
        },
        "Freeze Rate On Damage Received": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "20% chance to place Freeze for 1 turn when attacked by an enemy Champion"}],
        },
        "AoE Damage Decrease": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Decreases incoming AoE damage by 30%"}],
        },
        "Ignore Defense": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Ignores 25% of enemy DEF"}],
        },
        "Sleep Chance": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "25% chance to place Sleep for 1 turn when attacking"}],
        },
        "Decrease Max HP": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Decreases target MAX HP by 40% of the damage dealt"}],
        },
        "Attack Power": {
            "set_kind": "fixed",
            "pieces_required": 2,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("atk_pct", 15.0)],
        },
        "Cooldown Reduction Chance": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "40% chance to reduce a random skill cooldown by 1"}],
        },
        "Critical Heal Multiplier": {
            "set_kind": "fixed",
            "pieces_required": 2,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("crit_dmg", 20.0)],
        },
        "Unkillable And SPD And CR Damage": {
            "set_kind": "variable",
            "pieces_required": 1,
            "max_pieces": 9,
            "counts_accessories": True,
            "piece_bonuses": [
                {"pieces_required": 1, "stats": [("crit_dmg", 15.0)]},
                {"pieces_required": 2, "stats": [("spd", 8.0)]},
                {"pieces_required": 3, "stats": [("crit_dmg", 15.0)]},
                {"pieces_required": 4, "stats": [("spd", 10.0)], "effect_text": "50% chance to place Unkillable for 1 turn when receiving fatal damage"},
                {"pieces_required": 5, "stats": [("hp_pct", 10.0)]},
                {"pieces_required": 6, "effect_text": "Enemy single-target attacks deal 15% less damage to this Champion"},
                {"pieces_required": 7, "stats": [("hp_pct", 15.0)]},
                {"pieces_required": 8, "stats": [("spd", 10.0)]},
                {"pieces_required": 9, "effect_text": "Ignores 50% of enemy DEF"},
            ],
        },
        "Attack And Crit Rate": {
            "set_kind": "fixed",
            "pieces_required": 2,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("atk_pct", 15.0), ("crit_rate", 5.0)],
        },
        "Block Debuff": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Places Block Debuffs on the wearer for 2 turns at the start of each round"}],
        },
        "Crit Rate And Ignore DEF Multiplier": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("crit_rate", 10.0)],
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Ignores 25% of enemy DEF"}],
        },
        "Damage Increase On HP Decrease": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Damage increases as HP decreases, up to +50% below 50% HP"}],
        },
        "Get Extra Turn": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "18% chance to gain an Extra Turn"}],
        },
        "HP": {
            "set_kind": "fixed",
            "pieces_required": 2,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("hp_pct", 15.0)],
        },
        "Stun Chance": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "18% chance to place Stun for 1 turn when attacking"}],
        },
        "Crit Damage And Transform Week Into Crit Hit": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("crit_dmg", 30.0)],
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "50% chance to change a weak hit into a critical hit"}],
        },
        "Crit Rate And Life Drain": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("crit_rate", 12.0)],
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Heals by 30% of damage dealt"}],
        },
        "Resistance": {
            "set_kind": "fixed",
            "pieces_required": 2,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("res", 40.0)],
        },
        "Critical Chance": {
            "set_kind": "fixed",
            "pieces_required": 2,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("crit_rate", 12.0)],
        },
        "Defense": {
            "set_kind": "fixed",
            "pieces_required": 2,
            "max_pieces": 6,
            "counts_accessories": False,
            "stats": [("def_pct", 15.0)],
        },
        "Shield": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Places a Shield worth 30% of the wearer's HP on all allies for 3 turns at the start of each round"}],
        },
        "Counterattack": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "25% chance to counterattack when hit"}],
        },
        "Passive Share Damage And Heal": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "Absorbs 10% of damage dealt to allies and heals the wearer by 10% each turn"}],
        },
        "Provoke Chance": {
            "set_kind": "fixed",
            "pieces_required": 4,
            "max_pieces": 6,
            "counts_accessories": False,
            "piece_bonuses": [{"pieces_required": 4, "effect_text": "30% chance to place Provoke for 1 turn when attacking"}],
        },
        "Change Hit Type": {
            "set_kind": "accessory",
            "pieces_required": 1,
            "max_pieces": 3,
            "counts_accessories": True,
            "piece_bonuses": [
                {"pieces_required": 1, "effect_text": "25% chance to change a Critical Hit into a Normal Hit when attacked before the first turn"},
                {"pieces_required": 2, "effect_text": "50% chance to change a Critical Hit into a Normal Hit when attacked before the first turn"},
                {"pieces_required": 3, "effect_text": "75% chance to change a Critical Hit into a Normal Hit when attacked before the first turn"},
            ],
        },
    }
)


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
        booked INTEGER NOT NULL,
        relic_count INTEGER NOT NULL DEFAULT 0
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
    CREATE TABLE IF NOT EXISTS account_champion_masteries (
        champ_id TEXT NOT NULL,
        mastery_order INTEGER NOT NULL,
        mastery_id TEXT NOT NULL,
        mastery_name TEXT,
        tree TEXT,
        active INTEGER NOT NULL,
        PRIMARY KEY (champ_id, mastery_order)
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
        set_kind TEXT NOT NULL DEFAULT 'fixed',
        counts_accessories INTEGER NOT NULL DEFAULT 0,
        max_pieces INTEGER NOT NULL DEFAULT 0,
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
    CREATE TABLE IF NOT EXISTS set_definition_piece_bonuses (
        set_name TEXT NOT NULL,
        bonus_order INTEGER NOT NULL,
        pieces_required INTEGER NOT NULL,
        stat_type TEXT,
        stat_value REAL NOT NULL,
        effect_text TEXT,
        PRIMARY KEY (set_name, bonus_order)
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
    CREATE TABLE IF NOT EXISTS run_history_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        saved_at TEXT NOT NULL,
        source TEXT NOT NULL,
        source_run_uid TEXT,
        battle_id TEXT,
        probe_session_slug TEXT,
        encounter_key TEXT NOT NULL,
        encounter_name TEXT,
        encounter_family TEXT,
        area_region TEXT,
        game_mode TEXT,
        difficulty TEXT,
        stage_id TEXT,
        stage_label TEXT,
        stage_tier INTEGER,
        boss_affinity TEXT,
        affinity_context TEXT,
        result_code TEXT,
        success INTEGER NOT NULL DEFAULT 0,
        completed INTEGER NOT NULL DEFAULT 0,
        auto_play INTEGER NOT NULL DEFAULT 1,
        formation_index INTEGER,
        team_name TEXT,
        team_hash TEXT,
        leader_slot INTEGER,
        elapsed_seconds REAL,
        turns INTEGER,
        boss_turn INTEGER,
        total_damage REAL,
        account_power REAL,
        model_target TEXT,
        feature_schema_version TEXT NOT NULL DEFAULT 'run_history_v1',
        notes TEXT,
        labels_json TEXT NOT NULL DEFAULT '{}',
        context_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_history_members (
        run_id INTEGER NOT NULL,
        member_order INTEGER NOT NULL,
        champ_id TEXT,
        champion_name TEXT NOT NULL,
        champion_type_id INTEGER,
        role_hint TEXT,
        level INTEGER,
        rank INTEGER,
        awakening_level INTEGER,
        empowerment_level INTEGER,
        booked INTEGER NOT NULL DEFAULT 0,
        build_fingerprint TEXT,
        set_summary_json TEXT NOT NULL DEFAULT '[]',
        tags_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (run_id, member_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_history_member_stats (
        run_id INTEGER NOT NULL,
        member_order INTEGER NOT NULL,
        stat_name TEXT NOT NULL,
        stat_value REAL NOT NULL,
        stat_source TEXT,
        PRIMARY KEY (run_id, member_order, stat_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_history_member_metrics (
        run_id INTEGER NOT NULL,
        member_order INTEGER NOT NULL,
        damage_done REAL NOT NULL DEFAULT 0,
        damage_taken REAL NOT NULL DEFAULT 0,
        healing_done REAL NOT NULL DEFAULT 0,
        shields_done REAL NOT NULL DEFAULT 0,
        buffs_applied INTEGER NOT NULL DEFAULT 0,
        debuffs_applied INTEGER NOT NULL DEFAULT 0,
        deaths INTEGER NOT NULL DEFAULT 0,
        revives INTEGER NOT NULL DEFAULT 0,
        alive_at_end INTEGER,
        metric_payload_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (run_id, member_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_history_member_skill_usage (
        run_id INTEGER NOT NULL,
        member_order INTEGER NOT NULL,
        skill_order INTEGER NOT NULL,
        skill_slot TEXT,
        skill_code TEXT,
        usage_count INTEGER NOT NULL DEFAULT 0,
        usage_payload_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (run_id, member_order, skill_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_history_assets (
        run_id INTEGER NOT NULL,
        asset_order INTEGER NOT NULL,
        asset_kind TEXT NOT NULL,
        asset_path TEXT NOT NULL,
        sha256 TEXT,
        size_bytes INTEGER,
        captured_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (run_id, asset_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_history_events (
        run_id INTEGER NOT NULL,
        event_index INTEGER NOT NULL,
        event_time TEXT,
        event_type TEXT,
        source_name TEXT,
        actor_slot INTEGER,
        target_slot INTEGER,
        skill_id TEXT,
        skill_name TEXT,
        value_numeric REAL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (run_id, event_index)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_history_effect_timeline (
        run_id INTEGER NOT NULL,
        timeline_index INTEGER NOT NULL,
        effect_index INTEGER NOT NULL,
        event_index INTEGER,
        source_member_order INTEGER,
        source_slot INTEGER,
        source_name TEXT,
        source_type_id INTEGER,
        target_party_id INTEGER,
        target_slot INTEGER,
        skill_order INTEGER,
        skill_slot TEXT,
        skill_code TEXT,
        skill_name TEXT,
        skill_type TEXT,
        skill_provider TEXT,
        effect_type TEXT NOT NULL,
        effect_category TEXT,
        effect_action TEXT,
        effect_target TEXT,
        duration_turns INTEGER,
        chance_pct REAL,
        effect_value REAL,
        resolution_status TEXT,
        cast_certainty TEXT,
        landed_status TEXT,
        landed_confidence REAL,
        base_chance_pct REAL,
        source_acc REAL,
        target_res_estimate REAL,
        target_res_source TEXT,
        weak_hit_risk TEXT,
        outcome_model TEXT,
        condition_text TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (run_id, timeline_index, effect_index)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_run_history_runs_encounter
    ON run_history_runs (encounter_key, difficulty, success, elapsed_seconds)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_run_history_runs_battle
    ON run_history_runs (battle_id, source)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_run_history_members_name
    ON run_history_members (champion_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_run_history_effect_timeline_effect
    ON run_history_effect_timeline (run_id, effect_type, source_name)
    """,
    """
    CREATE TABLE IF NOT EXISTS app_state (
        state_key TEXT PRIMARY KEY,
        state_value TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gear_snapshots (
        snapshot_key TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        scope TEXT NOT NULL DEFAULT '',
        snapshot_kind TEXT NOT NULL DEFAULT 'manual',
        saved_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        context_json TEXT NOT NULL DEFAULT '{}',
        snapshot_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gear_snapshots_scope
    ON gear_snapshots (scope, updated_at)
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
    ensure_column(
        conn,
        table_name="set_definitions",
        column_name="set_kind",
        column_sql="TEXT NOT NULL DEFAULT 'fixed'",
    )
    ensure_column(
        conn,
        table_name="set_definitions",
        column_name="counts_accessories",
        column_sql="INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(
        conn,
        table_name="set_definitions",
        column_name="max_pieces",
        column_sql="INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(
        conn,
        table_name="account_champions",
        column_name="relic_count",
        column_sql="INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="cast_certainty",
        column_sql="TEXT",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="landed_status",
        column_sql="TEXT",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="landed_confidence",
        column_sql="REAL",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="base_chance_pct",
        column_sql="REAL",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="source_acc",
        column_sql="REAL",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="target_res_estimate",
        column_sql="REAL",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="target_res_source",
        column_sql="TEXT",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="weak_hit_risk",
        column_sql="TEXT",
    )
    ensure_column(
        conn,
        table_name="run_history_effect_timeline",
        column_name="outcome_model",
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
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        clear_all_tables(conn)
        conn.commit()


def load_source_account(source_path: Path = NORMALIZED_SOURCE_PATH) -> Dict[str, Any]:
    account = json.loads(source_path.read_text(encoding="utf-8-sig"))
    if not isinstance(account, dict):
        return {}
    reconcile_loaded_account_ownership(account)
    repair_loaded_account_gear(account, source_path)
    return account


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
    curated_set_rules = load_local_set_rules()
    bootstrap_set_rules = dict(DEFAULT_SET_RULES)
    bootstrap_set_rules.update(curated_set_rules)

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
                    level, rank, awakening_level, empowerment_level, booked, relic_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    len(list_value(champion.get("relic_ids"))),
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
            for mastery_order, mastery in enumerate(list_value(champion.get("masteries")), start=1):
                mastery_map = dict_value(mastery)
                conn.execute(
                    """
                    INSERT INTO account_champion_masteries (
                        champ_id, mastery_order, mastery_id, mastery_name, tree, active
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        champ_id,
                        mastery_order,
                        string_value(mastery_map.get("mastery_id")),
                        string_value(mastery_map.get("name")),
                        string_value(mastery_map.get("tree")),
                        1 if bool(mastery_map.get("active", True)) else 0,
                    ),
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

        for set_name in sorted(observed_sets | set(bootstrap_set_rules)):
            rule = dict_value(bootstrap_set_rules.get(set_name))
            conn.execute(
                """
                INSERT INTO set_definitions (
                    set_name, pieces_required, heal_each_turn_pct, set_kind, counts_accessories, max_pieces, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    set_name,
                    int_value(rule.get("pieces_required")),
                    float_value(rule.get("heal_each_turn_pct")),
                    string_value(first_non_empty(rule.get("set_kind"), "unknown")),
                    1 if bool(rule.get("counts_accessories")) else 0,
                    int_value(first_non_empty(rule.get("max_pieces"), rule.get("pieces_required"))),
                    string_value(first_non_empty(rule.get("source"), "bootstrap_rules" if rule else "observed_gear")),
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
            bonus_order = 0
            for piece_bonus in list_value(rule.get("piece_bonuses")):
                pieces_required = int_value(piece_bonus.get("pieces_required"))
                for stat_row in list_value(piece_bonus.get("stats")):
                    stat_type, stat_value = normalize_set_stat(stat_row)
                    bonus_order += 1
                    conn.execute(
                        """
                        INSERT INTO set_definition_piece_bonuses (
                            set_name, bonus_order, pieces_required, stat_type, stat_value, effect_text
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (set_name, bonus_order, pieces_required, stat_type, stat_value, None),
                    )
                effect_text = optional_string(first_non_empty(piece_bonus.get("effect_text"), piece_bonus.get("effect")))
                if effect_text:
                    bonus_order += 1
                    conn.execute(
                        """
                        INSERT INTO set_definition_piece_bonuses (
                            set_name, bonus_order, pieces_required, stat_type, stat_value, effect_text
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (set_name, bonus_order, pieces_required, None, 0.0, effect_text),
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


def list_placeholder_skill_champions(
    db_path: Path = DB_PATH,
    champion_names: Optional[Iterable[str]] = None,
) -> List[str]:
    ensure_schema(db_path)
    selected_names = [str(name).strip() for name in (champion_names or []) if str(name).strip()]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if selected_names:
            placeholders = ", ".join("?" for _ in selected_names)
            rows = conn.execute(
                f"""
                SELECT
                    cs.champion_name,
                    COUNT(*) AS skill_count,
                    SUM(
                        CASE
                            WHEN TRIM(COALESCE(cs.description_clean, '')) != ''
                              OR TRIM(COALESCE(cs.description, '')) != ''
                            THEN 1 ELSE 0
                        END
                    ) AS rich_skill_count,
                    SUM(
                        CASE
                            WHEN TRIM(COALESCE(cs.skill_name, '')) != ''
                              AND TRIM(COALESCE(cs.skill_name, '')) GLOB '*[^0-9]*'
                            THEN 1 ELSE 0
                        END
                    ) AS named_skill_count,
                    COUNT(cse.effect_type) AS effect_count
                FROM champion_skills cs
                LEFT JOIN champion_skill_effects cse
                    ON cse.champion_name = cs.champion_name
                    AND cse.slot = cs.slot
                WHERE cs.champion_name IN ({placeholders})
                GROUP BY cs.champion_name
                ORDER BY cs.champion_name ASC
                """,
                selected_names,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    cs.champion_name,
                    COUNT(*) AS skill_count,
                    SUM(
                        CASE
                            WHEN TRIM(COALESCE(cs.description_clean, '')) != ''
                              OR TRIM(COALESCE(cs.description, '')) != ''
                            THEN 1 ELSE 0
                        END
                    ) AS rich_skill_count,
                    SUM(
                        CASE
                            WHEN TRIM(COALESCE(cs.skill_name, '')) != ''
                              AND TRIM(COALESCE(cs.skill_name, '')) GLOB '*[^0-9]*'
                            THEN 1 ELSE 0
                        END
                    ) AS named_skill_count,
                    COUNT(cse.effect_type) AS effect_count
                FROM champion_skills cs
                LEFT JOIN champion_skill_effects cse
                    ON cse.champion_name = cs.champion_name
                    AND cse.slot = cs.slot
                GROUP BY cs.champion_name
                ORDER BY cs.champion_name ASC
                """
            ).fetchall()

    missing: List[str] = []
    for row in rows:
        skill_count = int(row["skill_count"] or 0)
        rich_skill_count = int(row["rich_skill_count"] or 0)
        named_skill_count = int(row["named_skill_count"] or 0)
        effect_count = int(row["effect_count"] or 0)
        if skill_count <= 0:
            continue
        if rich_skill_count > 0 and effect_count > 0 and named_skill_count >= skill_count:
            continue
        missing.append(str(row["champion_name"] or ""))
    return [name for name in missing if name]


def enrich_placeholder_skills(
    db_path: Path = DB_PATH,
    provider: str = "auto",
    champion_names: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    targets = list_placeholder_skill_champions(db_path=db_path, champion_names=champion_names)
    if limit is not None:
        targets = targets[: max(0, int(limit))]
    if not targets:
        return {
            "provider": str(provider or "auto"),
            "requested": 0,
            "updated": 0,
            "effect_rows_written": 0,
            "provider_hits": {},
            "not_found": [],
            "champions": [],
        }

    from hellhades_enrich import enrich_registry_from_source

    summary = enrich_registry_from_source(
        source_name=str(provider or "auto"),
        db_path=db_path,
        champion_names=targets,
        limit=None,
    )
    summary["champions"] = targets
    return summary


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
        "account_champion_masteries",
        "account_champion_stat_models",
        "gear_items",
        "gear_substats",
        "account_bonuses",
        "set_definitions",
        "set_definition_stats",
        "set_definition_piece_bonuses",
        "combat_runs",
        "combat_run_members",
        "combat_sessions",
        "run_history_runs",
        "run_history_members",
        "run_history_member_stats",
        "run_history_member_metrics",
        "run_history_member_skill_usage",
        "run_history_assets",
        "run_history_events",
        "run_history_effect_timeline",
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
        "account_champion_masteries",
        "account_champion_stat_models",
        "gear_items",
        "gear_substats",
        "account_bonuses",
        "set_definitions",
        "set_definition_stats",
        "set_definition_piece_bonuses",
    ):
        conn.execute(f"DELETE FROM {table}")


def clear_all_tables(conn: sqlite3.Connection) -> None:
    clear_runtime_tables(conn)
    for table in (
        "combat_run_members",
        "combat_runs",
        "combat_sessions",
        "run_history_events",
        "run_history_effect_timeline",
        "run_history_assets",
        "run_history_member_metrics",
        "run_history_member_skill_usage",
        "run_history_member_stats",
        "run_history_members",
        "run_history_runs",
        "app_state",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")


def insert_run_effect_timeline(conn: sqlite3.Connection, run_id: int, effect_timeline: Dict[str, Any]) -> int:
    timeline_rows = list_value(dict_value(effect_timeline).get("timeline"))
    inserted = 0
    effect_model_context = load_run_effect_model_context(conn, run_id)

    for timeline_index, timeline_row in enumerate(timeline_rows, start=1):
        timeline_map = dict_value(timeline_row)
        source_slot = nullable_int(timeline_map.get("source_slot"))
        source_member_order = nullable_int(timeline_map.get("source_member_order"))
        if source_member_order is None and source_slot is not None:
            source_member_order = source_slot + 1

        for effect_index, raw_effect in enumerate(list_value(timeline_map.get("status_effects")), start=1):
            effect_map = dict_value(raw_effect)
            model_fields = build_effect_model_fields(
                effect_model_context,
                timeline_map=timeline_map,
                effect_map=effect_map,
                source_member_order=source_member_order,
            )
            conn.execute(
                """
                INSERT INTO run_history_effect_timeline (
                    run_id, timeline_index, effect_index, event_index, source_member_order,
                    source_slot, source_name, source_type_id, target_party_id, target_slot,
                    skill_order, skill_slot, skill_code, skill_name, skill_type, skill_provider,
                    effect_type, effect_category, effect_action, effect_target, duration_turns,
                    chance_pct, effect_value, resolution_status, cast_certainty, landed_status,
                    landed_confidence, base_chance_pct, source_acc, target_res_estimate, target_res_source,
                    weak_hit_risk, outcome_model, condition_text, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    timeline_index,
                    effect_index,
                    nullable_int(timeline_map.get("event_index")),
                    source_member_order,
                    source_slot,
                    optional_string(timeline_map.get("source_name")),
                    nullable_int(timeline_map.get("source_type_id")),
                    nullable_int(timeline_map.get("target_party_id")),
                    nullable_int(timeline_map.get("target_slot")),
                    nullable_int(timeline_map.get("skill_order")),
                    optional_string(timeline_map.get("skill_slot")),
                    optional_string(timeline_map.get("skill_code")),
                    optional_string(timeline_map.get("skill_name")),
                    optional_string(timeline_map.get("skill_type")),
                    optional_string(timeline_map.get("skill_provider")),
                    optional_string(effect_map.get("effect_type")) or "unknown_effect",
                    optional_string(effect_map.get("category")),
                    optional_string(effect_map.get("action")),
                    optional_string(effect_map.get("target")),
                    nullable_int(effect_map.get("duration")),
                    nullable_float(effect_map.get("chance")),
                    nullable_float(effect_map.get("effect_value")),
                    optional_string(effect_map.get("resolution")),
                    optional_string(model_fields.get("cast_certainty")),
                    optional_string(model_fields.get("landed_status")),
                    nullable_float(model_fields.get("landed_confidence")),
                    nullable_float(model_fields.get("base_chance_pct")),
                    nullable_float(model_fields.get("source_acc")),
                    nullable_float(model_fields.get("target_res_estimate")),
                    optional_string(model_fields.get("target_res_source")),
                    optional_string(model_fields.get("weak_hit_risk")),
                    optional_string(model_fields.get("outcome_model")),
                    optional_string(effect_map.get("condition_text")),
                    json_text({"timeline_event": timeline_map, "effect": effect_map}, {}),
                ),
            )
            inserted += 1

    return inserted


CLAN_BOSS_RESISTANCE_ESTIMATES: Dict[str, float] = {
    "easy": 100.0,
    "normal": 140.0,
    "hard": 180.0,
    "brutal": 210.0,
    "nightmare": 230.0,
    "nm": 230.0,
    "ultra_nightmare": 250.0,
    "unm": 250.0,
}


def estimate_target_resistance(encounter_key: Any, difficulty: Any) -> Tuple[float | None, str | None]:
    encounter = string_value(encounter_key).strip().lower()
    difficulty_key = string_value(difficulty).strip().lower()
    if encounter.startswith("demon_lord_"):
        resistance = CLAN_BOSS_RESISTANCE_ESTIMATES.get(difficulty_key) or CLAN_BOSS_RESISTANCE_ESTIMATES.get(encounter.removeprefix("demon_lord_"))
        if resistance is not None:
            return resistance, "clan_boss_difficulty_estimate"
    return None, None


def affinity_is_weak(source_affinity: Any, boss_affinity: Any) -> bool:
    source = string_value(source_affinity).strip().lower()
    boss = string_value(boss_affinity).strip().lower()
    if not source or not boss or source == "void" or boss == "void":
        return False
    weak_pairs = {
        ("magic", "force"),
        ("force", "spirit"),
        ("spirit", "magic"),
    }
    return (source, boss) in weak_pairs


def load_run_effect_model_context(conn: sqlite3.Connection, run_id: int) -> Dict[str, Any]:
    run_row = conn.execute(
        """
        SELECT encounter_key, difficulty, boss_affinity
        FROM run_history_runs
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    encounter_key = string_value(run_row[0] if run_row else "")
    difficulty = string_value(run_row[1] if run_row else "")
    boss_affinity = string_value(run_row[2] if run_row else "")
    target_res_estimate, target_res_source = estimate_target_resistance(encounter_key, difficulty)

    member_rows = conn.execute(
        """
        SELECT m.member_order, m.champion_name, cc.affinity,
               MAX(CASE WHEN lower(ms.stat_name) = 'acc' THEN ms.stat_value END) AS acc
        FROM run_history_members m
        LEFT JOIN run_history_member_stats ms
          ON ms.run_id = m.run_id
         AND ms.member_order = m.member_order
        LEFT JOIN champion_catalog cc
          ON cc.champion_name = m.champion_name
        WHERE m.run_id = ?
        GROUP BY m.member_order, m.champion_name, cc.affinity
        """,
        (run_id,),
    ).fetchall()
    members_by_order = {
        int(row[0]): {
            "champion_name": string_value(row[1]),
            "affinity": string_value(row[2]),
            "acc": nullable_float(row[3]),
        }
        for row in member_rows
    }

    return {
        "encounter_key": encounter_key,
        "difficulty": difficulty,
        "boss_affinity": boss_affinity,
        "target_res_estimate": target_res_estimate,
        "target_res_source": target_res_source,
        "members_by_order": members_by_order,
    }


def build_effect_model_fields(
    effect_model_context: Dict[str, Any],
    *,
    timeline_map: Dict[str, Any],
    effect_map: Dict[str, Any],
    source_member_order: int | None,
) -> Dict[str, Any]:
    source_party_role = string_value(timeline_map.get("source_party_role")).strip().lower()
    effect_category = string_value(first_non_empty(effect_map.get("category"), effect_map.get("effect_category"))).strip().lower()
    effect_target = string_value(first_non_empty(effect_map.get("target"), effect_map.get("effect_target"))).strip().lower()
    skill_type = string_value(timeline_map.get("skill_type")).strip().lower()
    raw_chance = nullable_float(first_non_empty(effect_map.get("chance"), effect_map.get("chance_pct")))
    source_context = dict_value(dict(effect_model_context.get("members_by_order") or {}).get(int(source_member_order or 0)))
    source_acc = nullable_float(source_context.get("acc"))
    source_affinity = string_value(source_context.get("affinity"))
    boss_affinity = string_value(effect_model_context.get("boss_affinity"))
    target_res_estimate = nullable_float(effect_model_context.get("target_res_estimate"))
    target_res_source = optional_string(effect_model_context.get("target_res_source"))

    deterministic_target = effect_target in {"self", "ally", "all_allies"}
    if source_party_role == "player" and deterministic_target and effect_category in {"buff", "utility"}:
        base_chance = raw_chance if raw_chance is not None else 100.0
        return {
            "cast_certainty": "observed_cast",
            "landed_status": "certain_from_cast",
            "landed_confidence": 1.0,
            "base_chance_pct": base_chance,
            "source_acc": source_acc,
            "target_res_estimate": None,
            "target_res_source": None,
            "weak_hit_risk": "none",
            "outcome_model": "deterministic_allied_effect_from_cast",
        }

    if source_party_role == "player" and effect_category == "debuff":
        weak_hit_risk = "none"
        if skill_type in {"basic", "active"}:
            weak_hit_risk = "possible" if affinity_is_weak(source_affinity, boss_affinity) else "unlikely"
        return {
            "cast_certainty": "observed_cast",
            "landed_status": "unknown_from_cast_only",
            "landed_confidence": None,
            "base_chance_pct": raw_chance if raw_chance is not None else 100.0,
            "source_acc": source_acc,
            "target_res_estimate": target_res_estimate,
            "target_res_source": target_res_source,
            "weak_hit_risk": weak_hit_risk,
            "outcome_model": "base_chance_plus_acc_res_and_weak_hit",
        }

    return {
        "cast_certainty": "observed_cast",
        "landed_status": "not_modeled",
        "landed_confidence": None,
        "base_chance_pct": raw_chance,
        "source_acc": source_acc,
        "target_res_estimate": target_res_estimate if effect_category == "debuff" else None,
        "target_res_source": target_res_source if effect_category == "debuff" else None,
        "weak_hit_risk": "unknown",
        "outcome_model": "not_modeled",
    }


def backfill_run_effect_model_fields(db_path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    updated_rows = 0
    updated_runs: set[int] = set()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_ids = [
            int(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT run_id
                FROM run_history_effect_timeline
                ORDER BY run_id ASC
                """
            ).fetchall()
        ]

        for run_id in run_ids:
            effect_model_context = load_run_effect_model_context(conn, run_id)
            rows = conn.execute(
                """
                SELECT timeline_index, effect_index, source_member_order, payload_json
                FROM run_history_effect_timeline
                WHERE run_id = ?
                ORDER BY timeline_index ASC, effect_index ASC
                """,
                (run_id,),
            ).fetchall()
            for row in rows:
                payload = dict_value(json.loads(string_value(row["payload_json"]) or "{}"))
                timeline_map = dict_value(payload.get("timeline_event"))
                effect_map = dict_value(payload.get("effect"))
                model_fields = build_effect_model_fields(
                    effect_model_context,
                    timeline_map=timeline_map,
                    effect_map=effect_map,
                    source_member_order=nullable_int(row["source_member_order"]),
                )
                conn.execute(
                    """
                    UPDATE run_history_effect_timeline
                    SET cast_certainty = ?,
                        landed_status = ?,
                        landed_confidence = ?,
                        base_chance_pct = ?,
                        source_acc = ?,
                        target_res_estimate = ?,
                        target_res_source = ?,
                        weak_hit_risk = ?,
                        outcome_model = ?
                    WHERE run_id = ? AND timeline_index = ? AND effect_index = ?
                    """,
                    (
                        optional_string(model_fields.get("cast_certainty")),
                        optional_string(model_fields.get("landed_status")),
                        nullable_float(model_fields.get("landed_confidence")),
                        nullable_float(model_fields.get("base_chance_pct")),
                        nullable_float(model_fields.get("source_acc")),
                        nullable_float(model_fields.get("target_res_estimate")),
                        optional_string(model_fields.get("target_res_source")),
                        optional_string(model_fields.get("weak_hit_risk")),
                        optional_string(model_fields.get("outcome_model")),
                        run_id,
                        int(row["timeline_index"]),
                        int(row["effect_index"]),
                    ),
                )
                updated_rows += 1
                updated_runs.add(run_id)

        conn.commit()

    return {
        "runs": len(updated_runs),
        "rows": updated_rows,
    }


def record_run_history(run_payload: Dict[str, Any], db_path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    payload = dict_value(run_payload)
    saved_at = optional_string(payload.get("saved_at")) or now_utc_iso()
    source = optional_string(payload.get("source")) or "manual"
    source_run_uid = optional_string(first_non_empty(payload.get("source_run_uid"), payload.get("battle_id")))
    labels = dict_value(payload.get("labels"))
    context = dict_value(payload.get("context"))
    members = list_value(payload.get("members"))
    assets = list_value(payload.get("assets"))
    events = list_value(payload.get("events"))
    effect_timeline = dict_value(payload.get("effect_timeline"))

    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if source_run_uid:
            existing = conn.execute(
                """
                SELECT run_id
                FROM run_history_runs
                WHERE source = ? AND source_run_uid = ?
                ORDER BY run_id DESC
                LIMIT 1
                """,
                (source, source_run_uid),
            ).fetchone()
            if existing:
                return run_history_summary(run_id=int(existing[0]), db_path=db_path)

        cursor = conn.execute(
            """
            INSERT INTO run_history_runs (
                saved_at, source, source_run_uid, battle_id, probe_session_slug,
                encounter_key, encounter_name, encounter_family, area_region, game_mode,
                difficulty, stage_id, stage_label, stage_tier, boss_affinity,
                affinity_context, result_code, success, completed, auto_play,
                formation_index, team_name, team_hash, leader_slot, elapsed_seconds,
                turns, boss_turn, total_damage, account_power, model_target,
                feature_schema_version, notes, labels_json, context_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                saved_at,
                source,
                source_run_uid,
                optional_string(payload.get("battle_id")),
                optional_string(payload.get("probe_session_slug")),
                optional_string(first_non_empty(payload.get("encounter_key"), payload.get("stage_id"), "unknown_encounter")) or "unknown_encounter",
                optional_string(payload.get("encounter_name")),
                optional_string(payload.get("encounter_family")),
                optional_string(payload.get("area_region")),
                optional_string(payload.get("game_mode")),
                optional_string(payload.get("difficulty")),
                optional_string(payload.get("stage_id")),
                optional_string(payload.get("stage_label")),
                nullable_int(payload.get("stage_tier")),
                optional_string(payload.get("boss_affinity")),
                optional_string(payload.get("affinity_context")),
                optional_string(payload.get("result_code")),
                1 if bool(payload.get("success")) else 0,
                1 if bool(payload.get("completed", True)) else 0,
                1 if bool(payload.get("auto_play", True)) else 0,
                nullable_int(payload.get("formation_index")),
                optional_string(payload.get("team_name")),
                optional_string(payload.get("team_hash")),
                nullable_int(payload.get("leader_slot")),
                nullable_float(payload.get("elapsed_seconds")),
                nullable_int(payload.get("turns")),
                nullable_int(payload.get("boss_turn")),
                nullable_float(payload.get("total_damage")),
                nullable_float(payload.get("account_power")),
                optional_string(payload.get("model_target")),
                optional_string(payload.get("feature_schema_version")) or "run_history_v1",
                optional_string(payload.get("notes")),
                json_text(labels, {}),
                json_text(context, {}),
            ),
        )
        run_id = int(cursor.lastrowid)

        for member_order, member in enumerate(members, start=1):
            member_map = dict_value(member)
            conn.execute(
                """
                INSERT INTO run_history_members (
                    run_id, member_order, champ_id, champion_name, champion_type_id, role_hint,
                    level, rank, awakening_level, empowerment_level, booked, build_fingerprint,
                    set_summary_json, tags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    member_order,
                    optional_string(member_map.get("champ_id")),
                    optional_string(first_non_empty(member_map.get("champion_name"), member_map.get("name"), f"slot_{member_order}")) or f"slot_{member_order}",
                    nullable_int(first_non_empty(member_map.get("champion_type_id"), member_map.get("type_id"))),
                    optional_string(first_non_empty(member_map.get("role_hint"), member_map.get("role"))),
                    nullable_int(member_map.get("level")),
                    nullable_int(member_map.get("rank")),
                    nullable_int(member_map.get("awakening_level")),
                    nullable_int(member_map.get("empowerment_level")),
                    1 if bool(member_map.get("booked")) else 0,
                    optional_string(member_map.get("build_fingerprint")),
                    json_text(list_value(member_map.get("set_summary")), []),
                    json_text(list_value(member_map.get("tags")), []),
                ),
            )

            for stat_name, stat_value in sorted(dict_value(member_map.get("stats")).items()):
                conn.execute(
                    """
                    INSERT INTO run_history_member_stats (
                        run_id, member_order, stat_name, stat_value, stat_source
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        member_order,
                        string_value(stat_name),
                        float_value(stat_value),
                        optional_string(member_map.get("stat_source")),
                    ),
                )

            metrics = dict_value(member_map.get("metrics"))
            if metrics:
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
                        float_value(metrics.get("damage_done")),
                        float_value(metrics.get("damage_taken")),
                        float_value(metrics.get("healing_done")),
                        float_value(metrics.get("shields_done")),
                        int_value(metrics.get("buffs_applied")),
                        int_value(metrics.get("debuffs_applied")),
                        int_value(metrics.get("deaths")),
                        int_value(metrics.get("revives")),
                        nullable_int(metrics.get("alive_at_end")),
                        json_text(metrics, {}),
                    ),
                )

            for skill_usage in list_value(member_map.get("skill_usage")):
                skill_usage_map = dict_value(skill_usage)
                conn.execute(
                    """
                    INSERT INTO run_history_member_skill_usage (
                        run_id, member_order, skill_order, skill_slot, skill_code, usage_count, usage_payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        member_order,
                        nullable_int(skill_usage_map.get("skill_order")),
                        optional_string(skill_usage_map.get("skill_slot")),
                        optional_string(skill_usage_map.get("skill_code")),
                        int_value(skill_usage_map.get("usage_count")),
                        json_text(skill_usage_map, {}),
                    ),
                )

        for asset_order, asset in enumerate(assets, start=1):
            asset_map = dict_value(asset)
            conn.execute(
                """
                INSERT INTO run_history_assets (
                    run_id, asset_order, asset_kind, asset_path, sha256, size_bytes, captured_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    asset_order,
                    optional_string(first_non_empty(asset_map.get("asset_kind"), asset_map.get("kind"), "unknown")) or "unknown",
                    optional_string(first_non_empty(asset_map.get("asset_path"), asset_map.get("path"), f"asset_{asset_order}")) or f"asset_{asset_order}",
                    optional_string(asset_map.get("sha256")),
                    nullable_int(first_non_empty(asset_map.get("size_bytes"), asset_map.get("size"))),
                    optional_string(asset_map.get("captured_at")),
                    json_text(dict_value(asset_map.get("metadata")), {}),
                ),
            )

        for event_index, event in enumerate(events, start=1):
            event_map = dict_value(event)
            conn.execute(
                """
                INSERT INTO run_history_events (
                    run_id, event_index, event_time, event_type, source_name,
                    actor_slot, target_slot, skill_id, skill_name, value_numeric, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_index,
                    optional_string(event_map.get("event_time")),
                    optional_string(event_map.get("event_type")),
                    optional_string(first_non_empty(event_map.get("source_name"), event_map.get("source"))),
                    nullable_int(event_map.get("actor_slot")),
                    nullable_int(event_map.get("target_slot")),
                    optional_string(event_map.get("skill_id")),
                    optional_string(event_map.get("skill_name")),
                    nullable_float(first_non_empty(event_map.get("value_numeric"), event_map.get("value"))),
                    json_text(event_map, {}),
                ),
            )

        insert_run_effect_timeline(conn, run_id=run_id, effect_timeline=effect_timeline)
        conn.commit()

    return run_history_summary(run_id=run_id, db_path=db_path)


def cleanup_duplicate_run_history_runs(db_path: Path = DB_PATH, source: str = "") -> Dict[str, Any]:
    ensure_schema(db_path)
    source_text = str(source or "").strip()
    filters = [
        "NULLIF(TRIM(COALESCE(source_run_uid, '')), '') IS NOT NULL",
    ]
    params: List[Any] = []
    if source_text:
        filters.append("source = ?")
        params.append(source_text)

    duplicate_query = f"""
        SELECT source, source_run_uid, COUNT(*) AS duplicate_count
        FROM run_history_runs
        WHERE {' AND '.join(filters)}
        GROUP BY source, source_run_uid
        HAVING COUNT(*) > 1
        ORDER BY source ASC, source_run_uid ASC
    """
    child_tables = (
        "run_history_effect_timeline",
        "run_history_events",
        "run_history_assets",
        "run_history_member_metrics",
        "run_history_member_skill_usage",
        "run_history_member_stats",
        "run_history_members",
    )

    groups: List[Dict[str, Any]] = []
    deleted_run_ids: List[int] = []
    preserved_run_ids: List[int] = []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        duplicate_rows = conn.execute(duplicate_query, params).fetchall()

        for duplicate_row in duplicate_rows:
            run_rows = conn.execute(
                """
                SELECT
                    r.run_id,
                    r.saved_at,
                    r.total_damage,
                    r.elapsed_seconds,
                    (SELECT COUNT(*) FROM run_history_members m WHERE m.run_id = r.run_id) AS member_count,
                    (SELECT COUNT(*) FROM run_history_assets a WHERE a.run_id = r.run_id) AS asset_count,
                    (SELECT COUNT(*) FROM run_history_events e WHERE e.run_id = r.run_id) AS event_count,
                    (SELECT COUNT(*) FROM run_history_member_skill_usage su WHERE su.run_id = r.run_id) AS skill_usage_count,
                    (SELECT COUNT(*) FROM run_history_effect_timeline et WHERE et.run_id = r.run_id) AS effect_timeline_count
                FROM run_history_runs r
                WHERE r.source = ? AND r.source_run_uid = ?
                ORDER BY r.run_id ASC
                """,
                (str(duplicate_row["source"] or ""), str(duplicate_row["source_run_uid"] or "")),
            ).fetchall()
            if len(run_rows) <= 1:
                continue

            scored_rows = sorted(
                run_rows,
                key=lambda row: (
                    1 if row["total_damage"] is not None else 0,
                    int(row["effect_timeline_count"] or 0),
                    int(row["skill_usage_count"] or 0),
                    int(row["event_count"] or 0),
                    int(row["asset_count"] or 0),
                    int(row["member_count"] or 0),
                    1 if row["elapsed_seconds"] is not None else 0,
                    -int(row["run_id"]),
                ),
                reverse=True,
            )
            keep_run_id = int(scored_rows[0]["run_id"])
            remove_run_ids = [int(row["run_id"]) for row in scored_rows[1:]]
            if not remove_run_ids:
                continue

            preserved_run_ids.append(keep_run_id)
            deleted_run_ids.extend(remove_run_ids)
            groups.append(
                {
                    "source": str(duplicate_row["source"] or ""),
                    "source_run_uid": str(duplicate_row["source_run_uid"] or ""),
                    "duplicate_count": int(duplicate_row["duplicate_count"] or 0),
                    "keep_run_id": keep_run_id,
                    "remove_run_ids": remove_run_ids,
                }
            )

            placeholders = ", ".join("?" for _ in remove_run_ids)
            for table in child_tables:
                conn.execute(f"DELETE FROM {table} WHERE run_id IN ({placeholders})", remove_run_ids)
            conn.execute(f"DELETE FROM run_history_runs WHERE run_id IN ({placeholders})", remove_run_ids)

        conn.commit()

    return {
        "ok": True,
        "source_filter": source_text,
        "duplicate_groups": len(groups),
        "removed_runs": len(deleted_run_ids),
        "kept_runs": len(preserved_run_ids),
        "groups": groups,
        "deleted_run_ids": deleted_run_ids,
        "preserved_run_ids": preserved_run_ids,
    }


def run_history_summary(run_id: int, db_path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT run_id, encounter_key, stage_id, battle_id, success, elapsed_seconds, total_damage
            FROM run_history_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return {}
        member_count = conn.execute(
            "SELECT COUNT(*) FROM run_history_members WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        event_count = conn.execute(
            "SELECT COUNT(*) FROM run_history_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        asset_count = conn.execute(
            "SELECT COUNT(*) FROM run_history_assets WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        skill_usage_count = conn.execute(
            "SELECT COUNT(*) FROM run_history_member_skill_usage WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        effect_timeline_count = conn.execute(
            "SELECT COUNT(*) FROM run_history_effect_timeline WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return {
        "run_id": int(row[0]),
        "encounter_key": string_value(row[1]),
        "stage_id": string_value(row[2]),
        "battle_id": string_value(row[3]),
        "success": bool(row[4]),
        "elapsed_seconds": float_value(row[5]),
        "total_damage": float_value(row[6]),
        "members": int(member_count[0] if member_count else 0),
        "events": int(event_count[0] if event_count else 0),
        "assets": int(asset_count[0] if asset_count else 0),
        "skill_usages": int(skill_usage_count[0] if skill_usage_count else 0),
        "effect_timeline_rows": int(effect_timeline_count[0] if effect_timeline_count else 0),
    }


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
    masteries_by_champ = load_masteries_by_champion(conn)

    champion_rows = conn.execute(
        """
        SELECT champ_id, champion_name, affinity, rarity, awakening_level, empowerment_level
        FROM account_champions
        ORDER BY champion_name ASC, champ_id ASC
        """
    ).fetchall()

    conn.execute("DELETE FROM account_champion_total_stats")
    conn.execute("DELETE FROM account_champion_stat_models")

    source_counts = {"raw": 0, "derived": 0, "missing": 0}
    partial_count = 0
    computed_at = now_utc_iso()

    for champ_id, champion_name, affinity, rarity, awakening_level, empowerment_level in champion_rows:
        stat_result = build_stat_computation(
            base_stats=base_stats_by_name.get(string_value(champion_name), {}),
            raw_total_stats=raw_totals_by_champ.get(string_value(champ_id), {}),
            equipped_items=gear_by_owner.get(string_value(champ_id), []),
            bonuses=bonuses,
            set_rules=set_rules,
            masteries=masteries_by_champ.get(string_value(champ_id), []),
            affinity=string_value(affinity),
            rarity=string_value(rarity),
            awakening_level=int_value(awakening_level),
            empowerment_level=int_value(empowerment_level),
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
    definition_rows = conn.execute(
        """
        SELECT set_name, pieces_required, heal_each_turn_pct, set_kind, counts_accessories, max_pieces, source
        FROM set_definitions
        ORDER BY set_name ASC
        """
    ).fetchall()
    stat_rows = conn.execute(
        """
        SELECT set_name, stat_type, stat_value
        FROM set_definition_stats
        ORDER BY set_name ASC, stat_order ASC
        """
    ).fetchall()
    bonus_rows = conn.execute(
        """
        SELECT set_name, pieces_required, stat_type, stat_value, effect_text
        FROM set_definition_piece_bonuses
        ORDER BY set_name ASC, bonus_order ASC
        """
    ).fetchall()
    rules: Dict[str, Dict[str, Any]] = {}
    for set_name, pieces_required, heal_each_turn_pct, set_kind, counts_accessories, max_pieces, source in definition_rows:
        rules[string_value(set_name)] = {
            "pieces_required": int_value(pieces_required),
            "heal_each_turn_pct": float_value(heal_each_turn_pct),
            "set_kind": string_value(set_kind),
            "counts_accessories": bool(counts_accessories),
            "max_pieces": int_value(max_pieces),
            "source": string_value(source),
            "stats": [],
            "piece_bonuses": [],
        }
    for set_name, stat_type, stat_value in stat_rows:
        rule = rules.setdefault(string_value(set_name), {"stats": [], "piece_bonuses": []})
        if stat_type is not None:
            rule["stats"].append((string_value(stat_type), float_value(stat_value)))
    for set_name, pieces_required, stat_type, stat_value, effect_text in bonus_rows:
        rule = rules.setdefault(string_value(set_name), {"stats": [], "piece_bonuses": []})
        piece_bonus: Dict[str, Any] = {"pieces_required": int_value(pieces_required), "stats": []}
        if stat_type is not None:
            piece_bonus["stats"].append((string_value(stat_type), float_value(stat_value)))
        if effect_text is not None and string_value(effect_text).strip():
            piece_bonus["effect_text"] = string_value(effect_text)
        rule["piece_bonuses"].append(piece_bonus)
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
        SELECT item_id, item_class, slot, set_name, equipped_by, main_stat_type, main_stat_value
        FROM gear_items
        WHERE equipped_by IS NOT NULL AND equipped_by != ''
        ORDER BY equipped_by ASC, item_id ASC
        """
    ).fetchall()
    gear_by_owner: Dict[str, List[Dict[str, Any]]] = {}
    for item_id, item_class, slot, set_name, equipped_by, main_stat_type, main_stat_value in item_rows:
        gear_by_owner.setdefault(string_value(equipped_by), []).append(
            {
                "item_id": string_value(item_id),
                "item_class": string_value(item_class),
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


def load_masteries_by_champion(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT champ_id, mastery_id, mastery_name, tree, active
        FROM account_champion_masteries
        ORDER BY champ_id ASC, mastery_order ASC
        """
    ).fetchall()
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for champ_id, mastery_id, mastery_name, tree, active in rows:
        payload.setdefault(string_value(champ_id), []).append(
            {
                "mastery_id": string_value(mastery_id),
                "name": string_value(mastery_name),
                "tree": string_value(tree),
                "active": bool(active),
            }
        )
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


def repair_loaded_account_gear(account: Dict[str, Any], source_path: Path) -> None:
    gear = list_value(account.get("gear"))
    if not gear:
        return
    kind_by_item_id = load_raw_item_kind_map(source_path.parent / RAW_SOURCE_PATH.name)
    for item in gear:
        repair_single_gear_item(item, kind_by_item_id.get(string_value(item.get("item_id"))))


def load_raw_item_kind_map(raw_source_path: Path) -> Dict[str, int]:
    if not raw_source_path.exists():
        return {}
    try:
        raw_payload = json.loads(raw_source_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    containers = []
    if isinstance(raw_payload, dict):
        containers.extend(list_value(raw_payload.get("inventory")))
        containers.extend(list_value(raw_payload.get("gear")))
    mapping: Dict[str, int] = {}
    for item in containers:
        item_map = dict_value(item)
        item_id = string_value(first_non_empty(item_map.get("item_id"), item_map.get("id")))
        if not item_id:
            continue
        kind = int_value(item_map.get("kind"))
        if kind > 0:
            mapping[item_id] = kind
    return mapping


def repair_single_gear_item(item: Dict[str, Any], raw_kind: Optional[int] = None) -> None:
    item_class = string_value(item.get("item_class")).strip().lower()
    slot = string_value(item.get("slot")).strip().lower()
    main_stat = dict_value(item.get("main_stat"))
    main_stat_type = string_value(main_stat.get("type")).strip().lower()
    substat_types = collect_item_substat_types(item)

    if raw_kind is not None and raw_kind in LEGACY_KIND_SLOT_MAP:
        expected_class, expected_slot = LEGACY_KIND_SLOT_MAP[raw_kind]
        if is_valid_gear_item_for_slot(expected_class, expected_slot, main_stat_type, substat_types):
            item["item_class"] = expected_class
            item["slot"] = expected_slot
            item_class = expected_class
            slot = expected_slot

    if is_valid_gear_item_for_slot(item_class, slot, main_stat_type, substat_types):
        return

    candidate_slots = [
        candidate_slot
        for candidate_slot in infer_candidate_slots(item_class, main_stat_type)
        if is_valid_substats_for_slot(item_class, candidate_slot, substat_types)
    ]
    if len(candidate_slots) == 1:
        item["slot"] = candidate_slots[0]


def is_valid_main_stat_for_slot(item_class: str, slot: str, stat_type: str) -> bool:
    if not item_class or not slot or not stat_type:
        return True
    allowed_by_slot = GEAR_ALLOWED_MAIN_STATS.get(item_class, {})
    allowed_stats = allowed_by_slot.get(slot)
    if not allowed_stats:
        return True
    return stat_type in allowed_stats


def is_valid_substats_for_slot(item_class: str, slot: str, stat_types: Iterable[str]) -> bool:
    if not item_class or not slot:
        return True
    allowed_by_slot = GEAR_ALLOWED_SUBSTATS.get(item_class, {})
    allowed_stats = allowed_by_slot.get(slot)
    if not allowed_stats:
        return True
    normalized_types = [string_value(stat_type).strip().lower() for stat_type in stat_types if string_value(stat_type).strip()]
    return all(stat_type in allowed_stats for stat_type in normalized_types)


def is_valid_gear_item_for_slot(item_class: str, slot: str, main_stat_type: str, substat_types: Iterable[str]) -> bool:
    return is_valid_main_stat_for_slot(item_class, slot, main_stat_type) and is_valid_substats_for_slot(
        item_class,
        slot,
        substat_types,
    )


def collect_item_substat_types(item: Dict[str, Any]) -> List[str]:
    return [
        string_value(dict_value(substat).get("type")).strip().lower()
        for substat in list_value(item.get("substats"))
        if string_value(dict_value(substat).get("type")).strip()
    ]


def collect_gear_validation_issues(item: Dict[str, Any]) -> List[str]:
    item_class = string_value(item.get("item_class")).strip().lower()
    slot = string_value(item.get("slot")).strip().lower()
    main_stat = dict_value(item.get("main_stat"))
    main_stat_type = string_value(main_stat.get("type")).strip().lower()
    substat_types = collect_item_substat_types(item)
    issues: List[str] = []
    if not is_valid_main_stat_for_slot(item_class, slot, main_stat_type):
        issues.append(f"main_stat:{main_stat_type or 'missing'}@{slot or 'unknown'}")
    if not is_valid_substats_for_slot(item_class, slot, substat_types):
        allowed_by_slot = GEAR_ALLOWED_SUBSTATS.get(item_class, {})
        allowed_stats = allowed_by_slot.get(slot, set())
        invalid_substats = [stat_type for stat_type in substat_types if stat_type not in allowed_stats]
        for stat_type in invalid_substats:
            issues.append(f"substat:{stat_type}@{slot or 'unknown'}")
    return issues


def is_valid_gear_item(item: Dict[str, Any]) -> bool:
    return not collect_gear_validation_issues(item)


def infer_candidate_slots(item_class: str, stat_type: str) -> List[str]:
    if not item_class or not stat_type:
        return []
    allowed_by_slot = GEAR_ALLOWED_MAIN_STATS.get(item_class, {})
    return [slot for slot, allowed_stats in allowed_by_slot.items() if stat_type in allowed_stats]


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


def json_text(value: Any, fallback: Any) -> str:
    normalized = value if isinstance(value, (dict, list)) else fallback
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> None:
    summary = bootstrap_database()
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
