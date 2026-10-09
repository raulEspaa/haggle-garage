# ADR-0011: Real iconic cars (1960s-1980s) with dealer-specific synthetic data

- **Status:** Accepted (2026-10-09, product decision by Raúl). **Supersedes [ADR-0010](0010-fictional-car-models.md).**
- **Date:** 2026-10-09

## Context

ADR-0010 chose a fictional brand so the LLM could not answer from pre-trained knowledge,
making RAG measurable. The product owner prefers **real, mythical cars from the 1960s to the
1980s with real data**: a recruiter instantly recognizes a 1969 Camaro Z/28, and the game is more
fun. The trade-off has to be handled, not ignored.

## Decision

Inventory: **1969 Chevrolet Camaro Z/28**, **1970 Dodge Challenger R/T (440 Six Pack)**,
**1987 Buick Grand National**. One icon per decade, all American performance cars.

Each model sheet in `db/sheets/` has two kinds of content:

| Kind | Examples | Truth source |
|------|----------|--------------|
| **Public facts** (real, verified, sources listed in front matter) | engine, power, production numbers, known issues | the web pages in `sources:` |
| **Dealer-specific facts** (fictional) | the history and flaws of *this* unit, the dealer's synthetic price guide | the sheet itself, nowhere else |

All prices (list prices, floors, market notes) remain **fictional game data** and are labeled as
such. Real collector-market values change constantly and are not the point of the game.

## Consequences

- **RAG evals target dealer-specific facts** ("what was replaced in 2022 on the Grand
  National?", "what does the dealer's guide say for a grade 3 Challenger?"). Questions about
  public specs can't prove retrieval worked, because the model may know the answer anyway.
- **Groundedness gets a new failure mode:** the seller may state true-but-unsourced facts from
  memory, or *wrong* ones (hallucinated production numbers). The judge checks claims against
  the sheet, and the sheets must be accurate: every figure is sourced.
- **Buyer appraisal** must use the dealer's synthetic market notes, not the model's memory of
  real auction prices. The buyer prompt (Week 5) says so explicitly, and the evals check it.
- **Brands:** model names are used descriptively in a non-commercial portfolio. No logos and no
  manufacturer images. The UI shows "not affiliated with any manufacturer" (Week 4).
- Schema: the year CHECK widened from 1960–1979 to **1960–1989** (migration `0002`).

## Revisit if

- The RAG evals show retrieval can't be distinguished from memory even on dealer-specific
  questions. Then go back to fictional models for an "eval mode" inventory.
