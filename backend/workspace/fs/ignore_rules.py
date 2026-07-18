import os
from typing import Callable

from gitignore_parser import parse_gitignore, parse_gitignore_str

type IgnoreRule = Callable[[str], bool]

GLOBAL_GITIGNORE = """
# Ignore git files
.git

# Ignore macOS system files
.DS_Store

# Ignore temporary files
*.swp
*.swo
*.tmp
*.temp

# Ignore IDE settings
.idea/
.vscode/

# Ignore log files
*.log

# Ignore node_modules
node_modules/

# Ignore build files
build/
dist/

# Ignore Python files
__pycache__/
wheels/
*.egg-info
*.py[oc]
.venv
"""


def ignore_rules_from_gitignore_files(path: str) -> IgnoreRule:
    ignore_rules = [parse_gitignore_str(GLOBAL_GITIGNORE, path)]

    def collect_rules_recursively(current_path: str):
        # Check if a .gitignore file exists in the current directory
        gitignore_path = os.path.join(current_path, ".gitignore")
        if os.path.isfile(gitignore_path):
            # Parse the .gitignore file and add its rules to the list
            ignore_rule = parse_gitignore(gitignore_path)
            ignore_rules.append(ignore_rule)

        # Recursively traverse subdirectories
        for item in os.listdir(current_path):
            full_path = os.path.join(current_path, item)
            if os.path.isdir(full_path) and item != ".git":  # Skip .git directory
                collect_rules_recursively(full_path)

    # Start collecting rules from the root path
    collect_rules_recursively(path)

    return lambda path_to_be_checked: any(
        safe_rule_check(rule, path_to_be_checked) for rule in ignore_rules
    )


def safe_rule_check(rule, path_to_be_checked):
    try:
        return rule(path_to_be_checked)
    except Exception as e:
        if " is not in the subpath of " in str(e):
            return False
        raise
