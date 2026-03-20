from normalize import find_first_list, normalize_account, parse_gear_item


def test_parse_gear_item_preserves_required_faction() -> None:
    item = parse_gear_item(
        {
            "item_id": "ring-1",
            "item_class": "accessory",
            "slot": "ring",
            "set_name": "",
            "rarity": "epic",
            "rank": 6,
            "level": 16,
            "required_faction": "Orcs",
            "required_faction_id": 8,
        },
        1,
    )

    assert item.required_faction == "Orcs"
    assert item.required_faction_id == 8


def test_normalize_account_reconciles_missing_equipped_by_from_champion_items() -> None:
    account = normalize_account(
        {
            "meta": {},
            "roster": [
                {
                    "champ_id": "champ-1",
                    "name": "Frozen Banshee",
                    "rarity": "rare",
                    "affinity": "magic",
                    "faction": "Undead Hordes",
                    "level": 60,
                    "rank": 6,
                    "equipped_item_ids": ["boots-1"],
                }
            ],
            "inventory": [
                {
                    "item_id": "boots-1",
                    "item_class": "artifact",
                    "slot": "boots",
                    "set_name": "Life Drain",
                    "rarity": "legendary",
                    "rank": 6,
                    "level": 16,
                    "equipped_by": None,
                }
            ],
        }
    )

    assert account.gear[0].equipped_by == "champ-1"


def test_find_first_list_prefers_top_level_empty_list_over_nested_candidates() -> None:
    raw = {
        "roster": [],
        "local_client": {
            "some_cache": {
                "heroes": [{"champ_id": "nested-1", "name": "Wrong Source"}]
            }
        },
    }

    assert find_first_list(raw, ("champions", "heroes", "units", "roster")) == []
