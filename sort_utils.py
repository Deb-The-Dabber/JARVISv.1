def sort_list(items, reverse=False):
    """Sort a list in ascending order by default.

    Args:
        items: List to sort.
        reverse: If True, sort in descending order.

    Returns:
        A new sorted list.
    """
    return sorted(items, reverse=reverse)


# Example usage
if __name__ == "__main__":
    nums = [4, 2, 9, 1, 5]
    print(sort_list(nums))  # [1, 2, 4, 5, 9]
    print(sort_list(nums, True))  # [9, 5, 4, 2, 1]
