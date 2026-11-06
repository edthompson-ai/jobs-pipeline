"""Optional LLM assist for low-confidence rows, with a hard budget cap.

Off by default. When enabled it only revisits rows the rules marked
confidence="low" and that were not skipped (senior/SDR/marketing skips are
always deterministic). It never changes fit-score weights.

Budget enforcement: before every call we compute a worst-case cost for that
call (estimated input tokens + max_tokens of output, at list price). If
spent + worst_case would exceed max_usd, or max_calls is reached, we stop and
leave the remaining rows with their rule result. After each call the actual
usage reported by the API is added to `spent_usd`.

The client is injected, so tests use a fake and never touch the network. The
real client is created lazily and only if `anthropic` is installed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# USD per million tokens (input, output). Anthropic list prices as cached in
# the claude-api skill on 2026-10-06; check current pricing before relying on them.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 1024  # room for adaptive thinking + a one-word answer

SYSTEM_PROMPT = """You classify startup job titles into one role family.
A = Implementation / Onboarding / Customer Success / Customer Solutions Engineer (CSE) / Customer & Forward-Deployed Engineering
B = AI Agent Ops / Automation (operating or building AI agents and automated workflows, GTM engineering)
C = Solutions / Sales Engineering (solutions engineer/architect/consultant, presales)
D = Tech / Product Support (technical, product, customer, or IT support)
Other = anything else (software/hardware engineering, product management, design, sales, marketing, finance, legal, etc.)
Answer with exactly one of: A, B, C, D, Other."""

ANSWER = re.compile(r"\b(A|B|C|D|Other)\b")


@dataclass
class Budget:
    max_usd: float
    max_calls: int
    spent_usd: float = 0.0
    calls: int = 0
    stopped_reason: str = ""

    def can_afford(self, worst_case_usd: float) -> bool:
        if self.calls >= self.max_calls:
            self.stopped_reason = f"max_calls {self.max_calls} reached"
            return False
        if self.spent_usd + worst_case_usd > self.max_usd:
            self.stopped_reason = f"max_usd ${self.max_usd:.2f} would be exceeded"
            return False
        return True


@dataclass
class LLMResult:
    family: str | None
    note: str


@dataclass
class LLMAssist:
    client: object
    budget: Budget
    model: str = DEFAULT_MODEL
    price_in: float | None = None
    price_out: float | None = None
    log: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.price_in is None or self.price_out is None:
            if self.model not in PRICES:
                raise ValueError(f"No price for {self.model}; pass --llm-price-in/--llm-price-out")
            self.price_in, self.price_out = PRICES[self.model]

    def _cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.price_in + tokens_out * self.price_out) / 1_000_000

    def classify(self, title: str, category: str) -> LLMResult:
        user = f"Job title: {title}\nCSV category: {category}"
        # Upper-bound estimate: ~1 token per 3 chars, plus fixed overhead.
        est_in = (len(SYSTEM_PROMPT) + len(user)) // 3 + 50
        if not self.budget.can_afford(self._cost(est_in, MAX_TOKENS)):
            return LLMResult(None, f"budget: {self.budget.stopped_reason}")
        self.budget.calls += 1
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except Exception as e:  # network/API failure: keep the rule result
            self.log.append({"title": title, "error": type(e).__name__})
            return LLMResult(None, f"error: {type(e).__name__}")
        usage = getattr(resp, "usage", None)
        cost = self._cost(getattr(usage, "input_tokens", est_in), getattr(usage, "output_tokens", MAX_TOKENS))
        self.budget.spent_usd += cost
        if getattr(resp, "stop_reason", "") == "refusal":
            self.log.append({"title": title, "refusal": True, "usd": cost})
            return LLMResult(None, "refusal")
        text = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        m = ANSWER.search(text)
        self.log.append({"title": title, "answer": text.strip()[:40], "usd": round(cost, 6)})
        if not m:
            return LLMResult(None, "unparseable")
        return LLMResult(m.group(1), "ok")


def make_real_client():
    """Create the Anthropic client. Credentials come from the environment
    (ANTHROPIC_API_KEY or an `ant auth login` profile); nothing is stored here."""
    import anthropic  # imported lazily so the default path has no dependency

    return anthropic.Anthropic()
