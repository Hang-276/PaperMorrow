from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError
from langchain_openai import ChatOpenAI

from backend.agent.researcher import create_researcher
from backend.model.deep_wiki import Page, WikiStructure
from backend.model.notepad import Notepad
from backend.model.state import TokenCounter
from backend.model.todo_list import TodoList
from backend.prompts.prompt_template import apply_prompt_template
from backend.workspace import Project

from .llm import LLMClient
from .usage_service import estimate_tokens, record_token_usage


class OriginalDeepWikiEngine:
    """Adapter around the repository's original ReAct/LangGraph DeepWiki.

    The prompts, state graph, tools and schema remain in their original modules;
    this class only connects them to PaperMorrow's selected API profile, storage
    and token accounting.
    """

    def __init__(self, llm: LLMClient, repository_root: Path):
        if not llm.configured:
            raise RuntimeError("尚未配置 LLM API")
        self.llm = llm
        self.root = repository_root.resolve()
        self.project = Project(root_dir=str(self.root))
        self.chat_model = _chat_model(llm)
        self.researcher = create_researcher(
            self.chat_model,
            system_prompt_suffix="""
# Integrated execution protocol (highest priority)

The original tool-call-only response rule applies only while researching.
When research is sufficient, call `react` exactly once with
`ready_to_answer=true` and an empty `add_todo`. After that tool returns `Done`,
immediately write the requested final JSON or Markdown as ordinary assistant
content. Do not call any more tools. The final content is the required exception
to the tool-call-only rule. Never restart research after declaring readiness.
""",
        )

    async def generate_structure(self) -> dict[str, Any]:
        source_files = _source_files(self.root)
        evidence_policy = _repository_evidence_policy(source_files)
        content = await self._ask(f"{apply_prompt_template('wiki_structure')}\n\n{evidence_policy}")
        try:
            return WikiStructure.model_validate(_parse_json(content)).model_dump()
        except (json.JSONDecodeError, ValidationError, ValueError) as error:
            return await self._repair_structure(content, error)

    async def _repair_structure(self, content: str, error: Exception) -> dict[str, Any]:
        """Repair provider JSON without throwing away completed repository research."""
        last_error: Exception = error
        candidate = content
        for _ in range(2):
            callback = UsageMetadataCallbackHandler()
            repair_prompt = f"""下面是代码研究代理生成的 Wiki 目录，但它没有通过 JSON Schema 校验。
只修复 JSON 语法和字段结构，保留原有事实、页面和文件路径，不要重新研究仓库。

必须严格返回一个 JSON 对象，且只能返回 JSON，不得使用代码围栏或解释。Schema：
- title: string
- description: string
- sections: array，每项包含 id:string, title:string, pages:string[], subsections:string[]
- pages: array，每项包含 id:string, title:string, description:string,
  importance:"high"|"medium"|"low", relevant_files:string[],
  related_pages:string[], parent_section:string|null
- 至少 2 个 sections、8 个 pages；section.pages 与 parent_section 必须引用有效 id。

当前校验错误：{last_error}

待修复内容：
{candidate}
"""
            response = await self.chat_model.ainvoke(
                [
                    SystemMessage(content="你是严格的 JSON Schema 修复器，只输出有效 JSON。"),
                    HumanMessage(content=repair_prompt),
                ],
                config={"callbacks": [callback]},
            )
            candidate = _message_text(response.content)
            self._record_usage(callback, repair_prompt, candidate)
            try:
                return WikiStructure.model_validate(_parse_json(candidate)).model_dump()
            except (json.JSONDecodeError, ValidationError, ValueError) as retry_error:
                last_error = retry_error
        raise ValueError(f"原版 DeepWiki 目录 JSON 修复失败：{last_error}") from last_error

    async def generate_page(self, page_data: dict[str, Any]) -> str:
        page = Page.model_validate(page_data)
        source_files = _source_files(self.root)
        prompt = (
            apply_prompt_template("wiki_page", page=page.model_dump())
            + "\n\n"
            + _repository_evidence_policy(source_files)
        )
        minimum_sources = max(1, min(5, len(source_files)))
        content = _strip_markdown_wrapper(await self._ask(prompt)).strip()
        issues = _page_quality_issues(content, minimum_sources)
        if issues:
            content = await self._revise_page(page, prompt, content, issues, minimum_sources)
            issues = _page_quality_issues(content, minimum_sources)
        if issues:
            raise ValueError(
                f"原版 DeepWiki 页面 {page.id} 未满足详细教程输出约束：{'；'.join(issues)}"
            )
        return content

    async def _revise_page(
        self,
        page: Page,
        original_prompt: str,
        draft: str,
        issues: list[str],
        minimum_sources: int,
    ) -> str:
        """Repair an already researched draft without repeating repository search."""
        callback = UsageMetadataCallbackHandler()
        revision_prompt = f"""请把下面的原版 DeepWiki 草稿修订成最终中文 Markdown 页面。

页面：{page.title}（{page.id}）
未通过的验收项：{'；'.join(issues)}

硬性格式：
1. 第一个字符开始就是 <details>，其中至少列出 {minimum_sources} 个不同的真实源码文件，然后关闭 </details>。
2. 紧接一个 H1；正文不少于 2500 字符，至少 3 个 H2。
3. 至少一个从源码证据推导的竖向 ```mermaid 图。
4. 重要结论使用真实文件路径和行号引用；不允许虚构文件、API 或行为。
5. 只输出页面 Markdown，不得输出解释、道歉、外层代码围栏、工具调用、XML/DSML 调用标签。

原始页面要求：
{original_prompt}

待修订草稿：
{draft}
"""
        response = await self.chat_model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是 DeepWiki 的最终技术编辑。研究阶段已经完成，工具不可用。"
                        "只能根据给定要求和草稿直接输出准确、完整的 Markdown，禁止请求或模拟工具调用。"
                    )
                ),
                HumanMessage(content=revision_prompt),
            ],
            config={"callbacks": [callback]},
        )
        content = _strip_markdown_wrapper(_message_text(response.content)).strip()
        self._record_usage(callback, revision_prompt, content)
        return content

    async def _ask(self, question: str) -> str:
        project_tree = self.project.file_tree(path="", max_depth=3)
        callback = UsageMetadataCallbackHandler()
        result = await self.researcher.ainvoke(
            {
                "messages": [
                    HumanMessage(content=project_tree, id="file_tree"),
                    HumanMessage(content=Notepad(notes=[]).to_markdown(), id="notepad"),
                    HumanMessage(content=TodoList().to_markdown(), id="todo_list"),
                    HumanMessage(content=question, id="user_question"),
                ],
                "project": self.project,
                "todo_list": TodoList(),
                "notepad": Notepad(notes=[]),
                "token_counter": TokenCounter(),
                "research_steps": 0,
            },
            config={
                # Match the original DeepWiki entry point. Repository research
                # often needs many alternating react/search/read calls before a
                # grounded structure or page can be written.
                "recursion_limit": 500,
                "configurable": {"thread_id": str(uuid.uuid4())},
                "callbacks": [callback],
            },
        )
        messages = result.get("messages") or []
        if not messages:
            raise ValueError("原版 DeepWiki graph 没有返回最终内容")
        content = _message_text(messages[-1].content)
        if not content.strip():
            raise ValueError("原版 DeepWiki graph 返回了空内容")
        if _looks_like_serialized_tool_call(content):
            content = await self._finalize_from_research(
                question=question,
                project_tree=project_tree,
                result=result,
                callback=callback,
            )
        self._record_usage(callback, question, content)
        return content

    async def _finalize_from_research(
        self,
        question: str,
        project_tree: str,
        result: dict[str, Any],
        callback: UsageMetadataCallbackHandler,
    ) -> str:
        """Turn accumulated ReAct evidence into the final artifact without tools.

        DeepSeek-compatible endpoints can serialize a requested tool call as
        DSML text after tools have deliberately been removed at the research
        limit.  Running a clean writer call without the researcher's
        tool-call-only system prompt prevents that provider-specific syntax from
        being mistaken for a Wiki page.
        """
        notepad = result.get("notepad")
        if isinstance(notepad, dict):
            notepad = Notepad.model_validate(notepad)
        research_notes = notepad.to_markdown() if isinstance(notepad, Notepad) else str(notepad or "")
        final_prompt = f"""代码研究阶段已经结束。请根据研究记录直接完成原始任务。

严格要求：
- 只输出原始任务要求的最终 JSON 或 Markdown；
- 不得调用、请求或模拟任何工具；
- 不得输出 DSML、tool_calls、invoke、XML 工具标签或过程解释；
- 所有事实必须来自仓库树与研究记录，证据不足时明确边界，不得虚构。

仓库树：
{project_tree}

研究记录：
{research_notes}

原始任务：
{question}
"""
        response = await self.chat_model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是 DeepWiki 的最终写作者，不是研究代理。工具已经永久关闭。"
                        "直接输出最终交付物，任何形式的工具调用文本都属于错误。"
                    )
                ),
                HumanMessage(content=final_prompt),
            ],
            config={"callbacks": [callback]},
        )
        content = _strip_markdown_wrapper(_message_text(response.content)).strip()
        if not content or _looks_like_serialized_tool_call(content):
            raise ValueError("DeepWiki 最终写作阶段仍返回了序列化工具调用，未生成正文")
        return content

    def _record_usage(self, callback: UsageMetadataCallbackHandler, prompt: str, content: str) -> None:
        prompt_tokens = completion_tokens = 0
        for usage in callback.usage_metadata.values():
            prompt_tokens += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        estimated = prompt_tokens == 0 and completion_tokens == 0
        if estimated:
            prompt_tokens, completion_tokens = estimate_tokens(prompt), estimate_tokens(content)
        record_token_usage(
            profile_id=self.llm.profile_id,
            profile_name=self.llm.profile_name,
            provider=self.llm.provider,
            model=self.llm.model,
            purpose="deepwiki",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated=estimated,
        )


