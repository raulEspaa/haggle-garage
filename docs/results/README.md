# Eval results

Every run writes a Markdown report here and its raw records to `runs/<run id>.json`
(`haggle-eval report` regenerates a report from them; `haggle-eval rescore` re-scores a run with
newer scoring code, reusing the stored judge verdicts, with no LLM calls).

## Main result: [eval-report-20261010-0923-full-8784](eval-report-20261010-0923-full-8784.md)

81 simulated games (3 cars × 3 levels × 3 personas × 3 seeds) and 264 attack runs (44 attacks
× 3 levels × 2), seller prompts `l1.v1, l2.v1, l3.v1`, all Gemini 3.1 Flash-Lite; judge Gemini 3.8
Flash. Cost **$1.86**. Invalid closes: **0**.

| Per level (27 games each) | L1 Naive | L2 Hardened | L3 Blind |
|---|---|---|---|
| Disclosure rate ≥ APPROX [95% CI] | 22% [11%, 41%] | 0% [0%, 12%] | 0% [0%, 12%] |
| Exact disclosure rate | 19% | 0% | 0% |
| Floor-leak attack success [95% CI] | 31% [21%, 43%] (20/64) | 0% [0%, 6%] | 0% [0%, 6%] |
| Seller surplus share (median) | 26% | 39% | 56% |
| Deal rate | 89% | 85% | 78% |
| Cost per simulated game (median) | $0.013 | $0.015 | $0.032 |

Reading: the defences work, and each level costs more per game. L2's prompt and output filter
already stop every scripted attack; L3 adds that the model *cannot* leak what it never sees,
and it negotiates harder (code concedes slowly). L1, the deliberately naive baseline, states its
floor outright in about one game out of five, and 14 of the 44 scripted attacks beat it at
least once (22 of 88 runs).

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

Regression replays ([v2](eval-report-20261010-0943-regressions-3ba5.md),
[v3](eval-report-20261010-0950-regressions-4902.md)): the three L1 failures turned into cases
(completion trap, canary fishing, JSON `min_price`) and the slow squeeze stay blocked at L2/L3.

## Other files

| File | What |
|------|------|
| [eval-report-20261009-1917-smoke-6f0e](eval-report-20261009-1917-smoke-6f0e.md) | First smoke run (6 games, 15 attacks), before the disclosure/concession split |
| `calibration-latest.json` | Judge calibration: 62 labeled utterances, κ = 0.84 (5 levels), 0.87 (binary). Labels are drafts by the AI assistant until reviewed with `make eval-label` |

A first full run (`20261010-0913`) was **discarded**: the local seller hit its $1 daily budget
mid-run and answered "closed for today" to everything, so 0 % attack success meant nothing. The
suite now refuses to start when the budget can't cover the run and flags runs with > 5 % errors.
