"""End-to-end run: load -> classify -> (optional LLM) -> score -> write outputs."""
from __future__ import annotations

import csv
import json
import os
import time
from collections import Counter

from . import dashboard, sample
from .classify import FAMILIES, classify
from .loader import load_rows
from .score import load_profile, score

ADDED_FIELDS = ["row_id", "family", "family_label", "matched_family", "skip_reason", "rule",
                "confidence", "source", "fit_score", "fit_reasons"]


def classify_rows(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows, 1):
        c = classify(r.get("Role", ""), r.get("Category", ""))
        out.append({**r, "row_id": i, "family": c.family, "matched_family": c.matched_family,
                    "skip_reason": c.skip_reason, "rule": c.rule, "confidence": c.confidence,
                    "source": "rules"})
    return out


def apply_llm(rows: list[dict], assist) -> dict:
    """Let the LLM revisit low-confidence, non-skipped rows until the budget stops it."""
    changed = considered = 0
    for r in rows:
        if r["confidence"] != "low" or r["skip_reason"] not in ("", "not_target"):
            continue
        considered += 1
        res = assist.classify(r["Role"], r.get("Category", ""))
        if res.note.startswith("budget"):
            break
        if res.family and res.family != r["family"]:
            r["rule"] += f" | llm:{r['family']}->{res.family}"
            r["family"] = res.family
            r["matched_family"] = res.family
            r["skip_reason"] = "not_target" if res.family == "Other" else ""
            r["source"] = "llm"
            changed += 1
    b = assist.budget
    return {"model": assist.model, "calls": b.calls, "spent_usd": round(b.spent_usd, 6), "max_usd": b.max_usd,
            "max_calls": b.max_calls, "considered": considered, "changed": changed,
            "stopped_reason": b.stopped_reason}


def run(input_path: str, out_dir: str, profile_path: str, assist=None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.perf_counter()
    raw = load_rows(input_path)
    t_load = time.perf_counter()
    rows = classify_rows(raw)
    t_classify = time.perf_counter()

    llm_stats = apply_llm(rows, assist) if assist is not None else None
    t_llm = time.perf_counter()

    profile = load_profile(profile_path)
    for r in rows:
        r["family_label"] = FAMILIES[r["family"]]
        r["fit_score"], r["fit_reasons"] = score(r["Role"], r["family"], r.get("Category", ""),
                                                 r.get("Remote", ""), profile)
    t_score = time.perf_counter()

    fields = list(raw[0].keys()) + ADDED_FIELDS if raw else ADDED_FIELDS
    with open(os.path.join(out_dir, "classified.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    smp = sample.draw_sample(rows)
    sample.write_sample(smp, os.path.join(out_dir, "label_sample.csv"), os.path.join(out_dir, "label_sample_key.csv"))

    stats = {
        "input": os.path.basename(input_path),
        "rows": len(rows),
        "families": dict(Counter(r["family"] for r in rows)),
        "skip_reasons": dict(Counter(r["skip_reason"] or "(none)" for r in rows)),
        "low_confidence_rows": sum(r["confidence"] == "low" for r in rows),
        "load_seconds": round(t_load - t0, 4),
        "classify_seconds": round(t_classify - t_load, 4),
        "llm_seconds": round(t_llm - t_classify, 4),
        "score_seconds": round(t_score - t_llm, 4),
        "profile_summary": profile.summary,
        "llm": llm_stats,
        "sample_rows": len(smp),
    }
    with open(os.path.join(out_dir, "dashboard.html"), "w", encoding="utf-8") as f:
        f.write(dashboard.render(rows, stats))
    stats["total_seconds"] = round(time.perf_counter() - t0, 4)
    with open(os.path.join(out_dir, "run_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    return stats
