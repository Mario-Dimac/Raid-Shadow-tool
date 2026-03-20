from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class BossProfile:
    key: str
    label: str
    focus: str
    required_roles: List[str] = field(default_factory=list)
    fill_roles: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BuildProfile:
    key: str
    label: str
    stat_weights: Dict[str, float]
    preferred_sets: List[str] = field(default_factory=list)
    notes: str = ""
    allocation_priority: int = 0
    target_stats: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChampionHint:
    roles: List[str]
    boss_scores: Dict[str, float]
    default_build: str
    build_overrides: Dict[str, str] = field(default_factory=dict)
    notes: str = ""


BOSS_PROFILES: Dict[str, BossProfile] = {
    "demon_lord_unm": BossProfile(
        key="demon_lord_unm",
        label="Demon Lord UNM",
        focus="Massimizzare danno e stabilita sul Clan Boss con un occhio a speed tune e debuff uptime.",
        required_roles=["damage", "survival", "debuffer"],
        fill_roles=["poisoner", "burner", "speed", "cleanse"],
    ),
    "hydra_normal": BossProfile(
        key="hydra_normal",
        label="Hydra Normal",
        focus="Massimizzare numero di run e stabilita su Hydra con controllo teste e sustain.",
        required_roles=["provoker", "block_buffs", "cleanse", "damage"],
        fill_roles=["support", "hex", "burner"],
    ),
    "dragon_hard": BossProfile(
        key="dragon_hard",
        label="Dragon Hard",
        focus="Pulire le wave e abbattere il boss con danni stabili e controllo debuff.",
        required_roles=["wave_clear", "damage", "debuffer"],
        fill_roles=["support", "poisoner", "speed"],
    ),
    "fire_knight_hard": BossProfile(
        key="fire_knight_hard",
        label="Fire Knight Hard",
        focus="Aprire lo scudo e tenere basso il turn meter con multi-hit e controllo.",
        required_roles=["multi_hit", "turn_meter", "debuffer"],
        fill_roles=["support", "freeze", "speed"],
    ),
    "spider_hard": BossProfile(
        key="spider_hard",
        label="Spider Hard",
        focus="Bruciare o controllare gli spiderling e chiudere il fight in modo affidabile.",
        required_roles=["burner", "control", "damage"],
        fill_roles=["support", "turn_meter", "revive"],
    ),
    "ice_golem_hard": BossProfile(
        key="ice_golem_hard",
        label="Ice Golem Hard",
        focus="Fare run sicure con sustain, controllo e danno disciplinato.",
        required_roles=["survival", "debuffer", "damage"],
        fill_roles=["revive", "cleanse", "support"],
    ),
}


