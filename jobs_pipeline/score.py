"""Transparent fit scoring.

score = family_base + sum(signal weights that fire), clamped to 0..100.
Each contribution is written to fit_reasons so the number can be audited by hand.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass

AI_SIGNAL = re.compile(r"\bai\b|\bagent|\bagentic\b|\bllm\b|automation|\bgtm (ai )?engineer\b", re.I)
CUSTOMER_FACING = re.compile(
    r"implementation|onboarding|deploy|customer|client|member success|solutions? (engineer|architect|consultant)"
    r"|sales engineer|pre-?sales|support", re.I)
HAND_CODING = re.compile(
    r"software engineer|software developer|\bdeveloper\b|back-?end|front-?end|full[- ]?stack|\bsdet\b|firmware", re.I)
SENIOR_IC = re.compile(r"\bsenior\b|\bsr\.?\b|\b(ii|iii|iv)\b", re.I)


@dataclass
class Profile:
    family_base: dict[str, int]
    signals: dict[str, int]
    summary: str = ""


def load_profile(path: str) -> Profile:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Profile(
        family_base={k: int(v) for k, v in data["family_base"].items()},
        signals={k: int(v) for k, v in data["signals"].items()},
        summary=data.get("candidate", {}).get("summary", ""),
    )


def score(title: str, family: str, category: str, remote: str, profile: Profile) -> tuple[int, str]:
    parts: list[tuple[str, int]] = [(f"family {family}", profile.family_base.get(family, 0))]
    s = profile.signals
    if AI_SIGNAL.search(title):
        parts.append(("ai_signal", s.get("ai_signal", 0)))
    if CUSTOMER_FACING.search(title):
        parts.append(("customer_facing", s.get("customer_facing", 0)))
    if HAND_CODING.search(title):
        parts.append(("hand_coding", s.get("hand_coding", 0)))
    if SENIOR_IC.search(title):
        parts.append(("senior_ic", s.get("senior_ic", 0)))
    if category == "Data & AI":
        parts.append(("data_ai_category", s.get("data_ai_category", 0)))
    if remote.strip().lower() == "yes":
        parts.append(("remote", s.get("remote", 0)))
    raw = sum(v for _, v in parts)
    total = max(0, min(100, raw))
    reasons = "; ".join(f"{name} {v:+d}" for name, v in parts if v != 0 or name.startswith("family"))
    if total != raw:
        reasons += f"; clamped {raw}->{total}"
    return total, reasons
