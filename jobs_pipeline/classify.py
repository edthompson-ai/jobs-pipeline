"""Rule-based role-family classifier.

Every decision is a regex hit on the job title (plus the CSV Category column for
marketing). The rule that fired is recorded on each row so a reviewer can see
exactly why a row landed where it did.

Order of evaluation (first hit wins):
  1. senior_lead skip   -> Other
  2. sdr_sales skip     -> Other
  3. marketing skip     -> Other
  4. Forward-deployed   -> A
  4b. hand-coding / hardware engineering titles -> Other (not_target)
      (support titles exempt)
  5. Customer Solutions (CSE) -> A  (before generic Solutions)
  6. C Solutions/SE
  7. A Implementation/Onboarding/CSE
  8. D Tech/Product Support
  9. PM / design / legal / finance exclusions -> Other (not_target)
 10. B AI Agent Ops/Automation
 11. anything else      -> Other (not_target)

Skips 1-3 still record the family the title would otherwise have matched
(matched_family), so senior roles in a target family stay visible.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

FAMILIES = {
    "A": "Implementation / Onboarding / CSE",
    "B": "AI Agent Ops / Automation",
    "C": "Solutions / Sales Engineering",
    "D": "Tech / Product Support",
    "Other": "Other / skip",
}


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts), re.I)


SENIOR_LEAD = _rx(
    r"\bvp\b", r"\bvice president\b", r"\b[se]vp\b", r"\bhead of\b", r"^head\b", r"\bhead,",
    r"\bdirector\b", r"\bchief\b", r"\bc[teofrmp]o\b", r"\bprincipal\b", r"\bstaff\b",
    r"\blead\b", r"\bmanaging partner\b", r"\bgeneral manager\b",
    r"\bengineering manager\b", r"\bsenior manager\b", r"\bsr\.? manager\b",
    r"\bteam manager\b", r"^manager\b", r"\bmanager of\b", r"\bleader\b",
)
SDR_SALES = _rx(
    r"\bsdr\b", r"\bbdr\b", r"sales development", r"business development",
    r"account executive", r"\bae\b", r"(?<!technical )account manager", r"inside sales", r"sales rep", r"sales representative",
    r"sales specialist", r"sales associate", r"sales manager", r"account director",
    r"partnerships?\b",
)
# Only applied when no target family matched ("Founding Sales", "Sales, Channel")
SALES_LOOSE = _rx(r"\bsales\b", r"\bchannel\b")
MARKETING = _rx(
    r"marketing", r"marketer", r"\bbrand\b", r"\bcontent\b", r"\bseo\b", r"social media",
    r"communications", r"\bpr\b", r"public relations", r"copywrit", r"\bcreative\b",
    r"\bgrowth\b", r"demand gen", r"lifecycle", r"\bcommunity\b",
)
MARKETING_EXPLICIT = _rx(r"marketing", r"marketer")
FORWARD_DEPLOYED = _rx(r"forward[- ]deploy")
FAMILY_C = _rx(
    r"\bsolutions? engineer", r"\bsolutions? architect", r"\bsolutions? consultant",
    r"sales engineer", r"pre-?sales", r"(?<!business )applications? engineer", r"value engineer",
    r"alliance engineer",
    r"technical (sales|consultant)", r"solution architecture",
)
FAMILY_A = _rx(
    r"implementation", r"onboarding", r"customer success", r"client success",
    r"customer solutions", r"customer engineer", r"technical account manager", r"\btam\b",
    r"deployment", r"\bdeployed engineer\b", r"professional services", r"solutions delivery",
    r"delivery manager", r"customer integrations?", r"^(senior |sr\.? )?integrations? engineer",
    r"customer experience engineer", r"adoption", r"member success",
    r"outcomes manager",
)
FAMILY_D = _rx(
    r"(?<!ground )support engineer", r"technical support", r"tech support", r"product support",
    r"customer support", r"support specialist", r"support analyst", r"support associate",
    r"application support", r"help ?desk", r"service desk", r"\bit support\b",
    r"\bit operations\b", r"\bit specialist\b", r"\bit administrator\b", r"desktop support",
    r"\bit engineer\b", r"systems administrator", r"\btier [123]\b", r"\bl[123]\b.*support", r"support.*\bl[123]\b", r"troubleshoot",
)
EXCLUDE_ENGINEERING = _rx(
    r"software engineer", r"software developer", r"\bdeveloper\b", r"back-?end", r"front-?end",
    r"full[- ]?stack", r"\bsdet\b", r"firmware", r"embedded", r"machine learning", r"\bml\b",
    r"data engineer", r"data scien", r"infrastructure", r"platform engineer", r"devops",
    r"\bsre\b", r"site reliability", r"security (engineer|operations)", r"mechanical", r"electrical",
    r"hardware", r"manufactur", r"robotics", r"controls", r"avionics", r"\brf\b",
    r"test engineer", r"integration (&|and) test", r"\bi&t\b", r"\bqa\b", r"quality",
    r"member of technical staff", r"research", r"scientist", r"technician", r"spacecraft",
    r"flight", r"network automation", r"\bscience\b", r"satellite", r"payload",
    r"mission", r"\btest\b",
)
EXCLUDE_NON_ENGINEERING = _rx(
    r"product manager", r"product owner", r"\bdesigner\b", r"\bdesign\b", r"recruit",
    r"account(ant|ing)", r"counsel", r"attorney", r"paralegal", r"\bnurse\b", r"physician",
)
FAMILY_B = _rx(
    r"automation engineer", r"\bai ops\b", r"\baiops\b", r"agent ops", r"agent operations",
    r"\bai agents?\b", r"\bagentic\b", r"\bagents?\b", r"gtm (operations |systems |ai )?engineer",
    r"sales ?ops engineer", r"revops engineer", r"sales ai engineer",
    r"ai enablement", r"applied ai", r"ai (operations|deployment|strategist|specialist|trainer)",
    r"prompt engineer", r"workflow", r"\bllm\b", r"ai implementation",
)

# Categories where an unmatched title is plausibly a target role -> low confidence
AMBIGUOUS_CATEGORIES = {"Sales & Customer Success", "Operations", "Data & AI"}


@dataclass
class Classification:
    family: str
    matched_family: str
    skip_reason: str
    rule: str
    confidence: str  # "high" | "low"


def _hit(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(0) if m else None


def match_family(title: str) -> tuple[str, str, list[str]]:
    """Return (family, rule, all_families_whose_patterns_hit) ignoring skips."""
    hits = [f for f, p in (("A", FAMILY_A), ("B", FAMILY_B), ("C", FAMILY_C), ("D", FAMILY_D))
            if p.search(title)]
    if h := _hit(FORWARD_DEPLOYED, title):
        return "A", f"A:forward_deployed:'{h}'", hits or ["A"]
    # Coding / hardware titles are excluded before A/C/D so that e.g. "Backend
    # Engineer, Onboarding" or "Integration Engineer, Avionics Test" don't land in A.
    # Support titles are exempt ("Support Engineer (DevTools & AI Reliability)").
    if not FAMILY_D.search(title) and (h := _hit(EXCLUDE_ENGINEERING, title)):
        return "Other", f"exclude:'{h}'", hits
    # Prefer "Customer Solutions" (CSE) -> A before generic Solutions -> C.
    # FAMILY_C's "solutions engineer" otherwise matches the CSE substring.
    if h := _hit(_rx(r"customer solutions"), title):
        return "A", f"A:'{h}'", hits
    if h := _hit(FAMILY_C, title):
        return "C", f"C:'{h}'", hits
    if h := _hit(FAMILY_A, title):
        return "A", f"A:'{h}'", hits
    if h := _hit(FAMILY_D, title):
        return "D", f"D:'{h}'", hits
    if h := _hit(EXCLUDE_NON_ENGINEERING, title):
        return "Other", f"exclude:'{h}'", hits
    if h := _hit(FAMILY_B, title):
        return "B", f"B:'{h}'", hits
    return "Other", "no_match", hits


def classify(title: str, category: str = "") -> Classification:
    title = " ".join(title.split())
    fam, rule, hits = match_family(title)
    # Low confidence: patterns from more than one family hit, or nothing matched
    # in a category where target roles live. These are the rows the optional
    # LLM step may revisit.
    conf = "low" if len(set(hits)) > 1 else "high"
    if rule == "no_match" and category in AMBIGUOUS_CATEGORIES:
        conf = "low"

    if h := _hit(SENIOR_LEAD, title):
        return Classification("Other", fam, "senior_lead", f"skip:senior_lead:'{h}'", "high")
    # "Partner Solutions Engineer" is still SE work, so C is exempt from the sales skip.
    # "Partnerships Solutions Engineer" is BD/sales that happens to say Solutions Engineer.
    if h := _hit(SDR_SALES, title):
        if fam != "C" or _rx(r"\bpartnerships?\b").search(title):
            return Classification("Other", fam, "sdr_sales", f"skip:sdr_sales:'{h}'", "high")
    if fam == "Other" and (h := _hit(SALES_LOOSE, title)):
        return Classification("Other", fam, "sdr_sales", f"skip:sdr_sales:'{h}'", "high")
    if fam == "Other":
        h = _hit(MARKETING, title)
        if h or category == "Growth & Marketing":
            why = f"'{h}'" if h else "category=Growth & Marketing"
            return Classification("Other", fam, "marketing", f"skip:marketing:{why}", "high")
        return Classification("Other", "Other", "not_target", rule, conf)
    # A target-family title that is explicitly a marketing job ("Marketing Automation")
    if h := _hit(MARKETING_EXPLICIT, title):
        return Classification("Other", fam, "marketing", f"skip:marketing:'{h}'", "high")
    return Classification(fam, fam, "", rule, conf)
