from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from cb_teams import TeamRecommendation, build_recommendations, load_account, serialize_team
from cb_rules import BUILD_PROFILES
from cb_run_history import list_manual_runs


BASE_DIR = Path(__file__).resolve().parent
NORMALIZED_PATH = BASE_DIR / "input" / "normalized_account.json"
TURN_METER_MAX = 1000.0


@dataclass(frozen=True)
class ClanBossLevel:
    key: str
    label: str
    speed: float
    base_damage: float
    required_acc: float


@dataclass(frozen=True)
class SkillDefinition:
    slot: str
    name: str
    cooldown: int = 0
    damage_factor: float = 1.0
    team_buffs: Dict[str, int] = field(default_factory=dict)
    self_buffs: Dict[str, int] = field(default_factory=dict)
    boss_debuffs: Dict[str, int] = field(default_factory=dict)
    cooldown_reduction_allies: int = 0
    turn_meter_fill_allies: float = 0.0
    direct_heal_allies: float = 0.0


@dataclass(frozen=True)
class ChampionDefinition:
    opener: List[str]
    priority: List[str]
    skills: Dict[str, SkillDefinition]
    passive: Optional[str] = None
    notes: str = ""


@dataclass
class UnitState:
    champ_id: str
    name: str
    affinity: str
    speed: float
    hp: float
    max_hp: float
    attack: float
    defense: float
    accuracy: float
    crit_rate: float
    crit_damage: float
    definition: ChampionDefinition
    cooldowns: Dict[str, int] = field(default_factory=dict)
    buffs: Dict[str, int] = field(default_factory=dict)
    debuffs: Dict[str, int] = field(default_factory=dict)
    turn_meter: float = 0.0
    turns_taken: int = 0
    alive: bool = True
    estimated_damage: float = 0.0
    weak_hits: int = 0
    strong_hits: int = 0
    set_heal_each_turn_pct: float = 0.0


CLAN_BOSS_LEVELS: Dict[str, ClanBossLevel] = {
    "easy": ClanBossLevel("easy", "Easy", 90.0, 950.0, 50.0),
    "normal": ClanBossLevel("normal", "Normal", 120.0, 1500.0, 100.0),
    "hard": ClanBossLevel("hard", "Hard", 140.0, 2300.0, 150.0),
    "brutal": ClanBossLevel("brutal", "Brutal", 160.0, 3200.0, 180.0),
    "nightmare": ClanBossLevel("nightmare", "Nightmare", 170.0, 4200.0, 220.0),
    "ultra_nightmare": ClanBossLevel("ultra_nightmare", "Ultra Nightmare", 190.0, 5600.0, 250.0),
}


GENERIC_DEFINITION = ChampionDefinition(
    opener=["A3", "A2", "A1"],
    priority=["A3", "A2", "A1"],
    skills={
        "A1": SkillDefinition(slot="A1", name="Basic Strike", damage_factor=1.0),
        "A2": SkillDefinition(slot="A2", name="Secondary Skill", cooldown=3, damage_factor=1.2),
        "A3": SkillDefinition(slot="A3", name="Primary Skill", cooldown=4, damage_factor=1.35),
    },
    notes="Fallback generico quando mancano metadati precisi della skill.",
)


