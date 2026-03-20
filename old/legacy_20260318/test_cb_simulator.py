from __future__ import annotations

from cb_simulator import (
    CHAMPION_DEFINITIONS,
    assess_contextual_history,
    assess_clan_boss_team_readiness,
    assess_clan_boss_team_advisory,
    available_clan_boss_affinities,
    available_clan_boss_levels,
    build_clan_boss_survival_plan,
    clan_boss_recommendation_score,
    estimate_total_stats,
    recommend_clan_boss_options,
    simulate_best_clan_boss_team,
    simulate_clan_boss_affinity_matrix,
    survival_priority_score,
)


def test_clan_boss_config_lists_expected_variants() -> None:
    level_keys = {item["key"] for item in available_clan_boss_levels()}
    affinity_keys = {item["key"] for item in available_clan_boss_affinities()}

    assert {"easy", "normal", "hard", "brutal", "nightmare", "ultra_nightmare"} <= level_keys
    assert {"void", "magic", "force", "spirit"} == affinity_keys


def test_simulation_returns_turn_timeline_for_best_team() -> None:
    payload = simulate_best_clan_boss_team(difficulty="ultra_nightmare", affinity="void", turns=6)

    assert payload["team_name"]
    assert payload["summary"]["boss_turns_simulated"] == 6
    assert payload["timeline"]
    assert any("Boss Ultra Nightmare void esegue" in line for line in payload["timeline"])
    assert len(payload["members"]) == 5
    assert all("gear_plan" in member for member in payload["members"])


def test_estimate_total_stats_applies_common_set_bonuses() -> None:
    stats = estimate_total_stats(
        {
            "base_stats": {
                "hp": 100,
                "atk": 100,
                "def": 100,
                "spd": 100,
                "acc": 0,
                "res": 0,
                "crit_rate": 15,
                "crit_dmg": 50,
            },
            "affinity": "void",
        },
        [
            {"set_name": "Attack Speed", "main_stat": {}, "substats": []},
            {"set_name": "Attack Speed", "main_stat": {}, "substats": []},
            {"set_name": "Accuracy And Speed", "main_stat": {}, "substats": []},
            {"set_name": "Accuracy And Speed", "main_stat": {}, "substats": []},
            {"set_name": "HP And Heal", "main_stat": {}, "substats": []},
            {"set_name": "HP And Heal", "main_stat": {}, "substats": []},
        ],
        [],
    )

    assert stats["spd"] == 117.0
    assert stats["acc"] == 40.0
    assert stats["hp"] == 27600.0
    assert stats["set_heal_each_turn_pct"] == 0.03


def test_registry_contains_real_definitions_for_key_legendary_cb_champions() -> None:
    for name in ["Valkyrie", "Venus", "Riho Bonespear", "Jintoro", "Teodor the Savant", "Michinaki"]:
        assert name in CHAMPION_DEFINITIONS


def test_simulation_changes_with_affinity_and_difficulty() -> None:
    void_payload = simulate_best_clan_boss_team(difficulty="nightmare", affinity="void", turns=6)
    force_payload = simulate_best_clan_boss_team(difficulty="ultra_nightmare", affinity="force", turns=6)

    assert void_payload["boss"]["speed"] != force_payload["boss"]["speed"]
    assert force_payload["summary"]["affinity"] == "force"
    assert force_payload["summary"]["boss_turns_simulated"] == 6
    assert isinstance(force_payload["summary"]["warnings"], list)


def test_affinity_matrix_returns_best_variant_for_each_affinity() -> None:
    payload = simulate_clan_boss_affinity_matrix(difficulty="ultra_nightmare", turns=6)

    assert len(payload["rows"]) == 4
    assert {row["affinity"] for row in payload["rows"]} == {"void", "magic", "force", "spirit"}
    assert all(row["team_name"] for row in payload["rows"])


