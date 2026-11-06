"""Read the startup-jobs CSV.

The export in s.csv has a 3-line preamble (a promo line, a blank row, a title
row) before the real header. We locate the header by looking for the first line
that starts with "Company,Role" instead of hard-coding a line offset.
"""
from __future__ import annotations

import csv
import io

REQUIRED_COLUMNS = ["Company", "Role", "Category", "Location", "Remote"]


def find_header_index(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line.lstrip("﻿").startswith("Company,Role"):
            return i
    raise ValueError("No header row starting with 'Company,Role' found")


def load_rows(path: str) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    lines = text.splitlines(keepends=True)
    start = find_header_index(lines)
    reader = csv.DictReader(io.StringIO("".join(lines[start:])))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    rows = []
    for row in reader:
        if not (row.get("Role") or "").strip():
            continue
        rows.append({k.lstrip("﻿"): (v or "").strip() for k, v in row.items() if k is not None})
    return rows
