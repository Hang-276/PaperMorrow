from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from .config import DATA_DIR
from .database import SessionLocal
from .llm import LLMClient
from .models import DeepWikiJob
from .original_deepwiki import OriginalDeepWikiEngine


ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cc", ".cpp", ".h",
    ".md", ".json", ".toml", ".yaml", ".yml", ".html", ".css", ".sql", ".sh",
}
IGNORED_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".next", ".venv", "venv", "__pycache__", "data", "models"}
LANGUAGE_NAMES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".go": "Go", ".rs": "Rust", ".c": "C", ".cc": "C++", ".cpp": "C++", ".md": "Markdown",
}


def validate_repository_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("仅允许 HTTPS GitHub 仓库")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ValueError("仓库地址格式无效")
    return f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}"


def run_deepwiki_job(job_id: int) -> None:
    db = SessionLocal()
    job = db.get(DeepWikiJob, job_id)
    if not job:
        db.close()
        return
    try:
        repository_url = validate_repository_url(job.repository_url)
        work_dir = DATA_DIR / "repositories" / str(job.id)
        output_dir = DATA_DIR / "wikis" / str(job.id)
        work_dir.parent.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        _update(db, job, "running", 8, "正在安全下载仓库")
        if not work_dir.exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", "--filter=blob:limit=2m", repository_url, str(work_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        _update(db, job, "running", 35, "正在建立代码结构索引")
        analysis = _analyze_repository(work_dir)
        _update(db, job, "running", 62, "正在运行原版 DeepWiki 研究 Agent 与代码检索工具")
        wiki = _generate_wiki(db, repository_url, analysis, work_dir)
        _write_wiki(output_dir, wiki)
        job.output_dir = str(output_dir)
        job.error = None
        _update(db, job, "completed", 100, "原版 DeepWiki 完整研究 Wiki 已生成")
        from .knowledge_graph_service import generate_reproduction_checklist
        generate_reproduction_checklist(db, job.paper, job)
        db.commit()
    except Exception as exc:
        job.error = str(exc)[:2000]
        _update(db, job, "failed", job.progress, "解析失败")
    finally:
        db.close()


def _analyze_repository(root: Path) -> dict:
    files: list[Path] = []
    total_bytes = 0
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS or path.stat().st_size > 500_000:
            continue
        files.append(path)
        total_bytes += path.stat().st_size
        if len(files) >= 800 or total_bytes >= 20_000_000:
            break
    language_counts = Counter(LANGUAGE_NAMES.get(path.suffix.lower(), path.suffix.lower() or "Other") for path in files)
    tree_lines = [str(path.relative_to(root)) for path in files[:400]]
    readme = ""
    for name in ("README.md", "README.rst", "README"):
        target = root / name
        if target.exists():
            readme = target.read_text(encoding="utf-8", errors="replace")[:25000]
            break
    key_snippets = []
    file_contents: dict[str, str] = {}
    preferred = [path for path in files if path.name.lower() in {"package.json", "pyproject.toml", "requirements.txt", "cargo.toml", "go.mod", "main.py", "app.py", "server.js"}]
    for path in (preferred + files)[:30]:
        try:
            relative = str(path.relative_to(root))
            content = path.read_text(encoding="utf-8", errors="replace")[:12000]
            file_contents[relative] = content
            key_snippets.append(f"## {relative}\n{content[:3500]}")
        except OSError:
            continue
    return {"files": tree_lines, "languages": dict(language_counts), "readme": readme, "snippets": key_snippets, "file_contents": file_contents}


def _generate_wiki(db: Session, repository_url: str, analysis: dict, work_dir: Path | None = None) -> dict:
    llm = LLMClient(db)
    if not llm.configured:
        raise RuntimeError("完整 DeepWiki 必须使用 LLM 研究代码仓库；当前激活的模型配置缺少 API Key，请先在设置中补全密钥")
    if work_dir is None:
        raise ValueError("原版 DeepWiki graph 需要仓库工作目录")
    engine = OriginalDeepWikiEngine(llm, work_dir)
    return asyncio.run(_generate_original_wiki(engine, repository_url, analysis, db=db))


