import re


from pydantic import BaseModel


class FileSearchResultLine(BaseModel):
    line_number: int
    context: str


class FileSearchResult(BaseModel):
    file_path: str
    lines: list[FileSearchResultLine]


def search_in_file(query: str | re.Pattern, file: str) -> FileSearchResult | None:
    # Read the file content
    try:
        with open(file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return None

    result_lines = []

    # Iterate through each line in the file
    for i, line in enumerate(lines):
        # Check if the query matches the current line
        if isinstance(query, str):
            match = query.lower() in line.lower()
        else:
            match = query.search(line)

        if match:
            result_lines.append(
                FileSearchResultLine(line_number=i + 1, context=line.rstrip())
            )

    if len(result_lines) > 0:
        return FileSearchResult(file_path=file, lines=result_lines)
    return None
