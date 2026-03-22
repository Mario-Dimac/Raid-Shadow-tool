from __future__ import annotations

from client_run_probe import parse_latest_battle_block, summarize_recent_log_signals


def test_parse_latest_battle_block_reads_player_team_and_enemy_rows() -> None:
    lines = [
        "noise",
        ">>> CreateBattle with setup:Id: abc-def-1234 RandomSeed: 7 Stage: 5029021 FormationIndex 0",
        " First Team: Owner: 83832666, Hero Setups:",
        "Round: 1 Slot: 1 Type: 396 Grd: Stars6 Lvl: 60",
        "Round: 1 Slot: 2 Type: 3566 Grd: Stars6 Lvl: 60",
        "Round: 1 Slot: 3 Type: 2366 Grd: Stars6 Lvl: 60",
        "Round: 1 Slot: 4 Type: 7106 Grd: Stars6 Lvl: 60",
        "Round: 1 Slot: 5 Type: 4086 Grd: Stars6 Lvl: 60",
        " Second Team: Owner: -1, Hero Setups:",
        "Round: 1 Slot: 1 Type: 1876 Grd: Stars6 Lvl: 244",
        "Round: 1 Slot: 2 Type: 1666 Grd: Stars6 Lvl: 244",
        "Round: 2 Slot: 1 Type: 22300 Grd: Stars6 Lvl: 250",
    ]

    parsed = parse_latest_battle_block(
        lines,
        {
            396: "Heiress",
            3566: "Arbiter",
            2366: "Elenaril",
            7106: "Deliana",
            4086: "Yannica",
        },
    )

    assert parsed["battle_id"] == "abc-def-1234"
    assert parsed["stage_id"] == "5029021"
    assert parsed["player_members"] == ["Heiress", "Arbiter", "Elenaril", "Deliana", "Yannica"]
    assert len(parsed["enemy_rows"]) == 3
    assert parsed["enemy_rows"][2]["round"] == 2


def test_summarize_recent_log_signals_keeps_state_and_battle_id() -> None:
    lines = [
        "random",
        "Change battle state [Loading -> Started]",
        "BattleResult added: [Id=8fb97928-eaba-4014-a5ea-6813d5c40974] TotalCount=1",
    ]

    summary = summarize_recent_log_signals(lines)

    assert summary["battle_state"] == "Started"
    assert summary["battle_id"] == "8fb97928-eaba-4014-a5ea-6813d5c40974"
    assert len(summary["recent_events"]) == 2
