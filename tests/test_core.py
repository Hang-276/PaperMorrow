from datetime import datetime, timezone
import base64
import uuid
import asyncio
import json
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from pypdf import PdfWriter

from backend.agent.researcher import create_researcher, _requested_final_answer
from backend.app.catalog import detect_venue
from backend.app.deepwiki_service import _fallback_page, _generate_llm_wiki, _generate_original_wiki, _generate_wiki, _valid_page_content, _write_wiki, validate_repository_url, wiki_is_full_deepwiki
from backend.app.main import app
from backend.app.database import SessionLocal
from backend.app.models import ChatSession, LibraryEntry, LibraryFolder, LibraryTag, LocalPaperFile, Paper, PaperNote, RecommendationAssessment, RecommendationBatch, ResearchProfile, ResearchStudy, Tag, TokenUsage
from backend.app.library_folder_service import LibraryFolderService
from backend.app.research_service import ResearchService
from backend.app.recommendation import RecommendationService
from backend.app.paper_sources import PaperCandidate
from backend.app.recommendation import identity_hash, normalize_title
from backend.app.recommendation_pipeline import (
    ArxivCandidateSource, CandidateFilter, CandidateSource, DefaultSelector,
    PermanentCandidateFilter, RecommendationContext as PipelineContext,
    RecommendationResult, RuleRanker,
)
from backend.app.llm import LLMClient, provider_defaults
from backend.app.schemas import SettingsUpdate
from backend.app.settings_service import get_settings, update_settings
from backend.app.usage_service import token_usage_stats
from backend.app.zotero_service import ZoteroService
from backend.prompts.prompt_template import apply_prompt_template
from backend.model.notepad import Notepad
from backend.model.todo_list import TodoList
from backend.model.state import TokenCounter
from backend.workspace import Project
from backend.tools.code_rag_tools import search_in_folders as search_in_folders_tool


def test_title_normalization_and_identity_are_stable():
    assert normalize_title("  A Paper: About AI! ") == "a paper about ai"
    candidate = PaperCandidate(
        title="A Paper About AI",
        abstract="abstract",
        authors=["A"],
        published_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        arxiv_id="2607.01234",
        primary_url="https://arxiv.org/abs/2607.01234",
        pdf_url=None,
    )
    digest = identity_hash(candidate)
    candidate.title = "A completely changed title"
    assert identity_hash(candidate) == digest


def test_recommendation_pipeline_interfaces_and_permanent_filter():
    class FakeArxiv:
        async def fetch(self, categories, keywords, limit):
            return []

    source = ArxivCandidateSource(FakeArxiv())
    assert isinstance(source, CandidateSource)
    assert isinstance(RuleRanker(), object)
    assert isinstance(DefaultSelector(), object)
    assert RecommendationResult(items=[], degraded=True).degraded is True

    db = SessionLocal()
    marker = uuid.uuid4().hex[:12]
    paper = Paper(
        title_en=f"Permanent dedup {marker}", abstract_en="Known local paper.", authors_json="[]",
        primary_url="https://example.com/known", arxiv_id=f"known-{marker}", identity_hash=uuid.uuid4().hex,
    )
    paper.library_entry = LibraryEntry(source="test")
    db.add(paper); db.commit()
    known = PaperCandidate(
        title=paper.title_en, abstract="Known local paper.", authors=["A"],
        published_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        arxiv_id=paper.arxiv_id, primary_url=paper.primary_url, pdf_url=None,
    )
    excluded = PaperCandidate(
        title=f"Excluded {marker}", abstract="prompt-only approach", authors=["B"],
        published_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        arxiv_id=f"excluded-{marker}", primary_url="https://example.com/excluded", pdf_url=None,
    )
    fresh = PaperCandidate(
        title=f"Fresh {marker}", abstract="New candidate", authors=["C"],
        published_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        arxiv_id=f"fresh-{marker}", primary_url="https://example.com/fresh", pdf_url=None,
    )
    resolver = lambda item: db.query(Paper).filter(Paper.arxiv_id == item.arxiv_id).one_or_none()
    candidate_filter = PermanentCandidateFilter(db, resolver)
    assert isinstance(candidate_filter, CandidateFilter)
    context = PipelineContext(tags=[], count=5, mode="broad", settings={}, exclusions=["prompt-only"])
    try:
        accepted = candidate_filter.apply([known, excluded, fresh, fresh], context)
        assert accepted == [fresh]
    finally:
        db.delete(paper); db.commit(); db.close()


def test_venue_detection_requires_explicit_publication_signal_upstream():
    assert detect_venue("Accepted at CVPR 2026")[1] == "CCF-A/top"
    assert detect_venue("Physical Review Letters 130, 010001")[1] == "field-top"
    assert detect_venue("Submitted to CVPR 2026")[1] == "preprint"
    assert detect_venue(None)[2] == "preprint"


