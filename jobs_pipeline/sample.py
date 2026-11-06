"""100-row hand-label sample and accuracy scoring.

Sampling is stratified by predicted family with a fixed seed: up to
PER_TARGET_FAMILY rows from each of A-D, the rest from Other. Stratifying
means every family's precision can be checked, but the sample over-represents
A-D relative to the full file, so `score_labels` reports both the raw sample
accuracy and a population-weighted estimate (each stratum weighted by its share
of all rows).

The labeler file is BLIND: it holds the job fields and an empty human_family
column only. Predictions go to a separate key file so they can't bias the labels.
"""
from __future__ import annotations

import csv
import random
from collections import Counter, defaultdict

SAMPLE_SIZE = 100
PER_TARGET_FAMILY = 15
SEED = 20261106
VALID = {"A", "B", "C", "D", "Other"}
BLIND_FIELDS = ["sample_id", "Company", "Role", "Category", "Location", "Remote", "human_family", "notes"]
KEY_FIELDS = ["sample_id", "row_id", "Role", "family", "rule", "confidence", "stratum_size"]


def draw_sample(rows: list[dict], size: int = SAMPLE_SIZE, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    by_fam: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_fam[r["family"]].append(r)
    picked: list[dict] = []
    for fam in ("A", "B", "C", "D"):
        pool = by_fam.get(fam, [])
        picked += rng.sample(pool, min(PER_TARGET_FAMILY, len(pool)))
    rest = by_fam.get("Other", [])
    picked += rng.sample(rest, min(size - len(picked), len(rest)))
    rng.shuffle(picked)
    sizes = Counter(r["family"] for r in rows)
    out = []
    for i, r in enumerate(picked[:size], 1):
        out.append({**r, "sample_id": f"S{i:03d}", "stratum_size": sizes[r["family"]]})
    return out


def write_sample(sample: list[dict], blind_path: str, key_path: str) -> None:
    with open(blind_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=BLIND_FIELDS)
        w.writeheader()
        for r in sample:
            w.writerow({k: r.get(k, "") for k in BLIND_FIELDS} | {"human_family": "", "notes": ""})
    with open(key_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KEY_FIELDS)
        w.writeheader()
        for r in sample:
            w.writerow({k: r.get(k, "") for k in KEY_FIELDS})


def _norm(label: str) -> str:
    t = label.strip()
    return "Other" if t.lower() == "other" else t.upper()


def score_labels(blind_path: str, key_path: str) -> dict:
    with open(key_path, encoding="utf-8") as f:
        key = {r["sample_id"]: r for r in csv.DictReader(f)}
    with open(blind_path, encoding="utf-8") as f:
        labels = list(csv.DictReader(f))
    rows, invalid = [], []
    for r in labels:
        lab = _norm(r.get("human_family", ""))
        if not lab:
            continue
        if lab not in VALID:
            invalid.append((r["sample_id"], r["human_family"]))
            continue
        k = key[r["sample_id"]]
        rows.append({"sample_id": r["sample_id"], "Role": k["Role"], "pred": k["family"], "human": lab,
                     "stratum_size": int(k["stratum_size"])})
    n = len(rows)
    correct = sum(r["pred"] == r["human"] for r in rows)
    # Population-weighted accuracy: weight each labeled row by stratum_size / n_in_stratum
    n_in = Counter(r["pred"] for r in rows)
    wsum = sum(r["stratum_size"] / n_in[r["pred"]] for r in rows)
    wcorrect = sum(r["stratum_size"] / n_in[r["pred"]] for r in rows if r["pred"] == r["human"])
    per_family = {}
    for fam in sorted(VALID):
        p = [r for r in rows if r["pred"] == fam]
        h = [r for r in rows if r["human"] == fam]
        tp = sum(r["pred"] == r["human"] for r in p)
        per_family[fam] = {"predicted": len(p), "labeled": len(h), "precision": tp / len(p) if p else None,
                           "recall": tp / len(h) if h else None}
    confusion = Counter((r["human"], r["pred"]) for r in rows)
    return {
        "labeled": n,
        "of": len(labels),
        "invalid": invalid,
        "accuracy": correct / n if n else None,
        "weighted_accuracy": wcorrect / wsum if wsum else None,
        "per_family": per_family,
        "confusion": {f"{h}->{p}": c for (h, p), c in sorted(confusion.items())},
        "errors": [r for r in rows if r["pred"] != r["human"]],
    }


def report_markdown(res: dict, target: float = 0.90) -> str:
    def pct(x):
        return "n/a" if x is None else f"{x:.1%}"

    lines = ["# Family accuracy on hand-labeled sample", "",
             f"Labeled rows: {res['labeled']} of {res['of']}"]
    if res["labeled"] < res["of"]:
        lines.append(f"**Incomplete:** {res['of'] - res['labeled']} rows not labeled yet; result is provisional.")
    if res["invalid"]:
        lines.append(f"Invalid labels ignored: {res['invalid']}")
    acc = res["accuracy"]
    verdict = "n/a" if acc is None else ("MEETS" if acc >= target else "BELOW")
    lines += ["", f"- Sample accuracy: **{pct(acc)}** ({verdict} {target:.0%} target)",
              f"- Population-weighted estimate: {pct(res['weighted_accuracy'])}", "",
              "| family | predicted | labeled | precision | recall |", "|---|---|---|---|---|"]
    for fam, v in res["per_family"].items():
        lines.append(f"| {fam} | {v['predicted']} | {v['labeled']} | {pct(v['precision'])} | {pct(v['recall'])} |")
    lines += ["", "Confusion (human->predicted): " + ", ".join(f"{k}: {v}" for k, v in res["confusion"].items()), ""]
    if res["errors"]:
        lines += ["## Misclassified rows", "", "| id | role | human | predicted |", "|---|---|---|---|"]
        for e in res["errors"]:
            lines.append(f"| {e['sample_id']} | {e['Role']} | {e['human']} | {e['pred']} |")
    return "\n".join(lines) + "\n"