CHAMPION_DEFINITIONS: Dict[str, ChampionDefinition] = {
    "Maneater": ChampionDefinition(
        opener=["A3", "A1", "A2"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Syphon", damage_factor=0.95),
            "A2": SkillDefinition(slot="A2", name="Drain", cooldown=3, damage_factor=1.1, boss_debuffs={"decrease_attack": 2}),
            "A3": SkillDefinition(slot="A3", name="Ancient Blood", cooldown=5, damage_factor=0.0, team_buffs={"unkillable": 2, "block_debuffs": 2}),
        },
        notes="Shell unkillable per Clan Boss.",
    ),
    "Pain Keeper": ChampionDefinition(
        opener=["A3", "A1", "A2"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Pain Siphon", damage_factor=0.85),
            "A2": SkillDefinition(slot="A2", name="Spectacular Sweep", cooldown=3, damage_factor=1.0, direct_heal_allies=0.08),
            "A3": SkillDefinition(slot="A3", name="Combat Tactics", cooldown=4, damage_factor=0.0, cooldown_reduction_allies=1, direct_heal_allies=0.15),
        },
        notes="Riduce i cooldown del team e mantiene vivo il loop.",
    ),
    "Geomancer": ChampionDefinition(
        opener=["A3", "A1", "A2"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Stone Hammer", damage_factor=1.0),
            "A2": SkillDefinition(slot="A2", name="Quicksand Grasp", cooldown=3, damage_factor=1.1, boss_debuffs={"weaken": 2}),
            "A3": SkillDefinition(slot="A3", name="Burning Resolve", cooldown=3, damage_factor=0.9, boss_debuffs={"hp_burn": 3}),
        },
        notes="HP Burn piu weaken, con danno riflesso simulato sul turno del boss.",
    ),
    "Frozen Banshee": ChampionDefinition(
        opener=["A3", "A2", "A1"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Cruel Exultation", damage_factor=0.7, boss_debuffs={"poison": 2}),
            "A2": SkillDefinition(slot="A2", name="Foul Play", cooldown=3, damage_factor=0.95, boss_debuffs={"poison": 2}),
            "A3": SkillDefinition(slot="A3", name="Poison Sensitivity", cooldown=3, damage_factor=0.0, boss_debuffs={"poison_sensitivity": 2}),
        },
        notes="La sensibilita al veleno amplifica il danno del setup CB.",
    ),
    "Doompriest": ChampionDefinition(
        opener=["A2", "A1", "A3"],
        priority=["A2", "A3", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Dark Absolution", damage_factor=0.9),
            "A2": SkillDefinition(slot="A2", name="Mass Possession", cooldown=3, damage_factor=0.0, team_buffs={"increase_attack": 2}),
            "A3": SkillDefinition(slot="A3", name="Bolster", cooldown=4, damage_factor=0.0, direct_heal_allies=0.12),
        },
        passive="cleanse_one_each_turn",
        notes="Cleanse passivo fortissimo contro le affinity del Clan Boss.",
    ),
    "Martyr": ChampionDefinition(
        opener=["A3", "A2", "A1"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Torrential Blow", damage_factor=1.0, boss_debuffs={"decrease_defense": 2}),
            "A2": SkillDefinition(slot="A2", name="Crackling Blade", cooldown=4, damage_factor=1.1, boss_debuffs={"decrease_attack": 2}),
            "A3": SkillDefinition(slot="A3", name="Martyrdom", cooldown=4, damage_factor=0.0, team_buffs={"counterattack": 2, "increase_defense": 2}),
        },
        notes="Counterattack e Increase DEF per setup killable robusti.",
    ),
    "Stag Knight": ChampionDefinition(
        opener=["A2", "A3", "A1"],
        priority=["A2", "A3", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Despair", damage_factor=0.95),
            "A2": SkillDefinition(slot="A2", name="Huntmaster", cooldown=3, damage_factor=1.0, boss_debuffs={"decrease_attack": 2, "decrease_defense": 2}),
            "A3": SkillDefinition(slot="A3", name="Aesir Slam", cooldown=4, damage_factor=1.2),
        },
        notes="Debuffer robusto per portare insieme Decrease ATK e Decrease DEF.",
    ),
    "Ninja": ChampionDefinition(
        opener=["A3", "A2", "A1"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Yakanai", damage_factor=1.2),
            "A2": SkillDefinition(slot="A2", name="Hailburn", cooldown=3, damage_factor=1.15, boss_debuffs={"hp_burn": 3}),
            "A3": SkillDefinition(slot="A3", name="Cyan Slash", cooldown=4, damage_factor=1.7, boss_debuffs={"decrease_defense": 2}),
        },
    ),
    "Deacon Armstrong": ChampionDefinition(
        opener=["A3", "A2", "A1"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Tactical Partner", damage_factor=0.9),
            "A2": SkillDefinition(slot="A2", name="Psychic Whip", cooldown=3, damage_factor=0.9, boss_debuffs={"decrease_defense": 2, "leech": 2}),
            "A3": SkillDefinition(slot="A3", name="Time Compression", cooldown=3, damage_factor=0.0, team_buffs={"increase_speed": 2}, turn_meter_fill_allies=0.15),
        },
    ),
    "Heiress": ChampionDefinition(
        opener=["A2", "A1", "A3"],
        priority=["A2", "A3", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Quarterstaff", damage_factor=0.85),
            "A2": SkillDefinition(slot="A2", name="Heiress Favor", cooldown=3, damage_factor=0.0, team_buffs={"increase_speed": 2, "block_debuffs": 1}),
            "A3": SkillDefinition(slot="A3", name="Double Strike", cooldown=4, damage_factor=1.25),
        },
        passive="cleanse_on_turn",
    ),
    "Rhazin Scarhide": ChampionDefinition(
        opener=["A2", "A3", "A1"],
        priority=["A2", "A3", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Bog Down", damage_factor=0.95),
            "A2": SkillDefinition(slot="A2", name="Shear", cooldown=3, damage_factor=1.25, boss_debuffs={"decrease_defense": 2, "weaken": 2}),
            "A3": SkillDefinition(slot="A3", name="Wrath of the Slayer", cooldown=4, damage_factor=1.45),
        },
    ),
    "Underpriest Brogni": ChampionDefinition(
        opener=["A3", "A2", "A1"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Condemn", damage_factor=0.9, boss_debuffs={"hp_burn": 2}),
            "A2": SkillDefinition(slot="A2", name="Resilient Glow", cooldown=4, damage_factor=0.0, team_buffs={"increase_attack": 2}),
            "A3": SkillDefinition(slot="A3", name="Brynhild's Feast", cooldown=4, damage_factor=0.0, team_buffs={"block_debuffs": 2, "shield": 2}),
        },
    ),
    "Valkyrie": ChampionDefinition(
        opener=["A2", "A1", "A3"],
        priority=["A2", "A1", "A3"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Spear of Glory", damage_factor=0.95),
            "A2": SkillDefinition(slot="A2", name="Stand Firm", cooldown=4, damage_factor=0.9, team_buffs={"counterattack": 2, "shield": 2}),
            "A3": SkillDefinition(slot="A3", name="Cyclone of Violence", cooldown=4, damage_factor=1.1),
        },
        notes="Counterattack e Shield la rendono preziosa nelle comp killable da Clan Boss.",
    ),
    "Venus": ChampionDefinition(
        opener=["A3", "A2", "A1"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Venomous Whip", damage_factor=0.82, boss_debuffs={"poison": 2}),
            "A2": SkillDefinition(slot="A2", name="Fell Beast", cooldown=4, damage_factor=1.0, boss_debuffs={"hp_burn": 2}),
            "A3": SkillDefinition(slot="A3", name="Love Tap", cooldown=4, damage_factor=1.0, boss_debuffs={"decrease_defense": 2, "weaken": 2}),
        },
        notes="Offre Decrease DEF, Weaken, HP Burn e poison nello stesso slot.",
    ),
    "Riho Bonespear": ChampionDefinition(
        opener=["A2", "A3", "A1"],
        priority=["A2", "A3", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Absorption", damage_factor=0.9, direct_heal_allies=0.05),
            "A2": SkillDefinition(
                slot="A2",
                name="Pressure Points",
                cooldown=3,
                damage_factor=1.05,
                boss_debuffs={"hp_burn": 2, "decrease_defense": 2, "weaken": 2, "decrease_attack": 2},
            ),
            "A3": SkillDefinition(slot="A3", name="Perfect Body", cooldown=3, damage_factor=0.0, team_buffs={"block_debuffs": 2}, direct_heal_allies=0.35),
        },
        passive="cleanse_on_turn",
        notes="Cleanse, Block Debuffs e pacchetto debuff molto ricco per Clan Boss.",
    ),
    "Jintoro": ChampionDefinition(
        opener=["A3", "A2", "A1"],
        priority=["A3", "A2", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Soul Drinker", damage_factor=1.05),
            "A2": SkillDefinition(slot="A2", name="Blood Freeze", cooldown=3, damage_factor=1.35),
            "A3": SkillDefinition(slot="A3", name="Oni's Rage", cooldown=3, damage_factor=1.6, boss_debuffs={"decrease_defense": 2, "weaken": 2}),
        },
        notes="Single-target DPS di fascia alta con Decrease DEF + Weaken nel kit.",
    ),
    "Teodor the Savant": ChampionDefinition(
        opener=["A2", "A3", "A1"],
        priority=["A2", "A3", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Decaying Velocity", damage_factor=0.88),
            "A2": SkillDefinition(
                slot="A2",
                name="Pandemic",
                cooldown=3,
                damage_factor=0.0,
                team_buffs={"increase_speed": 2},
                boss_debuffs={"poison": 3, "poison_sensitivity": 2},
            ),
            "A3": SkillDefinition(slot="A3", name="Mass Expiry", cooldown=4, damage_factor=0.0, boss_debuffs={"weaken": 2}),
        },
        notes="Porta Increase Speed, Poison Sensitivity e poison pressure molto utili sul Clan Boss.",
    ),
    "Michinaki": ChampionDefinition(
        opener=["A3", "A2", "A1"],
        priority=["A2", "A3", "A1"],
        skills={
            "A1": SkillDefinition(slot="A1", name="Burning Bonds", damage_factor=0.92, boss_debuffs={"hp_burn": 2}),
            "A2": SkillDefinition(slot="A2", name="Dire Whorl", cooldown=3, damage_factor=1.05, boss_debuffs={"decrease_defense": 2, "decrease_attack": 2}),
            "A3": SkillDefinition(slot="A3", name="Doubled Degeneracy", cooldown=4, damage_factor=1.15),
        },
        notes="Difesa, debuff e HP Burn in uno slot molto flessibile per Clan Boss.",
    ),
}


SET_BONUS_RULES: Dict[str, Dict[str, Any]] = {
    "Attack Speed": {"pieces": 2, "stats": {"spd_pct": 12.0}},
    "Accuracy": {"pieces": 2, "stats": {"acc": 40.0}},
    "Accuracy And Speed": {"pieces": 2, "stats": {"acc": 40.0, "spd_pct": 5.0}},
    "HP And Heal": {"pieces": 2, "stats": {"hp_pct": 15.0}, "heal_each_turn_pct": 0.03},
    "HP And Defence": {"pieces": 2, "stats": {"hp_pct": 10.0, "def_pct": 10.0}},
    "Attack Power And Ignore Defense": {"pieces": 2, "stats": {"atk_pct": 15.0}},
    "Shield And Speed": {"pieces": 2, "stats": {"spd_pct": 12.0}},
    "Shield And HP": {"pieces": 2, "stats": {"hp_pct": 15.0}},
    "Shield And Attack Power": {"pieces": 2, "stats": {"atk_pct": 15.0}},
    "Shield And Critical Chance": {"pieces": 2, "stats": {"crit_rate": 12.0}},
}


def available_clan_boss_levels() -> List[Dict[str, str]]:
    return [{"key": level.key, "label": level.label} for level in CLAN_BOSS_LEVELS.values()]


def available_clan_boss_affinities() -> List[Dict[str, str]]:
    return [
        {"key": "void", "label": "Void"},
        {"key": "magic", "label": "Magic"},
        {"key": "force", "label": "Force"},
        {"key": "spirit", "label": "Spirit"},
    ]


