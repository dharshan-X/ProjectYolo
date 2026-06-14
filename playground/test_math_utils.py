import math

import pytest

from math_utils import factorial, fibonacci


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, 1),
        (1, 1),
        (2, 2),
        (3, 6),
        (5, 120),
        (10, 3628800),
    ],
)
def test_factorial_values(n, expected):
    assert factorial(n) == expected


def test_factorial_matches_math_factorial_for_range():
    for n in range(0, 25):
        assert factorial(n) == math.factorial(n)


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, 0),
        (1, 1),
        (2, 1),
        (3, 2),
        (7, 13),
        (10, 55),
        (20, 6765),
    ],
)
def test_fibonacci_values(n, expected):
    assert fibonacci(n) == expected


def test_fibonacci_recurrence_relation():
    # Verify F(n) = F(n-1) + F(n-2) for a small range
    for n in range(2, 25):
        assert fibonacci(n) == fibonacci(n - 1) + fibonacci(n - 2)


@pytest.mark.parametrize("fn", [factorial, fibonacci])
def test_rejects_negative(fn):
    with pytest.raises(ValueError, match="non-negative"):
        fn(-1)


@pytest.mark.parametrize("bad", [1.0, 3.14, "5", None, True, False])
@pytest.mark.parametrize("fn", [factorial, fibonacci])
def test_rejects_non_int(fn, bad):
    with pytest.raises(TypeError, match="integer"):
        fn(bad)


@pytest.mark.parametrize("fn", [factorial, fibonacci])
def test_rejects_missing_argument(fn):
    with pytest.raises(TypeError):
        fn()  # type: ignore[misc]
