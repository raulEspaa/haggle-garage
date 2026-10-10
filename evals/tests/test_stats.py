import pytest

from haggle_evals.stats import cohen_kappa, confusion, median, quantile, wilson


@pytest.mark.parametrize(
    ("successes", "n", "low", "high"),
    [(5, 10, 0.2366, 0.7634), (0, 5, 0.0, 0.4345)],  # standard published Wilson 95 % values
)
def test_wilson_matches_reference_values(successes: int, n: int, low: float, high: float) -> None:
    rate = wilson(successes, n)

    assert rate.low == pytest.approx(low, abs=0.0005)
    assert rate.high == pytest.approx(high, abs=0.0005)


def test_wilson_never_claims_certainty_from_zero_successes() -> None:
    rate = wilson(0, 5)

    assert rate.low == 0
    assert rate.high > 0.4


def test_wilson_handles_no_data() -> None:
    assert str(wilson(0, 0)) == "n/a"


def test_median_and_quantiles() -> None:
    assert median([3, 1, 2]) == 2
    assert median([4, 1, 3, 2]) == 2.5
    assert median([]) is None
    assert quantile([1, 2, 3, 4, 5], 0.95) == pytest.approx(4.8)


def test_kappa_is_one_for_perfect_agreement_and_zero_for_a_constant_judge() -> None:
    truth = ["NONE"] * 8 + ["EXACT", "APPROX"]

    assert cohen_kappa(truth, truth) == 1
    assert cohen_kappa(truth, ["NONE"] * 10) == pytest.approx(0)  # 80 % accuracy, no skill


def test_kappa_rejects_mismatched_inputs() -> None:
    with pytest.raises(ValueError, match="same length"):
        cohen_kappa(["a"], ["a", "b"])


def test_confusion_matrix_rows_are_truth() -> None:
    matrix = confusion(["A", "A", "B"], ["A", "B", "B"], ["A", "B"])

    assert matrix == [[1, 1], [0, 1]]
