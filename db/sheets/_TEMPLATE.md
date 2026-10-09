---
# Front matter: machine-readable metadata. The ingestion script (week 3) reads it.
slug: vantor-kestrel            # lowercase-with-hyphens, unique
make: Vantor
model: Kestrel
years: "1968-1972"
title: Vantor Kestrel (1968-1972)
version: 1
---

<!--
HOW TO WRITE A SHEET (ADR-0010). Delete this comment when done.

* FICTIONAL brand and models only: the LLM must NOT be able to answer from memory, so RAG is
  the only source of truth and retrieval quality becomes measurable.
* 600-900 words. Each "##" section becomes ONE retrievable chunk: keep a section self-contained
  (repeat the model name; don't write "as said above").
* Facts, not instructions. Never write anything that reads like a command to an AI ("ignore",
  "you must", "always say"...). A poisoned sheet for injection tests lives in the eval DB only.
* Be consistent with db/seed/cars.yaml (engines, trims, years) and with your other sheets.
* Market notes are SYNTHETIC: invent a believable price range per condition grade. The buyer
  uses them to appraise, so they should bracket the list prices in cars.yaml.
-->

## Overview

What the car is, where it sits in the (fictional) Vantor range, production years and volumes,
what it is known for.

## Variants and engines

Trims (e.g. base, R/S), engine options with displacement and power, transmissions, notable
options packages, how to identify each variant (badges, codes).

## Known issues and red flags

Typical rust spots, mechanical weak points, reproduction parts that lower value, how to spot a
fake R/S, what a buyer should inspect.

## What drives value

Originality ("numbers-matching"), documentation (build sheet), color rarity, options, quality
of the restoration, condition grade definitions (1 = concours ... 5 = project car).

## Market notes (synthetic)

| Condition grade | Typical price range (USD) |
|-----------------|---------------------------|
| 1 | ... |
| 2 | ... |
| 3 | ... |
| 4 | ... |
| 5 | ... |

Recent (fictional) sales trends, which variants carry a premium and by how much.
