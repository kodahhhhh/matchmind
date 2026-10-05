"""Offline source-export column ordering; no model or production data writes."""

import json

import pandas as pd

from matchpulse.config import get_settings
from matchpulse.sources.common import SPADL_COLUMNS, save_json


def main() -> None:
    """Make already exported parquet column order identical to StatsBomb SPADL."""
    root = get_settings().data_dir / "sources"
    changed = {}
    for source in ("wyscout", "whoscored", "dynasty"):
        catalogue = root / f"catalogue_{source}.json"
        if not catalogue.exists():
            continue
        count = 0
        for entry in json.loads(catalogue.read_text()):
            for folder in ("spadl", "scored"):
                path = root / f"{source}/{folder}/{entry['native_id']}.parquet"
                frame = pd.read_parquet(path)
                if not set(SPADL_COLUMNS).issubset(frame.columns):
                    raise ValueError(f"Missing standard source columns: {path}")
                columns = SPADL_COLUMNS + [c for c in frame if c not in SPADL_COLUMNS]
                if list(frame.columns) != columns:
                    temporary = path.with_suffix(".part")
                    frame[columns].to_parquet(temporary, index=False)
                    temporary.replace(path)
                    count += 1
        changed[source] = count
    save_json(root / "standardize_report.json", changed)
    print(json.dumps(changed))


if __name__ == "__main__":
    main()
