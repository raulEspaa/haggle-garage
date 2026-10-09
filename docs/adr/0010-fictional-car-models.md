# ADR-0010: Fictional car models for synthetic data and RAG

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

Synthetic data only. You write the model sheets yourself. The buyer appraises the listing before offering, and the seller answers questions about the car.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. Real models** (e.g., a 1970 muscle car everyone knows) | Instantly relatable. | The LLM **already knows** real specs and market values, so answers mix pre-trained knowledge with RAG. You can't tell whether retrieval worked. Appraisals anchor on real-world prices, not your synthetic market. Brand/trademark use in a public demo. |
| **B. Fictional brand and models "inspired by" the 1970s** (e.g., "1970 Vantor Kestrel 440 R/S") | **RAG is the only source of facts**, so retrieval and groundedness are measurable. Fully synthetic. No brand issues. | Slightly less recognizable. You must write coherent lore. |

## Decision

**B.** Three cars, one fictional brand, three model sheets of ~600–900 words each, using a fixed template:

1. Overview and production years.
2. Variants and engines.
3. Known issues and red flags.
4. What drives value (condition grades, originality).
5. Market notes: a synthetic price range per condition grade, used by the buyer's appraisal.

## Consequences

- A spec hallucination (the seller states a fact that is not in the sheet) becomes detectable. It is an optional groundedness metric in [06](../06-evaluation-plan.md).
- Keep the sheets free of instructions. To test indirect prompt injection, add a separate **poisoned sheet** in the eval DB only.
