from __future__ import annotations

import math


DEFAULT_DEFENSE_REDUCTION_CAP = 0.85
DEFAULT_DEFENSE_CURVE = 3000.0


def final_enemy_defense(
    base_defense: float,
    aura_def_pct: float = 0.0,
    increase_def_buff_pct: float = 0.0,
    decrease_def_debuff_pct: float = 0.0,
    ignore_def_pct: float = 0.0,
) -> float:
    return (
        float(base_defense)
        * (1.0 + float(aura_def_pct))
        * (1.0 + float(increase_def_buff_pct))
        * (1.0 - float(decrease_def_debuff_pct))
        * (1.0 - float(ignore_def_pct))
    )


def scaled_offense_stat(
    base_stat: float,
    gear_pct: float = 0.0,
    flat_bonus: float = 0.0,
    great_hall_pct: float = 0.0,
    arena_pct: float = 0.0,
    guardians_pct: float = 0.0,
    books_pct: float = 0.0,
    masteries_pct: float = 0.0,
) -> float:
    base = float(base_stat)
    scaled_base = (
        base
        * (1.0 + float(great_hall_pct))
        * (1.0 + float(arena_pct))
        * (1.0 + float(guardians_pct))
        * (1.0 + float(books_pct))
        * (1.0 + float(masteries_pct))
    )
    gear_bonus = base * float(gear_pct)
    return scaled_base + gear_bonus + float(flat_bonus)


def raw_direct_skill_damage(
    offense_stat: float,
    skill_multiplier: float,
    crit_damage_pct: float = 0.0,
    damage_buff_pct: float = 0.0,
) -> float:
    return (
        float(offense_stat)
        * float(skill_multiplier)
        * (1.0 + float(crit_damage_pct))
        * (1.0 + float(damage_buff_pct))
    )


def post_mitigation_damage(
    raw_damage: float,
    target_final_defense: float,
    weaken_pct: float = 0.0,
    defense_reduction_cap: float = DEFAULT_DEFENSE_REDUCTION_CAP,
    defense_curve: float = DEFAULT_DEFENSE_CURVE,
) -> float:
    mitigation_factor = 1.0 - float(defense_reduction_cap) * (
        1.0 - math.exp((-2.0 * float(target_final_defense)) / float(defense_curve))
    )
    return float(raw_damage) * mitigation_factor * (1.0 + float(weaken_pct))


def estimate_direct_skill_damage(
    base_stat: float,
    skill_multiplier: float,
    target_base_defense: float,
    gear_pct: float = 0.0,
    flat_bonus: float = 0.0,
    great_hall_pct: float = 0.0,
    arena_pct: float = 0.0,
    guardians_pct: float = 0.0,
    books_pct: float = 0.0,
    masteries_pct: float = 0.0,
    crit_damage_pct: float = 0.0,
    damage_buff_pct: float = 0.0,
    weaken_pct: float = 0.0,
    aura_def_pct: float = 0.0,
    increase_def_buff_pct: float = 0.0,
    decrease_def_debuff_pct: float = 0.0,
    ignore_def_pct: float = 0.0,
    defense_reduction_cap: float = DEFAULT_DEFENSE_REDUCTION_CAP,
    defense_curve: float = DEFAULT_DEFENSE_CURVE,
) -> float:
    final_stat = scaled_offense_stat(
        base_stat=base_stat,
        gear_pct=gear_pct,
        flat_bonus=flat_bonus,
        great_hall_pct=great_hall_pct,
        arena_pct=arena_pct,
        guardians_pct=guardians_pct,
        books_pct=books_pct,
        masteries_pct=masteries_pct,
    )
    raw_damage = raw_direct_skill_damage(
        offense_stat=final_stat,
        skill_multiplier=skill_multiplier,
        crit_damage_pct=crit_damage_pct,
        damage_buff_pct=damage_buff_pct,
    )
    target_final_defense = final_enemy_defense(
        base_defense=target_base_defense,
        aura_def_pct=aura_def_pct,
        increase_def_buff_pct=increase_def_buff_pct,
        decrease_def_debuff_pct=decrease_def_debuff_pct,
        ignore_def_pct=ignore_def_pct,
    )
    return post_mitigation_damage(
        raw_damage=raw_damage,
        target_final_defense=target_final_defense,
        weaken_pct=weaken_pct,
        defense_reduction_cap=defense_reduction_cap,
        defense_curve=defense_curve,
    )