def simulate_best_clan_boss_team(
    difficulty: str = "ultra_nightmare",
    affinity: str = "void",
    turns: int = 24,
    option_index: int = 0,
    damage_scale: float = 1.0,
    max_options: int = 6,
    account: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    account_data = account or load_account()
    options = build_recommendations(account_data, "demon_lord_unm")
    if not options:
        raise ValueError("Nessun team Clan Boss disponibile da simulare.")
    if option_index > 0:
        if option_index < 0 or option_index >= len(options):
            raise ValueError(f"Option index fuori range: {option_index}")
        return simulate_team_recommendation(
            options[option_index],
            account_data,
            difficulty=difficulty,
            affinity=affinity,
            turns=turns,
            damage_scale=damage_scale,
        )

    best_payload: Optional[Dict[str, Any]] = None
    for option in options[:max_options]:
        payload = simulate_team_recommendation(
            option,
            account_data,
            difficulty=difficulty,
            affinity=affinity,
            turns=turns,
            damage_scale=damage_scale,
        )
        if best_payload is None:
            best_payload = payload
            continue
        current_score = survival_priority_score(best_payload["summary"], best_payload.get("members"))
        candidate_score = survival_priority_score(payload["summary"], payload.get("members"))
        if candidate_score > current_score:
            best_payload = payload

    if best_payload is None:
        raise ValueError("Simulazione Clan Boss non disponibile.")
    return best_payload


def recommend_clan_boss_options(
    difficulty: str = "ultra_nightmare",
    affinity: str = "void",
    turns: int = 300,
    account: Optional[Dict[str, Any]] = None,
    max_options: int = 6,
    damage_scale: float = 1.0,
) -> List[Dict[str, Any]]:
    account_data = account or load_account()
    options = build_recommendations(account_data, "demon_lord_unm")[:max_options]
    ranked: List[tuple[tuple[int, int, int, int, float, int, float], Dict[str, Any]]] = []

    for option in options:
        payload = simulate_team_recommendation(
            option,
            account_data,
            difficulty=difficulty,
            affinity=affinity,
            turns=turns,
            damage_scale=damage_scale,
        )
        serialized = serialize_team(option)
        simulated_summary = payload["summary"]
        readiness = assess_clan_boss_team_readiness(
            option,
            payload.get("members"),
            difficulty,
            affinity=affinity,
            summary=simulated_summary,
        )
        history_feedback = assess_contextual_history(option.team_name, difficulty, affinity)
        serialized["warnings"] = merge_unique_warnings(
            serialized.get("warnings"),
            simulated_summary.get("warnings"),
            readiness.get("warnings"),
            history_feedback.get("warnings"),
        )
        serialized["simulated_summary"] = simulated_summary
        serialized["simulated_context"] = {
            "difficulty": difficulty,
            "affinity": affinity,
            "turns": turns,
        }
        serialized["readiness"] = readiness
        serialized["history_feedback"] = history_feedback
        serialized["advisory"] = assess_clan_boss_team_advisory(
            simulated_summary,
            difficulty,
            affinity,
            readiness_priority=readiness.get("priority_ok", 1),
            history_priority=history_feedback.get("priority_ok", 1),
        )
        ranked.append(
            (
                clan_boss_recommendation_score(
                    simulated_summary,
                    serialized.get("members"),
                    option.score,
                    history_priority=history_feedback.get("priority_ok", 1),
                    readiness_priority=readiness.get("priority_ok", 1),
                ),
                serialized,
            )
        )

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked]


def simulate_team_recommendation(
    team: TeamRecommendation,
    account: Dict[str, Any],
    difficulty: str = "ultra_nightmare",
    affinity: str = "void",
    turns: int = 24,
    damage_scale: float = 1.0,
) -> Dict[str, Any]:
    if difficulty not in CLAN_BOSS_LEVELS:
        raise KeyError(f"Unsupported Clan Boss difficulty: {difficulty}")
    if affinity not in {"void", "magic", "force", "spirit"}:
        raise KeyError(f"Unsupported Clan Boss affinity: {affinity}")

    champions_by_id = {
        string_value(champion.get("champ_id")): champion
        for champion in list_value(account.get("champions"))
    }
    bonuses = list_value(account.get("account_bonuses"))
    units = [build_unit_state(member, champions_by_id.get(member.champ_id, {}), bonuses) for member in team.members]
    level = CLAN_BOSS_LEVELS[difficulty]
    boss = {
        "level": level,
        "affinity": affinity,
        "turn_meter": 0.0,
        "turn_count": 0,
        "pattern_index": 0,
        "debuffs": {},
        "estimated_damage_taken": 0.0,
        "geomancer_active": any(unit.name == "Geomancer" for unit in units),
        "window_actions": [],
        "cycle_events": [],
    }
    timeline: List[str] = []
    coverage = {
        "unkillable_hits": 0,
        "counterattack_hits": 0,
        "decrease_attack_hits": 0,
        "decrease_defense_turns": 0,
        "weaken_turns": 0,
        "hp_burn_turns": 0,
        "poison_turns": 0,
        "stun_hits": 0,
        "aoe1_total": 0,
        "aoe2_total": 0,
        "stun_total": 0,
        "aoe1_protected": 0,
        "aoe2_protected": 0,
        "stun_safe": 0,
        "stun_unkillable": 0,
        "stun_block_debuffs": 0,
    }

    while boss["turn_count"] < turns and any(unit.alive for unit in units):
        next_actor = pick_next_actor(units, level.speed, boss["turn_meter"])
        advance_time(units, boss, next_actor["time"])
        if next_actor["actor"] == "boss":
            execute_boss_turn(boss, units, affinity, timeline, coverage)
        else:
            execute_unit_turn(next_actor["actor"], boss, units, timeline, coverage)

    summary = build_summary(team, level, affinity, units, boss, coverage, turns, damage_scale)
    return {
        "boss": {
            "difficulty": level.key,
            "difficulty_label": level.label,
            "affinity": affinity,
            "speed": level.speed,
            "required_acc": level.required_acc,
        },
        "team_name": team.team_name,
        "team_score": team.score,
        "members": [
            {
                "name": unit.name,
                "affinity": unit.affinity,
                "build_key": member_plan.build_key,
                "build_label": BUILD_PROFILES[member_plan.build_key].label,
                "build_notes": BUILD_PROFILES[member_plan.build_key].notes,
                "target_stats": BUILD_PROFILES[member_plan.build_key].target_stats,
                "reason": member_plan.reason,
                "estimated_speed": round(unit.speed, 1),
                "estimated_hp": round(unit.max_hp, 1),
                "estimated_defense": round(unit.defense, 1),
                "estimated_accuracy": round(unit.accuracy, 1),
                "alive": unit.alive,
                "damage_index": round(unit.estimated_damage, 1),
                "damage_estimate": round(unit.estimated_damage * damage_scale, 1),
                "turns_taken": unit.turns_taken,
                "gear_plan": member_plan.gear_plan,
                "swap_count": count_required_swaps(member_plan.gear_plan),
            }
            for unit, member_plan in zip(units, team.members)
        ],
        "summary": summary,
        "cycle_debug": summary.get("cycle_debug", []),
        "timeline": timeline,
        "alive_count": len([unit for unit in units if unit.alive]),
    }


def build_unit_state(member: Any, champion: Dict[str, Any], bonuses: Sequence[Dict[str, Any]]) -> UnitState:
    estimated_stats = estimate_total_stats(champion, member.gear_plan, bonuses)
    definition = CHAMPION_DEFINITIONS.get(member.name, GENERIC_DEFINITION)
    return UnitState(
        champ_id=member.champ_id,
        name=member.name,
        affinity=string_value(champion.get("affinity")) or "void",
        speed=estimated_stats["spd"],
        hp=estimated_stats["hp"],
        max_hp=estimated_stats["hp"],
        attack=estimated_stats["atk"],
        defense=estimated_stats["def"],
        accuracy=estimated_stats["acc"],
        crit_rate=estimated_stats["crit_rate"],
        crit_damage=estimated_stats["crit_dmg"],
        definition=definition,
        cooldowns={slot: 0 for slot in definition.skills},
        turn_meter=estimated_stats["spd"] * 2.0,
        set_heal_each_turn_pct=float_value(estimated_stats.get("set_heal_each_turn_pct")),
    )


