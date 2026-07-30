import os
from pathlib import Path

from pydantic import BaseModel
from backend.workspace.code import code_outline
from backend.workspace.fs import (
    IgnoreRule,
    file_tree,
    ignore_rules_from_gitignore_files,
    read_lines,
)
from backend.workspace.search import search_in_file, search_in_folders


class Project(BaseModel):
    root_dir: str

    _ignore_rules: list[IgnoreRule] | None = None

    def map_path(self, path: str) -> str:
        root = Path(self.root_dir).resolve()
        raw_path = str(path)
        candidate = Path(raw_path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            # Code models commonly spell a repository-root path as
            # `/src/main.py`.  Treat that form as repository-relative unless it
            # already points inside the checked-out repository.  It remains
            # impossible to escape the root because the stripped path is joined
            # below and checked again.
            if resolved == root or root in resolved.parents:
                target = resolved
            elif candidate.drive:
                target = resolved
            else:
                target = (root / raw_path.lstrip("/\\")).resolve()
        elif not candidate.drive and raw_path.startswith(("/", "\\")):
            # On Windows, `\src\main.py` is rooted on the current drive but
            # pathlib does not consider it absolute without a drive letter.
            # Code models use this spelling for repository-root paths.
            target = (root / raw_path.lstrip("/\\")).resolve()
        else:
            target = (root / candidate).resolve()
        if target != root and root not in target.parents:
            raise ValueError("Path must stay inside the repository")
        return str(target)

    def rel_path(self, path: str) -> str:
        if path.startswith(self.root_dir):
            return path.replace(self.root_dir, ".")
        return path

    def file_tree(self, path: str = "./", max_depth: int = 5) -> str:
        joined_path = self.map_path(path)
        return file_tree(joined_path, max_depth, self.ignore_rules())

    def file_outline(self, path: str) -> str:
        if path.endswith(".py"):
            return code_outline(self.map_path(path))
        else:
            return f"Unsupported code file extension: {path}"

    def search_in_folders(
        self,
        keyword: str,
        folders: list[str],
        file_extensions: list[str],
    ) -> str:
        results = search_in_folders(
            keyword,
            [self.map_path(folder) for folder in folders],
            file_extensions,
            self.ignore_rules(),
        )
        if len(results) == 0:
            return "No search result found"
        result_str = ""
        for result in results:
            for line in result.lines:
                result_str += f'File "{self.rel_path(result.file_path)}", line {line.line_number}: {line.context}\n'
            result_str += "\n"
        return result_str

    def search_in_file(self, keyword: str, file: str) -> str:
        result = search_in_file(keyword, self.map_path(file))
        if result is None:
            return "No search result found"
        result_str = ""
        for line in result.lines:
            result_str += f"Line {line.line_number}: {line.context}\n"
        return result_str

    def read_lines(
        self,
        path: str,
    ) -> list[str]:
        return read_lines(self.map_path(path))

    def ignore_rules(self) -> list[IgnoreRule]:
        if self._ignore_rules is None:
            self._ignore_rules = [ignore_rules_from_gitignore_files(self.root_dir)]
        return self._ignore_rules
