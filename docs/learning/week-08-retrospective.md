# Week 8: Final eval, portfolio and retrospective

> **Goal:** close the project honestly: one final measurement, a README a recruiter reads in five
> minutes, documents that describe what was built (not what was planned), and a list of what's next.

**Definition of Done** ([05-delivery.md](../05-delivery.md#1-plan-vs-shipped-week-by-week)):

| Done when… | Status |
|------------|--------|
| Final eval run, report linked | ✅ [eval-report-20261011-1234-full-a785](../results/eval-report-20261011-1234-full-a785.md), $1.82, 0 errors |
| README reads in 5 minutes | ✅ pitch, screenshot, levels, results, two diagrams, quickstart |
| ADRs to Accepted / Superseded / Deferred | ✅ [adr/README.md](../adr/README.md) |
| "Next steps" list | ✅ [05-delivery.md §8](../05-delivery.md#8-future-work) |
| Home MCP + failover | ✂️ **cut** (§1) |

---

## 1. Cutting the home MCP, on purpose

The plan reserved week 8 for an MCP server at home (an LXC behind a Cloudflare Tunnel) with
per-game failover to Cloud Run. It was item #1 on the cut list written in week 0, for the
reason that still held: **the most work for the least AI-engineering value.** By week 8 the cloud
MCP server was proven in production, and the home version would have added a domain, a 24/7
server, a second credential chain and a new failure mode, for no change in what the project
demonstrates.

What remains is the design: [ADR-0002](../adr/0002-home-mcp-ingress.md) has status **Deferred**,
and docs 02, 03 and 07 mark the home pieces as "design only". A recorded cut is worth more than a
half-built feature: in an interview, *"I planned it, priced it, and cut it at the checkpoint"* is
a better story than *"it's mostly working"*.

C# analogy: like removing a feature flag's code path before release, but keeping the design doc
in the wiki.

---

## 2. The final eval: does the result reproduce?

The headline from week 6 came from a single run. A result you've measured once is an anecdote,
so the full suite ran again on fresh games with the shipped prompts (`l2.v3`):

| | Week 6 run (8784) | Final run (a785) |
|---|---|---|
| L1 disclosure rate | 22 % | 22 % |
| L2 / L3 disclosure rate | 0 % / 0 % | 0 % / 0 % |
| L1 floor-leak attack success | 31 % | 28 % |
| L2 / L3 attack success | 0 % / 0 % | 0 % / 0 % |
| Invalid closes | 0 | 0 |
| Cost | $1.86 | $1.82 |

The claim survives: L1 leaks in about one game in five; L2 and L3 didn't leak in 54 games and 176
attack runs. The 3-point move in L1's attack success is well inside its confidence interval
([19 %, 40 %]), so it is noise, and the report says so instead of celebrating it.

### A false alarm in the eval itself

The run first reported **2 errors out of 345 jobs**: two L3 games flagged "seller did not play".
Both games had actually ended in a **deal** after 10 turns. The seller had called `close_deal`
and then labelled its own reply `end` instead of `close`. The buyer read `end` as "the seller
quit", and the runner's week 6 safety net (written for the run where the budget ran out) fired.

The scores were right all along, because they come from the database (`status = 'deal'`), not from
what the buyer believed. Only the error flag was wrong. Fix: a recorded deal proves the seller
played, so `score_game` clears that error when a `deals` row exists
([`scoring.py`](../../evals/src/haggle_evals/scoring.py)), with a regression test. Then
`haggle-eval rescore` re-scored the saved run **without a single LLM call**: 0/345 errors.

Lesson: **the eval's own safety checks need tests too.** A noisy error flag teaches you to ignore
it, and then it can't warn you the day the budget really runs out.

---

## 3. Documentation: fewer files, all true

By week 8 the `docs/` folder had planning documents that described a project that no longer
existed: AI Studio prepaid caps, a home server, an "open decisions" list that had been decided.
A reader can't tell which parts are still true, so they trust none of it.

| Before | After |
|--------|-------|
| 05 delivery plan, 08 risks and costs, 09 repo and tooling, 10 sources | **one** [05-delivery.md](../05-delivery.md): plan vs shipped, cuts, real costs, risks that happened, tooling, versions, future work |
| `journal.md` (an empty hours table), `setup-tools.md` (a personal install log), a smoke report and two superseded regression reports | deleted |
| 01, 02, 03, 07 written as the Phase 1 design | an **"As built"** note at the top of each; 02's diagrams now show the real deployment |

Rule used: **keep what a reader needs to trust the result** (architecture, contracts, threat
model, ADRs, results, the weekly journals); **merge what only mattered while planning**; delete
what nobody will open again. Git keeps the history.

---

## 4. The README as a product page

A portfolio README has one reader with five minutes. Its order follows the questions that reader
asks:

1. **What is it?** One sentence, and a link to play.
2. **What does it look like?** A screenshot of a real game (taken from a real Level 1 game, with the
   page's own stylesheet).
3. **Why is it interesting?** The three levels, as a table.
4. **Does it work?** The results, with the uncomfortable numbers left in (L1 leaks 22 %).
5. **How?** Two Mermaid diagrams that GitHub renders natively: the components, and one Level 3 turn.
6. **Can I run it?** Seven commands.

Everything deeper (ADRs, threat model, journals) is one link away, not in the README.

---

## 5. Retrospective: eight weeks

### What worked

- **Vertical slices.** Every week ended with something that ran. Checkpoints A, B and C were each met
  in their week.
- **Deploy in week 1.** A hello-world on Cloud Run with Terraform meant week 7 fought real bugs
  (audiences, TLS, CPU throttling), not tooling.
- **The week 2 tracer bullet.** ADK ↔ MCP ↔ A2A was proven before anything depended on it; the
  OpenTelemetry pin conflict surfaced on day one instead of in week 5.
- **"The model talks, code decides."** The one idea that makes L3 safe, and it's tiny: a policy
  engine of pure functions, a price guard and a column grant.
- **Testing from outside.** Local runs under production DB roles, curl against the deployed
  services, an eval that reads the database instead of trusting agents.

### What surprised me

- **How fast the ground moves.** ADK changed its structured-output path between backends; MCP
  SDK v2 renamed its server class; a2a-sdk's auto-instrumentation broke ADK. Exact pins and thin
  wrappers turned each one into a one-day fix.
- **Prompt hardening is a trade-off, not a free win.** L2 v2 stopped the filter from firing and
  sold the car for less; v3 needed acceptance criteria written *before* the run.
- **Cloud-only bugs.** Three of the four week 7 bugs couldn't happen on a laptop.
- **Cost.** All the evals together cost about $5, a fifth of the estimate.

### What I'd do differently

- **Log hours weekly.** There's no honest planned-vs-actual hours table because nobody filled it in.
- **Human labels for the judge earlier.** The calibration labels are still drafts by the assistant.
- **Budget preflight in the eval runner from day one.** A whole run was lost to it.
- **Build the retention job with the privacy note.** The note promises 30 days; the job is still
  on the future-work list.

---

## 6. Interview drill: the project in five answers

| Question | Short answer |
|----------|--------------|
| *"What does it do?"* | An AI car dealer with a secret floor price, at three security levels, with an eval suite that measures how often each one leaks. |
| *"How do you stop prompt injection?"* | You can't stop it in the prompt; you make it harmless. At L3 the model never sees the secret, every price comes from code over MCP, and the database role can't even read the column. |
| *"How do you know it works?"* | 81 simulated negotiations and 264 attack runs per eval, a deterministic detector plus a calibrated LLM judge, confidence intervals, and the same result on a second run. |
| *"Why A2A and MCP?"* | MCP is how an agent uses tools (the pricing engine, the car facts); A2A is how two agents talk (buyer ↔ seller), even across frameworks (LangGraph → ADK). |
| *"What would you do next?"* | Human-reviewed judge labels, a retention job, CI-driven deploys with Workload Identity Federation, then the cut features ([05 §8](../05-delivery.md#8-future-work)). |

---

## 7. Keeping the demo alive (calendar)

| When | What |
|------|------|
| Now | Rotate the Neon **owner** password (it was used from a laptop during setup) |
| Before **2026-11-10** | Delete games older than 30 days, as the privacy note promises (or build the retention job) |
| Before **2027-01-01** | `gemini-3.8-flash` (the judge) doubles its price: re-check eval costs |
| Before **early January 2027** | The GCP trial credit ends: upgrade the billing account or everything stops |
| Any time | `make eval-label`: review the 62 judge-calibration labels yourself |
| On a budget alert | Kill switch: `HAGGLE_API_DEMO_ENABLED=false` on `haggle-api`, then investigate `llm_usage` |

---

## 8. Your turn

1. Read the [README](../../README.md) as a stranger, with a five-minute timer. Where did you stop?
2. Re-run `haggle-eval rescore` on the week 6 run (`docs/results/runs/20261010-0923-full-8784.json`).
   Which numbers change with today's scoring code, and why don't the headline ones? (It rewrites
   the report and the JSON: `git diff` them, then `git checkout` to restore.)
3. Pick one item from the future-work list and write its "Done when…" line before building
   anything.
4. **Interview drill:** explain in two minutes why L2's 0 % is less reassuring than L3's 0 %.
