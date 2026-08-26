def lines_to_list(value: str) -> list[str]:
    """Convert teacher-entered, line-separated text into clean list items."""

    return [line.strip() for line in value.splitlines() if line.strip()]
