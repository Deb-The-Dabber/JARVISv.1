def sort_list(items, reverse=False):
    """Sort a list in ascending order by default.

    Args:
        items: List to sort
        reverse: If True, sort in descending order (default: False)

    Returns:
        A new sorted list
    """
    return sorted(items, reverse=reverse)


# Example usage
if __name__ == "__main__":
    numbers = [4, 2, 9, 1, 5]
    print(f"Original: {numbers}")
    print(f"Ascending: {sort_list(numbers)}")
    print(f"Descending: {sort_list(numbers, reverse=True)}")

    words = ["banana", "apple", "cherry", "date"]
    print(f"Words sorted: {sort_list(words)}")