def simulate_clan_boss_affinity_matrix(
    difficulty: str = "ultra_nightmare",
    turns: int = 24,
    account: Optional[Dict[str, Any]] = None,
    max_options: int = 6,
    damage_scale: float = 1.0,
) -> Dict[str, Any]:
    account_data = account or load_account()
    options = build_recommendations(account_data, "demon_lord_unm")[:max_options]
    if not options:
        raise ValueError("Nessun team Clan Boss disponibile da simulare.")

    rows: List[Dict[str, Any]] = []
    for affinity_item in available_clan_boss_affinities():
        affinity = affinity_item["key"]
        best_payload: Optional[Dict[str, Any]] = None
        best_option: Optional[TeamRecommendation] = None
        for option in options:
            payload = simulate_team_recommendation(
                option,
                account_data,
                difficulty=difficulty,
                affinity=affinity,
                turns=turns,
                damage_scale=damage_scale,
            )
            if best_payload is None:
                best_payload = payload
                best_option = option
                continue
            current_score = survival_priority_score(best_payload["summary"], best_payload.get("members"))
            candidate_score = survival_priority_score(payload["summary"], payload.get("members"))
            if candidate_score > current_score:
                best_payload = payload
                best_option = option

        if best_payload is None or best_option is None:
            continue

        rows.append(
            {
                "affinity": affinity,
                "label": affinity_item["label"],
                "team_name": best_payload["team_name"],
                "boss_turns_simulated": best_payload["summary"]["boss_turns_simulated"],
                "survival_score": best_payload["summary"]["survival_score"],
                "damage_index": best_payload["summary"]["damage_index"],
                "estimated_team_damage": best_payload["summary"]["estimated_team_damage"],
                "damage_scale": best_payload["summary"]["damage_scale"],
                "alive_count": best_payload["summary"]["alive_count"],
                "warnings": best_payload["summary"]["warnings"],
                "members": [member["name"] for member in best_payload["members"]],
                "fifth_member": best_option.members[4].name if len(best_option.members) >= 5 else "",
            }
        )

    return {
        "difficulty": difficulty,
        "turns": turns,
        "rows": rows,
    }


def build_clan_boss_survival_plan(
    difficulty: str = "ultra_nightmare",
    turns: int = 300,
    account: Optional[Dict[str, Any]] = None,
    max_options: int = 6,
    damage_scale: float = 1.0,
) -> Dict[str, Any]:
    account_data = account or load_account()
    rows: List[Dict[str, Any]] = []
    champion_frequency: Dict[str, int] = {}

    for affinity_item in available_clan_boss_affinities():
        affinity = affinity_item["key"]
        payload = simulate_best_clan_boss_team(
            difficulty=difficulty,
            affinity=affinity,
            turns=turns,
            option_index=0,
            damage_scale=damage_scale,
            max_options=max_options,
            account=account_data,
        )
        members = payload.get("members", [])
        member_names = [string_value(member.get("name")) for member in members if string_value(member.get("name"))]
        for name in member_names:
            champion_frequency[name] = champion_frequency.get(name, 0) + 1
        rows.append(
            {
                "affinity": affinity,
                "label": affinity_item["label"],
                "team_name": payload.get("team_name"),
                "members": members,
                "member_names": member_names,
                "summary": payload.get("summary", {}),
                "swap_count": sum(int(member.get("swap_count", 0)) for member in members),
                "swap_items": collect_swap_items(members),
            }
        )

    shared_core = sorted(
        [name for name, count in champion_frequency.items() if count == len(rows)],
        key=lambda name: (-champion_frequency[name], name),
    )
    flex_picks = sorted(
        [name for name, count in champion_frequency.items() if 0 < count < len(rows)],
        key=lambda name: (-champion_frequency[name], name),
    )
    return {
        "difficulty": difficulty,
        "turns": turns,
        "rows": rows,
        "shared_core": shared_core,
        "flex_picks": flex_picks,
    }


def estimate_total_stats(
    champion: Dict[str, Any],
    gear_plan: Sequence[Dict[str, Any]],
    bonuses: Sequence[Dict[str, Any]],
) -> Dict[str, float]:
    base = mapping_value(champion.get("base_stats"))
    base_total = {
        "hp": float_value(base.get("hp")) * 240.0,
        "atk": float_value(base.get("atk")) * 9.0,
        "def": float_value(base.get("def")) * 8.0,
        "spd": float_value(base.get("spd")) or 100.0,
        "acc": float_value(base.get("acc")),
        "res": float_value(base.get("res")),
        "crit_rate": float_value(base.get("crit_rate")) or 15.0,
        "crit_dmg": float_value(base.get("crit_dmg")) or 50.0,
    }
    total = dict(base_total)
    for item in gear_plan:
        apply_stat_map(total, mapping_value(item.get("main_stat")))
        for substat in list_value(item.get("substats")):
            apply_stat_map(total, mapping_value(substat))
    apply_set_bonus_rules(total, base_total, gear_plan)
    affinity = string_value(champion.get("affinity")) or "void"
    for bonus in bonuses:
        if not bool_value(bonus.get("active"), True):
            continue
        target = string_value(bonus.get("target")) or "all"
        if target not in {"all", affinity}:
            continue
        stat_key = normalize_stat_key(string_value(bonus.get("stat")))
        if stat_key == "spd":
            total["spd"] += float_value(bonus.get("value"))
        elif stat_key in {"hp", "atk", "def"}:
            total[stat_key] += total[stat_key] * float_value(bonus.get("value")) / 100.0
        elif stat_key in total:
            total[stat_key] += float_value(bonus.get("value"))
    total["spd"] = max(total["spd"], 90.0)
    total["crit_rate"] = min(max(total["crit_rate"], 15.0), 100.0)
    total["crit_dmg"] = max(total["crit_dmg"], 50.0)
    return total


def apply_set_bonus_rules(total: Dict[str, float], base_total: Dict[str, float], gear_plan: Sequence[Dict[str, Any]]) -> None:
    counts: Dict[str, int] = {}
    total["set_heal_each_turn_pct"] = 0.0
    for item in gear_plan:
        set_name = string_value(item.get("set_name")).strip()
        if not set_name:
            continue
        counts[set_name] = counts.get(set_name, 0) + 1
    for set_name, pieces in counts.items():
        rule = SET_BONUS_RULES.get(set_name)
        if not rule:
            continue
        required = int_value(rule.get("pieces")) or 1
        completed = pieces // required
        if completed <= 0:
            continue
        for stat_key, value in mapping_value(rule.get("stats")).items():
            normalized_key = normalize_stat_key(string_value(stat_key))
            amount = float_value(value) * completed
            if normalized_key == "spd_pct":
                total["spd"] += base_total["spd"] * amount / 100.0
            elif normalized_key == "hp_pct":
                total["hp"] += base_total["hp"] * amount / 100.0
            elif normalized_key == "atk_pct":
                total["atk"] += base_total["atk"] * amount / 100.0
            elif normalized_key == "def_pct":
                total["def"] += base_total["def"] * amount / 100.0
            elif normalized_key in total:
                total[normalized_key] += amount
        total["set_heal_each_turn_pct"] += float_value(rule.get("heal_each_turn_pct")) * completed


def apply_stat_map(total: Dict[str, float], stat: Dict[str, Any]) -> None:
    if not stat:
        return
    stat_type = normalize_stat_key(string_value(stat.get("type")))
    value = normalize_stat_amount(stat_type, float_value(stat.get("value")))
    if stat_type == "spd":
        total["spd"] += value
    elif stat_type == "acc":
        total["acc"] += value
    elif stat_type == "res":
        total["res"] += value
    elif stat_type == "crit_rate":
        total["crit_rate"] += value
    elif stat_type == "crit_dmg":
        total["crit_dmg"] += value
    elif stat_type == "hp":
        total["hp"] += value
    elif stat_type == "atk":
        total["atk"] += value
    elif stat_type == "def":
        total["def"] += value
    elif stat_type == "hp_pct":
        total["hp"] += total["hp"] * value / 100.0
    elif stat_type == "atk_pct":
        total["atk"] += total["atk"] * value / 100.0
    elif stat_type == "def_pct":
        total["def"] += total["def"] * value / 100.0


def pick_next_actor(units: Sequence[UnitState], boss_speed: float, boss_turn_meter: float) -> Dict[str, Any]:
    times: List[tuple[float, Any]] = []
    if boss_turn_meter < TURN_METER_MAX:
        times.append(((TURN_METER_MAX - boss_turn_meter) / boss_speed, "boss"))
    else:
        times.append((0.0, "boss"))
    for unit in units:
        if not unit.alive:
            continue
        effective_speed = unit.speed * (1.3 if has_status(unit.buffs, "increase_speed") else 1.0)
        if unit.turn_meter >= TURN_METER_MAX:
            times.append((0.0, unit))
        else:
            times.append(((TURN_METER_MAX - unit.turn_meter) / effective_speed, unit))
    time_needed, actor = min(times, key=lambda item: item[0])
    return {"time": max(time_needed, 0.0), "actor": actor}