async def _generate_original_wiki(
    engine: OriginalDeepWikiEngine,
    repository_url: str,
    analysis: dict,
    db: Session | None = None,
) -> dict:
    structure = await engine.generate_structure()
    pages = _validated_structure_pages(structure, analysis["files"], min_pages=8)
    sections = _validated_sections(structure.get("sections"), pages)
    if len(sections) < 2:
        raise ValueError("原版 DeepWiki 目录分区不足，拒绝保存为完整知识库")
    final_pages = []
    # The original project researches one page at a time. Keeping that mode
    # avoids cross-page state leakage and preserves its prompt/tool workflow.
    for index, page in enumerate(pages, 1):
        if db is not None:
            job = db.get(DeepWikiJob, int(Path(engine.root).name)) if Path(engine.root).name.isdigit() else None
            if job is not None:
                progress = 64 + int((index - 1) / max(len(pages), 1) * 31)
                _update(db, job, "running", progress, f"正在研究并撰写第 {index}/{len(pages)} 页：{page['title']}")
        content = await engine.generate_page(page)
        if not _valid_page_content(content):
            raise ValueError(f"Wiki 页面 {page['id']} 正文为空或过短")
        final_pages.append({**page, "content": content.strip()})
    return {
        "title": str(structure.get("title") or repository_url.rsplit("/", 1)[-1] + " 代码知识库"),
        "description": str(structure.get("description") or "基于原版 DeepWiki graph 生成的中文代码教程。"),
        "sections": sections,
        "pages": final_pages,
        "generator": "ace-deepwiki",
        "schema_version": 2,
    }


async def _generate_llm_wiki(llm: LLMClient, repository_url: str, context: str, analysis: dict) -> dict:
    structure = await llm.generate_wiki_structure(repository_url, context)
    pages = _validated_structure_pages(structure, analysis["files"])
    semaphore = asyncio.Semaphore(3)

    async def generate(page: dict) -> dict:
        source_context = _page_source_context(page, analysis)
        related = [{"id": item["id"], "title": item["title"]} for item in pages if item["id"] in page.get("related_pages", [])]
        async with semaphore:
            content = await llm.generate_wiki_page(repository_url, page, source_context, related)
        if not _valid_page_content(content):
            raise ValueError(f"Wiki 页面 {page['id']} 正文为空或过短")
        return {**page, "content": content.strip()}

    generated = await asyncio.gather(*(generate(page) for page in pages), return_exceptions=True)
    final_pages = []
    for page, result in zip(pages, generated):
        if isinstance(result, Exception):
            final_pages.append({**page, "content": _fallback_page(page, repository_url, analysis)})
        else:
            final_pages.append(result)
    if not all(_valid_page_content(page.get("content")) for page in final_pages):
        raise ValueError("Wiki 正文完整性检查失败")
    return {
        "title": str(structure.get("title") or repository_url.rsplit("/", 1)[-1] + " 代码知识库"),
        "description": str(structure.get("description") or "基于仓库源码生成的中文技术 Wiki。"),
        "pages": final_pages,
    }


def _validated_structure_pages(structure: dict, available_files: list[str], min_pages: int = 1) -> list[dict]:
    raw_pages = structure.get("pages")
    if not isinstance(raw_pages, list) or not min_pages <= len(raw_pages) <= 30:
        raise ValueError("LLM 未返回有效的 Wiki 页面结构")
    available = set(available_files)
    pages: list[dict] = []
    seen: set[str] = set()
    for raw in raw_pages:
        if not isinstance(raw, dict):
            continue
        page_id = _safe_page_id(str(raw.get("id") or raw.get("title") or "page"))
        if page_id in seen:
            continue
        seen.add(page_id)
        relevant = [str(item).removeprefix("./") for item in raw.get("relevant_files") or []]
        relevant = [item for item in relevant if item in available][:12]
        pages.append({
            "id": page_id,
            "title": str(raw.get("title") or page_id)[:200],
            "description": str(raw.get("description") or "")[:1000],
            "importance": raw.get("importance") if raw.get("importance") in {"high", "medium", "low"} else "medium",
            "relevant_files": relevant,
            "related_pages": [_safe_page_id(str(item)) for item in raw.get("related_pages") or []][:12],
            "parent_section": _safe_page_id(str(raw.get("parent_section"))) if raw.get("parent_section") else None,
        })
    if not pages:
        raise ValueError("Wiki 页面结构为空")
    return pages


def _validated_sections(raw_sections: object, pages: list[dict]) -> list[dict]:
    page_ids = {page["id"] for page in pages}
    sections = []
    for raw in raw_sections if isinstance(raw_sections, list) else []:
        if not isinstance(raw, dict):
            continue
        section_id = _safe_page_id(str(raw.get("id") or raw.get("title") or "section"))
        sections.append({
            "id": section_id,
            "title": str(raw.get("title") or section_id)[:200],
            "pages": [_safe_page_id(str(item)) for item in raw.get("pages") or [] if _safe_page_id(str(item)) in page_ids],
            "subsections": [_safe_page_id(str(item)) for item in raw.get("subsections") or []][:20],
        })
    if sections:
        return sections
    return [{"id": "overview", "title": "知识库", "pages": [page["id"] for page in pages], "subsections": []}]