def test_repository_url_validation():
    assert validate_repository_url("https://github.com/openai/codex") == "https://github.com/openai/codex"
    with pytest.raises(ValueError):
        validate_repository_url("https://example.com/owner/repo")
    with pytest.raises(ValueError):
        validate_repository_url("https://github.com/owner/repo/issues")


def test_zhizengzeng_openai_compatible_preset():
    preset = provider_defaults("zhizengzeng")
    assert preset["base_url"] == "https://api.zhizengzeng.com/v1"
    assert SettingsUpdate(llm_provider="zhizengzeng").llm_provider == "zhizengzeng"
    client = object.__new__(LLMClient)
    client.base_url = preset["base_url"]
    assert client._chat_url() == "https://api.zhizengzeng.com/v1/chat/completions"


def test_multiple_llm_profiles_can_be_created_and_activated():
    with TestClient(app) as client:
        profiles = client.get("/api/llm/profiles").json()
        assert profiles and sum(item["is_active"] for item in profiles) == 1
        original_active_id = next(item["id"] for item in profiles if item["is_active"])
        created = client.post("/api/llm/profiles", json={
            "name": "测试中转", "provider": "custom", "base_url": "https://relay.example.com/v1",
            "model": "test-model", "api_key": "test-secret",
        })
        assert created.status_code == 200
        profile_id = created.json()["id"]
        try:
            activated = client.post(f"/api/llm/profiles/{profile_id}/activate")
            assert activated.status_code == 200
            assert activated.json()["is_active"] is True
            refreshed = client.get("/api/llm/profiles").json()
            assert next(item for item in refreshed if item["id"] == profile_id)["has_api_key"] is True
        finally:
            client.delete(f"/api/llm/profiles/{profile_id}")
            restored = client.post(f"/api/llm/profiles/{original_active_id}/activate")
            assert restored.status_code == 200


def test_token_usage_rollup_keeps_estimated_flag():
    db = SessionLocal()
    row = TokenUsage(
        profile_id="usage-test", profile_name="Usage Test", provider="custom", model="model",
        purpose="chat", prompt_tokens=120, completion_tokens=30, total_tokens=150, estimated=True,
    )
    db.add(row); db.commit()
    try:
        stats = token_usage_stats(db, "Asia/Shanghai")
        profile = next(item for item in stats["by_profile"] if item["profile_id"] == "usage-test")
        assert profile["total_tokens"] == 150
        assert profile["estimated_requests"] == 1
        assert stats["total"]["total_tokens"] >= 150
    finally:
        db.delete(row); db.commit(); db.close()


