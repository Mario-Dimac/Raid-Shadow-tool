from __future__ import annotations

import json

from forge_db import bootstrap_database


def main() -> None:
    summary = bootstrap_database()
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
