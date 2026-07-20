# PaperMorrow

<p align="center">
  <img src="frontend/public/papermorrow-logo.png" width="112" alt="PaperMorrow logo" />
</p>

<p align="center"><strong>Turn papers, evidence, experiments, and writing into a research workflow that keeps moving forward.</strong></p>

<p align="center"><a href="README.md">简体中文</a></p>

> [!IMPORTANT]
> PaperMorrow is a personal vibe-coding project and is still in **Beta**. Back up important material and always verify AI output against the original paper and experiment record.

I wanted a more connected research workspace—something beyond a PDF collection or another chat box, where paper discovery, close reading, evidence, notes, projects, experiments, deadlines, presentations, and AI collaboration could work together. I could not find exactly the tool I wanted, so I started learning and building PaperMorrow one piece at a time.

## What PaperMorrow is

PaperMorrow is a local-first desktop research workspace. It organizes papers, notes, experiments, and research artifacts around projects, helping material move from collection to understanding, verification, connection, and communication.

The app is designed to distinguish paper facts, author claims, personal records, and AI inference. Paper-based answers retain evidence sources, while abstract-only evidence is labeled explicitly instead of being presented as a verified conclusion.

## Core experiences

### AI collaboration

Select papers, files, or a folder and describe an outcome. PaperMorrow creates an editable plan and shows its steps, sources, tool calls, approval requests, and artifacts. The main Agent can delegate bounded work to specialists for literature evidence, research synthesis, and project planning, while each specialist receives only the minimum context and permissions required for its task.

- Pause, resume, cancel, retry a step, or recover from a checkpoint.
- File access is denied by default and limited to user-approved scopes.
- Writes, overwrites, bulk imports, and external actions require preview and confirmation.
- Research Skills expose their source, license, version, and required permissions before import.
- Page-level Ask AI can read only the visible page and does not scan the full library by default.

### Discovery and evidence-grounded reading

- Broad, focused, and focus-plus-exploration recommendation modes.
- Academic sources including arXiv, Semantic Scholar, OpenAlex, Crossref, PubMed, and Europe PMC.
- Persistent deduplication using DOI, arXiv ID, Semantic Scholar ID, and title fingerprints.
- On-demand bilingual summaries and analysis with explicit abstract-only labels.
- A PDF reader with lazy rendering, selection-based translation, questions, citations, and figure capture into notes.

### Projects, experiments, and knowledge relations

- Each project has its own paper queue, notes, literature studies, experiment timeline, and AI retrieval scope.
- Evidence-based knowledge relations are isolated by project and retain provenance, evidence, and confidence.
- Experiment analysis connects configurations, metrics, observations, and artifacts through experiment IDs.
- DeepWiki turns repository structure, key modules, and source evidence into a local wiki without executing third-party repository code.

### Notes, presentations, and research artifacts

- Unified paper and standalone notes with Markdown, LaTeX, visual editing, and source editing.
- Editable outlines can be turned into `.pptx` files while retaining paper, note, and experiment sources.
- The Cowork artifact area brings reports, tables, presentations, notes, and imported papers together.
- The LLM call log stores purpose, model, and token counts only—never prompt text, response text, or API keys.

## Local-first by design

Your database, API keys, papers, PDFs, notes, wikis, projects, and experiments stay on your computer by default. PaperMorrow uses SQLite, FTS5, and BM25 for local retrieval and does not require a separate vector database, cloud account, or always-on remote service.

A model API is contacted only when you actively use an AI feature, and the interface describes the data scope. Without an API key, the library, projects, notes, experiment records, deadlines, basic search, and local organization remain available. Model-dependent features pause or degrade explicitly instead of fabricating results.
