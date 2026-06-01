def factorial(n):
    """Return the factorial of n (n!).

    Handles n=0 and n=1 correctly. Raises ValueError for negative inputs.
    Uses an iterative implementation for efficiency.
    """
    if n < 0:
        raise ValueError("factorial() not defined for negative values")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def fibonacci(n):
    """Return the n-th Fibonacci number (0, 1, 1, 2, 3, 5, ...).

    Raises ValueError for negative inputs.
    Uses an iterative implementation for efficiency.
    """
    if n < 0:
        raise ValueError("fibonacci() not defined for negative values")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
