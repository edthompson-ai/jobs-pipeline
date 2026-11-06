"""Static single-file HTML dashboard. No JS libraries, no external requests.

Colors follow the reference palette in the dataviz skill: one series (family
counts) uses series-1 blue; text uses ink tokens; dark mode has its own steps.
"""
from __future__ import annotations

from collections import Counter
from html import escape

from .classify import FAMILIES

CSS = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--bar:#2a78d6}
@media (prefers-color-scheme:dark){:root{--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--bar:#3987e5}}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--page);color:var(--ink);
font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.sub{color:var(--ink2);margin:0 0 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--grid);border-radius:8px;padding:12px 14px}
.tile .v{font-size:26px;font-weight:600}.tile .l{color:var(--ink2);font-size:12px}
.card{background:var(--surface);border:1px solid var(--grid);border-radius:8px;padding:16px}
.bars{display:grid;grid-template-columns:max-content 1fr max-content;gap:8px 12px;align-items:center}
.bars .lab{color:var(--ink2)}.bars .val{font-variant-numeric:tabular-nums;color:var(--ink)}
.track{border-left:1px solid var(--axis);height:20px;display:flex;align-items:center}
.bar{height:16px;background:var(--bar);border-radius:0 4px 4px 0;min-width:2px}
.bar:hover{filter:brightness(1.15)}
table{border-collapse:collapse;width:100%;background:var(--surface)}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink2);font-weight:600;font-size:12px}td.n{font-variant-numeric:tabular-nums;text-align:right}
.reasons{color:var(--muted);font-size:12px}details{margin-top:8px}a{color:inherit}
footer{margin-top:32px;color:var(--muted);font-size:12px}
"""


def _table(rows: list[dict], cols: list[tuple[str, str]], numeric: set[str] = frozenset()) -> str:
    head = "".join(f"<th>{escape(label)}</th>" for _, label in cols)
    body = []
    for r in rows:
        tds = []
        for key, _ in cols:
            v = str(r.get(key, ""))
            if key == "Role" and r.get("Apply link", "").startswith(("http://", "https://")):
                cell = f'<a href="{escape(r["Apply link"], quote=True)}" rel="noopener">{escape(v)}</a>'
            elif key == "fit_reasons":
                cell = f'<span class="reasons">{escape(v)}</span>'
            else:
                cell = escape(v)
            cls = ' class="n"' if key in numeric else ""
            tds.append(f"<td{cls}>{cell}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render(rows: list[dict], stats: dict, top_n: int = 40) -> str:
    fam_counts = Counter(r["family"] for r in rows)
    skip_counts = Counter(r["skip_reason"] for r in rows if r["skip_reason"])
    total = len(rows)
    target = [r for r in rows if r["family"] != "Other"]
    top = sorted(target, key=lambda r: (-int(r["fit_score"]), r["Company"], r["Role"]))[:top_n]
    senior_in_family = [r for r in rows if r["skip_reason"] == "senior_lead" and r["matched_family"] != "Other"]

    tiles = [
        ("Roles classified", f"{total:,}"),
        ("Target families A-D", f"{len(target):,}"),
        ("Skipped (senior / SDR-sales / marketing)", f"{sum(v for k, v in skip_counts.items() if k != 'not_target'):,}"),
        ("Classify runtime", f"{stats.get('classify_seconds', 0):.2f}s"),
    ]
    tiles_html = "".join(f'<div class="tile"><div class="v">{escape(v)}</div><div class="l">{escape(l)}</div></div>'
                         for l, v in tiles)

    peak = max(fam_counts.values()) if fam_counts else 1
    bars = []
    for fam, label in FAMILIES.items():
        n = fam_counts.get(fam, 0)
        share = n / total if total else 0
        tip = f"{fam} {label}: {n} roles ({share:.1%})"
        bars.append(
            f'<div class="lab">{escape(fam)} · {escape(label)}</div>'
            f'<div class="track" title="{escape(tip, quote=True)}"><div class="bar" '
            f'style="width:{n / peak * 100:.1f}%" aria-label="{escape(tip, quote=True)}"></div></div>'
            f'<div class="val">{n:,}</div>')
    count_rows = [{"family": f, "label": l, "n": fam_counts.get(f, 0),
                   "pct": f"{fam_counts.get(f, 0) / total:.1%}" if total else ""} for f, l in FAMILIES.items()]
    skip_rows = [{"reason": k, "n": v} for k, v in skip_counts.most_common()]

    llm = stats.get("llm")
    llm_line = ("LLM assist: off (rules only)." if not llm else
                f"LLM assist: {llm['calls']} calls, ${llm['spent_usd']:.4f} of ${llm['max_usd']:.2f} cap, "
                f"{llm['changed']} rows changed. {escape(llm.get('stopped_reason') or '')}")

    cols_top = [("fit_score", "Fit"), ("family", "Fam"), ("Role", "Role"), ("Company", "Company"),
                ("Location", "Location"), ("Remote", "Remote"), ("fit_reasons", "Why this score")]
    cols_skip = [("matched_family", "Would be"), ("Role", "Role"), ("Company", "Company"), ("rule", "Rule")]

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Startup roles: family &amp; fit dashboard</title><style>{CSS}</style></head><body>
<h1>Startup roles: family &amp; fit</h1>
<p class="sub">Source: {escape(stats.get('input', ''))} · {total:,} roles · scoring profile: {escape(stats.get('profile_summary', ''))}</p>
<div class="tiles">{tiles_html}</div>

<h2>Roles by family</h2>
<div class="card"><div class="bars">{''.join(bars)}</div>
<details><summary>Table view</summary>{_table(count_rows, [("family", "Family"), ("label", "Definition"), ("n", "Roles"), ("pct", "Share")], {"n", "pct"})}</details></div>

<h2>Top {len(top)} fits (families A-D, highest score first)</h2>
<p class="sub">Score = family base + title signals, 0-100. Weights live in profile.toml; reasons show every contribution.</p>
{_table(top, cols_top, {"fit_score"})}

<h2>Skips</h2>
{_table(skip_rows, [("reason", "Skip reason"), ("n", "Roles")], {"n"})}
<details><summary>Senior/lead roles skipped that otherwise match a target family ({len(senior_in_family)})</summary>
{_table(sorted(senior_in_family, key=lambda r: (r["matched_family"], r["Role"])), cols_skip)}</details>

<footer>{llm_line}<br>Built with Claude Code at my direction.</footer>
</body></html>
"""