BUILD_PROFILES: Dict[str, BuildProfile] = {
    "speed_tuned_support": BuildProfile(
        key="speed_tuned_support",
        label="Speed Tuned Support",
        stat_weights={"spd": 7.0, "hp_pct": 3.5, "def_pct": 3.5, "res": 1.4, "acc": 1.2},
        preferred_sets=["Attack Speed", "Accuracy And Speed", "HP And Heal", "HP And Defence"],
        notes="Priorita assoluta a speed e sopravvivenza per stare nel tune.",
        allocation_priority=100,
        target_stats=["SPD", "HP%", "DEF%", "RES", "ACC"],
    ),
    "cooldown_support": BuildProfile(
        key="cooldown_support",
        label="Cooldown Support",
        stat_weights={"spd": 7.2, "hp_pct": 3.4, "def_pct": 3.2, "res": 1.0},
        preferred_sets=["Attack Speed", "Cooldown Reduction Chance", "Accuracy And Speed", "HP And Heal"],
        notes="Speed e robustezza per far girare la skill chiave.",
        allocation_priority=95,
        target_stats=["SPD", "HP%", "DEF%", "RES"],
    ),
    "cleanser": BuildProfile(
        key="cleanser",
        label="Cleanser",
        stat_weights={"spd": 6.4, "hp_pct": 3.2, "def_pct": 3.2, "res": 2.0},
        preferred_sets=["Attack Speed", "HP And Defence", "HP And Heal", "Block Debuff"],
        notes="Serve rapidita e sustain per mantenere pulito il team.",
        allocation_priority=90,
        target_stats=["SPD", "HP%", "DEF%", "RES"],
    ),
    "ally_protector": BuildProfile(
        key="ally_protector",
        label="Ally Protector",
        stat_weights={"spd": 5.2, "hp_pct": 4.4, "def_pct": 4.2, "res": 1.0},
        preferred_sets=["Passive Share Damage And Heal", "Defiant", "HP And Heal", "HP And Defence"],
        notes="Difesa e vita prima del danno.",
        allocation_priority=88,
        target_stats=["HP%", "DEF%", "SPD", "RES"],
    ),
    "decrease_attack_support": BuildProfile(
        key="decrease_attack_support",
        label="Decrease ATK Support",
        stat_weights={"spd": 6.2, "acc": 5.0, "hp_pct": 3.4, "def_pct": 3.2, "res": 1.0},
        preferred_sets=["Accuracy And Speed", "Attack Speed", "Accuracy", "HP And Defence", "HP And Heal"],
        notes="Priorita a far atterrare Decrease ATK senza perdere stabilita.",
        allocation_priority=89,
        target_stats=["ACC", "SPD", "HP%", "DEF%", "RES"],
    ),
    "poisoner": BuildProfile(
        key="poisoner",
        label="Poisoner",
        stat_weights={"spd": 5.4, "acc": 4.8, "hp_pct": 2.2, "def_pct": 2.2, "crit_rate": 1.0, "crit_dmg": 0.8},
        preferred_sets=["Accuracy And Speed", "Dot Rate", "Attack Speed", "Accuracy"],
        notes="Accuracy e speed per tenere alto l'uptime dei debuff.",
        allocation_priority=82,
        target_stats=["ACC", "SPD", "HP%", "DEF%", "CRIT RATE"],
    ),
    "hp_burner": BuildProfile(
        key="hp_burner",
        label="HP Burner",
        stat_weights={"spd": 5.2, "acc": 4.8, "hp_pct": 2.4, "def_pct": 2.0, "crit_rate": 1.0, "crit_dmg": 0.8},
        preferred_sets=["Accuracy And Speed", "Attack Speed", "Accuracy", "Cooldown Reduction Chance"],
        notes="Accuracy e speed per il burn, poi sopravvivenza.",
        allocation_priority=80,
        target_stats=["ACC", "SPD", "HP%", "DEF%", "CRIT RATE"],
    ),
    "clan_boss_dps": BuildProfile(
        key="clan_boss_dps",
        label="Clan Boss DPS",
        stat_weights={"spd": 4.8, "acc": 3.4, "crit_rate": 3.8, "crit_dmg": 3.4, "atk_pct": 2.6, "def_pct": 2.0, "hp_pct": 1.6},
        preferred_sets=["Attack Power And Ignore Defense", "Ignore Defense", "Accuracy And Speed", "Attack Speed", "Get Extra Turn"],
        notes="Bilancia danno, speed e accuracy dove serve.",
        allocation_priority=78,
        target_stats=["CRIT RATE", "CRIT DMG", "ATK%", "SPD", "ACC", "DEF%"],
    ),
    "support_general": BuildProfile(
        key="support_general",
        label="General Support",
        stat_weights={"spd": 5.0, "hp_pct": 3.0, "def_pct": 3.0, "acc": 2.0, "res": 1.2},
        preferred_sets=["Attack Speed", "Accuracy And Speed", "HP And Heal", "HP And Defence"],
        notes="Build di supporto flessibile per dungeon e Hydra.",
        allocation_priority=76,
        target_stats=["SPD", "HP%", "DEF%", "ACC", "RES"],
    ),
    "hydra_damage": BuildProfile(
        key="hydra_damage",
        label="Hydra Damage",
        stat_weights={"spd": 4.6, "acc": 3.2, "crit_rate": 3.2, "crit_dmg": 3.0, "hp_pct": 2.2, "def_pct": 2.2, "res": 1.0},
        preferred_sets=["Get Extra Turn", "Feral", "Accuracy And Speed", "Attack Speed", "Merciless"],
        notes="Serve danno, accuratezza e abbastanza robustezza per le teste.",
        allocation_priority=74,
        target_stats=["CRIT RATE", "CRIT DMG", "SPD", "ACC", "HP%", "DEF%"],
    ),
    "fire_knight_breaker": BuildProfile(
        key="fire_knight_breaker",
        label="Fire Knight Breaker",
        stat_weights={"spd": 5.6, "crit_rate": 2.4, "crit_dmg": 2.2, "acc": 2.2, "hp_pct": 1.8, "def_pct": 1.6},
        preferred_sets=["Cooldown Reduction Chance", "Attack Speed", "Accuracy And Speed", "Get Extra Turn"],
        notes="Multi-hit e controllo turn meter vogliono speed alta.",
        allocation_priority=72,
        target_stats=["SPD", "CRIT RATE", "CRIT DMG", "ACC", "HP%"],
    ),
    "spider_burner": BuildProfile(
        key="spider_burner",
        label="Spider Burner",
        stat_weights={"spd": 5.2, "acc": 4.8, "hp_pct": 2.6, "def_pct": 2.0},
        preferred_sets=["Accuracy And Speed", "Attack Speed", "Cooldown Reduction Chance", "HP And Heal"],
        notes="HP Burn e controllo richiedono accuracy e consistenza.",
        allocation_priority=70,
        target_stats=["ACC", "SPD", "HP%", "DEF%"],
    ),
    "wave_nuker": BuildProfile(
        key="wave_nuker",
        label="Wave Nuker",
        stat_weights={"spd": 4.0, "crit_rate": 4.2, "crit_dmg": 4.0, "atk_pct": 3.4, "def_pct": 2.2, "hp_pct": 1.4},
        preferred_sets=["Ignore Defense", "Attack Power And Ignore Defense", "Crit Rate And Ignore DEF Multiplier", "Instinct"],
        notes="Danno puro per wave e dungeon rapidi.",
        allocation_priority=68,
        target_stats=["CRIT RATE", "CRIT DMG", "ATK%", "SPD", "DEF%"],
    ),
}