def test_api_defaults_and_chat_contract():
    with TestClient(app) as client:
        health = client.get("/api/system/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["service"] == "PaperMorrow"
        tags = client.get("/api/tags").json()
        assert len(tags) >= 10
        assert {"ai", "computer", "physics", "math"}.issubset({item["domain"] for item in tags})
        assert {"agent-harness", "self-evolving-models", "test-time-learning"}.issubset({item["slug"] for item in tags})
        settings = client.get("/api/settings").json()
        assert settings["daily_enabled"] is False
        assert settings["default_abstract_language"] == "zh"
        assert 13 <= settings["font_size"] <= 20
        assert settings["llm_rerank_enabled"] is True
        assert {item["value"] for item in settings["timezone_options"]} == {
            "Asia/Shanghai", "America/New_York", "America/Los_Angeles"
        }
        chat = client.post("/api/papers/999/chat", json={"message": "hello"})
        assert chat.status_code == 404


def test_research_profile_crud_and_weight_validation():
    profile_id = None
    with TestClient(app) as client:
        created = client.post("/api/research-profiles", json={
            "name": "自进化 LLM", "domain": "ai",
            "description": "关注模型利用反馈、经验与自生成数据持续改进自身能力",
            "positive_keywords": ["self-improving language model", "reflective learning"],
            "negative_keywords": ["prompt-only"], "seed_papers": ["https://arxiv.org/abs/2601.00001"],
            "relevance_weight": .6, "recency_weight": .25, "exploration_ratio": .15,
        })
        assert created.status_code == 200
        profile_id = created.json()["id"]
        assert created.json()["positive_keywords"][0] == "self-improving language model"
        invalid = client.put(f"/api/research-profiles/{profile_id}", json={"relevance_weight": .8, "recency_weight": .2})
        assert invalid.status_code == 400
        updated = client.put(f"/api/research-profiles/{profile_id}", json={"exploration_ratio": .3})
        assert updated.status_code == 200 and updated.json()["exploration_ratio"] == .3
        deleted = client.delete(f"/api/research-profiles/{profile_id}")
        assert deleted.status_code == 200


def test_focused_recommendation_records_direction_match(monkeypatch):
    now = datetime.now(timezone.utc)
    candidates = [
        PaperCandidate(
            title="Reflective Self-Improvement for Language Model Agents",
            abstract="A self-improving language model agent learns from reflective experience and feedback.",
            authors=["A"], published_at=now, updated_at=now, arxiv_id=f"test-{uuid.uuid4().hex[:10]}",
            primary_url="https://arxiv.org/abs/test", pdf_url="https://arxiv.org/pdf/test",
        ),
        PaperCandidate(
            title="A General Vision Benchmark",
            abstract="A broad image recognition benchmark with no agent adaptation.",
            authors=["B"], published_at=now, updated_at=now, arxiv_id=f"test-{uuid.uuid4().hex[:10]}",
            primary_url="https://arxiv.org/abs/test2", pdf_url="https://arxiv.org/pdf/test2",
        ),
    ]

    class FakeArxiv:
        async def fetch(self, categories, keywords, limit):
            return candidates

    class FakeS2:
        async def enrich(self, candidate):
            return {}

    class UnconfiguredLLM:
        configured = False
        def __init__(self, db): pass

    monkeypatch.setattr("backend.app.recommendation.LLMClient", UnconfiguredLLM)
    db = SessionLocal()
    profile = ResearchProfile(
        name="自进化 LLM", domain="ai", description="language model agents that improve from reflection and experience",
        positive_keywords_json='["self-improving", "reflective experience"]', negative_keywords_json="[]", seed_papers_json="[]",
        relevance_weight=.65, recency_weight=.2, exploration_ratio=.2,
    )
    db.add(profile); db.commit()
    tag = db.query(Tag).filter(Tag.slug == "self-evolving-models").one()
    service = RecommendationService(db); service.arxiv = FakeArxiv(); service.s2 = FakeS2()
    try:
        batch = asyncio.run(service.generate([tag.id], 1, profile_id=profile.id, mode="focus"))
        assert batch.status == "completed" and batch.context.profile_name == "自进化 LLM"
        assert batch.recommendations[0].match is not None
        assert batch.recommendations[0].match.relevance_score > 0
        assert batch.recommendations[0].paper.title_en.startswith("Reflective")
    finally:
        created_papers = [db.query(Paper).filter(Paper.arxiv_id == item.arxiv_id).one_or_none() for item in candidates]
        stored_batch = db.get(RecommendationBatch, batch.id) if 'batch' in locals() else None
        if stored_batch: db.delete(stored_batch)
        db.flush()
        for paper in created_papers:
            if paper: db.delete(paper)
        stored_profile = db.get(ResearchProfile, profile.id)
        if stored_profile: db.delete(stored_profile)
        db.commit(); db.close()


def test_reader_figure_can_be_saved_and_served():
    # Valid 1x1 PNG generated once for the endpoint contract test.
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    db = SessionLocal()
    paper = Paper(title_en="Reader figure test", abstract_en="", authors_json="[]", primary_url="https://example.com", identity_hash=uuid.uuid4().hex)
    db.add(paper); db.commit(); paper_id = paper.id; db.close()
    figure_url = None
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/papers/{paper_id}/reader/figures", json={
                "data_url": "data:image/png;base64," + base64.b64encode(png).decode(), "page": 3, "caption": "方法示意图",
            })
            assert response.status_code == 200
            figure_url = response.json()["url"]
            assert "![方法示意图]" in response.json()["markdown"]
            served = client.get(figure_url)
            assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    finally:
        if figure_url:
            from backend.app.reader_service import reader_figure_path
            path = reader_figure_path(paper_id, figure_url.rsplit("/", 1)[-1])
            if path: path.unlink(missing_ok=True)
        db = SessionLocal(); stored = db.get(Paper, paper_id)
        if stored: db.delete(stored)
        db.commit(); db.close()


def test_chat_session_persistence_contract():
    db = SessionLocal()
    paper = Paper(
        title_en="A Test Paper for Chat",
        abstract_en="A minimal abstract.",
        authors_json="[]",
        primary_url="https://example.com/paper",
        identity_hash=uuid.uuid4().hex,
    )
    db.add(paper)
    db.commit()
    paper_id = paper.id
    db.close()
    try:
        with TestClient(app) as client:
            created = client.post(f"/api/papers/{paper_id}/chat/sessions", json={"title": "方法讨论"})
            assert created.status_code == 200
            session_id = created.json()["id"]
            sessions = client.get(f"/api/papers/{paper_id}/chat/sessions").json()
            assert sessions[0]["title"] == "方法讨论"
            assert client.get(f"/api/papers/{paper_id}/chat/sessions/{session_id}/messages").json() == []
    finally:
        db = SessionLocal()
        for session in db.query(ChatSession).filter(ChatSession.paper_id == paper_id).all():
            db.delete(session)
        stored = db.get(Paper, paper_id)
        if stored:
            db.delete(stored)
        db.commit()
        db.close()


