from __future__ import annotations

from battle_results_burst_probe import is_battle_results_trigger, is_interesting_line


def test_is_battle_results_trigger_matches_finish_markers() -> None:
    assert is_battle_results_trigger("Battle [abc] ProcessBattleFinish")
    assert is_battle_results_trigger("BattleResult added: [Id=abc] TotalCount=1")
    assert is_battle_results_trigger("Finishing Battle - abc")
    assert not is_battle_results_trigger("Change battle state [Loading -> Started]")


def test_is_interesting_line_includes_finish_related_lines() -> None:
    assert is_interesting_line("BattleResult deleted: [Id=abc] Remaining=0")
    assert is_interesting_line("Battle [abc] StageCompleted")
    assert is_interesting_line("Change battle state [Started -> Finished]")
    assert not is_interesting_line("Loaded random asset bundle")
