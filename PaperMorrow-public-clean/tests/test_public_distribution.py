from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_public_tree_contains_no_user_data_or_secret_files():
    forbidden_names = {".env", "secrets.json", "credentials.json", "paper_radar.db"}
    forbidden_suffixes = {".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}
    offenders = []
    git_root_result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, capture_output=True, text=True, check=False)
    git = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    candidates = [Path(git_root_result.stdout.strip()) / value for value in git.stdout.splitlines()] if git.returncode == 0 and git_root_result.returncode == 0 else ROOT.rglob("*")
    for path in candidates:
        if any(part in {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        if path.is_file() and (path.name in forbidden_names or path.suffix.lower() in forbidden_suffixes):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_desktop_package_includes_cowork_skill_catalog():
    spec = (ROOT / "desktop" / "PaperMorrow.spec").read_text(encoding="utf-8")
    assert '"backend" / "cowork_skills"' in spec
    assert (ROOT / "backend" / "cowork_skills" / "catalog.json").is_file()
