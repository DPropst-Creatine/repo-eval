# Agent Evaluation Guide

How to turn `repo_eval.py`'s deterministic report into a decision-ready
evaluation. Written for AI agents, usable by humans.

Two layers, kept separate:

1. **Deterministic** — `repo_eval.py` reports checkable facts only. Never let an
   LLM invent, override, or "adjust" these numbers.
2. **Qualitative** — the agent judges fit: problem solved, strongest established
   alternative, licensing nuance, local-only feasibility, and evidence quality.

## Workflow

1. **Parse the link.** If it isn't a github.com repo URL, say so — don't guess.
2. **Run `repo_eval.py`.** On error, surface the message plainly and stop. On
   rate-limit, set `GITHUB_TOKEN` or wait for the reset.
3. **Classify the repo type** before interpreting the score: software library,
   guide/docs, hardware build guide, dataset, or model weights. The software
   signals (tests, CI, contributors) apply fully to software; for guides and
   build docs, weight README substance, freshness, and author credibility
   instead — and state explicitly which frame the verdict uses.
4. **Qualitative layer.** For adoption candidates, answer:
   - What specific problem does it solve (one sentence, no marketing copy)?
   - Which of *your* active projects does it map to, if any? (Bring your own
     project list — search by the underlying engineering problem, not just
     project names.)
   - The strongest established alternative — including mature, non-AI, boring
     options. A 6-year-old maintained library beats a new unproven one if it
     solves the problem.
   - Its actual advantage over that alternative — measured, not claimed.
   - **License check:** code, model weights, and dependencies separately. A MIT
     repo pulling a non-commercial model is not MIT in practice. Flag
     non-commercial clauses (e.g. CC-BY-NC) explicitly and keep them out of
     commercial workflows.
   - Local-only execution feasibility and network dependencies (phoning home,
     required cloud accounts, telemetry).
   - **Evidence quality:** documented (maintainer claims) vs independently
     tested (benchmarks, third-party reproduction) vs actually implemented
     (you ran it).
   - Record the four evaluation gates, each as PASS / FAIL / NOT TESTED:
     - **Source verified** — named implementation files inspected; what the
       code actually does, including gaps between claims and behavior.
     - **Tests reproduced** — tests run independently, with negative controls
       (e.g. deliberately planted false successes).
     - **Comparative value** — measured against the incumbent tool or a
       realistic alternative, not a strawman or no baseline.
     - **Deployment readiness** — maintenance, security posture, integration
       effort, and operational safeguards assessed.
   - A compelling architecture alone never earns TEST NOW. That requires gates
     1–3 to pass, or a TEST IN ISOLATION plan designed to pass them.
5. **Verdict:** TEST NOW / TEST IN ISOLATION / WATCH / STUDY ARCHITECTURE /
   SAVE FOR LATER / SKIP, with one concrete proposed test when TEST NOW or
   TEST IN ISOLATION. TEST IN ISOLATION means: implementation promising but
   immature or risky — sandboxed evaluation only, no production use, no
   replacement of working systems.

## Output contract

- One-line verdict + health score, with the 3–5 most decisive breakdown lines.
- Red flags from the tool, verbatim — these are verified facts.
- Fit assessment: project mapping, strongest alternative, actual advantage,
  license (code/weights/deps), local-only feasibility, evidence quality.
- The four evaluation gates, each marked PASS / FAIL / NOT TESTED.
- Proposed test (TEST NOW / TEST IN ISOLATION) or the skip reason.

## Rules

- Report the deterministic layer and the qualitative layer separately. Never
  blend them into one number.
- Novelty, stars, and recency are supporting signals only. A boring, maintained
  library that solves the problem outranks a flashy new one.
- The health score measures adoption-readiness, not test-worthiness. TEST NOW
  vs WATCH hinges on project relevance plus how cheap and decisive a hands-on
  test is. Never let maturity signals override relevance.
- Discovery is not deployment: TEST NOW means worth hands-on testing, never
  install or integrate on anyone's behalf.
- Public repos only. When the tool's output contradicts a first impression,
  trust the tool and explain why.