def _chat_model(llm: LLMClient):
    if llm.provider == "claude":
        base_url = llm.base_url
        if base_url.endswith("/messages"):
            base_url = base_url.removesuffix("/messages")
        return ChatAnthropic(
            model_name=llm.model,
            api_key=llm.api_key,
            base_url=base_url or None,
            temperature=0,
            max_tokens_to_sample=8192,
            max_retries=3,
        )
    base_url = llm.base_url.removesuffix("/chat/completions")
    return ChatOpenAI(
        model=llm.model,
        base_url=base_url,
        api_key=llm.api_key,
        temperature=0,
        max_retries=3,
        timeout=180,
        stream_usage=True,
    )


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("原版 DeepWiki 未返回 JSON schema")
    return json.loads(text[start:end + 1])


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text") or block.get("content") or "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "")


def _strip_markdown_wrapper(content: str) -> str:
    match = re.fullmatch(r"\s*```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*", content, re.I)
    return match.group(1) if match else content


def _looks_like_serialized_tool_call(content: str) -> bool:
    compact = content.lstrip()[:2000].lower()
    return (
        "dsml" in compact and ("tool_calls" in compact or "invoke name=" in compact)
    ) or compact.startswith("<tool_call") or compact.startswith("<function=")


def _source_files(root: Path) -> list[str]:
    ignored = {".git", "node_modules", "dist", "build", ".next", ".venv", "venv", "__pycache__"}
    source_suffixes = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
        ".c", ".cc", ".cpp", ".h", ".md", ".json", ".toml", ".yaml",
        ".yml", ".html", ".css", ".sql", ".sh",
    }
    return sorted(
        str(path.relative_to(root)) for path in root.rglob("*")
        if path.is_file()
        and not any(part in ignored for part in path.relative_to(root).parts)
        and path.suffix.lower() in source_suffixes
    )


