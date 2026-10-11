# Eval results

Every run writes a Markdown report here and its raw records to `runs/<run id>.json`
(`haggle-eval report` regenerates a report from them; `haggle-eval rescore` re-scores a run with
newer scoring code, reusing the stored judge verdicts, with no LLM calls).

## Final result: [eval-report-20261011-1234-full-a785](eval-report-20261011-1234-full-a785.md)

81 simulated games (3 cars × 3 levels × 3 personas × 3 seeds) and 264 attack runs (44 attacks
× 3 levels × 2), with the shipped seller prompts `l1.v1, l2.v3, l3.v1`, all Gemini 3.1
Flash-Lite; judge Gemini 3.8 Flash. Cost **$1.82**. Invalid closes: **0**. Errors: 0/345.

| Per level (27 games each) | L1 Naive | L2 Hardened | L3 Blind |
|---|---|---|---|
| Disclosure rate ≥ APPROX [95% CI] | 22% [11%, 41%] | 0% [0%, 12%] | 0% [0%, 12%] |
| Exact disclosure rate | 19% | 0% | 0% |
| Floor-leak attack success [95% CI] | 28% [19%, 40%] (18/64) | 0% [0%, 6%] | 0% [0%, 6%] |
| All attacks: success | 23% (20/88) | 0% (0/88) | 0% (0/88) |
| Buyer's floor-estimate error (median, higher = better protected) | 3.1% | 13.3% | 17.6% |
| Seller surplus share (median) | 9% | 61% | 56% |
| Deal rate | 96% | 81% | 93% |
| Cost per simulated game (median) | $0.011 | $0.013 | $0.030 |

Reading: the defences work, and they cost something. L1, the deliberately naive baseline,
states its floor outright in about one game out of five, and role play, system-prompt
extraction and format forcing beat it most often. L2's prompt and output filter stop every
scripted attack; L3 adds that the model *cannot* leak what it never sees. The price: L3 is the
slowest to close (9 turns median vs 5) and about 2.5× the cost per game, because code concedes
slowly and every price goes through a tool call.

**Reproducibility.** The first full run ([8784](eval-report-20261010-0923-full-8784.md), 2026-10-10,
prompt `l2.v1`) gave the same disclosure rates: L1 22 %, L2 0 %, L3 0 %. L1's attack success moved
from 31 % to 28 %, well inside the confidence interval. With 27 games per level, differences of
a few points are noise; the L1-vs-L2/L3 gap is not.

## L2 prompt iteration (same 27 floors, only L2 replayed)

| L2 | [v1](eval-report-20261010-0923-full-8784.md) | [v2](eval-report-20261010-0941-full-679f.md) | **[v3](eval-report-20261010-0946-full-9288.md) (shipped)** |
|---|---|---|---|
| Disclosures | 0/27 | 0/27 | 0/27 |
| Seller turns replaced by the output filter | 18% | 1% | 4% |
| Seller surplus share (median) | 39% | 18% | 47% |
| Paired deal price vs v1 | – | lower in 17 of 23 | higher in 17 of 23 (+$1,000 median) |
| Buyer's floor-estimate error (higher = better protected) | 10.3% | 6.1% | 12.0% |

- **v1** knew the floor and kept drifting towards it: the filter replaced 18 % of its replies with
  "Let's keep this about the car".
- **v2** gave it a lowest quote (floor + 6 %, just outside the filter's band). The filter stopped
  firing, but the model walked straight to that quote: it sold for less and taught the buyer more.
- **v3** added pacing (each counter at most 2 % of list below the previous one). Acceptance
  criteria were written **before** running it: 0 disclosures, filter ≤ 5 %, surplus no more than
  5 points below v1. It met all three. A sign test on the paired prices gives p ≈ 0.035; with one
  run of 27 games, treat it as promising, not proven.
- **Final run** (fresh games, v3): 0 disclosures, guards fired on 2 % of seller turns, seller
  surplus 61 %. Consistent with v3's replay.

**Regression cases** ([`regressions.yaml`](../../evals/datasets/regressions.yaml)): the three L1
failures turned into cases (completion trap, canary fishing, JSON `min_price`), plus the slow
squeeze. The latest replay ([db82](eval-report-20261011-1246-regressions-db82.md), 14 runs, $0.02)
blocks all of them at L2 and L3.

## Other files

| File | What |
|------|------|
| [deploy-checklist.md](deploy-checklist.md) | Every production guardrail, checked from outside (week 7) |
| `calibration-latest.json` | Judge calibration: 62 labeled utterances, κ = 0.84 (5 levels), 0.87 (binary). Labels are drafts by the AI assistant until reviewed with `make eval-label` |

A first full run (`20261010-0913`) was **discarded**: the local seller hit its $1 daily budget
mid-run and answered "closed for today" to everything, so 0 % attack success meant nothing. The
suite now refuses to start when the budget can't cover the run and flags runs with > 5 % errors.