def test_llm_rerank_changes_mechanical_order(monkeypatch):
    class FakeLLM:
        configured = True
        model = "taste-test-model"

        def __init__(self, db):
            pass

        async def rank_papers(self, papers, preferences):
            return [
                {"paper_id": papers[0]["paper_id"], "taste_score": 10, "novelty_score": 10, "value_score": 20, "confidence": 100, "reason": "增量工作", "caution": "价值有限"},
                {"paper_id": papers[1]["paper_id"], "taste_score": 96, "novelty_score": 92, "value_score": 98, "confidence": 95, "reason": "问题重要且方法有启发", "caution": ""},
            ]

    monkeypatch.setattr("backend.app.recommendation.LLMClient", FakeLLM)
    db = SessionLocal()
    papers = [
        Paper(title_en="Mechanical favorite", abstract_en="Incremental.", authors_json="[]", primary_url="https://example.com/1", identity_hash=uuid.uuid4().hex),
        Paper(title_en="Taste favorite", abstract_en="Novel and valuable.", authors_json="[]", primary_url="https://example.com/2", identity_hash=uuid.uuid4().hex),
    ]
    db.add_all(papers)
    db.commit()
    ranked = [(papers[0], 90.0), (papers[1], 60.0)]
    used = asyncio.run(RecommendationService(db)._apply_llm_rerank(ranked, [Tag(name_en="Agents", name_zh="智能体", slug="test", query="agent")], 2, {"llm_rerank_enabled": True, "llm_rerank_weight": 0.6}))
    try:
        assert used is True
        assert ranked[1][1] > ranked[0][1]
        assert db.get(RecommendationAssessment, papers[1].id).reason == "问题重要且方法有启发"
    finally:
        for paper in papers:
            stored = db.get(Paper, paper.id)
            if stored:
                db.delete(stored)
        db.commit()
        db.close()


def test_chat_endpoint_persists_both_messages(monkeypatch):
    class FakeChatLLM:
        def __init__(self, db):
            pass

        async def chat_about_paper(self, context, messages):
            assert "Grounded chat paper" in context
            assert messages[-1]["content"] == "核心创新是什么？"
            return "核心创新在于测试可追踪的论文上下文对话。"

    monkeypatch.setattr("backend.app.api.LLMClient", FakeChatLLM)
    db = SessionLocal()
    paper = Paper(title_en="Grounded chat paper", abstract_en="A grounded abstract.", authors_json="[]", primary_url="https://example.com/chat", identity_hash=uuid.uuid4().hex)
    db.add(paper); db.commit(); paper_id = paper.id; db.close()
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/papers/{paper_id}/chat", json={"message": "核心创新是什么？"})
            assert response.status_code == 200
            session_id = response.json()["session_id"]
            messages = client.get(f"/api/papers/{paper_id}/chat/sessions/{session_id}/messages").json()
            assert [item["role"] for item in messages] == ["user", "assistant"]
    finally:
        db = SessionLocal()
        for session in db.query(ChatSession).filter(ChatSession.paper_id == paper_id).all():
            db.delete(session)
        stored = db.get(Paper, paper_id)
        if stored:
            db.delete(stored)
        db.commit(); db.close()


def test_library_membership_and_multiple_personal_tags():
    db = SessionLocal()
    paper = Paper(
        title_en="Library classification contract", abstract_en="A paper used to test the learning library.",
        authors_json='["Researcher One"]', primary_url="https://example.com/library-contract",
        identity_hash=uuid.uuid4().hex,
    )
    db.add(paper); db.commit(); paper_id = paper.id; db.close()
    tag_ids = []
    try:
        with TestClient(app) as client:
            added = client.post(f"/api/library/papers/{paper_id}")
            assert added.status_code == 200 and added.json()["in_library"] is True
            for name, color in (("Harness", "#0a84ff"), ("自进化", "#af52de")):
                response = client.post("/api/library/tags", json={"name": f"{name}-{paper_id}", "color": color})
                assert response.status_code == 200
                tag_ids.append(response.json()["id"])
            classified = client.put(f"/api/library/papers/{paper_id}/tags", json={"tag_ids": tag_ids})
            assert classified.status_code == 200
            assert {tag["id"] for tag in classified.json()["library_tags"]} == set(tag_ids)
            filtered = client.get("/api/library/papers", params=[("tag_ids", tag_ids[0]), ("tag_ids", tag_ids[1])])
            assert any(item["id"] == paper_id for item in filtered.json())
            removed = client.delete(f"/api/library/papers/{paper_id}")
            assert removed.status_code == 200
            assert client.get(f"/api/papers/{paper_id}").status_code == 200
    finally:
        db = SessionLocal()
        for tag_id in tag_ids:
            tag = db.get(LibraryTag, tag_id)
            if tag:
                db.delete(tag)
        entry = db.get(LibraryEntry, paper_id)
        if entry:
            db.delete(entry)
        stored = db.get(Paper, paper_id)
        if stored:
            db.delete(stored)
        db.commit(); db.close()


