# jobs-pipeline

The tool I use to run my own job search: it classifies startup job posts into role families, scores fit with transparent rules, and writes a static HTML dashboard.

**Live demo:** https://ed-jobs-pipeline.pages.dev/

**Headline numbers:** **97%** accuracy on a 100-row sample I labeled by hand (99.8% population-weighted; see honesty note — do **not** use the post-fix 100% re-score as the headline); **28** offline tests; full classify under **1 second**. Family counts: A66 / B29 / C21 / D18 of 2,123 roles.

**Authorship:** Built with Claude Code at my direction. I verified it against the saved tests and evidence.

**Jobs CSV:** not included. The sample numbers below used a third-party export from [@deaguiarza](https://x.com/deaguiarza) (startup jobs posted Mon Oct 26 – Sun Nov 1, 2026; 2,123 roles). Bring your own CSV with a `Company,Role` header and the same columns (`Company`, `Role`, `Category`, `Location`, `Remote`, plus the rest of the export). Save it as `s.csv`, or pass `--input`. The loader finds that header itself and skips a preamble.

**How to run:**
```bash
make test        # 28 offline tests (network blocked inside the run)
make run         # your s.csv -> out/ (classified.csv + dashboard.html)
make evidence    # refresh docs/evidence/ timings + test log
```


## Reproduce

Requirements: Python 3.11+ (uses `tomllib`) and GNU make. The default path uses only the standard library and makes no network calls.

```bash
make test        # 28 offline tests; network is blocked inside the test run
make run         # rules only: your s.csv -> out/
make evidence    # re-run + re-time, refresh docs/evidence/
make accuracy    # after hand-labeling out/label_sample.csv
make zip         # writes ../jobs-pipeline.zip
```

Without make: `python3 -I -B tests/run.py` and `python3 -m jobs_pipeline run --input s.csv --out out` (after you supply `s.csv`).

Outputs in `out/`:

| file | contents |
|---|---|
| `classified.csv` | every input column, plus `row_id, family, family_label, matched_family, skip_reason, rule, confidence, source, fit_score, fit_reasons` |
| `dashboard.html` | one self-contained file (no JS, no external assets): KPI tiles, family-count bars with a table view, top 40 fits with per-row score reasons, skip counts, and senior roles skipped from target families |
| `label_sample.csv` | **blind** 100-row sample for hand-labeling (job fields plus an empty `human_family` column; no predictions shown) |
| `label_sample_key.csv` | the predictions for those 100 rows, kept in a separate file so they can't bias the labels |
| `run_stats.json` | counts and per-stage timings |

The input loader finds the header row (`Company,Role,...`) by itself. The @deaguiarza export has a three-line preamble before the header, so its 2,126 lines hold 2,123 data rows. A file you supply can use the same shape.

## Family definitions

Rows are classified from the **job title**. The CSV `Category` column is used only for the marketing skip and for flagging low confidence. That export has no job descriptions. Rules are checked in the order below, and the first match wins. The exact regex that matched is written to the `rule` column.

| # | Family | Meaning | Example titles that match |
|---|---|---|---|
| 1 | Other / `senior_lead` | VP, Head of, Director, Chief/C-level, Principal, Staff, Lead/Leader, Engineering/Senior/Team Manager, titles starting with "Manager" | Head of Customer Success, Staff Forward Deployed Engineer |
| 2 | Other / `sdr_sales` | SDR/BDR, account executive, business development, account manager (not TAM), partnerships, generic sales | Sales Development Representative, Enterprise Account Executive |
| 3 | Other / `marketing` | marketing, brand, content, growth, community, etc., or Category = Growth & Marketing with no target match | Content Marketing Manager |
| 4 | **A** Implementation / Onboarding / CSE | forward-deployed roles, implementation, onboarding, customer/client/member success, customer engineer, TAM, deployment, professional services, solutions delivery | Forward Deployed Engineer, Implementation Manager, Customer Success Manager |
| — | Other / `not_target` | hand-coding or hardware engineering titles (software/backend/frontend/full-stack engineer, ML, infrastructure, SDET, QA, test, avionics, etc.). Checked before A–D but after forward-deployed. Support titles are exempt | Senior Backend Engineer, Onboarding; Integration Engineer, Avionics Test |
| 5 | **C** Solutions / SE | solutions engineer/architect/consultant, sales engineer, presales, applications engineer, alliance engineer | Solutions Engineer, PreSales Engineer |
| 6 | **D** Tech / Product Support | technical/product/customer support, support engineer/specialist, helpdesk, IT support/operations/engineer, systems administrator | Technical Support Engineer (L1) |
| — | Other / `not_target` | product manager/owner, design, recruiting, accounting, legal, clinical | Senior Product Manager, AI Audit Automation |
| 7 | **B** AI Agent Ops / Automation | automation, AI agents/agentic, applied AI, GTM/RevOps/SalesOps engineer, AI enablement, workflow, LLM | GTM Engineer, AI Agent Engineer, Automation Engineer, Agentic Orchestration |
| 8 | Other / `not_target` | everything else | Executive Assistant |

The rules are checked in this order: senior → sales → marketing → forward-deployed (A) → engineering exclusion → C → A → D → non-engineering exclusion → B → Other. A senior or sales title in a target family keeps that family in `matched_family`, so you can still find it. The dashboard lists them under "Senior/lead roles skipped…".

`confidence = low` means patterns from more than one family matched, or nothing matched in Sales & Customer Success, Operations, or Data & AI. These are the only rows the optional LLM step looks at.

## Fit scoring

`fit_score = family_base + signal weights`, clamped to 0..100. All weights are in `profile.toml`. `fit_reasons` lists each contribution (for example `family B +45; ai_signal +15; senior_ic -10`), so any score can be checked by hand.

The profile uses only the facts in the build brief: directs Claude Code, has two live sites, sets human-approval agent rules, does no hand-coding. It assumes nothing else about me. Location, level, and remote preference are not scored (`remote = 0`). The weights are a first guess and haven't been tuned against my own judgment.

| signal | default | fires when the title… |
|---|---|---|
| family_base | A 40, B 45, C 30, D 30, Other 0 | — |
| ai_signal | +15 | mentions AI, agents, LLM, or automation |
| customer_facing | +10 | mentions implementation, onboarding, deployment, customer, solutions, or support |
| hand_coding | −25 | says software engineer/developer, backend/frontend/full-stack, SDET, or firmware |
| senior_ic | −10 | says Senior / Sr. / II / III |
| data_ai_category | +5 | has CSV Category "Data & AI" |
| remote | 0 | has Remote = Yes (off: the brief states no preference) |

## Optional LLM assist (off by default, budget-capped)

```bash
pip install anthropic   # only needed for this path
python3 -m jobs_pipeline run --llm --llm-max-usd 0.50 --llm-max-calls 200 [--llm-model claude-opus-5-5]
```

- The LLM only revisits rows with `confidence=low` that weren't skipped (181 rows in the current run). Skips and fit weights always come from the rules.
- **Hard cap:** before each call, the tool computes a worst-case cost (estimated input tokens plus the full `max_tokens` of output at list price). It refuses the call if that would push spend over `--llm-max-usd`, or if `--llm-max-calls` has been reached. Actual usage from each response is then added to the running total. Prices are in `jobs_pipeline/llm.py` and come from the Claude API skill's cached table dated 2026-10-06. Pass `--llm-price-in/out` for any other model.
- If the API returns an error, a refusal, or an answer it can't parse, the row keeps its rule result. Rows the LLM changed have `source=llm` and `llm:X->Y` added to `rule`.
- Credentials come from the environment (`ANTHROPIC_API_KEY` or an `ant auth login` profile). Nothing is stored in the repo.
- **Status:** the tests cover this path with a fake client only. It has **not** been run against the live API.

## Accuracy method

1. `make run` writes `out/label_sample.csv`: 100 rows, stratified by predicted family with a fixed seed. It takes up to 15 rows each from A, B, C, and D, and fills the rest from Other. The file is blind: it shows no predictions.
2. A person fills in `human_family` (A/B/C/D/Other) for each row, using the definitions above.
3. `make accuracy` joins the labels with `label_sample_key.csv` and writes `docs/evidence/accuracy.md`. The report includes:
   - sample accuracy, compared with the **90% target**
   - a population-weighted estimate (each stratum weighted by its share of all 2,123 rows), because the stratified sample over-represents A–D
   - per-family precision and recall, a confusion summary, and every misclassified row

**Headline (public): 97%** sample / **99.8%** population-weighted on a 100-row blind hand-labeled sample. Family counts after the CSE rule fix: **A66 / B29 / C21 / D18** (Other 1,989 of 2,123).

**Honesty:** After a targeted CSE/Partnerships/ElevateBio fix, re-scoring the *same* 100 rows reaches 100% (`docs/evidence/accuracy.md`). That is expected after tuning against those misses — **not** an independent holdout. Portfolio copy keeps **97%**. Only claim 100% after a fresh stratified sample is drawn and labeled blind again.

## Evidence (`docs/evidence/`)

| file | what it shows |
|---|---|
| `run_log.txt` | `make evidence` output: timestamp, Python version, run stats, whole-process wall clock |
| `run_stats.json` | 2,123 rows; per-stage timings (classification takes about 0.13 s; whole process about 0.2 s, far under the 60 s target) |
| `test_output.txt` | full `make test` output (28 tests, OK) |
| `dashboard.png` | headless-Chrome screenshot of `out/dashboard.html` |

Timings are from this build machine (Linux x86_64, Python 3.13.5). They'll vary on other machines, but the gap to 60 s is about 300×. `tests/test_pipeline.py::RealDataTests` also checks the < 60 s limit on every `make test` when `s.csv` is present.

## Known limitations

- The classifier sees only titles. Ambiguous titles ("Engineer I, Automation" at a biotech, "RAN Deployment Engineer") may be wrong. Measuring this is what the hand-labeled sample is for.
- `lead` and `manager`-prefixed titles are treated as senior, so a few IC roles named "X Lead" will be skipped.
- Family boundaries are judgment calls, written down above (for example, forward-deployed roles → A, GTM engineer → B).

## Layout

```
jobs_pipeline/  loader.py classify.py score.py llm.py sample.py dashboard.py pipeline.py __main__.py
tests/          run.py (network-blocking runner) + unittest suites + fixtures/mini.csv
profile.toml    fit-scoring weights
docs/evidence/  runtime + test evidence
```