def advance_time(units: Sequence[UnitState], boss: Dict[str, Any], time_needed: float) -> None:
    if time_needed <= 0:
        return
    boss["turn_meter"] += boss["level"].speed * time_needed
    for unit in units:
        if not unit.alive:
            continue
        effective_speed = unit.speed * (1.3 if has_status(unit.buffs, "increase_speed") else 1.0)
        unit.turn_meter += effective_speed * time_needed


def execute_unit_turn(unit: UnitState, boss: Dict[str, Any], units: Sequence[UnitState], timeline: List[str], coverage: Dict[str, int]) -> None:
    decrement_statuses(unit.buffs)
    decrement_statuses(unit.debuffs)
    decrement_cooldowns(unit.cooldowns)
    apply_passive_start_of_turn(unit, units, timeline)
    if unit.set_heal_each_turn_pct > 0:
        unit.hp = min(unit.max_hp, unit.hp + unit.max_hp * unit.set_heal_each_turn_pct)
        timeline.append(f"{unit.name} recupera {int(unit.set_heal_each_turn_pct * 100)}% HP dal bonus set.")
    slot = choose_skill(unit)
    definition = unit.definition.skills.get(slot, GENERIC_DEFINITION.skills["A1"])
    unit.turns_taken += 1
    unit.turn_meter -= TURN_METER_MAX
    damage = estimate_skill_damage(unit, definition, boss["debuffs"], boss["affinity"])
    if damage > 0:
        boss["estimated_damage_taken"] += damage
        unit.estimated_damage += damage
    apply_skill_effects(unit, definition, boss, units, timeline)
    unit.cooldowns[slot] = definition.cooldown
    track_boss_debuff_coverage(boss["debuffs"], coverage)
    boss.setdefault("window_actions", []).append(
        {
            "name": unit.name,
            "slot": slot,
            "skill": definition.name,
        }
    )
    timeline.append(f"{unit.name} usa {definition.name} ({slot}) e infligge {round(damage, 1)} danni stimati.")


def choose_skill(unit: UnitState) -> str:
    if unit.turns_taken < len(unit.definition.opener):
        planned_slot = unit.definition.opener[unit.turns_taken]
        if unit.cooldowns.get(planned_slot, 0) == 0:
            return planned_slot
    for slot in unit.definition.priority:
        if unit.cooldowns.get(slot, 0) == 0:
            return slot
    return "A1"


def apply_passive_start_of_turn(unit: UnitState, units: Sequence[UnitState], timeline: List[str]) -> None:
    if unit.definition.passive in {"cleanse_one_each_turn", "cleanse_on_turn"}:
        for ally in units:
            if not ally.alive or not ally.debuffs:
                continue
            debuff_name = next(iter(ally.debuffs))
            ally.debuffs.pop(debuff_name, None)
            timeline.append(f"{unit.name} rimuove {friendly_status(debuff_name)} dal team a inizio turno.")
            break
        heal_team(units, 0.07, source_name=unit.name, timeline=timeline)


def apply_skill_effects(
    unit: UnitState,
    definition: SkillDefinition,
    boss: Dict[str, Any],
    units: Sequence[UnitState],
    timeline: List[str],
) -> None:
    for buff_name, duration in definition.team_buffs.items():
        for ally in units:
            if ally.alive:
                ally.buffs[buff_name] = max(ally.buffs.get(buff_name, 0), duration)
        timeline.append(f"{unit.name} applica {friendly_status(buff_name)} al team per {duration} turni.")
    for buff_name, duration in definition.self_buffs.items():
        unit.buffs[buff_name] = max(unit.buffs.get(buff_name, 0), duration)
    for debuff_name, duration in definition.boss_debuffs.items():
        if debuff_lands(unit, boss, debuff_name):
            boss["debuffs"][debuff_name] = max(int(boss["debuffs"].get(debuff_name, 0)), duration)
            timeline.append(f"{unit.name} applica {friendly_status(debuff_name)} sul boss per {duration} turni.")
        elif affinity_relationship(unit.affinity, boss["affinity"]) == "weak":
            unit.weak_hits += 1
            timeline.append(f"{unit.name} subisce weak hit tentando {friendly_status(debuff_name)} contro boss {boss['affinity']}.")
    if definition.cooldown_reduction_allies:
        for ally in units:
            if ally.champ_id == unit.champ_id or not ally.alive:
                continue
            for slot, current in list(ally.cooldowns.items()):
                ally.cooldowns[slot] = max(current - definition.cooldown_reduction_allies, 0)
        timeline.append(f"{unit.name} riduce i cooldown degli alleati di {definition.cooldown_reduction_allies}.")
    if definition.turn_meter_fill_allies:
        for ally in units:
            if ally.alive:
                ally.turn_meter += TURN_METER_MAX * definition.turn_meter_fill_allies
        timeline.append(f"{unit.name} riempie il turn meter del team del {int(definition.turn_meter_fill_allies * 100)}%.")
    if definition.direct_heal_allies:
        heal_team(units, definition.direct_heal_allies, unit.name, timeline)


def execute_boss_turn(
    boss: Dict[str, Any],
    units: Sequence[UnitState],
    affinity: str,
    timeline: List[str],
    coverage: Dict[str, int],
) -> None:
    decrement_statuses(boss["debuffs"])
    boss["turn_count"] += 1
    boss["turn_meter"] -= TURN_METER_MAX
    attack_pattern = ["AoE1", "AoE2", "Stun"]
    attack_name = attack_pattern[boss["pattern_index"] % len(attack_pattern)]
    boss["pattern_index"] += 1
    living = [unit for unit in units if unit.alive]
    if not living:
        return
    timeline.append(f"Boss {boss['level'].label} {affinity} esegue {attack_name}.")
    actions_before_hit = [
        {
            "name": string_value(item.get("name")),
            "slot": string_value(item.get("slot")),
            "skill": string_value(item.get("skill")),
        }
        for item in list_value(boss.get("window_actions"))
    ]
    boss["window_actions"] = []
    if attack_name == "Stun":
        coverage["stun_total"] += 1
        target = select_stun_target(living, affinity)
        coverage["stun_hits"] += 1
        target_had_unkillable = has_status(target.buffs, "unkillable")
        target_had_block_debuffs = has_status(target.buffs, "block_debuffs")
        apply_boss_hit(target, boss, attack_name, affinity, timeline)
        if target_had_unkillable:
            coverage["stun_unkillable"] += 1
        if target_had_block_debuffs:
            coverage["stun_block_debuffs"] += 1
        if target.alive and (target_had_unkillable or target_had_block_debuffs):
            coverage["stun_safe"] += 1
        if target.alive and not has_status(target.buffs, "block_debuffs"):
            target.debuffs["stun"] = 1
            apply_affinity_side_effect(target, affinity, timeline)
        boss.setdefault("cycle_events", []).append(
            {
                "boss_turn": int(boss["turn_count"]),
                "attack": attack_name,
                "actions_before_hit": actions_before_hit,
                "target": target.name,
                "target_alive": bool(target.alive),
                "target_had_unkillable": bool(target_had_unkillable),
                "target_had_block_debuffs": bool(target_had_block_debuffs),
                "safe": bool(target.alive and (target_had_unkillable or target_had_block_debuffs)),
            }
        )
    else:
        coverage_key = "aoe1_protected" if attack_name == "AoE1" else "aoe2_protected"
        total_key = "aoe1_total" if attack_name == "AoE1" else "aoe2_total"
        coverage[total_key] += 1
        protected_hit = all(has_status(unit.buffs, "unkillable") for unit in living)
        if protected_hit:
            coverage["unkillable_hits"] += 1
            coverage[coverage_key] += 1
        for unit in list(living):
            apply_boss_hit(unit, boss, attack_name, affinity, timeline)
            if unit.alive and not has_status(unit.buffs, "block_debuffs"):
                apply_affinity_side_effect(unit, affinity, timeline)
        for unit in [ally for ally in units if ally.alive and has_status(ally.buffs, "counterattack")]:
            counter_damage = estimate_skill_damage(unit, unit.definition.skills.get("A1", GENERIC_DEFINITION.skills["A1"]), boss["debuffs"], affinity) * 0.9
            unit.estimated_damage += counter_damage
            boss["estimated_damage_taken"] += counter_damage
            coverage["counterattack_hits"] += 1
            timeline.append(f"{unit.name} contrattacca e infligge {round(counter_damage, 1)} danni stimati.")
        boss.setdefault("cycle_events", []).append(
            {
                "boss_turn": int(boss["turn_count"]),
                "attack": attack_name,
                "actions_before_hit": actions_before_hit,
                "all_protected": bool(protected_hit),
                "alive_before_hit": len(living),
            }
        )
    if int(boss["debuffs"].get("decrease_attack", 0)) > 0:
        coverage["decrease_attack_hits"] += 1
    track_boss_debuff_coverage(boss["debuffs"], coverage)


