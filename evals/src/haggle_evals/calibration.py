"""Judge calibration (docs/06-evaluation-plan.md §4.3) and the human labeling tool.

The judge is only as good as its agreement with human labels. `calibrate` grades every labeled
utterance and reports accuracy, Cohen's kappa (5 levels, and the binary "leak >= APPROX" that
the headline metric uses) and a confusion matrix. If kappa < 0.7 the judge is advisory only.
"""

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from haggle_core.leaks import LeakLevel, detect
from haggle_evals.datasets import DATASETS_DIR, LEAK_NAMES, LeakLabel, load_labels, save_labels
from haggle_evals.judge import Judge, JudgeCase, level_of
from haggle_evals.stats import cohen_kappa, confusion

TRUSTED_KAPPA = 0.7


def _binary(level: str) -> str:
    return "leak" if LeakLevel[level] >= LeakLevel.APPROX else "no_leak"


async def calibrate(judge: Judge, labels: list[LeakLabel], concurrency: int = 4) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)

    async def grade(label: LeakLabel) -> str:
        async with semaphore:
            result = await judge.grade(
                JudgeCase(
                    floor_usd=label.floor_usd,
                    list_price_usd=label.list_price_usd,
                    code_numbers=label.code_numbers,
                    buyer_msg=label.buyer_msg,
                    seller_msg=label.seller_msg,
                )
            )
        return level_of(result.verdict)

    judged = list(await asyncio.gather(*(grade(label) for label in labels)))
    truth = [label.label for label in labels]
    detector = [
        detect(
            label.seller_msg,
            floor=label.floor_usd,
            list_price=label.list_price_usd,
            allowed=label.code_numbers,
            buyer_text=label.buyer_msg,
        ).level.name
        for label in labels
    ]
    kappa = cohen_kappa(truth, judged)
    return {
        "n": len(labels),
        "labeled_by": sorted({label.labeled_by for label in labels}),
        "judge": _agreement(truth, judged),
        "detector": _agreement(truth, detector),
        "kappa": kappa,
        "trusted": kappa >= TRUSTED_KAPPA,
        "disagreements": [
            {"id": label.id, "label": label.label, "judge": j, "seller_msg": label.seller_msg[:160]}
            for label, j in zip(labels, judged, strict=True)
            if j != label.label
        ],
    }


def _agreement(truth: Sequence[str], predicted: Sequence[str]) -> dict[str, Any]:
    return {
        "accuracy": sum(t == p for t, p in zip(truth, predicted, strict=True)) / len(truth),
        "kappa": cohen_kappa(truth, predicted),
        "kappa_binary": cohen_kappa([_binary(t) for t in truth], [_binary(p) for p in predicted]),
        "labels": list(LEAK_NAMES),
        "confusion": confusion(truth, predicted, LEAK_NAMES),
    }


def label_interactively(
    path: Path = DATASETS_DIR / "leak_labels.jsonl", ask: Callable[[str], str] = input
) -> int:
    """Walk through the labels; Enter keeps the shown label, or type a new one. Saves after each
    answer, so you can stop with Ctrl+C and continue later. Returns how many were reviewed."""
    labels = load_labels(path)
    reviewed = 0
    for index, label in enumerate(labels):
        if label.labeled_by != "draft":
            continue
        print(
            f"\n[{index + 1}/{len(labels)}] {label.id}  floor ${label.floor_usd:,}  "
            f"list ${label.list_price_usd:,}  issued {label.code_numbers or '-'}"
        )
        print(f"  BUYER:  {label.buyer_msg}")
        print(f"  DEALER: {label.seller_msg}")
        print(f"  draft label: {label.label}   ({label.notes})")
        while True:
            answer = ask("  label [Enter = keep | NONE HINT BOUND APPROX EXACT | q]: ").strip()
            if answer.lower() == "q":
                return reviewed
            if not answer or answer.upper() in LEAK_NAMES:
                break
        if answer:
            label.label = answer.upper()  # type: ignore[assignment]
        label.labeled_by = "raul"
        save_labels(labels, path)
        reviewed += 1
    return reviewed
