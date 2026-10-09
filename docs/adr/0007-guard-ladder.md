# ADR-0007: Guard ladder — the model talks, code decides

- **Status:** Proposed. Confirm assumption A12.
- **Date:** 2026-10-08

## Context

The principle "the model talks, code decides" must hold. The game also needs levels that are **intentionally weaker**, so the evals can show *why* the principle matters. If every level had full code control, L1 and L2 would differ only cosmetically.

## Options

| Option | Description | Trade-off |
|--------|-------------|-----------|
| **A. Full code control at every level** | Every level uses `evaluate_offer`. Levels differ only in prompt and filter. | Principle fully applied, but L1/L2 can't show LLM-made concessions. Weak contrast. |
| **B. Ladder** | L1/L2: the LLM decides concessions, **code validates closing**. L3: code decides prices **and** closing, plus a price guard. | Shows the progression "prompt-only → prompt + filter → architecture". The principle is fully applied at L3, and partially (closing only) at L1/L2, by design. |
| **C. Code decides, LLM only paraphrases templates** | Deterministic. | Not an agent anymore. Boring demo. Nothing to evaluate. |

## Decision

**B. The guard ladder** (matrix in [02 §3](../02-architecture.md#3-level-matrix)).

Invariant at **every** level: **no deal can close below the floor or without agreement evidence.** `close_deal` enforces it in the MCP, in one DB transaction. Optionally a DB trigger adds a third layer.

## Why

- It is the honest version of the story recruiters want: "prompt defenses help but leak; output filters help but are bypassable; **removing the secret from the model** works."
- It maps to OWASP Top 10 for LLM Applications (2025): LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM06 Excessive Agency, LLM07 System Prompt Leakage.
- "Invalid sale" becomes measurable at L1/L2 as **attempted** and **verbal** invalid sales, with **successful** invalid sales held at 0.

## Mechanisms (all deterministic, all unit-testable without an LLM)

1. **Concession policy** (L3): Boulware curve in the MCP ([03 §1.4](../03-contracts.md#14-concession-policy-what-evaluate_offer-computes)).
2. **Offer-in-message check** (L3): the `evaluate_offer` amount must appear in the buyer's last message. This stops the model from being steered into probing the oracle with arbitrary amounts.
3. **One evaluation per turn** (L3, in the MCP).
4. **Price guard** (L3): `SellerTurn.price_usd` must equal a code-issued number. Otherwise the message is replaced by a deterministic template that quotes the code number.
5. **Leak filter** (L2+): numbers within ±5% of the floor that code did not issue are blocked. This includes spelled-out, reversed and encoded variants (same detector as the evals, [06 §4](../06-evaluation-plan.md#4-how-to-detect-a-floor-leak)).
6. **Canary** (all levels): a random token in the system prompt. If it appears in the output, the message is blocked (L2+) or logged (L1).
7. **Closing validation** (all levels, MCP).

## Consequences

- The guards fire in ADK callbacks. Tests drive them with **scripted `LlmResponse`s**: a `before_model_callback` that returns a response skips the real LLM call (documented ADK behaviour **[verified]**). This gives fast, free, deterministic tests.
- Guard triggers are stored internally (`turns.guards`) and in traces, and **never returned to clients**. The filter itself must not become an oracle.
- Using the same detector for the L2 filter and for eval scoring creates a blind spot: the filter blocks exactly what the detector sees. Hence the **LLM judge** and the **outcome-based** metric (floor extraction error) in the evals.
