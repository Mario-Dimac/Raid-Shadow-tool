from __future__ import annotations

from gear_advisor import evaluate_gear_item


def test_pre12_piece_with_good_base_gets_push_12() -> None:
    item = {
        "slot": "boots",
        "main_stat_type": "spd",
        "rarity": "legendary",
        "rank": 6,
        "level": 0,
        "set_name": "Attack Speed",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "acc", "rolls": 0, "glyph_value": 0},
        {"stat_type": "hp_pct", "rolls": 0, "glyph_value": 0},
        {"stat_type": "res", "rolls": 0, "glyph_value": 0},
        {"stat_type": "atk", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "push_12"


def test_more_open_substats_improve_starting_score() -> None:
    legendary_item = {
        "slot": "boots",
        "main_stat_type": "spd",
        "rarity": "legendary",
        "rank": 6,
        "level": 0,
        "set_name": "Attack Speed",
        "equipped": False,
        "owner_name": "",
    }
    epic_item = {
        **legendary_item,
        "rarity": "epic",
    }
    legendary_substats = [
        {"stat_type": "acc", "rolls": 0, "glyph_value": 0},
        {"stat_type": "hp_pct", "rolls": 0, "glyph_value": 0},
        {"stat_type": "res", "rolls": 0, "glyph_value": 0},
        {"stat_type": "atk", "rolls": 0, "glyph_value": 0},
    ]
    epic_substats = legendary_substats[:3]

    legendary_advice = evaluate_gear_item(legendary_item, legendary_substats)
    epic_advice = evaluate_gear_item(epic_item, epic_substats)

    assert legendary_advice["pre12_score"] > epic_advice["pre12_score"]
    assert "partenza: 4 sub aperte" in legendary_advice["reasons"]
    assert "partenza: 3 sub aperte" in epic_advice["reasons"]


def test_plus12_piece_with_bad_rolls_gets_sold() -> None:
    item = {
        "slot": "gloves",
        "main_stat_type": "hp",
        "rarity": "epic",
        "rank": 5,
        "level": 12,
        "set_name": "",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "atk", "rolls": 2, "glyph_value": 0},
        {"stat_type": "def", "rolls": 1, "glyph_value": 0},
        {"stat_type": "hp", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "sell_after_12"


def test_pre8_bad_piece_gets_sold_now() -> None:
    item = {
        "slot": "gloves",
        "main_stat_type": "hp",
        "rarity": "epic",
        "rank": 5,
        "level": 4,
        "set_name": "",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "atk", "rolls": 1, "glyph_value": 0},
        {"stat_type": "def", "rolls": 0, "glyph_value": 0},
        {"stat_type": "hp", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "sell_now"


def test_plus8_bad_piece_gets_reviewed_before_sale() -> None:
    item = {
        "slot": "gloves",
        "main_stat_type": "hp",
        "rarity": "epic",
        "rank": 5,
        "level": 8,
        "set_name": "",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "atk", "rolls": 1, "glyph_value": 0},
        {"stat_type": "def", "rolls": 0, "glyph_value": 0},
        {"stat_type": "hp", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "review_pre12"


def test_plus12_piece_with_good_rolls_gets_push_16() -> None:
    item = {
        "slot": "chest",
        "main_stat_type": "hp_pct",
        "rarity": "legendary",
        "rank": 6,
        "level": 12,
        "set_name": "HP And Defence",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "spd", "rolls": 2, "glyph_value": 6},
        {"stat_type": "acc", "rolls": 1, "glyph_value": 0},
        {"stat_type": "def_pct", "rolls": 1, "glyph_value": 0},
        {"stat_type": "atk", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "push_16"


def test_plus12_rare_piece_with_good_rolls_is_not_promoted() -> None:
    item = {
        "slot": "chest",
        "main_stat_type": "hp_pct",
        "rarity": "rare",
        "rank": 6,
        "level": 12,
        "set_name": "HP And Defence",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "spd", "rolls": 2, "glyph_value": 6},
        {"stat_type": "acc", "rolls": 1, "glyph_value": 0},
        {"stat_type": "def_pct", "rolls": 1, "glyph_value": 0},
        {"stat_type": "atk", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "sell_after_12"
    assert "rarita bassa: azzurro" in advice["reasons"]


def test_equipped_bad_piece_is_review_not_sell() -> None:
    item = {
        "slot": "boots",
        "main_stat_type": "atk",
        "rarity": "rare",
        "rank": 5,
        "level": 12,
        "set_name": "",
        "equipped": True,
        "owner_name": "Coldheart",
    }
    substats = [
        {"stat_type": "atk", "rolls": 2, "glyph_value": 0},
        {"stat_type": "hp", "rolls": 1, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "review_equipped"


def test_equipped_plus8_bad_piece_stays_review_equipped() -> None:
    item = {
        "slot": "gloves",
        "main_stat_type": "hp",
        "rarity": "epic",
        "rank": 5,
        "level": 8,
        "set_name": "",
        "equipped": True,
        "owner_name": "Miscreated Monster",
    }
    substats = [
        {"stat_type": "atk", "rolls": 1, "glyph_value": 0},
        {"stat_type": "def", "rolls": 0, "glyph_value": 0},
        {"stat_type": "hp", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "review_equipped"


def test_plus16_rare_piece_never_becomes_keep_16() -> None:
    item = {
        "slot": "weapon",
        "main_stat_type": "atk",
        "rarity": "rare",
        "rank": 6,
        "level": 16,
        "set_name": "Attack Speed",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "spd", "rolls": 2, "glyph_value": 8},
        {"stat_type": "crit_rate", "rolls": 1, "glyph_value": 0},
        {"stat_type": "acc", "rolls": 1, "glyph_value": 0},
        {"stat_type": "hp_pct", "rolls": 1, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "review_16"


def test_plus8_uncommon_piece_goes_to_review_pre12() -> None:
    item = {
        "slot": "boots",
        "main_stat_type": "spd",
        "rarity": "uncommon",
        "rank": 5,
        "level": 8,
        "set_name": "Attack Speed",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "acc", "rolls": 1, "glyph_value": 0},
        {"stat_type": "hp_pct", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "review_pre12"
    assert "rarita scarsa: verde" in advice["reasons"]


def test_plus12_offensive_banner_with_speed_and_atk_pct_is_kept() -> None:
    item = {
        "slot": "banner",
        "main_stat_type": "crit_rate",
        "rarity": "legendary",
        "rank": 6,
        "level": 12,
        "set_name": "",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "spd", "rolls": 0, "glyph_value": 0},
        {"stat_type": "hp_pct", "rolls": 1, "glyph_value": 0},
        {"stat_type": "atk_pct", "rolls": 2, "glyph_value": 0},
        {"stat_type": "def", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "keep_after_12"
    assert advice["main_tier"] == "medium"


def test_plus12_accessory_medium_main_with_one_dead_sub_can_still_be_kept() -> None:
    item = {
        "slot": "banner",
        "main_stat_type": "atk",
        "rarity": "legendary",
        "rank": 6,
        "level": 12,
        "set_name": "",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "atk_pct", "rolls": 3, "glyph_value": 0},
        {"stat_type": "spd", "rolls": 0, "glyph_value": 0},
        {"stat_type": "def", "rolls": 0, "glyph_value": 0},
        {"stat_type": "hp_pct", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "keep_after_12"


def test_pre8_accessory_medium_main_with_borderline_base_gets_reviewed_not_sold() -> None:
    item = {
        "slot": "ring",
        "main_stat_type": "atk",
        "rarity": "epic",
        "rank": 6,
        "level": 0,
        "set_name": "Attack Speed",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "atk_pct", "rolls": 0, "glyph_value": 0},
        {"stat_type": "crit_rate", "rolls": 0, "glyph_value": 0},
        {"stat_type": "def", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "review_pre12"


def test_pre8_accessory_with_bad_base_still_gets_sold_now() -> None:
    item = {
        "slot": "ring",
        "main_stat_type": "hp",
        "rarity": "epic",
        "rank": 5,
        "level": 0,
        "set_name": "",
        "equipped": False,
        "owner_name": "",
    }
    substats = [
        {"stat_type": "atk", "rolls": 0, "glyph_value": 0},
        {"stat_type": "def", "rolls": 0, "glyph_value": 0},
        {"stat_type": "hp", "rolls": 0, "glyph_value": 0},
    ]

    advice = evaluate_gear_item(item, substats)

    assert advice["verdict"] == "sell_now"
