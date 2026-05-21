"""math_utils.py

A small collection of basic math utility functions.

Functions
---------
factorial(n):
    Compute n! for a non-negative integer n.

fibonacci(n):
    Compute the nth Fibonacci number (0-indexed) for a non-negative integer n.
"""

from __future__ import annotations


def _validate_non_negative_int(n: int, name: str = "n") -> None:
    """Validate that *n* is a non-negative integer.

    Parameters
    ----------
    n:
        Value to validate.
    name:
        Parameter name for error messages.

    Raises
    ------
    TypeError
        If *n* is not an integer.
    ValueError
        If *n* is negative.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"{name} must be an integer")
    if n < 0:
        raise ValueError(f"{name} must be non-negative")


def factorial(n: int) -> int:
    """Return the factorial of *n* (n!).

    Parameters
    ----------
    n:
        Non-negative integer.

    Returns
    -------
    int
        The computed factorial.

    Examples
    --------
    >>> factorial(0)
    1
    >>> factorial(5)
    120
    """
    _validate_non_negative_int(n)

    result = 1
    for k in range(2, n + 1):
        result *= k
    return result


def fibonacci(n: int) -> int:
    """Return the nth Fibonacci number (0-indexed).

    The sequence is defined as:
        F(0) = 0, F(1) = 1, and F(n) = F(n-1) + F(n-2) for n>1.

    Parameters
    ----------
    n:
        Non-negative integer index.

    Returns
    -------
    int
        The nth Fibonacci number.

    Examples
    --------
    >>> fibonacci(0)
    0
    >>> fibonacci(7)
    13
    """
    _validate_non_negative_int(n)

    if n == 0:
        return 0
    if n == 1:
        return 1

    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