def test_deepwiki_empty_llm_page_falls_back_to_real_markdown(tmp_path):
    class EmptyPageLLM:
        async def generate_wiki_structure(self, repository_url, context):
            return {
                "title": "测试 Wiki", "description": "两阶段生成测试",
                "pages": [{"id": "overview", "title": "项目概览", "description": "核心实现", "relevant_files": ["main.py"]}],
            }

        async def generate_wiki_page(self, repository_url, page, source_context, related):
            return ""

    analysis = {
        "files": ["main.py"], "languages": {"Python": 1}, "readme": "# Demo\nA reliable repository.",
        "snippets": ["## main.py\n" + "def run():\n    return 'ok'\n" * 5],
        "file_contents": {"main.py": "def run():\n    return 'ok'\n" * 8},
    }
    wiki = asyncio.run(_generate_llm_wiki(EmptyPageLLM(), "https://github.com/example/demo", "context", analysis))
    assert _valid_page_content(wiki["pages"][0]["content"])
    _write_wiki(tmp_path, wiki)
    saved = (tmp_path / "pages" / "overview.md").read_text()
    assert "相关源码" in saved and "def run" in saved


def test_zotero_payload_preserves_metadata_and_personal_tags():
    class TemplateResponse:
        status_code = 200

        def json(self):
            return {
                "itemType": "journalArticle", "title": "", "creators": [], "abstractNote": "", "url": "", "date": "",
                "DOI": "", "publicationTitle": "", "archive": "", "archiveLocation": "", "extra": "", "tags": [], "collections": [],
            }

        def raise_for_status(self):
            return None

    class TemplateClient:
        async def get(self, *args, **kwargs):
            return TemplateResponse()

    db = SessionLocal()
    paper = Paper(
        title_en="A Zotero Metadata Test", abstract_en="Metadata should remain searchable.", authors_json='["Ada Lovelace", "Alan Turing"]',
        published_at=datetime.now(timezone.utc), venue_name="Nature", publication_status="published", doi="10.0000/zotero-test-" + uuid.uuid4().hex,
        primary_url="https://example.com/zotero", identity_hash=uuid.uuid4().hex,
    )
    tag = LibraryTag(name="重要方法-" + uuid.uuid4().hex[:6], normalized_name="zotero-" + uuid.uuid4().hex, color="#0a84ff")
    paper.library_entry = LibraryEntry(source="test", tags=[tag])
    db.add(paper); db.commit()
    service = object.__new__(ZoteroService)
    service.sync_tags = True; service.collection_key = "COLLECTION1"
    try:
        payload = asyncio.run(service._item_payload(TemplateClient(), paper))
        assert payload["title"] == paper.title_en and payload["DOI"] == paper.doi
        assert [creator["name"] for creator in payload["creators"]] == ["Ada Lovelace", "Alan Turing"]
        assert {item["tag"] for item in payload["tags"]} == {"PaperMorrow", tag.name}
        assert payload["collections"] == ["COLLECTION1"]
    finally:
        db.delete(paper); db.delete(tag); db.commit(); db.close()


def test_original_deepwiki_prompts_schema_and_static_guardrail(tmp_path):
    structure_prompt = apply_prompt_template("wiki_structure")
    page_prompt = apply_prompt_template("wiki_page", page={
        "id": "architecture", "title": "系统架构", "description": "组件关系",
        "importance": "high", "relevant_files": ["main.py"], "related_pages": [], "parent_section": "system-architecture",
    })
    assert "Create 8-15 pages" in structure_prompt
    assert '"sections"' in structure_prompt and '"parent_section"' in structure_prompt
    assert "The very first thing on the page MUST be a `<details>` block" in page_prompt
    assert "EXTENSIVELY use Mermaid diagrams" in page_prompt
    assert "AT LEAST 5 different source files" in page_prompt

    analysis = {
        "files": ["main.py", "service.py"], "languages": {"Python": 2}, "readme": "",
        "snippets": [],
        "file_contents": {
            "main.py": "from service import run\n\ndef main():\n    return run()\n" * 20,
            "service.py": "def run():\n    return 'ok'\n" * 30,
        },
    }
    content = _fallback_page({
        "id": "architecture", "title": "系统架构", "description": "组件关系",
        "relevant_files": ["main.py", "service.py"], "related_pages": [], "parent_section": "system-architecture",
    }, "https://github.com/example/demo", analysis)
    assert content.startswith("<details>") and "```mermaid\ngraph TD" in content
    assert "Sources: [main.py:1-" in content and len(content) > 1200

    project = Project(root_dir=str(tmp_path))
    with pytest.raises(ValueError):
        project.map_path("../outside.txt")
    assert project.map_path("/main.py") == str((tmp_path / "main.py").resolve())


