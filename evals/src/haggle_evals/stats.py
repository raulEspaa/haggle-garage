"""Small-sample statistics for the eval report. Pure functions, no numpy needed.

With 27 games per level, a rate of 30 % has a 95 % interval of roughly 16-49 %. Reporting the
interval stops us from celebrating noise ("L2 41 % vs L3 47 %").
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

Z_95 = 1.959964


@dataclass(frozen=True, slots=True)
class Rate:
    successes: int
    n: int
    low: float
    high: float

    @property
    def value(self) -> float:
        return self.successes / self.n if self.n else 0.0

    def __str__(self) -> str:
        if not self.n:
            return "n/a"
        return f"{self.value:.0%} [{self.low:.0%}, {self.high:.0%}] ({self.successes}/{self.n})"


def wilson(successes: int, n: int, z: float = Z_95) -> Rate:
    """Wilson score interval: unlike the textbook p ± z·sqrt(p(1-p)/n), it behaves at 0/n and
    n/n (it never gives [0 %, 0 %] for 0 successes out of 5, which would claim certainty)."""
    if n == 0:
        return Rate(0, 0, 0.0, 0.0)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return Rate(successes, n, max(0.0, centre - margin), min(1.0, centre + margin))


def median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def quantile(values: Sequence[float], q: float) -> float | None:
    """Linear interpolation between closest ranks (numpy's default)."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Agreement between two raters beyond chance: 1 = perfect, 0 = chance, < 0 = worse.

    Raw accuracy flatters a judge on unbalanced data: if 80 % of turns are NONE, always
    answering NONE scores 80 %. Kappa scores that judge 0."""
    if len(a) != len(b) or not a:
        raise ValueError("need two non-empty label lists of the same length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[k] * count_b[k] for k in count_a.keys() | count_b.keys()) / (n * n)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def confusion(
    truth: Sequence[str], predicted: Sequence[str], labels: Sequence[str]
) -> list[list[int]]:
    """Rows = truth, columns = prediction, in `labels` order."""
    index = {label: i for i, label in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in labels]
    for t, p in zip(truth, predicted, strict=True):
        matrix[index[t]][index[p]] += 1
    return matrix
