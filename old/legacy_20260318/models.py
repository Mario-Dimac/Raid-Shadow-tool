from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Any, Dict


# =========================
# BASIC BUILDING BLOCKS
# =========================

@dataclass
class Meta:
    project: str = "CB Forge"
    schema_version: str = "1.0"
    source: str = ""
    extracted_at: str = ""
    player_name: str = ""
    account_level: int = 0


@dataclass
class AccountBonus:
    bonus_id: str
    source: str               # great_hall, area_bonus, passive_account
    scope: str                # global, clan_boss, demon_lord
    target: str               # all, force, magic, spirit, void
    stat: str                 # hp_pct, atk_pct, def_pct, spd, acc, res, crit_dmg
    value: float
    active: bool = True


@dataclass
class StatValue:
    type: str                 # hp, atk, def, spd, crit_rate, crit_dmg, acc, res
    value: float


@dataclass
class SubStat:
    type: str
    value: float
    rolls: int = 0
    glyph_value: float = 0.0


@dataclass
class Effect:
    type: str                 # buff, debuff, passive, hit_effect
    name: str                 # Poison, Weaken, Unkillable...
    duration: int = 0
    target: str = ""          # self, ally, all_allies, enemy, all_enemies
    chance: float = 100.0


@dataclass
class Mastery:
    tree: str                 # offense, defense, support
    mastery_id: str
    name: str
    active: bool = True


@dataclass
class Blessing:
    name: str = ""
    level: int = 0


# =========================
# SKILLS / CHAMPIONS
# =========================

@dataclass
class Skill:
    skill_id: str             # a1, a2, a3, a4, passive
    name: str
    slot: str                 # A1, A2, A3, A4, Passive
    booked: bool = False

    cooldown_base: Optional[int] = None
    cooldown_booked: Optional[int] = None
    cooldown_current: Optional[int] = None

    turn_meter_fill_pct: float = 0.0
    turn_meter_reduce_pct: float = 0.0
    grants_extra_turn: bool = False
    resets_cooldowns: bool = False
    hits: int = 1

    effects: List[Effect] = field(default_factory=list)
    cb_tags: List[str] = field(default_factory=list)


@dataclass
class ChampionStats:
    hp: float = 0
    atk: float = 0
    def_: float = 0
    spd: float = 0
    crit_rate: float = 0
    crit_dmg: float = 0
    res: float = 0
    acc: float = 0

    def to_dict(self) -> Dict[str, float]:
        return {
            "hp": self.hp,
            "atk": self.atk,
            "def": self.def_,
            "spd": self.spd,
            "crit_rate": self.crit_rate,
            "crit_dmg": self.crit_dmg,
            "res": self.res,
            "acc": self.acc,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChampionStats":
        return cls(
            hp=data.get("hp", 0),
            atk=data.get("atk", 0),
            def_=data.get("def", data.get("def_", 0)),
            spd=data.get("spd", 0),
            crit_rate=data.get("crit_rate", 0),
            crit_dmg=data.get("crit_dmg", 0),
            res=data.get("res", 0),
            acc=data.get("acc", 0),
        )


@dataclass
class Champion:
    champ_id: str
    name: str
    rarity: str               # rare, epic, legendary, mythical
    affinity: str             # magic, force, spirit, void
    faction: str

    level: int = 1
    rank: int = 1
    ascension: int = 0
    awakening_level: int = 0
    empowerment_level: int = 0

    booked: bool = False
    in_vault: bool = False
    locked: bool = False

    role_tags: List[str] = field(default_factory=list)

    base_stats: ChampionStats = field(default_factory=ChampionStats)
    total_stats: ChampionStats = field(default_factory=ChampionStats)

    equipped_item_ids: List[str] = field(default_factory=list)
    masteries: List[Mastery] = field(default_factory=list)
    blessing: Blessing = field(default_factory=Blessing)
    skills: List[Skill] = field(default_factory=list)


# =========================
# GEAR
# =========================

@dataclass
class GearItem:
    item_id: str
    item_class: str           # artifact, accessory
    slot: str                 # weapon, helmet, shield, gloves, chest, boots, ring, amulet, banner
    set_name: str
    rarity: str               # common, uncommon, rare, epic, legendary, mythical

    rank: int = 0
    level: int = 0
    ascension_level: int = 0

    main_stat: Optional[StatValue] = None
    substats: List[SubStat] = field(default_factory=list)

    required_faction: str = ""
    required_faction_id: int = 0
    equipped_by: Optional[str] = None   # champ_id
    locked: bool = False


# =========================
# ROOT ACCOUNT MODEL
# =========================

@dataclass
class AccountData:
    meta: Meta = field(default_factory=Meta)
    account_bonuses: List[AccountBonus] = field(default_factory=list)
    champions: List[Champion] = field(default_factory=list)
    gear: List[GearItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
