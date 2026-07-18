def read_lines(
    path: str,
) -> list[str]:
    try:
        with open(path, "r") as f:
            lines = f.readlines()
            return lines
    except Exception as e:
        return [f"{e}"]