CHAMPION_HINTS: Dict[str, ChampionHint] = {
    "Maneater": ChampionHint(
        roles=["speed", "survival", "unkillable", "support"],
        boss_scores={"demon_lord_unm": 100, "hydra_normal": 34},
        default_build="speed_tuned_support",
        notes="Core fortissimo per shell unkillable sul Clan Boss.",
    ),
    "Pain Keeper": ChampionHint(
        roles=["speed", "support", "cooldown"],
        boss_scores={"demon_lord_unm": 94},
        default_build="cooldown_support",
        notes="Riduzione cooldown fondamentale in budget unkillable.",
    ),
    "Geomancer": ChampionHint(
        roles=["damage", "burner", "debuffer"],
        boss_scores={"demon_lord_unm": 96, "hydra_normal": 80, "spider_hard": 72, "ice_golem_hard": 68},
        default_build="hp_burner",
    ),
    "Frozen Banshee": ChampionHint(
        roles=["damage", "poisoner", "debuffer"],
        boss_scores={"demon_lord_unm": 90, "dragon_hard": 70, "ice_golem_hard": 60},
        default_build="poisoner",
    ),
    "Ninja": ChampionHint(
        roles=["damage", "burner"],
        boss_scores={"demon_lord_unm": 93, "dragon_hard": 76, "fire_knight_hard": 62, "hydra_normal": 70},
        default_build="clan_boss_dps",
    ),
    "Deacon Armstrong": ChampionHint(
        roles=["speed", "debuffer", "support"],
        boss_scores={"demon_lord_unm": 82, "dragon_hard": 82, "fire_knight_hard": 78, "hydra_normal": 58},
        default_build="support_general",
    ),
    "Heiress": ChampionHint(
        roles=["cleanse", "speed", "support"],
        boss_scores={"demon_lord_unm": 78, "fire_knight_hard": 45},
        default_build="cleanser",
    ),
    "Doompriest": ChampionHint(
        roles=["cleanse", "support", "survival"],
        boss_scores={"demon_lord_unm": 84, "hydra_normal": 64, "ice_golem_hard": 55},
        default_build="cleanser",
    ),
    "Martyr": ChampionHint(
        roles=["survival", "ally_protect", "damage", "debuffer"],
        boss_scores={"demon_lord_unm": 88, "ice_golem_hard": 70, "dragon_hard": 64},
        default_build="ally_protector",
        build_overrides={"demon_lord_unm": "decrease_attack_support"},
    ),
    "Stag Knight": ChampionHint(
        roles=["debuffer", "support", "survival"],
        boss_scores={"demon_lord_unm": 86, "dragon_hard": 72, "fire_knight_hard": 58},
        default_build="decrease_attack_support",
        notes="Ottimo per portare Decrease ATK + Decrease DEF in modo stabile sul Clan Boss.",
    ),
    "Underpriest Brogni": ChampionHint(
        roles=["survival", "support", "burner"],
        boss_scores={"demon_lord_unm": 92, "hydra_normal": 86, "ice_golem_hard": 74},
        default_build="ally_protector",
    ),
    "Valkyrie": ChampionHint(
        roles=["survival", "support", "damage"],
        boss_scores={"demon_lord_unm": 94, "ice_golem_hard": 72, "dragon_hard": 66},
        default_build="ally_protector",
        notes="Counterattack e scudi la rendono una delle killable piu solide sul Clan Boss.",
    ),
    "Venus": ChampionHint(
        roles=["damage", "debuffer", "poisoner"],
        boss_scores={"demon_lord_unm": 92, "dragon_hard": 78, "hydra_normal": 74},
        default_build="poisoner",
        notes="Porta Decrease DEF e Weaken con ottimo valore anche sul Clan Boss.",
    ),
    "Riho Bonespear": ChampionHint(
        roles=["support", "debuffer", "cleanse", "survival"],
        boss_scores={"demon_lord_unm": 86, "hydra_normal": 84, "dragon_hard": 70},
        default_build="cleanser",
        notes="Support molto completa per comp killable che hanno bisogno di pulizia e debuff utili.",
    ),
    "Jintoro": ChampionHint(
        roles=["damage"],
        boss_scores={"demon_lord_unm": 91, "dragon_hard": 64},
        default_build="clan_boss_dps",
        notes="DPS single target molto forte quando il team riesce a sostenerlo a lungo.",
    ),
    "Teodor the Savant": ChampionHint(
        roles=["poisoner", "support", "survival"],
        boss_scores={"demon_lord_unm": 90, "dragon_hard": 84, "hydra_normal": 72},
        default_build="poisoner",
        notes="Poison pressure e consistenza lo rendono interessante nelle varianti Clan Boss piu lunghe.",
    ),
    "Michinaki": ChampionHint(
        roles=["damage", "burner", "debuffer", "survival"],
        boss_scores={"demon_lord_unm": 88, "hydra_normal": 92, "dragon_hard": 70},
        default_build="clan_boss_dps",
        notes="Buon mix di danno, HP Burn e debuff per comp killable aggressive.",
    ),
    "Tyrant Ixlimor": ChampionHint(
        roles=["survival", "ally_protect", "burner"],
        boss_scores={"demon_lord_unm": 88, "hydra_normal": 64, "ice_golem_hard": 62},
        default_build="ally_protector",
        notes="Ally Protect e HP Burn sono molto utili nelle varianti Clan Boss orientate alla tenuta.",
    ),
    "Rhazin Scarhide": ChampionHint(
        roles=["damage", "debuffer"],
        boss_scores={"demon_lord_unm": 78, "dragon_hard": 68, "fire_knight_hard": 64},
        default_build="clan_boss_dps",
    ),
    "Catacomb Councilor": ChampionHint(
        roles=["damage", "support", "multi_hit"],
        boss_scores={"demon_lord_unm": 76, "fire_knight_hard": 74},
        default_build="clan_boss_dps",
    ),
    "High Khatun": ChampionHint(
        roles=["speed", "support"],
        boss_scores={"demon_lord_unm": 68, "dragon_hard": 70, "fire_knight_hard": 60},
        default_build="support_general",
    ),
    "Aox the Rememberer": ChampionHint(
        roles=["poisoner", "support", "debuffer"],
        boss_scores={"demon_lord_unm": 70, "dragon_hard": 60},
        default_build="poisoner",
    ),
    "Occult Brawler": ChampionHint(
        roles=["poisoner", "damage"],
        boss_scores={"demon_lord_unm": 74, "dragon_hard": 60},
        default_build="poisoner",
    ),
    "Apothecary": ChampionHint(
        roles=["speed", "support"],
        boss_scores={"demon_lord_unm": 58, "dragon_hard": 68, "fire_knight_hard": 66},
        default_build="support_general",
    ),
    "Mithrala Lifebane": ChampionHint(
        roles=["support", "block_buffs", "hex", "cleanse"],
        boss_scores={"demon_lord_unm": 80, "hydra_normal": 100, "dragon_hard": 72, "spider_hard": 70},
        default_build="support_general",
    ),
    "Artak": ChampionHint(
        roles=["burner", "control", "damage"],
        boss_scores={"spider_hard": 98, "ice_golem_hard": 78, "hydra_normal": 72, "dragon_hard": 60},
        default_build="spider_burner",
    ),
    "Coldheart": ChampionHint(
        roles=["turn_meter", "damage", "multi_hit"],
        boss_scores={"fire_knight_hard": 92, "spider_hard": 86, "dragon_hard": 52},
        default_build="fire_knight_breaker",
    ),
    "Arbiter": ChampionHint(
        roles=["speed", "support", "revive"],
        boss_scores={"dragon_hard": 80, "fire_knight_hard": 72, "spider_hard": 68, "hydra_normal": 58},
        default_build="support_general",
    ),
    "Archmage Hellmut": ChampionHint(
        roles=["support", "wave_clear", "damage"],
        boss_scores={"dragon_hard": 72, "fire_knight_hard": 62, "ice_golem_hard": 60},
        default_build="support_general",
    ),
    "Hurndig": ChampionHint(
        roles=["wave_clear", "damage", "debuffer"],
        boss_scores={"dragon_hard": 84, "spider_hard": 66, "ice_golem_hard": 72},
        default_build="wave_nuker",
    ),
    "Ghostborn": ChampionHint(
        roles=["debuffer", "wave_clear", "damage"],
        boss_scores={"dragon_hard": 76, "spider_hard": 60, "fire_knight_hard": 50},
        default_build="wave_nuker",
    ),
    "Gorgorab": ChampionHint(
        roles=["support", "revive", "speed"],
        boss_scores={"dragon_hard": 62, "spider_hard": 58, "ice_golem_hard": 58},
        default_build="support_general",
    ),
    "Lanakis the Chosen": ChampionHint(
        roles=["support", "multi_hit", "damage"],
        boss_scores={"hydra_normal": 78, "fire_knight_hard": 72, "demon_lord_unm": 64},
        default_build="hydra_damage",
    ),
    "Harima": ChampionHint(
        roles=["damage", "survival"],
        boss_scores={"hydra_normal": 70, "ice_golem_hard": 72, "dragon_hard": 68},
        default_build="hydra_damage",
    ),
    "Ignatius": ChampionHint(
        roles=["burner", "control", "damage"],
        boss_scores={"spider_hard": 84, "ice_golem_hard": 64, "hydra_normal": 48},
        default_build="spider_burner",
    ),
    "Eostrid Dreamsong": ChampionHint(
        roles=["support", "speed", "damage"],
        boss_scores={"hydra_normal": 74, "dragon_hard": 70, "fire_knight_hard": 62},
        default_build="support_general",
    ),
    "Belletar Mage-slayer": ChampionHint(
        roles=["damage", "wave_clear"],
        boss_scores={"dragon_hard": 68, "ice_golem_hard": 60},
        default_build="wave_nuker",
    ),
}
