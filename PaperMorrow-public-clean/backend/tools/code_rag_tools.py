from langchain.tools import tool, ToolRuntime


HINT = "\n\n> Call `react()` immediately to save your findings to the notepad. Then mark finished items as done and draft your follow-up items if applicable."


@tool
def file_tree(path: str, max_depth: int, runtime: ToolRuntime) -> str:
    """
    Get the file tree of the current repository.

    Args:
        path: The path to the folder to get the file tree of. e.g. "./src"
        max_depth: The maximum depth of the file tree. e.g. 5
        state:
    """
    return runtime.state["project"].file_tree(path, max_depth) + HINT


@tool
def file_outline(path: str, runtime: ToolRuntime) -> str:
    """
    Get the outline of a Python file, as well as line range of each member.
    Use this tool together with `read_lines` to get the code of a specific member.
    **Only Python files are supported**

    Args:
        path: The path to a Python code file. e.g. "./src/file.py"
    """
    return runtime.state["project"].file_outline(path) + HINT


@tool
def search_in_folders(
    keyword: str, folders: list[str], file_extensions: list[str], runtime: ToolRuntime
) -> str:
    """
    Search keyword in specific folders.

    Args:
        keyword: The keyword to search for. e.g. "abc def" means search for exact match of "abc def"
        folders: The folders to search in. e.g. ["./src", "./tests"]
        file_extensions: The file extensions to search in. e.g. ["py", "md"]
        state:
    """
    if not file_extensions or "*" in file_extensions or ".*" in file_extensions:
        # OpenAI-compatible providers often express "all source files" with a
        # wildcard.  The original low-level search rejects wildcards to avoid a
        # broad binary scan, so translate the intent to the repository's known
        # text/source extensions instead.
        file_extensions = [
            "py", "js", "jsx", "ts", "tsx", "java", "go", "rs", "c",
            "cc", "cpp", "h", "md", "json", "toml", "yaml", "yml",
            "html", "css", "sql", "sh",
        ]
    return (
        runtime.state["project"].search_in_folders(keyword, folders, file_extensions)
        + HINT
    )


@tool
def search_in_file(keyword: str, path: str, runtime: ToolRuntime) -> str:
    """
    Search keyword in a specific file.

    Args:
        keyword: The keyword to search for. e.g. "abc def" means search for exact match of "abc def"
        path: The path to the code file. e.g. "./src/file.py"
    """
    return runtime.state["project"].search_in_file(keyword, path) + HINT


@tool
def read_lines(
    path: str, from_line: int | None, to_line: int | None, runtime: ToolRuntime
) -> str:
    """
    Read lines from a text file. At least read 100 lines at a time unless you know the right line range.
    The line number starts from 1.

    Args:
        path: The path to the code file. e.g. "./src/file.py"
        from_line: The line number to start reading from.
        to_line: The line number to stop reading at.
    """
    from_line = from_line or 1
    to_line = to_line or 100
    full_lines = runtime.state["project"].read_lines(path)
    lines = full_lines[from_line - 1 : to_line]
    total_read_lines = len(lines)
    total_lines = len(full_lines)
    all_lines_has_been_read = len(full_lines) == to_line - from_line + 1
    return f"""The file has {total_lines} lines in total.
{all_lines_has_been_read and "All lines have been read." or f"The content has been truncated. Lines from {from_line} to {from_line + total_read_lines - 1} have been returned as below:"}

```
{"".join(lines)}
```\n{HINT}"""
