# repo-eval

[![CI](https://github.com/DPropst-Creatine/repo-eval/actions/workflows/ci.yml/badge.svg)](https://github.com/DPropst-Creatine/repo-eval/actions/workflows/ci.yml)

A deterministic GitHub repository health check. It reports **checkable facts only** —
no AI, no cloning, no invented numbers. The point is to separate *what the repo
is* (facts an API can answer) from *whether you should use it* (judgment a human
or agent makes on top of the facts).

An LLM asked "is this repo any good?" will happily adjust its score to match the
vibe. This tool can't. ~6 GitHub REST API calls, stdlib-only, one file.

## Quick start

```bash
python3 repo_eval.py https://github.com/owner/repo
```

Output is a JSON health report (score, traceable breakdown, red flags). Set
`GITHUB_TOKEN` (a classic PAT, no scopes needed for public repos) to raise the
API rate limit from 60 to 5,000 requests/hour — or pass `--token TOKEN`.

## What it reports

Repository metadata (stars, forks, open issues, contributors, languages,
dependency manifest, license, README size, last push) plus a 0–100 **health
score** built additively — every point is traceable to a named check:

| Check | Points |
|---|---|
| Pushed in the last 30 / 90 days / year | 20 / 14 / 7 |
| Code license declared (SPDX) | 15 |
| LICENSE file present in tree | 5 |
| Test files/directories present | 10 |
| CI workflow configured | 10 |
| README present and substantive (≥500 bytes) | 5 (2 if thin) |
| Dockerfile present | 5 |
| Homepage/demo link set | 5 |
| 3+ contributors | 5 |
| Healthy open-issue ratio (<5% of stars) | 10 (6 / 3 at wider ratios) |

Red flags are verified facts, stated plainly: no license declared, no tests, no
CI, archived, unmaintained (>1 year since push), single contributor, committed
`.env` at root, truncated file tree.

## Read the score correctly

The score measures **adoption-readiness, not test-worthiness**. A low score on a
repo that exactly solves your problem — with a 30-minute reversible test — can
still be a TEST NOW. Stars, recency, and contributor counts are supporting
signals, never the decision. See `docs/agent-evaluation-guide.md` for the
decision framework that sits on top of this tool.

## Using it with an AI agent

`repo_eval.py` is the deterministic layer. `docs/agent-evaluation-guide.md`
defines the qualitative layer: project-fit mapping, strongest established
alternatives, license nuance (code/weights/dependencies separately), local-only
feasibility, evidence quality, four evaluation gates, and verdicts
(TEST NOW / TEST IN ISOLATION / WATCH / STUDY ARCHITECTURE / SAVE FOR LATER /
SKIP). The two layers are reported separately — the guide never lets the agent
invent, override, or "adjust" the deterministic numbers.

## Example

```bash
$ python3 repo_eval.py https://github.com/HunxByts/GhostTrack
{
  "repo": "HunxByts/GhostTrack",
  "health_score": 15,
  "score_breakdown": [
    {"label": "README present and substantive", "points": 5},
    {"label": "Healthy open-issue ratio", "points": 10}
  ],
  "red_flags": [
    "No code license declared — reuse/fork rights unclear.",
    "No test files detected — no automated verification of claims.",
    "No CI pipeline — contribution quality is unmeasured.",
    "Last push 1008 days ago — likely unmaintained."
  ],
  ...
}
```

## License

MIT. See [LICENSE](LICENSE).

## Development

Tests are stdlib-only (`unittest`) and make no network calls:

```bash
python3 -m unittest discover -s tests
```

CI runs them on Python 3.10–3.13 for every push and pull request.