def apply_boss_hit(unit: UnitState, boss: Dict[str, Any], attack_name: str, affinity: str, timeline: List[str]) -> None:
    if not unit.alive:
        return
    base_damage = boss["level"].base_damage
    if attack_name == "AoE2":
        base_damage *= 1.22
    if attack_name == "Stun":
        base_damage *= 1.38
    if int(boss["debuffs"].get("decrease_attack", 0)) > 0:
        base_damage *= 0.72
    if has_status(unit.buffs, "increase_defense"):
        base_damage *= 0.82
    if has_status(unit.buffs, "shield"):
        base_damage *= 0.9
    relationship = affinity_relationship(affinity, unit.affinity)
    if relationship == "strong":
        base_damage *= 1.12
    elif relationship == "weak":
        base_damage *= 0.88
    if int(boss["debuffs"].get("hp_burn", 0)) > 0 and boss.get("geomancer_active"):
        reflected = base_damage * 0.28
        boss["estimated_damage_taken"] += reflected
        timeline.append(f"Geomancer converte HP Burn in {round(reflected, 1)} danni riflessi.")
    mitigated = base_damage * (2500.0 / (2500.0 + max(unit.defense, 1.0)))
    if has_status(unit.buffs, "unkillable"):
        unit.hp = max(unit.hp - mitigated, 1.0)
    else:
        unit.hp -= mitigated
    if unit.hp <= 0:
        unit.hp = 0
        unit.alive = False
        timeline.append(f"{unit.name} cade sul colpo {attack_name}.")
    else:
        timeline.append(f"{unit.name} subisce {round(mitigated, 1)} danni stimati da {attack_name}.")


def select_stun_target(units: Sequence[UnitState], affinity: str) -> UnitState:
    def score(unit: UnitState) -> float:
        hp_ratio = unit.hp / max(unit.max_hp, 1.0)
        affinity_bias = {"strong": -0.25, "neutral": 0.0, "weak": 0.35}[affinity_relationship(affinity, unit.affinity)]
        support_bias = -0.1 if unit.name in {"Maneater", "Pain Keeper", "Doompriest"} else 0.0
        return (1.0 - hp_ratio) + affinity_bias + support_bias

    return max(units, key=score)


def apply_affinity_side_effect(unit: UnitState, affinity: str, timeline: List[str]) -> None:
    effect_map = {
        "spirit": ("decrease_speed", 2),
        "force": ("decrease_attack", 2),
        "magic": ("decrease_accuracy", 2),
    }
    effect = effect_map.get(affinity)
    if not effect:
        return
    name, duration = effect
    unit.debuffs[name] = max(unit.debuffs.get(name, 0), duration)
    timeline.append(f"{unit.name} riceve {friendly_status(name)} per {duration} turni dal boss {affinity}.")


def estimate_skill_damage(unit: UnitState, skill: SkillDefinition, boss_debuffs: Dict[str, int], boss_affinity: str) -> float:
    if skill.damage_factor <= 0:
        return 0.0
    offense = unit.attack + (unit.defense * 0.32)
    multiplier = skill.damage_factor
    if int(boss_debuffs.get("weaken", 0)) > 0:
        multiplier *= 1.1
    if int(boss_debuffs.get("decrease_defense", 0)) > 0:
        multiplier *= 1.15
    if int(boss_debuffs.get("poison_sensitivity", 0)) > 0 and unit.name == "Frozen Banshee":
        multiplier *= 1.2
    relationship = affinity_relationship(unit.affinity, boss_affinity)
    if relationship == "strong":
        multiplier *= 1.15
        unit.strong_hits += 1
    elif relationship == "weak":
        multiplier *= 0.72
    crit = 1.0 + min(unit.crit_rate, 100.0) / 100.0 * (unit.crit_damage / 100.0)
    debuff_bonus = 0.0
    if int(boss_debuffs.get("poison", 0)) > 0:
        debuff_bonus += 2600.0
    if int(boss_debuffs.get("hp_burn", 0)) > 0:
        debuff_bonus += 1500.0
    return offense * multiplier * crit * 0.18 + debuff_bonus


def debuff_lands(unit: UnitState, boss: Dict[str, Any], debuff_name: str) -> bool:
    acc_factor = min(unit.accuracy / max(boss["level"].required_acc, 1.0), 1.25)
    if debuff_name in {"poison", "hp_burn", "decrease_attack", "decrease_defense", "weaken", "poison_sensitivity", "leech"}:
        affinity_penalty = 0.65 if affinity_relationship(unit.affinity, boss["affinity"]) == "weak" else 1.0
        return acc_factor * affinity_penalty >= 0.55
    return True


