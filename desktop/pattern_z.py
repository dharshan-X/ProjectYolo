def print_z_pattern():
    # Using a fixed width for a cleaner look
    width = 7
    for i in range(width):
        if i == 0:
            # Top bar
            print("*" * width)
        elif i == width - 1:
            # Bottom bar
            print("*" * width)
        else:
            # Diagonal: only one * at the mirror position of the row index
            # row 1 -> index 5, row 2 -> index 4, etc.
            print(" " * (width - 1 - i) + "*")

if __name__ == "__main__":
    print_z_pattern()
