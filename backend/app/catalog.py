from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, Tag


DEFAULT_TAGS = [
    ("llm", "大语言模型", "Large Language Models", "large language model OR LLM OR language model", ["cs.CL", "cs.AI", "cs.LG"]),
    ("agents", "智能体", "AI Agents", "AI agent OR autonomous agent OR tool use OR agentic", ["cs.AI", "cs.CL", "cs.MA"]),
    ("agent-harness", "智能体 Harness 与基础设施", "Agent Harness & Infrastructure", "agent harness OR agent infrastructure OR tool orchestration OR agent runtime OR agent framework OR agent evaluation harness", ["cs.AI", "cs.CL", "cs.SE", "cs.DC"]),
    ("self-evolving-models", "自进化与自改进模型", "Self-Evolving & Self-Improving Models", "self evolving language model OR self improving model OR recursive self improvement OR continual self training OR reflective learning OR self refinement", ["cs.AI", "cs.CL", "cs.LG"]),
    ("test-time-learning", "测试时学习与自适应", "Test-Time Learning & Adaptation", "test time learning OR test time adaptation OR inference time scaling OR online adaptation", ["cs.LG", "cs.AI", "cs.CL"]),
    ("long-context-memory", "长上下文与记忆", "Long Context & Memory", "long context language model OR agent memory OR episodic memory OR context compression", ["cs.CL", "cs.AI", "cs.LG"]),
    ("reasoning", "推理与规划", "Reasoning & Planning", "language model reasoning OR chain of thought OR planning OR verification OR theorem proving", ["cs.CL", "cs.AI", "cs.LO"]),
    ("ai-evaluation", "评测与基准", "AI Evaluation & Benchmarks", "language model evaluation OR AI benchmark OR agent benchmark OR evaluation methodology", ["cs.AI", "cs.CL", "cs.LG"]),
    ("rag", "检索增强生成", "Retrieval-Augmented Generation", "retrieval augmented generation OR RAG", ["cs.CL", "cs.IR", "cs.AI"]),
    ("multimodal", "多模态", "Multimodal AI", "multimodal OR vision language OR audio language", ["cs.CV", "cs.CL", "cs.AI"]),
    ("computer-vision", "计算机视觉", "Computer Vision", "computer vision OR visual recognition", ["cs.CV"]),
    ("nlp", "自然语言处理", "Natural Language Processing", "natural language processing OR NLP", ["cs.CL"]),
    ("reinforcement-learning", "强化学习", "Reinforcement Learning", "reinforcement learning OR RL", ["cs.LG", "cs.AI"]),
    ("robotics-vla", "机器人与VLA", "Robotics & VLA", "robot OR robotics OR vision language action", ["cs.RO", "cs.AI", "cs.CV"]),
    ("generative-models", "生成模型", "Generative Models", "diffusion OR generative model OR flow matching", ["cs.LG", "cs.CV", "cs.AI"]),
    ("ai-safety", "AI安全与可信", "AI Safety & Trustworthiness", "AI safety OR alignment OR trustworthy OR hallucination", ["cs.AI", "cs.CL", "cs.CY"]),
    ("efficient-ai", "高效训练与推理", "Efficient AI", "efficient training OR inference OR quantization OR pruning", ["cs.LG", "cs.DC", "cs.AR"]),
    ("recommendation-search", "推荐与搜索", "Recommendation & Search", "recommender system OR information retrieval OR search", ["cs.IR", "cs.LG"]),
    ("speech", "语音智能", "Speech AI", "speech recognition OR speech synthesis OR audio", ["cs.SD", "eess.AS"]),
    ("cs-systems", "计算机系统", "Computer Systems", "operating system OR distributed system OR computer architecture", ["cs.OS", "cs.DC", "cs.AR"]),
    ("cs-databases", "数据库", "Databases", "database OR data management OR query processing", ["cs.DB"]),
    ("cs-security", "计算机安全", "Computer Security", "computer security OR privacy OR cryptography", ["cs.CR"]),
    ("cs-software", "软件工程", "Software Engineering", "software engineering OR program analysis OR software testing", ["cs.SE", "cs.PL"]),
    ("cs-networks", "网络与通信", "Networks", "computer network OR networking OR communication system", ["cs.NI"]),
    ("cs-hci", "人机交互", "Human-Computer Interaction", "human computer interaction OR HCI OR user study", ["cs.HC"]),
    ("physics-quantum", "量子物理", "Quantum Physics", "quantum information OR quantum computing OR quantum mechanics", ["quant-ph"]),
    ("physics-condensed", "凝聚态物理", "Condensed Matter", "condensed matter OR many body OR superconductivity", ["cond-mat.mes-hall", "cond-mat.str-el", "cond-mat.supr-con"]),
    ("physics-hep", "高能物理", "High Energy Physics", "high energy physics OR particle physics OR quantum field theory", ["hep-th", "hep-ph", "hep-ex"]),
    ("physics-astro", "天体物理", "Astrophysics", "astrophysics OR cosmology OR galaxy", ["astro-ph.CO", "astro-ph.GA", "astro-ph.HE"]),
    ("physics-stat", "统计物理", "Statistical Physics", "statistical physics OR complex systems OR phase transition", ["cond-mat.stat-mech", "physics.data-an"]),
    ("math-algebra", "代数", "Algebra", "algebra OR representation theory OR number theory", ["math.AG", "math.RA", "math.NT"]),
    ("math-analysis", "分析", "Analysis", "mathematical analysis OR differential equation OR functional analysis", ["math.AP", "math.CA", "math.FA"]),
    ("math-geometry", "几何与拓扑", "Geometry & Topology", "geometry OR topology OR manifold", ["math.DG", "math.GT", "math.AT"]),
    ("math-probability", "概率与统计", "Probability & Statistics", "probability theory OR stochastic process OR mathematical statistics", ["math.PR", "math.ST"]),
    ("math-optimization", "优化与运筹", "Optimization", "optimization OR operations research OR control theory", ["math.OC"]),
]