def test_original_deepwiki_async_agent_can_execute_tools(tmp_path):
    """Regress the async middleware mismatch that previously forced a static Wiki."""
    (tmp_path / "README.md").write_text("# Async DeepWiki test\n", encoding="utf-8")

    class ToolCallingModel(FakeMessagesListChatModel):
        seen_tool_contents: list[str] = []

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, *args, **kwargs):
            self.seen_tool_contents.extend(
                str(message.content) for message in messages if message.type == "tool"
            )
            return super()._generate(messages, *args, **kwargs)

    model = ToolCallingModel(responses=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_tree",
                "args": {"path": "", "max_depth": 1},
                "id": "file-tree-call",
                "type": "tool_call",
            }],
        ),
        AIMessage(content="已读取仓库结构并完成研究。"),
    ])
    state = {
        "messages": [HumanMessage(content="请研究这个仓库")],
        "project": Project(root_dir=str(tmp_path)),
        "todo_list": TodoList(),
        "notepad": Notepad(notes=[]),
        "token_counter": TokenCounter(),
        "research_steps": 0,
    }

    result = asyncio.run(create_researcher(model).ainvoke(state))

    assert result["messages"][-1].content == "已读取仓库结构并完成研究。"
    assert any("README.md" in content for content in model.seen_tool_contents)


def test_original_deepwiki_ready_signal_forces_plain_final_answer(tmp_path):
    """`ready_to_answer` must be a real graph stop protocol, not prompt advice."""
    (tmp_path / "README.md").write_text("# Completion protocol\n", encoding="utf-8")

    class ReadyModel(FakeMessagesListChatModel):
        tool_binding_sizes: ClassVar[list[int]] = []

        def bind_tools(self, tools, **kwargs):
            self.tool_binding_sizes.append(len(tools))
            return self

    ReadyModel.tool_binding_sizes = []
    model = ReadyModel(responses=[
        AIMessage(content="", tool_calls=[{
            "name": "react",
            "args": {
                "thoughts": "研究完成",
                "add_note": "## 完成\n已取得足够源码证据。",
                "mark_todo_as_done": [],
                "ready_to_answer": True,
                "father_id": 0,
                "add_todo": [],
            },
            "id": "ready-call",
            "type": "tool_call",
        }]),
        AIMessage(content='{"title":"最终目录"}'),
    ])
    state = {
        "messages": [HumanMessage(content="生成目录")],
        "project": Project(root_dir=str(tmp_path)),
        "todo_list": TodoList(),
        "notepad": Notepad(notes=[]),
        "token_counter": TokenCounter(),
        "research_steps": 0,
    }

    result = asyncio.run(create_researcher(model).ainvoke(state))

    assert result["messages"][-1].content == '{"title":"最终目录"}'
    assert ReadyModel.tool_binding_sizes == [6]
    assert result["research_steps"] == 2
    assert _requested_final_answer({**state, "research_steps": 64})


def test_original_deepwiki_repairs_invalid_structure_json(monkeypatch):
    from backend.app.original_deepwiki import OriginalDeepWikiEngine

    valid = {
        "title": "测试 Wiki",
        "description": "修复后的目录",
        "sections": [
            {"id": "overview", "title": "概述", "pages": ["intro"], "subsections": []},
            {"id": "implementation", "title": "实现", "pages": [], "subsections": []},
        ],
        "pages": [{
            "id": "intro", "title": "项目介绍", "description": "介绍项目",
            "importance": "high", "relevant_files": ["README.md"],
            "related_pages": [], "parent_section": "overview",
        }],
    }
    engine = object.__new__(OriginalDeepWikiEngine)
    engine.chat_model = FakeMessagesListChatModel(responses=[AIMessage(content=json.dumps(valid))])
    engine._record_usage = lambda *args, **kwargs: None

    repaired = asyncio.run(engine._repair_structure("{broken", ValueError("invalid JSON")))

    assert repaired["title"] == "测试 Wiki"
    assert repaired["pages"][0]["relevant_files"] == ["README.md"]


def test_original_deepwiki_source_requirement_respects_small_repository(tmp_path):
    from backend.app.original_deepwiki import _minimum_source_count, _repository_evidence_policy, _rich_page, _source_files

    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
    content = """<details>
<summary>相关源文件</summary>

- [README.md](README.md)
- [main.py](main.py)
</details>

# 小型仓库

## 架构
正文

## 实现
正文

## 修改指南
```mermaid
graph TD
  A --> B
```

Sources: [main.py:1-1](main.py#L1-L1)
""" + "基于源码的详细说明。" * 260

    assert _minimum_source_count(tmp_path) == 2
    assert _source_files(tmp_path) == ["README.md", "main.py"]
    policy = _repository_evidence_policy(_source_files(tmp_path))
    assert "required number of distinct files in source lists is therefore 2" in policy
    assert "never cite a path outside this exact list" in policy
    assert _rich_page(content, _minimum_source_count(tmp_path))
    assert not _rich_page(content)


