"""
Math Utilities Module
Contains functions for calculating the factorial and Fibonacci sequences.
"""

def factorial(n):
    """
    Calculates the factorial of a non-negative integer n.
    
    Args:
        n (int): The number to calculate the factorial of.
        
    Returns:
        int: The factorial of n.
        
    Raises:
        ValueError: If n is negative.
        TypeError: If n is not an integer.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("Input must be an integer.")
    if n < 0:
        raise ValueError("Factorial is only defined for non-negative integers.")
    
    if n == 0 or n == 1:
        return 1
    
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

def fibonacci(n):
    """
    Calculates the n-th Fibonacci number.
    
    Args:
        n (int): The position of the Fibonacci number to retrieve.
        
    Returns:
        int: The n-th Fibonacci number.
        
    Raises:
        ValueError: If n is negative.
        TypeError: If n is not an integer.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("Input must be an integer.")
    if n < 0:
        raise ValueError("Fibonacci sequence is only defined for non-negative indices.")
    
    if n == 0:
        return 0
    elif n == 1:
        return 1
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

if __name__ == "__main__":
    # Simple tests
    try:
        print(f"Factorial of 5: {factorial(5)}")    # Expected: 120
        print(f"Factorial of 0: {factorial(0)}")    # Expected: 1
        print(f"Fibonacci of 7: {fibonacci(7)}")      # Expected: 13
        print(f"Fibonacci of 0: {fibonacci(0)}")     # Expected: 0
        
        # Edge case tests
        print("Testing negative input for factorial...")
        factorial(-1)
    except Exception as e:
        print(f"Caught expected error: {e}")