DOMAIN_LABELS = {"ai": "AI", "computer": "计算机", "physics": "物理", "math": "数学"}
DOMAIN_PREFIXES = {"computer": ("cs-",), "physics": ("physics-",), "math": ("math-",)}


def tag_domain(slug: str) -> str:
    for domain, prefixes in DOMAIN_PREFIXES.items():
        if slug.startswith(prefixes):
            return domain
    return "ai"


def domain_categories(domain: str) -> list[str]:
    if domain == "ai":
        return sorted({category for slug, _, _, _, categories in DEFAULT_TAGS if tag_domain(slug) == "ai" for category in categories})
    return sorted({category for slug, _, _, _, categories in DEFAULT_TAGS if tag_domain(slug) == domain for category in categories})


# Initial, editable catalog. Matches are made only against explicit venue metadata.
TOP_VENUES = {
    "AAAI": ["AAAI"],
    "NeurIPS": ["NEURIPS", "NIPS"],
    "IJCAI": ["IJCAI"],
    "CVPR": ["CVPR"],
    "ICCV": ["ICCV"],
    "ICML": ["ICML"],
    "ICLR": ["ICLR", "INTERNATIONAL CONFERENCE ON LEARNING REPRESENTATIONS"],
    "ECCV": ["ECCV", "EUROPEAN CONFERENCE ON COMPUTER VISION"],
    "EMNLP": ["EMNLP", "EMPIRICAL METHODS IN NATURAL LANGUAGE PROCESSING"],
    "ACL": ["ACL ", "ANNUAL MEETING OF THE ASSOCIATION FOR COMPUTATIONAL LINGUISTICS"],
    "KDD": ["KDD"],
    "SIGIR": ["SIGIR"],
    "ACM MM": ["ACM MULTIMEDIA", "ACM MM"],
    "The Web Conference": ["WWW", "THE WEB CONFERENCE"],
    "TPAMI": ["TPAMI", "TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE"],
    "IJCV": ["INTERNATIONAL JOURNAL OF COMPUTER VISION", "IJCV"],
    "JMLR": ["JOURNAL OF MACHINE LEARNING RESEARCH", "JMLR"],
    "TNNLS": ["TNNLS", "TRANSACTIONS ON NEURAL NETWORKS AND LEARNING SYSTEMS"],
    "JAIR": ["JOURNAL OF ARTIFICIAL INTELLIGENCE RESEARCH", "JAIR"],
    "Artificial Intelligence": ["ARTIFICIAL INTELLIGENCE JOURNAL"],
    "SOSP": ["SOSP"], "OSDI": ["OSDI"], "SIGCOMM": ["SIGCOMM"], "NSDI": ["NSDI"],
    "SIGMOD": ["SIGMOD"], "VLDB": ["VLDB"], "CCS": ["ACM CCS", "COMPUTER AND COMMUNICATIONS SECURITY"],
    "IEEE S&P": ["IEEE SYMPOSIUM ON SECURITY AND PRIVACY"], "USENIX Security": ["USENIX SECURITY"],
    "PLDI": ["PLDI"], "POPL": ["POPL"], "ICSE": ["ICSE"], "CHI": ["ACM CHI", "HUMAN FACTORS IN COMPUTING SYSTEMS"],
}

