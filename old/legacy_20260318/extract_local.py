from __future__ import annotations

import json

from cbforge_extractor import build_raw_snapshot
from cbforge_extractor.paths import INPUT_DIR, RAW_PATH


def main() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_raw_snapshot()
    with RAW_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    print(f"Raw local snapshot saved to {RAW_PATH}")


if __name__ == "__main__":
    main()
