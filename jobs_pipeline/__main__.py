"""CLI.

  python3 -m jobs_pipeline run [--input s.csv] [--out out] [--llm ...]
  python3 -m jobs_pipeline accuracy [--labels out/label_sample.csv] [--key out/label_sample_key.csv]
"""
from __future__ import annotations

import argparse
import json
import sys

from . import pipeline, sample
from .llm import DEFAULT_MODEL, Budget, LLMAssist, make_real_client


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jobs_pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="classify, score, write CSV + dashboard + label sample")
    r.add_argument("--input", default="s.csv")
    r.add_argument("--out", default="out")
    r.add_argument("--profile", default="profile.toml")
    r.add_argument("--llm", action="store_true", help="enable LLM assist for low-confidence rows (off by default)")
    r.add_argument("--llm-model", default=DEFAULT_MODEL)
    r.add_argument("--llm-max-usd", type=float, default=0.50, help="hard spend cap in USD (default 0.50)")
    r.add_argument("--llm-max-calls", type=int, default=200, help="hard call cap (default 200)")
    r.add_argument("--llm-price-in", type=float, help="USD per 1M input tokens (required for unknown models)")
    r.add_argument("--llm-price-out", type=float, help="USD per 1M output tokens")

    a = sub.add_parser("accuracy", help="score the hand-labeled sample")
    a.add_argument("--labels", default="out/label_sample.csv")
    a.add_argument("--key", default="out/label_sample_key.csv")
    a.add_argument("--report", default="docs/evidence/accuracy.md")

    args = p.parse_args(argv)
    if args.cmd == "run":
        assist = None
        if args.llm:
            assist = LLMAssist(client=make_real_client(), budget=Budget(args.llm_max_usd, args.llm_max_calls),
                               model=args.llm_model, price_in=args.llm_price_in, price_out=args.llm_price_out)
        stats = pipeline.run(args.input, args.out, args.profile, assist)
        print(json.dumps(stats, indent=2))
        return 0

    res = sample.score_labels(args.labels, args.key)
    if res["labeled"] == 0:
        print(f"No labels yet: fill the human_family column in {args.labels} (A/B/C/D/Other) and re-run.")
        return 1
    md = sample.report_markdown(res)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
