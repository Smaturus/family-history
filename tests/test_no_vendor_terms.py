"""CI gate: tracked files must not mention legacy data formats or vendors.

The forbidden terms are assembled from fragments so that this test file itself
stays neutral and can be scanned like any other tracked file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Split on purpose: the raw source must not contain the terms it looks for.
TERMS = [
    "ged" + "com",
    "my" + "heritage",
    "smart" + " match",
    "." + "ged",
]


def tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return [line for line in proc.stdout.splitlines() if line]


def test_no_legacy_terms_in_tracked_files():
    hits: list[str] = []
    for rel in tracked_files():
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        low = text.lower()
        for term in TERMS:
            if term in low:
                hits.append(f"{rel}: {term}")
    assert not hits, "legacy terms in tracked files: " + ", ".join(sorted(hits))
