from __future__ import annotations

from loadout_snapshot import build_loadout_snapshot, load_account, reconcile_loaded_account_ownership


def test_build_loadout_snapshot_preserves_current_assignments() -> None:
    account = load_account()
    snapshot = build_loadout_snapshot(account)

    assert snapshot["champion_count"] > 0
    assert snapshot["gear_count"] > 0
    assert snapshot["champions"]
    assert snapshot["gear"]
    assert any(item["equipped_by_name"] for item in snapshot["gear"] if item["equipped_by"])


def test_reconcile_loaded_account_ownership_repairs_snapshot_inputs() -> None:
    account = {
        "champions": [
            {
                "champ_id": "fb-1",
                "name": "Frozen Banshee",
                "equipped_item_ids": ["gear-1", "gear-2"],
            }
        ],
        "gear": [
            {"item_id": "gear-1", "slot": "weapon", "equipped_by": None},
            {"item_id": "gear-2", "slot": "boots", "equipped_by": ""},
        ],
    }

    reconcile_loaded_account_ownership(account)
    snapshot = build_loadout_snapshot(account)

    champion = snapshot["champions"][0]
    assert [item["item_id"] for item in champion["equipped_items"]] == ["gear-1", "gear-2"]


def test_build_loadout_snapshot_sorts_duplicate_names_by_geared_variant() -> None:
    account = {
        "champions": [
            {"champ_id": "fb-low", "name": "Frozen Banshee", "level": 1, "rank": 3, "equipped_item_ids": []},
            {"champ_id": "fb-main", "name": "Frozen Banshee", "level": 60, "rank": 6, "equipped_item_ids": ["gear-1"]},
        ],
        "gear": [
            {"item_id": "gear-1", "slot": "weapon", "equipped_by": "fb-main"},
        ],
    }

    snapshot = build_loadout_snapshot(account)

    assert snapshot["champions"][0]["champ_id"] == "fb-main"