def _minimum_source_count(root: Path) -> int:
    return max(1, min(5, len(_source_files(root))))


def _repository_evidence_policy(source_files: list[str]) -> str:
    available = "\n".join(f"- {path}" for path in source_files) or "- （仓库中没有可读源码文件）"
    required = max(1, min(5, len(source_files)))
    return f"""# Repository evidence policy (overrides conflicting source-count instructions)

The checkout contains {len(source_files)} eligible source/document files. The
required number of distinct files in source lists is therefore {required}, not
five when fewer than five files exist. Never split one file into multiple list
items merely to meet a count, and never cite a path outside this exact list:
{available}

README statements describe documentation claims, not necessarily checked-in
implementation. If README mentions files, dependencies, commands, components,
or behavior that the actual checkout does not contain, label them explicitly as
README-documented or absent from this checkout. Never present them as verified
code. Prefer explaining the real implementation boundary over inventing depth.
"""


def _page_quality_issues(content: str, minimum_sources: int = 5) -> list[str]:
    stripped = content.lstrip()
    opening_details = re.match(r"<details>[\s\S]*?</details>", stripped)
    opening_sources = re.findall(r"(?m)^-\s+\[[^\]]+\]\([^)]*\)", opening_details.group(0) if opening_details else "")
    issues = []
    if _looks_like_serialized_tool_call(stripped):
        issues.append("返回了序列化工具调用而非正文")
    if len(stripped) < 2500:
        issues.append(f"正文仅 {len(stripped)} 字符（至少 2500）")
    if opening_details is None:
        issues.append("开头缺少 <details> 相关源文件区块")
    elif len(opening_sources) < minimum_sources:
        issues.append(f"开头仅列出 {len(opening_sources)} 个规范源码链接（至少 {minimum_sources}）")
    if re.search(r"(?m)^#\s+\S", stripped) is None:
        issues.append("缺少 H1 标题")
    h2_count = len(re.findall(r"(?m)^##\s+", stripped))
    if h2_count < 3:
        issues.append(f"仅有 {h2_count} 个 H2 章节（至少 3）")
    if "```mermaid" not in stripped:
        issues.append("缺少 Mermaid 图")
    if "Sources:" not in stripped and "相关源文件" not in stripped:
        issues.append("缺少源码引用标记")
    return issues


def _rich_page(content: str, minimum_sources: int = 5) -> bool:
    return not _page_quality_issues(content, minimum_sources)