def test_original_deepwiki_search_wildcard_maps_to_safe_text_extensions(tmp_path):
    (tmp_path / "main.py").write_text("UNIQUE_AGENT_SYMBOL = 1\n", encoding="utf-8")

    class RuntimeStub:
        state = {"project": Project(root_dir=str(tmp_path))}

    result = search_in_folders_tool.func(
        keyword="UNIQUE_AGENT_SYMBOL",
        folders=["."],
        file_extensions=["*"],
        runtime=RuntimeStub(),
    )

    assert "main.py" in result


def test_original_deepwiki_serialized_dsml_is_finalized_without_tools(tmp_path):
    from backend.app.original_deepwiki import OriginalDeepWikiEngine

    (tmp_path / "main.py").write_text("def run():\n    return True\n", encoding="utf-8")

    class SerializedToolResearcher:
        async def ainvoke(self, state, config=None):
            return {
                **state,
                "messages": [AIMessage(
                    content='<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="read_lines">',
                )],
                "notepad": Notepad(notes=[]),
            }

    engine = object.__new__(OriginalDeepWikiEngine)
    engine.project = Project(root_dir=str(tmp_path))
    engine.researcher = SerializedToolResearcher()
    engine.chat_model = FakeMessagesListChatModel(
        responses=[AIMessage(content="# 已完成的最终页面\n\n基于已有研究证据。")]
    )
    engine._record_usage = lambda *args, **kwargs: None

    content = asyncio.run(engine._ask("请输出最终 Markdown"))

    assert content.startswith("# 已完成的最终页面")
    assert "DSML" not in content


def test_original_deepwiki_page_quality_reports_exact_failures():
    from backend.app.original_deepwiki import _page_quality_issues

    issues = _page_quality_issues(
        '<｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke name="read_lines">',
        minimum_sources=5,
    )

    assert "返回了序列化工具调用而非正文" in issues
    assert any("2500" in issue for issue in issues)
    assert "开头缺少 <details> 相关源文件区块" in issues
    assert "缺少 H1 标题" in issues
    assert "缺少 Mermaid 图" in issues


def test_deepwiki_never_marks_static_fallback_as_llm_success(monkeypatch, tmp_path):
    class UnconfiguredLLM:
        configured = False

        def __init__(self, db):
            pass

    monkeypatch.setattr("backend.app.deepwiki_service.LLMClient", UnconfiguredLLM)
    with pytest.raises(RuntimeError, match="缺少 API Key"):
        _generate_wiki(object(), "https://github.com/example/demo", {"files": []}, tmp_path)


def test_original_deepwiki_requires_comprehensive_structure():
    class ShallowEngine:
        async def generate_structure(self):
            return {
                "title": "浅层 Wiki", "description": "不应被接受", "sections": [],
                "pages": [{
                    "id": f"page-{index}", "title": f"页面 {index}", "description": "过少",
                    "importance": "high", "relevant_files": [], "related_pages": [], "parent_section": None,
                } for index in range(3)],
            }

        async def generate_page(self, page):
            raise AssertionError("浅层目录不应进入页面生成")

    with pytest.raises(ValueError, match="页面结构"):
        asyncio.run(_generate_original_wiki(ShallowEngine(), "https://github.com/example/demo", {"files": []}))


def test_full_deepwiki_quality_marker_requires_original_graph(tmp_path):
    pages = [{
        "id": f"page-{index}", "title": f"页面 {index}", "description": "完整主题页",
        "importance": "high", "relevant_files": ["main.py"], "related_pages": [],
        "parent_section": "section-a" if index < 4 else "section-b",
        "content": f"# 页面 {index}\n\n" + "来自源码的完整内容。" * 20,
    } for index in range(8)]
    _write_wiki(tmp_path, {
        "title": "完整 Wiki", "description": "原版研究图输出", "generator": "ace-deepwiki", "schema_version": 2,
        "sections": [
            {"id": "section-a", "title": "架构", "pages": [f"page-{i}" for i in range(4)], "subsections": []},
            {"id": "section-b", "title": "实现", "pages": [f"page-{i}" for i in range(4, 8)], "subsections": []},
        ],
        "pages": pages,
    })
    assert wiki_is_full_deepwiki(tmp_path)


