from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain_sources import SOURCE_ADAPTERS, validate_source_configs
from .models import DomainMetric, DomainPack, ResearchProfile


COMMON_WEIGHTS = {"relevance": .30, "venue": .20, "evidence": .20, "recency": .15, "citation_percentile": .10, "openness": .05}
BUILTIN_PACKS = [
    {"slug":"ai","name_zh":"人工智能","name_en":"Artificial Intelligence","description":"保持 PaperMorrow 最高完成度的核心专业，优先 CCF-A 与同级顶会顶刊，同时保留前沿预印本。","sources":["arxiv","semantic_scholar","openalex","crossref"],"categories":["cs.AI","cs.CL","cs.CV","cs.LG","cs.RO"],"keywords":["artificial intelligence","machine learning","agent","multimodal"],"venues":[{"name":"NeurIPS","aliases":["NIPS"],"paper_types":["conference"],"level":"CCF-A/top"},{"name":"ICML","aliases":[],"paper_types":["conference"],"level":"CCF-A/top"},{"name":"ICLR","aliases":[],"paper_types":["conference"],"level":"CCF-A/top"}]},
    {"slug":"computer","name_zh":"计算机科学","name_en":"Computer Science","description":"系统、数据库、安全、软件工程、网络与人机交互。","sources":["arxiv","semantic_scholar","openalex","crossref"],"categories":["cs.DC","cs.DB","cs.CR","cs.SE","cs.NI","cs.HC"],"keywords":["computer systems","software engineering","database"],"venues":[]},
    {"slug":"physics","name_zh":"物理学","name_en":"Physics","description":"量子、凝聚态、高能、天体与统计物理。","sources":["arxiv","openalex","crossref"],"categories":["quant-ph","cond-mat","hep-th","astro-ph"],"keywords":["physics","quantum","condensed matter"],"venues":[]},
    {"slug":"math","name_zh":"数学","name_en":"Mathematics","description":"代数、分析、几何拓扑、概率统计与优化。","sources":["arxiv","openalex","crossref"],"categories":["math.AG","math.AP","math.DG","math.PR","math.OC"],"keywords":["mathematics","theorem","proof"],"venues":[]},
    {"slug":"life-sciences","name_zh":"生命科学","name_en":"Life Sciences","description":"分子、细胞、遗传、神经、生态与生物信息学。","sources":["pubmed","europe_pmc","openalex","crossref","rss_atom"],"categories":["q-bio.BM","q-bio.GN","q-bio.NC"],"keywords":["molecular biology","genomics","cell biology","neuroscience"],"venues":[]},
    {"slug":"clinical-medicine","name_zh":"临床医学","name_en":"Clinical Medicine","description":"按证据等级评价临床研究，突出系统综述、随机对照试验、预注册、样本规模与预印本风险。","sources":["pubmed","europe_pmc","crossref","openalex"],"categories":[],"keywords":["clinical trial","randomized controlled trial","systematic review","meta-analysis"],"venues":[],"evidence":{"hierarchy":["systematic_review","meta_analysis","randomized_controlled_trial","prospective_cohort","retrospective_study","case_series","expert_opinion","preprint"],"require_preregistration_signal":True,"sample_size_weight":.15,"preprint_risk":True,"impact_factor_is_not_sufficient":True}},
    {"slug":"chemistry-materials","name_zh":"化学与材料","name_en":"Chemistry & Materials","description":"化学、能源材料、催化、聚合物、纳米与计算材料。","sources":["crossref","openalex","arxiv","rss_atom"],"categories":["cond-mat.mtrl-sci","physics.chem-ph"],"keywords":["chemistry","materials science","catalysis","battery"],"venues":[]},
    {"slug":"economics-finance","name_zh":"经济学与金融","name_en":"Economics & Finance","description":"微观、宏观、计量、金融市场、公司金融与政策评估。","sources":["openalex","crossref","arxiv","rss_atom"],"categories":["econ.EM","econ.GN","q-fin.EC","q-fin.ST"],"keywords":["economics","econometrics","finance","causal inference"],"venues":[]},
]


