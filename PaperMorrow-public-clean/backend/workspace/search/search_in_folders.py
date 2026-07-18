import os
import re

from backend.workspace.fs import IgnoreRule
from backend.workspace.search.search_in_file import FileSearchResult, search_in_file


def search_in_folders(
    query: str | re.Pattern,
    folders: list[str],
    file_extensions: list[str],
    ignore_rules: list[IgnoreRule],
) -> list[FileSearchResult]:
    if "*" in file_extensions or ".*" in file_extensions:
        raise ValueError("Wildcard '*' or '.*' is not allowed in file extensions")

    file_extensions = [
        (f".{ext}" if not ext.startswith(".") else ext) for ext in file_extensions
    ]
    file_extension_regex = [re.compile(re.escape(ext) + "$") for ext in file_extensions]

    results: list[FileSearchResult] = []

    def matches_extension(file_name: str) -> bool:
        return any(regex.search(file_name) for regex in file_extension_regex)

    def should_ignore(path: str) -> bool:
        return any(rule(path) for rule in ignore_rules)

    def search_in_folder_recursive(folder: str):
        """Recursively search for matching files in the folder."""
        try:
            entries = os.listdir(folder)
        except PermissionError:
            # Skip folders we don't have permission to access
            return

        for entry in entries:
            full_path = os.path.join(folder, entry)

            if should_ignore(full_path):
                continue

            if os.path.isdir(full_path):
                # Recursively search in subdirectories
                search_in_folder_recursive(full_path)
            elif os.path.isfile(full_path) and matches_extension(entry):
                # Search in files
                result = search_in_file(query, full_path)
                if result is not None:
                    results.append(result)

    # Search in each folder
    for folder in folders:
        if os.path.exists(folder) and os.path.isdir(folder):
            search_in_folder_recursive(folder)

    return results