def test_local_pdf_vault_syncs_real_folders_and_knowledge_links(tmp_path):
    db = SessionLocal()
    original_root = str(get_settings(db).get("library_root") or "")
    vault = tmp_path / "paper-vault"
    unique = uuid.uuid4().hex
    top_folder = f"Agents-{unique}"
    nested = vault / top_folder / "Self-Evolution"
    nested.mkdir(parents=True)
    title = f"Local Vault Contract {unique}"
    pdf_path = nested / f"{title}.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Title": title, "/Author": "Paper Morrow"})
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    paper_id = None
    try:
        service = LibraryFolderService(db)
        result = service.scan(str(vault))
        assert result["imported"] == 1 and result["failed"] == 0
        folder = db.query(LibraryFolder).filter(LibraryFolder.relative_path == f"{top_folder}/Self-Evolution").one()
        local_file = db.query(LocalPaperFile).filter(LocalPaperFile.relative_path == f"{top_folder}/Self-Evolution/{title}.pdf").one()
        paper = local_file.paper
        paper_id = paper.id
        assert paper.library_entry is not None
        assert folder in paper.library_entry.folders
        assert paper.pdf_url == f"/api/library/files/{local_file.id}/pdf"

        paper.note = PaperNote(content=f"# Notes\n\nConnect to [[Verified Agent Loop {unique}]].")
        db.commit()
        graph = service.knowledge_graph()
        assert any(node["type"] == "concept" and unique in node["label"] for node in graph["nodes"])
        assert any(edge["type"] == "concept" and edge["source"] == f"paper:{paper.id}" for edge in graph["edges"])

        second = service.scan()
        assert second["skipped"] == 1 and second["imported"] == 0
    finally:
        if paper_id:
            paper = db.get(Paper, paper_id)
            if paper:
                db.delete(paper)
                db.flush()
        for row in db.query(LibraryFolder).filter(LibraryFolder.relative_path.like(f"{top_folder}%")).order_by(LibraryFolder.relative_path.desc()).all():
            db.delete(row)
        db.commit()
        update_settings(db, {"library_root": original_root})
        LibraryFolderService(db).sync_folder_tree()
        db.close()


def test_llm_research_ranks_deduplicates_and_generates_review():
    unique = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    candidates = [
        PaperCandidate(
            title=f"Verified Self-Evolving Agents {unique}",
            abstract="Agents improve through verifiable rewards, persistent experience and closed-loop evaluation.",
            authors=["Researcher A"], published_at=now, updated_at=now,
            arxiv_id=f"test-{unique}-a", primary_url="https://arxiv.org/abs/test-a", pdf_url="https://arxiv.org/pdf/test-a",
        ),
        PaperCandidate(
            title=f"Generic Vision Baseline {unique}", abstract="A generic visual recognition baseline.",
            authors=["Researcher B"], published_at=now, updated_at=now,
            arxiv_id=f"test-{unique}-b", primary_url="https://arxiv.org/abs/test-b", pdf_url="https://arxiv.org/pdf/test-b",
        ),
    ]

    class FakeSource:
        async def search(self, query, limit):
            return candidates

    class FakeResearchLLM:
        configured = True
        model = "research-contract-model"

        async def expand_research_profile(self, name, description, positive, negative, seeds):
            return {"search_terms": ["self-evolving agents", "verifiable rewards"], "core_concepts": ["闭环训练", "经验积累"]}

        async def rank_papers(self, papers, preferences):
            return [
                {"paper_id": papers[0]["paper_id"], "relevance_score": 96, "value_score": 94, "novelty_score": 91, "confidence": 93, "relation_reason": "直接覆盖可验证奖励与闭环自进化。"},
                {"paper_id": papers[1]["paper_id"], "relevance_score": 25, "value_score": 42, "novelty_score": 38, "confidence": 90, "relation_reason": "仅作为弱相关视觉基线。"},
            ]

        async def generate_literature_review(self, topic, domain, papers):
            assert papers[0]["title"].startswith("Verified Self-Evolving")
            return "# 自动综述\n\n可验证奖励形成闭环训练主线 [P1]。"

    db = SessionLocal()
    study_id = None
    paper_ids: list[int] = []
    try:
        service = ResearchService(db)
        service.llm = FakeResearchLLM()
        service.arxiv = FakeSource()
        service.s2 = FakeSource()
        study = asyncio.run(service.run("ai", "不依赖人工反馈的自进化智能体闭环训练", 2))
        study_id = study.id
        paper_ids = [item.paper_id for item in study.papers]
        assert study.status == "completed"
        assert len(study.papers) == 2
        assert study.papers[0].paper.title_en.startswith("Verified Self-Evolving")
        assert study.papers[0].final_score > study.papers[1].final_score
        assert len({item.paper_id for item in study.papers}) == 2
        generated = asyncio.run(service.generate_review(study))
        assert "[P1]" in generated.review_markdown
    finally:
        if study_id:
            study = db.get(ResearchStudy, study_id)
            if study:
                db.delete(study)
                db.flush()
        for paper_id in paper_ids:
            paper = db.get(Paper, paper_id)
            if paper:
                db.delete(paper)
        db.commit()
        db.close()