JSON_FIELDS = {
    "source_adapters":"source_adapters_json","search_templates":"search_templates_json","keywords":"keywords_json","exclusions":"exclusions_json",
    "category_codes":"category_codes_json","venue_rules":"venue_rules_json","paper_types":"paper_types_json","scoring_weights":"scoring_weights_json",
    "evidence_rules":"evidence_rules_json","citation_config":"citation_config_json","impact_config":"impact_config_json",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def seed_domain_packs(db: Session) -> None:
    now = datetime.now(timezone.utc)
    for definition in BUILTIN_PACKS:
        pack = db.scalar(select(DomainPack).where(DomainPack.slug == definition["slug"]))
        if pack is None:
            source_configs = [{"adapter": source, "enabled": source != "rss_atom"} for source in definition["sources"]]
            pack = DomainPack(
                slug=definition["slug"], name_zh=definition["name_zh"], name_en=definition["name_en"], description=definition["description"],
                is_builtin=True, version=1, enabled=True, source_adapters_json=_json(source_configs),
                search_templates_json=_json(["{keywords}", "{keywords} {category_codes}"]), keywords_json=_json(definition["keywords"]), exclusions_json="[]",
                category_codes_json=_json(definition["categories"]), venue_rules_json=_json(definition["venues"]),
                paper_types_json=_json(["journal_article","conference_paper","preprint","review"]), scoring_weights_json=_json(COMMON_WEIGHTS),
                evidence_rules_json=_json(definition.get("evidence", {"require_verifiable_source":True,"preprint_risk":True})),
                analysis_prompt="区分论文事实、作者主张与 AI 判断，并给出可核验证据。", review_prompt="生成可追溯到论文的结构化综述，不把推断伪装成事实。",
                citation_config_json=_json({"use_field_normalized_percentile":True,"minimum_year":2018}), impact_config_json=_json({"allow_custom_metrics":True,"require_source_url":True,"do_not_invent_jif":True}),
                created_at=now, updated_at=now,
            )
            db.add(pack)
            db.flush()
    packs = {item.slug:item.id for item in db.scalars(select(DomainPack)).all()}
    for profile in db.scalars(select(ResearchProfile).where(ResearchProfile.domain_pack_id.is_(None))).all():
        profile.domain_pack_id = packs.get(profile.domain)
    db.commit()


def domain_pack_dict(pack: DomainPack) -> dict[str, Any]:
    result = {"id":pack.id,"slug":pack.slug,"name_zh":pack.name_zh,"name_en":pack.name_en,"description":pack.description,"is_builtin":pack.is_builtin,"version":pack.version,"enabled":pack.enabled}
    for public, column in JSON_FIELDS.items():
        result[public] = json.loads(getattr(pack, column) or ("{}" if public.endswith(("weights","rules","config")) else "[]"))
    result.update({"analysis_prompt":pack.analysis_prompt,"review_prompt":pack.review_prompt,"metrics":[{"id":m.id,"name":m.name,"value":m.value,"year":m.year,"source_url":m.source_url} for m in pack.metrics],"created_at":pack.created_at.isoformat(),"updated_at":pack.updated_at.isoformat()})
    return result


def apply_domain_pack(pack: DomainPack, payload: dict[str, Any]) -> DomainPack:
    configs = payload.get("source_adapters")
    if configs is not None:
        validate_source_configs(configs)
    for field in ("slug","name_zh","name_en","description","enabled","analysis_prompt","review_prompt"):
        if field in payload and payload[field] is not None:
            setattr(pack, field, payload[field])
    for public, column in JSON_FIELDS.items():
        if public in payload and payload[public] is not None:
            setattr(pack, column, _json(payload[public]))
    if "metrics" in payload and payload["metrics"] is not None:
        pack.metrics = [DomainMetric(name=item["name"],value=item["value"],year=item["year"],source_url=str(item["source_url"])) for item in payload["metrics"]]
    pack.updated_at = datetime.now(timezone.utc)
    pack.version = max(1, pack.version + 1)
    return pack


def create_domain_pack(db: Session, payload: dict[str, Any]) -> DomainPack:
    slug = re.sub(r"[^a-z0-9-]+","-",payload["slug"].lower()).strip("-")
    if not slug or db.scalar(select(DomainPack).where(DomainPack.slug == slug)):
        raise ValueError("专业 slug 无效或已存在")
    pack = DomainPack(slug=slug,name_zh=payload["name_zh"],name_en=payload["name_en"],description=payload.get("description","") or "",is_builtin=False,version=0,enabled=payload.get("enabled",True))
    apply_domain_pack(pack,{**payload,"slug":slug})
    db.add(pack); db.commit(); db.refresh(pack)
    return pack


def search_preview(pack: DomainPack, query: str) -> dict[str, Any]:
    data = domain_pack_dict(pack)
    keywords = [query.strip(), *data["keywords"]]
    keywords = list(dict.fromkeys(item for item in keywords if item))[:12]
    return {"query":" OR ".join(keywords),"categories":data["category_codes"],"exclusions":data["exclusions"],"enabled_sources":[item["adapter"] for item in data["source_adapters"] if item.get("enabled",True)],"automatic_websites":"仅支持已注册 API 或 RSS/Atom；普通网页 URL 不会自动抓取。"}


def adapter_catalog() -> list[dict[str, str]]:
    return [{"slug":slug,"label":adapter.label} for slug,adapter in SOURCE_ADAPTERS.items()]
