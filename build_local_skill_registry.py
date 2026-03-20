from __future__ import annotations

import argparse
import json
from pathlib import Path

from forge_db import DB_PATH
from providers.local_registry_provider import LOCAL_SKILL_REGISTRY_PATH, export_local_skill_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export local skill registry from SQLite.")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--output-path", type=Path, default=LOCAL_SKILL_REGISTRY_PATH)
    parser.add_argument("--champion", action="append", dest="champions", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = export_local_skill_registry(
        db_path=args.db_path,
        output_path=args.output_path,
        champion_names=args.champions,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