def test_survival_priority_prefers_longer_runs_before_damage() -> None:
    glass_cannon = {
        "boss_turns_simulated": 20,
        "alive_count": 1,
        "coverage": {"decrease_attack_hits": 0},
        "warnings": [],
        "estimated_team_damage": 9000000.0,
    }
    stable_team = {
        "boss_turns_simulated": 30,
        "alive_count": 1,
        "coverage": {"decrease_attack_hits": 0},
        "warnings": ["minor"],
        "estimated_team_damage": 1000.0,
    }

    assert survival_priority_score(stable_team, []) > survival_priority_score(glass_cannon, [])


def test_survival_priority_prefers_attack_down_and_fewer_swaps_when_survival_is_equal() -> None:
    same_turns_more_swaps = {
        "boss_turns_simulated": 50,
        "alive_count": 5,
        "coverage": {"decrease_attack_hits": 0},
        "warnings": [],
        "estimated_team_damage": 999999.0,
    }
    safer_team = {
        "boss_turns_simulated": 50,
        "alive_count": 5,
        "coverage": {"decrease_attack_hits": 10},
        "warnings": [],
        "estimated_team_damage": 1000.0,
    }

    assert survival_priority_score(safer_team, [{"swap_count": 1}]) > survival_priority_score(same_turns_more_swaps, [{"swap_count": 5}])


def test_clan_boss_recommendations_value_damage_before_swap_count() -> None:
    lower_damage_fewer_swaps = {
        "boss_turns_simulated": 300,
        "alive_count": 5,
        "coverage": {"decrease_attack_hits": 155},
        "warnings": ["affinity"],
        "estimated_team_damage": 3448217.7,
    }
    higher_damage_more_swaps = {
        "boss_turns_simulated": 300,
        "alive_count": 5,
        "coverage": {"decrease_attack_hits": 155},
        "warnings": ["affinity"],
        "estimated_team_damage": 3752402.6,
    }

    assert clan_boss_recommendation_score(higher_damage_more_swaps, [{"swap_count": 4}], 900.0) > clan_boss_recommendation_score(
        lower_damage_fewer_swaps,
        [{"swap_count": 2}],
        950.0,
    )


def test_force_ninja_unkillable_loses_priority_even_with_same_survival() -> None:
    summary = {
        "boss_turns_simulated": 300,
        "alive_count": 5,
        "coverage": {"decrease_attack_hits": 155},
        "warnings": ["affinity"],
        "estimated_team_damage": 3752402.6,
    }

    assert clan_boss_recommendation_score(summary, [], 900.0, readiness_priority=1) > clan_boss_recommendation_score(
        summary,
        [],
        950.0,
        readiness_priority=0,
    )


def test_bad_contextual_history_loses_priority_even_with_same_survival() -> None:
    summary = {
        "boss_turns_simulated": 300,
        "alive_count": 5,
        "coverage": {"decrease_attack_hits": 155},
        "warnings": [],
        "estimated_team_damage": 3752402.6,
    }

    assert clan_boss_recommendation_score(summary, [], 900.0, history_priority=1, readiness_priority=1) > clan_boss_recommendation_score(
        summary,
        [],
        950.0,
        history_priority=0,
        readiness_priority=1,
    )


def test_assess_clan_boss_team_readiness_flags_force_ninja_budget_rule() -> None:
    readiness = assess_clan_boss_team_readiness(
        team=None,  # type: ignore[arg-type]
        members=[
            {"name": "Maneater", "estimated_speed": 246.0},
            {"name": "Pain Keeper", "estimated_speed": 243.0},
            {"name": "Stag Knight", "estimated_speed": 258.0},
            {"name": "Ninja", "estimated_speed": 142.0},
            {"name": "Geomancer", "estimated_speed": 172.0},
        ],
        difficulty="ultra_nightmare",
        affinity="force",
    )

    assert readiness["priority_ok"] == 0
    assert any("DeadwoodJedi" in warning for warning in readiness["warnings"])


