from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


archive_root = Path("data/archive")
rows: list[dict[str, object]] = []

for manifest_path in archive_root.glob(
    "*/wnba/pregame/manifest.json"
):
    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    artifacts = manifest.get(
        "artifacts",
        {}
    )

    rows.append(
        {
            "slate_date": manifest.get(
                "slate_date"
            ),
            "sport": manifest.get(
                "sport"
            ),
            "archive_complete": manifest.get(
                "archive_complete",
                False,
            ),
            "missing_required_count": len(
                manifest.get(
                    "missing_required",
                    [],
                )
            ),
            "missing_required": " | ".join(
                manifest.get(
                    "missing_required",
                    [],
                )
            ),
            "artifact_count": len(
                artifacts
            ),
            "copied_artifact_count": sum(
                bool(
                    record.get("copied")
                )
                for record in artifacts.values()
            ),
            "git_commit": manifest.get(
                "git_commit"
            ),
            "git_branch": manifest.get(
                "git_branch"
            ),
            "git_dirty": manifest.get(
                "git_dirty"
            ),
            "manifest_path": str(
                manifest_path
            ),
        }
    )

inventory = pd.DataFrame(rows)

if not inventory.empty:
    inventory = inventory.sort_values(
        "slate_date"
    )

output = Path(
    "data/backtests/"
    "wnba_archive_inventory.csv"
)

output.parent.mkdir(
    parents=True,
    exist_ok=True,
)

inventory.to_csv(
    output,
    index=False,
)

if inventory.empty:
    print("No archived slates found.")
else:
    print(
        inventory.to_string(
            index=False
        )
    )

print()
print("Saved:", output)