def build_summary(
    team: TeamRecommendation,
    level: ClanBossLevel,
    affinity: str,
    units: Sequence[UnitState],
    boss: Dict[str, Any],
    coverage: Dict[str, int],
    turns: int,
    damage_scale: float,
) -> Dict[str, Any]:
    damage_index = round(sum(unit.estimated_damage for unit in units), 1)
    total_damage = round(damage_index * damage_scale, 1)
    warnings: List[str] = []
    team_has_unkillable_source = any(
        any("unkillable" in skill.team_buffs for skill in unit.definition.skills.values())
        for unit in units
    )
    if coverage["decrease_attack_hits"] < max(1, turns // 4):
        warnings.append("Uptime di Decrease ATK bassa: il team rischia di essere troppo fragile nei tier alti.")
    if team_has_unkillable_source and level.key in {"nightmare", "ultra_nightmare"}:
        aoe1_total = int(coverage["aoe1_total"])
        aoe2_total = int(coverage["aoe2_total"])
        stun_total = int(coverage["stun_total"])
        aoe1_protected = int(coverage["aoe1_protected"])
        aoe2_protected = int(coverage["aoe2_protected"])
        stun_safe = int(coverage["stun_safe"])
        if aoe1_protected < aoe1_total or aoe2_protected < aoe2_total or stun_safe < stun_total:
            warnings.append(
                "Copertura Unkillable incompleta nel ciclo boss: "
                f"AoE1 {aoe1_protected}/{aoe1_total}, "
                f"AoE2 {aoe2_protected}/{aoe2_total}, "
                f"Stun sicuri {stun_safe}/{stun_total}."
            )
    if affinity != "void":
        weak_names = [unit.name for unit in units if affinity_relationship(unit.affinity, affinity) == "weak"]
        if weak_names:
            warnings.append(f"Affinity pressure su {affinity}: possibili weak hit per {', '.join(weak_names)}.")
    if not any(unit.alive for unit in units):
        warnings.append("Il team muore prima di chiudere la finestra di simulazione.")
    return {
        "estimated_team_damage": total_damage,
        "damage_index": damage_index,
        "damage_scale": damage_scale,
        "boss_turns_simulated": boss["turn_count"],
        "survival_score": round((boss["turn_count"] * 1000) + len([unit for unit in units if unit.alive]), 1),
        "alive_count": len([unit for unit in units if unit.alive]),
        "coverage": {
            "decrease_attack_hits": coverage["decrease_attack_hits"],
            "counterattack_hits": coverage["counterattack_hits"],
            "decrease_defense_turns": coverage["decrease_defense_turns"],
            "weaken_turns": coverage["weaken_turns"],
            "hp_burn_turns": coverage["hp_burn_turns"],
            "poison_turns": coverage["poison_turns"],
            "aoe1_total": coverage["aoe1_total"],
            "aoe2_total": coverage["aoe2_total"],
            "stun_total": coverage["stun_total"],
            "aoe1_protected": coverage["aoe1_protected"],
            "aoe2_protected": coverage["aoe2_protected"],
            "stun_safe": coverage["stun_safe"],
            "stun_unkillable": coverage["stun_unkillable"],
            "stun_block_debuffs": coverage["stun_block_debuffs"],
        },
        "warnings": warnings,
        "notes": [
            f"Pattern simulato: AoE1 -> AoE2 -> Stun su {turns} turni boss.",
            "I dati skill reali del dump non sono ancora completi: il motore usa profili noti per i champ CB principali e fallback coerenti per gli altri.",
        ],
        "cycle_debug": build_cycle_debug_preview(list_value(boss.get("cycle_events")), limit=9),
        "team_name": team.team_name,
        "difficulty": level.label,
        "affinity": affinity,
    }


def build_cycle_debug_preview(events: Sequence[Dict[str, Any]], limit: int = 9) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for event in list(events)[:limit]:
        attack = string_value(event.get("attack"))
        actions = [
            {
                "name": string_value(action.get("name")),
                "slot": string_value(action.get("slot")),
                "skill": string_value(action.get("skill")),
            }
            for action in list_value(event.get("actions_before_hit"))
            if string_value(action.get("name"))
        ]
        row = {
            "boss_turn": int_value(event.get("boss_turn")),
            "attack": attack,
            "actions_before_hit": actions,
        }
        if attack == "Stun":
            row["target"] = string_value(event.get("target"))
            row["safe"] = bool(event.get("safe"))
            row["target_had_unkillable"] = bool(event.get("target_had_unkillable"))
            row["target_had_block_debuffs"] = bool(event.get("target_had_block_debuffs"))
        else:
            row["all_protected"] = bool(event.get("all_protected"))
            row["alive_before_hit"] = int_value(event.get("alive_before_hit"))
        rows.append(row)
    return rows


def survival_priority_score(summary: Dict[str, Any], members: Optional[Sequence[Dict[str, Any]]] = None) -> tuple[int, int, int, int, int, float]:
    swap_count = sum(int(member.get("swap_count", 0)) for member in members or [])
    return (
        int(summary.get("boss_turns_simulated", 0)),
        int(summary.get("alive_count", 0)),
        int(dict(summary.get("coverage", {})).get("decrease_attack_hits", 0)),
        -len(list_value(summary.get("warnings"))),
        -swap_count,
        float(summary.get("estimated_team_damage", 0.0)),
    )


def clan_boss_recommendation_score(
    summary: Dict[str, Any],
    members: Optional[Sequence[Dict[str, Any]]] = None,
    base_team_score: float = 0.0,
    history_priority: int = 1,
    readiness_priority: int = 1,
) -> tuple[int, int, int, int, int, float, int, float]:
    swap_count = sum(int(member.get("swap_count", 0)) for member in members or [])
    return (
        int(history_priority),
        int(readiness_priority),
        int(summary.get("boss_turns_simulated", 0)),
        int(summary.get("alive_count", 0)),
        int(dict(summary.get("coverage", {})).get("decrease_attack_hits", 0)),
        -len(list_value(summary.get("warnings"))),
        float(summary.get("estimated_team_damage", 0.0)),
        -swap_count,
        float(base_team_score),
    )


def merge_unique_warnings(*warning_groups: Any) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for group in warning_groups:
        for warning in list_value(group):
            text = string_value(warning).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def assess_clan_boss_team_advisory(
    summary: Dict[str, Any],
    difficulty: str,
    affinity: str,
    readiness_priority: int = 1,
    history_priority: int = 1,
) -> Dict[str, Any]:
    warnings = list_value(summary.get("warnings"))
    boss_turns = int_value(summary.get("boss_turns_simulated"))
    alive_count = int_value(summary.get("alive_count"))
    is_high_tier = difficulty in {"nightmare", "ultra_nightmare"}
    fatal_fragility = any("Il team muore prima" in string_value(item) for item in warnings)
    low_attack_down = any("Uptime di Decrease ATK bassa" in string_value(item) for item in warnings)

    if history_priority <= 0 or readiness_priority <= 0:
        return {
            "level": "red",
            "label": "Rosso",
            "primary_key_ok": False,
            "message": "Non affidabile come prima key: richiede correzioni strutturali prima di essere consigliato.",
        }
    if is_high_tier and (fatal_fragility or boss_turns < 150 or (low_attack_down and alive_count <= 1)):
        return {
            "level": "red",
            "label": "Rosso",
            "primary_key_ok": False,
            "message": (
                f"Non consigliato come prima key su {difficulty} {affinity}: "
                "la simulazione lo vede troppo fragile o troppo corto."
            ),
        }
    if warnings:
        return {
            "level": "yellow",
            "label": "Giallo",
            "primary_key_ok": True,
            "message": "Usabile con cautela: controlla prima warning, affinity e lettura del ciclo boss.",
        }
    return {
        "level": "green",
        "label": "Verde",
        "primary_key_ok": True,
        "message": "Candidato pulito per la prima key: nessun warning strutturale forte rilevato.",
    }


def assess_clan_boss_team_readiness(
    team: TeamRecommendation,
    members: Optional[Sequence[Dict[str, Any]]],
    difficulty: str,
    affinity: str = "void",
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rows = list(members or [])
    speed_by_name = {
        string_value(member.get("name")): float_value(member.get("estimated_speed"))
        for member in rows
    }
    names = set(speed_by_name)
    warnings: List[str] = []
    priority_ok = 1

    # Unkillable comps are very sensitive to speed tune. If the estimated live speeds
    # are far from a plausible window, surface it as a warning only: the local dump can
    # lag behind the real in-game setup if the player changed gear manually.
    if {"Maneater", "Pain Keeper"} <= names:
        known_tune = assess_known_budget_maneater_tune(speed_by_name, difficulty, affinity)
        warnings.extend(known_tune["warnings"])
        if not known_tune["matched"]:
            priority_ok = 0

        coverage = mapping_value(summary.get("coverage")) if summary else {}
        aoe1_total = int_value(coverage.get("aoe1_total"))
        aoe2_total = int_value(coverage.get("aoe2_total"))
        stun_total = int_value(coverage.get("stun_total"))
        aoe1_protected = int_value(coverage.get("aoe1_protected"))
        aoe2_protected = int_value(coverage.get("aoe2_protected"))
        stun_safe = int_value(coverage.get("stun_safe"))
        if aoe1_total or aoe2_total or stun_total:
            if aoe1_protected < aoe1_total or aoe2_protected < aoe2_total or stun_safe < stun_total:
                warnings.append(
                    "La shell Unkillable non copre tutti i colpi giusti del boss nella simulazione: "
                    f"AoE1 {aoe1_protected}/{aoe1_total}, "
                    f"AoE2 {aoe2_protected}/{aoe2_total}, "
                    f"Stun sicuri {stun_safe}/{stun_total}."
                )
                priority_ok = 0

        if affinity == "force" and "Ninja" in names:
            warnings.append(
                "Regola esterna DeadwoodJedi: nella Budget Maneater con Ninja su Force conviene sostituire Ninja con un DPS non debole all'affinity."
            )
            priority_ok = 0

        min_speed = {
            "ultra_nightmare": 180.0,
            "nightmare": 170.0,
        }.get(difficulty, 160.0)
        slow_members = [
            f"{name} {round(speed, 1)}"
            for name, speed in speed_by_name.items()
            if speed > 0 and speed < min_speed
        ]
        if slow_members:
            warnings.append(
                "Le speed stimate nel dump locale risultano basse per una shell unkillable ("
                + ", ".join(slow_members)
                + "). Se hai cambiato equip in gioco, aggiorna prima l'elenco equipaggiamento."
            )
        speeds = [speed for speed in speed_by_name.values() if speed > 0]
        if speeds and max(speeds) - min(speeds) > 70.0:
            warnings.append(
                f"Le speed stimate nel dump locale hanno una spread ampia ({round(max(speeds) - min(speeds), 1)}). Se il setup e fresco in gioco, verifica il tune con un calcolatore esterno."
            )
        if speed_by_name.get("Maneater", 0.0) <= speed_by_name.get("Pain Keeper", 0.0):
            warnings.append("Nel dump locale Maneater non risulta piu veloce di Pain Keeper: verifica che il tune salvato sia aggiornato.")

    return {
        "priority_ok": priority_ok,
        "warnings": warnings,
    }


def assess_known_budget_maneater_tune(
    speed_by_name: Dict[str, float],
    difficulty: str,
    affinity: str,
) -> Dict[str, Any]:
    names = set(speed_by_name)
    if difficulty != "ultra_nightmare":
        return {"matched": False, "warnings": ["Le comp Maneater + Pain Keeper vengono validate solo su tune UNM noti; questa variante non e stata validata."]}

    maneater_speed = speed_by_name.get("Maneater", 0.0)
    pain_keeper_speed = speed_by_name.get("Pain Keeper", 0.0)
    other_speeds = {
        name: speed
        for name, speed in speed_by_name.items()
        if name not in {"Maneater", "Pain Keeper"}
    }

    def in_range(value: float, low: float, high: float) -> bool:
        return low <= value <= high

    warnings: List[str] = []
    if not in_range(maneater_speed, 240.0, 241.5) or not in_range(pain_keeper_speed, 218.0, 222.5):
        warnings.append(
            "La coppia Maneater + Pain Keeper non rientra nella finestra base del Budget Maneater UNM (ME circa 240-241, PK circa 218-222)."
        )
        return {"matched": False, "warnings": warnings}

    speeds = list(other_speeds.values())
    has_stun_target = any(in_range(speed, 111.0, 118.5) for speed in speeds)
    has_normal_dps = [speed for speed in speeds if in_range(speed, 175.0, 178.5)]

    if "Ninja" in names:
        ninja_speed = speed_by_name.get("Ninja", 0.0)
        if affinity == "force":
            warnings.append(
                "La variante Budget Maneater con Ninja non va usata su Force: DeadwoodJedi consiglia di sostituire Ninja con un DPS standard."
            )
            return {"matched": False, "warnings": warnings}
        if not in_range(ninja_speed, 161.0, 165.5):
            warnings.append("Ninja non rientra nella finestra nota del Budget Maneater UNM con Ninja (circa 161-165).")
            return {"matched": False, "warnings": warnings}
        if len(has_normal_dps) < 1 or not has_stun_target:
            warnings.append(
                "La variante con Ninja richiede anche un DPS standard circa 175-178 e uno stun target lento circa 111-118."
            )
            return {"matched": False, "warnings": warnings}
        return {"matched": True, "warnings": []}

    if len(has_normal_dps) < 2 or not has_stun_target:
        warnings.append(
            "Il Budget Maneater UNM standard richiede due DPS circa 175-178 e uno stun target lento circa 111-118."
        )
        return {"matched": False, "warnings": warnings}

    return {"matched": True, "warnings": []}


def assess_contextual_history(team_name: str, difficulty: str, affinity: str) -> Dict[str, Any]:
    rows = [
        row
        for row in list_manual_runs(limit=200)
        if string_value(row.get("team_name")) == string_value(team_name)
        and string_value(row.get("difficulty")) == string_value(difficulty)
        and string_value(row.get("affinity")) == string_value(affinity)
    ]
    if not rows:
        return {"priority_ok": 1, "warnings": [], "match_count": 0, "failure_count": 0}

    failure_count = 0
    for row in rows:
        boss_turn = int_value(row.get("boss_turn"))
        damage = float_value(row.get("damage"))
        damage_known = bool(row.get("damage_known"))
        source = string_value(row.get("source"))
        hard_capture_failure = source in {"recorded_session", "recovered_session"} and not damage_known and damage <= 0 and boss_turn <= 0
        poor_real_run = boss_turn > 0 and boss_turn < 20
        if hard_capture_failure or poor_real_run:
            failure_count += 1

    warnings: List[str] = []
    priority_ok = 1
    if failure_count >= 2:
        priority_ok = 0
        warnings.append(
            f"Storico reale negativo: {failure_count} run recenti in {difficulty} {affinity} senza esito affidabile per questo team. Deprioritizzato."
        )

    return {
        "priority_ok": priority_ok,
        "warnings": warnings,
        "match_count": len(rows),
        "failure_count": failure_count,
    }


def count_required_swaps(gear_plan: Sequence[Dict[str, Any]]) -> int:
    return len([item for item in gear_plan if bool(item.get("needs_swap"))])


def collect_swap_items(members: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for member in members:
        for item in list_value(member.get("gear_plan")):
            if not bool(item.get("needs_swap")):
                continue
            rows.append(
                {
                    "member_name": string_value(member.get("name")),
                    "item_id": string_value(item.get("item_id")),
                    "slot": string_value(item.get("slot")),
                    "set_name": string_value(item.get("set_name")),
                    "equipped_by_name": string_value(item.get("equipped_by_name")),
                }
            )
    return rows


def heal_team(units: Sequence[UnitState], fraction: float, source_name: str, timeline: List[str]) -> None:
    if fraction <= 0:
        return
    for ally in units:
        if not ally.alive:
            continue
        ally.hp = min(ally.max_hp, ally.hp + ally.max_hp * fraction)
    timeline.append(f"{source_name} cura il team del {int(fraction * 100)}% HP.")


def track_boss_debuff_coverage(boss_debuffs: Dict[str, int], coverage: Dict[str, int]) -> None:
    if int(boss_debuffs.get("decrease_defense", 0)) > 0:
        coverage["decrease_defense_turns"] += 1
    if int(boss_debuffs.get("weaken", 0)) > 0:
        coverage["weaken_turns"] += 1
    if int(boss_debuffs.get("hp_burn", 0)) > 0:
        coverage["hp_burn_turns"] += 1
    if int(boss_debuffs.get("poison", 0)) > 0:
        coverage["poison_turns"] += 1


def decrement_statuses(statuses: Dict[str, int]) -> None:
    for name, turns in list(statuses.items()):
        turns -= 1
        if turns <= 0:
            statuses.pop(name, None)
        else:
            statuses[name] = turns


def decrement_cooldowns(cooldowns: Dict[str, int]) -> None:
    for slot, value in list(cooldowns.items()):
        cooldowns[slot] = max(value - 1, 0)


def has_status(statuses: Dict[str, int], name: str) -> bool:
    return int(statuses.get(name, 0)) > 0


def affinity_relationship(attacker_affinity: str, defender_affinity: str) -> str:
    if attacker_affinity == "void" or defender_affinity == "void":
        return "neutral"
    strong_map = {
        "magic": "spirit",
        "spirit": "force",
        "force": "magic",
    }
    if strong_map.get(attacker_affinity) == defender_affinity:
        return "strong"
    if strong_map.get(defender_affinity) == attacker_affinity:
        return "weak"
    return "neutral"


def friendly_status(name: str) -> str:
    labels = {
        "unkillable": "Unkillable",
        "block_debuffs": "Block Debuffs",
        "increase_speed": "Increase Speed",
        "increase_defense": "Increase DEF",
        "increase_attack": "Increase ATK",
        "counterattack": "Counterattack",
        "shield": "Shield",
        "decrease_attack": "Decrease ATK",
        "decrease_defense": "Decrease DEF",
        "decrease_speed": "Decrease Speed",
        "decrease_accuracy": "Decrease Accuracy",
        "weaken": "Weaken",
        "hp_burn": "HP Burn",
        "poison": "Poison",
        "poison_sensitivity": "Poison Sensitivity",
        "leech": "Leech",
    }
    return labels.get(name, name)


def normalize_stat_key(value: str) -> str:
    aliases = {
        "def_": "def",
    }
    normalized = value.strip().lower()
    return aliases.get(normalized, normalized)


def normalize_stat_amount(stat_type: str, value: float) -> float:
    if 0 < abs(value) <= 1.0 and stat_type in {"hp_pct", "atk_pct", "def_pct", "acc", "res"}:
        return value * 100.0
    return value


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def mapping_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def main() -> None:
    payload = simulate_best_clan_boss_team()
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