def test_assess_clan_boss_team_readiness_flags_missing_unkillable_windows() -> None:
    readiness = assess_clan_boss_team_readiness(
        team=None,  # type: ignore[arg-type]
        members=[
            {"name": "Maneater", "estimated_speed": 240.0},
            {"name": "Pain Keeper", "estimated_speed": 220.0},
            {"name": "Geomancer", "estimated_speed": 177.0},
            {"name": "Frozen Banshee", "estimated_speed": 176.0},
            {"name": "Stag Knight", "estimated_speed": 115.0},
        ],
        difficulty="ultra_nightmare",
        affinity="void",
        summary={
            "coverage": {
                "aoe1_total": 4,
                "aoe2_total": 4,
                "stun_total": 4,
                "aoe1_protected": 4,
                "aoe2_protected": 1,
                "stun_safe": 0,
            }
        },
    )

    assert readiness["priority_ok"] == 0
    assert any("shell Unkillable non copre" in warning for warning in readiness["warnings"])


def test_assess_contextual_history_flags_repeated_failed_runs(monkeypatch) -> None:
    monkeypatch.setattr(
        "cb_simulator.list_manual_runs",
        lambda limit=200: [
            {
                "team_name": "Stabilized Unkillable Guard (Stag Knight)",
                "difficulty": "ultra_nightmare",
                "affinity": "force",
                "boss_turn": 0,
                "damage": 0.0,
                "damage_known": False,
                "source": "recorded_session",
            },
            {
                "team_name": "Stabilized Unkillable Guard (Stag Knight)",
                "difficulty": "ultra_nightmare",
                "affinity": "force",
                "boss_turn": 0,
                "damage": 0.0,
                "damage_known": False,
                "source": "recorded_session",
            },
        ],
    )

    feedback = assess_contextual_history("Stabilized Unkillable Guard (Stag Knight)", "ultra_nightmare", "force")

    assert feedback["priority_ok"] == 0
    assert feedback["failure_count"] == 2
    assert any("Storico reale negativo" in warning for warning in feedback["warnings"])


def test_advisory_marks_fragile_unm_team_as_red() -> None:
    advisory = assess_clan_boss_team_advisory(
        {
            "boss_turns_simulated": 126,
            "alive_count": 1,
            "warnings": [
                "Uptime di Decrease ATK bassa: il team rischia di essere troppo fragile nei tier alti.",
                "Il team muore prima di chiudere la finestra di simulazione.",
            ],
        },
        difficulty="ultra_nightmare",
        affinity="force",
        readiness_priority=1,
        history_priority=1,
    )

    assert advisory["level"] == "red"
    assert advisory["primary_key_ok"] is False


def test_recommend_clan_boss_options_attaches_simulated_context() -> None:
    options = recommend_clan_boss_options(difficulty="ultra_nightmare", affinity="force", turns=120)

    assert options
    assert options[0]["simulated_context"] == {
        "difficulty": "ultra_nightmare",
        "affinity": "force",
        "turns": 120,
    }
    assert options[0]["simulated_summary"]["affinity"] == "force"
    assert isinstance(options[0]["simulated_summary"].get("cycle_debug"), list)
    assert "advisory" in options[0]
    assert options[0]["team_name"] != "Budget Unkillable Shell"


def test_clan_boss_survival_plan_returns_affinity_rows_with_swaps() -> None:
    payload = build_clan_boss_survival_plan(difficulty="ultra_nightmare", turns=12)

    assert payload["turns"] == 12
    assert len(payload["rows"]) == 4
    assert {row["affinity"] for row in payload["rows"]} == {"void", "magic", "force", "spirit"}
    assert isinstance(payload["shared_core"], list)
    assert all("swap_count" in row for row in payload["rows"])
    assert all(isinstance(row["members"], list) and row["members"] for row in payload["rows"])