def _page_source_context(page: dict, analysis: dict) -> str:
    contents = analysis.get("file_contents") or {}
    selected = page.get("relevant_files") or []
    if not selected:
        selected = list(contents)[:8]
    blocks = []
    for path in selected:
        if path in contents:
            blocks.append(f"## {path}\n{contents[path]}")
    if not blocks:
        blocks = analysis.get("snippets") or []
    return "\n\n".join(blocks)[:60000]


def _valid_page_content(content: object) -> bool:
    return isinstance(content, str) and len(content.strip()) >= 80 and "#" in content


def _write_wiki(output_dir: Path, wiki: dict) -> None:
    pages = wiki.get("pages") or []
    if not pages or not all(_valid_page_content(page.get("content")) for page in pages):
        raise ValueError("拒绝保存正文为空的 Wiki")
    staging = output_dir / f".building-{uuid.uuid4().hex}"
    pages_dir = staging / "pages"
    pages_dir.mkdir(parents=True, exist_ok=False)
    structure_pages = []
    try:
        for page in pages:
            page_id = _safe_page_id(page.get("id") or page.get("title") or "page")
            (pages_dir / f"{page_id}.md").write_text(str(page["content"]).strip() + "\n", encoding="utf-8")
            structure_pages.append({
                "id": page_id,
                "title": page.get("title", page_id),
                "description": page.get("description", ""),
                "importance": page.get("importance", "medium"),
                "relevant_files": page.get("relevant_files", []),
                "related_pages": page.get("related_pages", []),
                "parent_section": page.get("parent_section"),
            })
        structure = {
            "title": wiki["title"],
            "description": wiki["description"],
            "sections": _validated_sections(wiki.get("sections"), structure_pages),
            "pages": structure_pages,
            "generator": wiki.get("generator", "legacy-or-static"),
            "schema_version": int(wiki.get("schema_version") or 1),
        }
        (staging / "wiki_structure.json").write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")
        live_pages = output_dir / "pages"
        if live_pages.exists():
            shutil.rmtree(live_pages)
        pages_dir.replace(live_pages)
        os.replace(staging / "wiki_structure.json", output_dir / "wiki_structure.json")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _fallback_wiki(repository_url: str, analysis: dict) -> dict:
    languages = ", ".join(f"{name} ({count})" for name, count in Counter(analysis["languages"]).most_common()) or "未知"
    tree = "\n".join(f"- `{path}`" for path in analysis["files"][:200])
    readme = analysis["readme"] or "仓库未提供 README。"
    return {
        "title": repository_url.rsplit("/", 1)[-1] + " 代码知识库",
        "description": "由 PaperMorrow DeepWiki 静态分析生成；未执行仓库中的任何代码。",
        "sections": [{"id": "overview", "title": "基础静态分析", "pages": ["overview", "structure", "key-files"], "subsections": []}],
        "pages": [
            {"id": "overview", "title": "项目概览", "description": "项目目标与技术栈", "importance": "high", "relevant_files": analysis["files"][:8], "related_pages": ["structure"], "content": f"# 项目概览\n\n来源：[{repository_url}]({repository_url})\n\n主要语言：{languages}\n\n## README\n\n{readme}"},
            {"id": "structure", "title": "代码结构", "description": "仓库文件结构索引", "importance": "high", "relevant_files": analysis["files"][:20], "related_pages": ["overview", "key-files"], "content": f"# 代码结构\n\n以下目录由仓库静态索引生成，用于快速定位入口、配置与核心实现文件；系统没有执行其中的代码。\n\n{tree or '- 当前仓库没有可读取的文件。'}"},
            {"id": "key-files", "title": "关键文件", "description": "入口与配置文件摘录", "importance": "medium", "relevant_files": list((analysis.get("file_contents") or {}).keys())[:12], "related_pages": ["structure"], "content": "# 关键文件\n\n以下内容来自仓库中的关键文件，不包含运行时推断。如果仓库规模很小，本页会如实保留当前能够读取到的文件范围。\n\n" + ("\n\n".join(analysis["snippets"][:12]) or "当前仓库没有符合安全读取规则的关键文本文件。")},
        ],
    }


