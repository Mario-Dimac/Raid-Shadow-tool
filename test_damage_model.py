from __future__ import annotations

import pytest

from damage_model import (
    estimate_direct_skill_damage,
    final_enemy_defense,
    post_mitigation_damage,
    raw_direct_skill_damage,
    scaled_offense_stat,
)


def test_final_enemy_defense_matches_delta89_sheet_example() -> None:
    assert final_enemy_defense(
        base_defense=3000,
        aura_def_pct=0.0,
        increase_def_buff_pct=0.0,
        decrease_def_debuff_pct=0.6,
        ignore_def_pct=0.5,
    ) == pytest.approx(600.0)


def test_scaled_offense_stat_matches_delta89_kael_a2_example() -> None:
    assert scaled_offense_stat(
        base_stat=1200,
        gear_pct=1.5,
        flat_bonus=800,
        great_hall_pct=0.2,
        arena_pct=0.2,
        guardians_pct=0.1,
        books_pct=0.2,
        masteries_pct=0.19,
    ) == pytest.approx(5314.3424)


def test_raw_direct_skill_damage_matches_delta89_kael_a2_example() -> None:
    assert raw_direct_skill_damage(
        offense_stat=5314.3424,
        skill_multiplier=4.65,
        crit_damage_pct=2.0,
        damage_buff_pct=0.5,
    ) == pytest.approx(111202.61472)


def test_post_mitigation_damage_matches_delta89_kael_a2_example() -> None:
    assert post_mitigation_damage(
        raw_damage=111202.61472,
        target_final_defense=600.0,
        weaken_pct=0.0,
    ) == pytest.approx(80040.53275363478)


@pytest.mark.parametrize(
    ("label", "kwargs", "expected"),
    [
        (
            "Kael A2",
            {
                "base_stat": 1200,
                "skill_multiplier": 4.65,
                "target_base_defense": 3000,
                "gear_pct": 1.5,
                "flat_bonus": 800,
                "great_hall_pct": 0.2,
                "arena_pct": 0.2,
                "guardians_pct": 0.1,
                "books_pct": 0.2,
                "masteries_pct": 0.19,
                "crit_damage_pct": 2.0,
                "damage_buff_pct": 0.5,
                "decrease_def_debuff_pct": 0.6,
                "ignore_def_pct": 0.5,
            },
            80040.53275363478,
        ),
        (
            "Trunda A3",
            {
                "base_stat": 1608,
                "skill_multiplier": 6.0,
                "target_base_defense": 3000,
                "gear_pct": 1.5,
                "flat_bonus": 800,
                "great_hall_pct": 0.2,
                "arena_pct": 0.2,
                "guardians_pct": 0.1,
                "books_pct": 0.3,
                "masteries_pct": 0.19,
                "crit_damage_pct": 2.0,
                "damage_buff_pct": 0.5,
                "decrease_def_debuff_pct": 0.6,
                "ignore_def_pct": 0.5,
            },
            138997.0861372308,
        ),
        (
            "Arbiter A2",
            {
                "base_stat": 1068,
                "skill_multiplier": 2.2,
                "target_base_defense": 3000,
                "gear_pct": 1.5,
                "flat_bonus": 800,
                "great_hall_pct": 0.2,
                "arena_pct": 0.2,
                "guardians_pct": 0.1,
                "books_pct": 0.1,
                "masteries_pct": 0.19,
                "crit_damage_pct": 2.0,
                "damage_buff_pct": 0.5,
                "decrease_def_debuff_pct": 0.6,
                "ignore_def_pct": 0.5,
            },
            32895.64432017526,
        ),
    ],
)
def test_estimate_direct_skill_damage_matches_delta89_examples(label: str, kwargs: dict[str, float], expected: float) -> None:
    assert estimate_direct_skill_damage(**kwargs) == pytest.approx(expected), label