FIELD_TOP_VENUES = {
    "Nature Physics": ["NATURE PHYSICS"], "Physical Review Letters": ["PHYSICAL REVIEW LETTERS"],
    "Physical Review X": ["PHYSICAL REVIEW X"], "The Astrophysical Journal": ["ASTROPHYSICAL JOURNAL"],
    "Annals of Mathematics": ["ANNALS OF MATHEMATICS"], "Inventiones Mathematicae": ["INVENTIONES MATHEMATICAE"],
    "Journal of the AMS": ["JOURNAL OF THE AMERICAN MATHEMATICAL SOCIETY"],
    "Acta Mathematica": ["ACTA MATHEMATICA"],
}


DEFAULT_SETTINGS = {
    "default_abstract_language": "zh",
    "font_size": 16,
    "daily_enabled": False,
    "daily_time": "09:00",
    "timezone": "Asia/Shanghai",
    "daily_count": 5,
    "daily_tag_ids": [],
    "top_venue_ratio": 0.7,
    "only_verified_top_venues": False,
    "llm_provider": "openai",
    "llm_model": "gpt-4.1-mini",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_rerank_enabled": True,
    "llm_rerank_weight": 0.45,
    "zotero_library_type": "user",
    "zotero_library_id": "",
    "zotero_collection_key": "",
    "zotero_sync_tags": True,
    "library_root": "",
}

TIMEZONE_OPTIONS = [
    {"value": "Asia/Shanghai", "label": "北京时间"},
    {"value": "America/New_York", "label": "美东时间"},
    {"value": "America/Los_Angeles", "label": "美西时间"},
]


def seed_catalog(db: Session) -> None:
    for slug, zh, en, query, categories in DEFAULT_TAGS:
        if db.scalar(select(Tag).where(Tag.slug == slug)) is None:
            db.add(Tag(slug=slug, name_zh=zh, name_en=en, query=query, arxiv_categories_json=json.dumps(categories)))
    for key, value in DEFAULT_SETTINGS.items():
        if db.get(AppSetting, key) is None:
            db.add(AppSetting(key=key, value=json.dumps(value, ensure_ascii=False)))
    db.commit()


def detect_venue(raw: str | None) -> tuple[str | None, str, str]:
    if not raw:
        return None, "preprint", "preprint"
    normalized = " ".join(raw.upper().split())
    if any(marker in normalized for marker in ("SUBMITTED TO", "UNDER REVIEW", "IN SUBMISSION")):
        return None, "preprint", "preprint"
    for venue, aliases in TOP_VENUES.items():
        if any(alias in normalized for alias in aliases):
            return venue, "CCF-A/top", "published"
    for venue, aliases in FIELD_TOP_VENUES.items():
        if any(alias in normalized for alias in aliases):
            return venue, "field-top", "published"
    return raw[:255], "other", "published"