def _fallback_page(page: dict, repository_url: str, analysis: dict) -> str:
    contents = analysis.get("file_contents") or {}
    relevant = [path for path in page.get("relevant_files") or [] if path in contents]
    if not relevant:
        relevant = list(contents)[:8]
    source_list = "\n".join(f"- [{path}]({path})：本页使用的仓库源文件" for path in relevant) or "- 当前没有可安全读取的文本源文件"
    table_rows = "\n".join(f"| `{path}` | {len(contents[path].splitlines())} | 静态源码上下文 |" for path in relevant)
    nodes = []
    for index, path in enumerate(relevant[:8]):
        nodes.append(f'    P{index}["{Path(path).name[:28]}"] --> T["{str(page["title"])[:28]}"]')
    diagram = "\n".join(nodes) or '    R["仓库"] --> T["当前主题"]'
    excerpts = []
    for path in relevant:
        lines = contents[path].splitlines()
        excerpt = "\n".join(f"{number:>4}  {line}" for number, line in enumerate(lines[:140], 1))
        excerpts.append(f"### `{path}`\n\n该文件共 {len(lines)} 行，下面保留前 {min(len(lines), 140)} 行作为可追溯的实现依据。\n\n```text\n{excerpt}\n```\n\nSources: [{path}:1-{min(len(lines), 140)}]()")
    return f"""<details>
<summary>相关源文件</summary>

{source_list}
</details>

# {page['title']}

{page.get('description') or '本页基于仓库静态源码生成。'} 本页是原版研究 Agent 页面生成失败时的静态保底版本，只呈现能够从仓库直接核验的文件与代码，不补造实现结论。

来源仓库：[{repository_url}]({repository_url})

## 学习范围

本页围绕上述主题建立源码索引，先说明相关文件之间的归属，再提供带行号的实现片段。重新生成成功后，原版 DeepWiki graph 会进一步补充模块联系、设计思路、表格和更细的逐段讲解。

## 相关文件概览

| 文件 | 总行数 | 在本页中的作用 |
|---|---:|---|
{table_rows or '| — | 0 | 没有可读取的文本源码 |'}

## 文件与主题关系

```mermaid
graph TD
{diagram}
```

该图只表达 Wiki schema 指定的“相关文件 → 当前主题”关系，不推断运行时调用顺序。

## 相关源码与实现依据

{chr(10).join(excerpts) or '当前仓库没有可安全展示的源码片段。'}

## 当前边界

静态保底不会声称代码已经运行，也不会根据文件名猜测行为。请在任务页点击“重新生成”，让原版 ReAct graph 使用文件树、代码大纲、分段读取和搜索工具完成更深入的中文教程。
"""


def repair_incomplete_wikis(db: Session) -> int:
    repaired = 0
    for job in db.query(DeepWikiJob).filter(DeepWikiJob.status == "completed").all():
        if not job.output_dir:
            continue
        output_dir = Path(job.output_dir)
        work_dir = DATA_DIR / "repositories" / str(job.id)
        if wiki_is_complete(output_dir) or not work_dir.exists():
            continue
        job.status = "failed"
        job.message = "检测到旧版不完整 Wiki，请重新生成"
        job.error = "完整 Wiki 必须由原版 DeepWiki 研究图生成，系统不会再用简化静态页面冒充成功结果"
        repaired += 1
    db.commit()
    return repaired


def wiki_is_complete(output_dir: str | Path | None) -> bool:
    if not output_dir:
        return False
    root = Path(output_dir)
    try:
        structure = json.loads((root / "wiki_structure.json").read_text(encoding="utf-8"))
        pages = structure.get("pages") or []
        return bool(pages) and all(
            _valid_page_content((root / "pages" / f"{_safe_page_id(page.get('id', ''))}.md").read_text(encoding="utf-8"))
            for page in pages
        )
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def wiki_is_full_deepwiki(output_dir: str | Path | None) -> bool:
    """Return true only for a complete Wiki produced by the original graph."""
    if not wiki_is_complete(output_dir):
        return False
    try:
        structure = json.loads((Path(output_dir) / "wiki_structure.json").read_text(encoding="utf-8"))
        pages = structure.get("pages") or []
        sections = structure.get("sections") or []
        return (
            structure.get("generator") == "ace-deepwiki"
            and int(structure.get("schema_version") or 0) >= 2
            and len(pages) >= 8
            and len(sections) >= 2
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False


def _safe_page_id(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    return cleaned[:80] or "page"


def _update(db: Session, job: DeepWikiJob, status: str, progress: int, message: str) -> None:
    job.status, job.progress, job.message = status, progress, message
    db.commit()
