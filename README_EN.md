# PaperMorrow

<p align="center">
  <img src="frontend/public/papermorrow-logo.png" width="112" alt="PaperMorrow logo" />
</p>

<p align="center"><strong>Turn papers, evidence, experiments, and writing into a research workflow you can keep moving forward.</strong></p>

<p align="center">
  <a href="README.md">简体中文</a> ·
  <a href="../../releases/tag/v0.5.4">v0.5.4 Beta</a> ·
  <a href="docs/DESKTOP_BUILD.md">Build guide</a>
</p>

> [!IMPORTANT]
> PaperMorrow is a personal vibe-coding project and is still in **Beta**. It can already handle useful research workflows, but there will be rough edges. Back up important material and always verify AI output against the original paper and experiment record.

I wanted a research workspace that felt more connected than a PDF collection and more useful than another chat box—something that could carry an idea through discovery, close reading, notes, projects, experiments, deadlines, presentations, and AI-assisted work. I could not find exactly the tool I wanted, so I started learning and building PaperMorrow one piece at a time. I am sharing it in case it also helps with a thesis, course project, graduate research, or an independent idea.

This is an independent hobby project, not an official product from a university, lab, or company. If it solves a problem for you, you are welcome to use it, share feedback, or help shape what it becomes.

## Download the desktop app

Installers are hosted directly on GitHub Releases—no external file hosting is used.

| Platform | Download | Notes |
|---|---|---|
| macOS 12+ | [DMG](../../releases/download/v0.5.4/PaperMorrow-macOS.dmg) | Apple silicon; Apple notarization is not complete |
| Windows 10/11 x64 | [Installer](../../releases/download/v0.5.4/PaperMorrow-Windows-Setup.exe) | Standard installer |
| Windows 10/11 x64 | [Portable ZIP](../../releases/download/v0.5.4/PaperMorrow-Windows-Portable.zip) | Extract and run |

Unsigned Beta builds may trigger macOS Gatekeeper or Windows SmartScreen. Download only from this repository's Releases page.

## Who it is for

PaperMorrow is designed for graduate students, undergraduate researchers, postdocs, and anyone who needs a durable research evidence trail. It is not just another chat screen. It is a local-first desktop research workspace that helps you:

- Keep a broad view of new work while following a precise research question.
- Separate paper facts, author claims, personal records, and AI inference.
- Connect reading queues, notes, literature studies, experiments, and code wikis inside projects.
- Ask an agent to propose an editable plan, then execute steps under explicit permissions and approvals.
- Continue from evidence to Markdown reports, data tables, and editable presentations.

## Core experiences

### Research Cowork Agent

Select papers, files, or a folder and describe an outcome. PaperMorrow creates an editable plan and shows progress, sources, tool calls, approvals, and artifacts. A supervisor can delegate bounded tasks to literature-evidence, synthesis, and project-planning specialists; each specialist receives only the minimum context and tools it needs.

- Pause, resume, cancel, retry a step, or recover from a checkpoint.
- File access is denied by default and confined to roots selected by the user.
- Path traversal, symlink escapes, hidden secrets, and `.env` access are blocked.
- Writes, overwrites, bulk imports, and external actions require preview and approval.
- Built-in research Skills are intentionally small in number and high in value. Imported Skills show source, license, version, and tool permissions before installation.
- Page-level Ask AI uses the same interaction model but can only read the visible page.

### Discovery and evidence-grounded reading

- Broad, focused, and focus-plus-exploration recommendation modes.
- Academic sources including arXiv, Semantic Scholar, OpenAlex, Crossref, PubMed, and Europe PMC.
- Permanent deduplication using DOI, arXiv ID, Semantic Scholar ID, and title fingerprints.
- On-demand bilingual summaries and analysis. Abstract-only evidence is labeled and never receives fabricated page numbers.
- A PDF reader with lazy rendering, selection-based translation/questions/citations, and figure capture into notes.

### Projects, experiments, and knowledge relations

- Each project has its own paper queue, notes, literature studies, experiments, and retrieval boundary.
- Each project gets an isolated evidence graph; content from other projects is not mixed in.
- Relations retain provenance, evidence, and confidence. The app does not invent generic “semantic similarity” edges.
- Experiment analysis cites experiment IDs and compares configurations, metrics, observations, and artifacts.
- DeepWiki turns repository structure and source evidence into a local wiki without executing third-party repository code.

### Notes, presentations, and artifacts

- Unified paper and standalone notes with Markdown, LaTeX, visual editing, and source editing.
- Presentation generation starts from an editable outline and produces `.pptx` files with paper, note, and experiment sources.
- Cowork artifacts collect reports, tables, presentations, notes, and imported papers in one place.
- The LLM call log stores purpose, model, and token counts only—never prompt text, response text, or API keys.

## Local-first by design

Your database, API keys, papers, PDFs, notes, wikis, projects, and experiments stay on your computer by default:

- macOS: `~/Library/Application Support/PaperMorrow`
- Windows: `%APPDATA%\PaperMorrow`

PaperMorrow uses SQLite, FTS5, and BM25 for local retrieval. It does not require a separate vector database, cloud account, or background microservice. A model API is contacted only when you explicitly use an AI feature, and the UI describes the data scope. Updating or uninstalling the app does not intentionally delete user research data.

## Useful without an API key

Without a model profile, you can still use the library, projects, notes, experiment records, deadlines, basic paper search, and local organization. AI analysis and Cowork specialists pause or degrade explicitly instead of fabricating results.

Multiple model profiles can be stored and switched under Settings. OpenAI, Anthropic Claude, GLM, DeepSeek, and custom OpenAI-compatible endpoints are supported at the protocol level; actual models and capabilities depend on the provider.

## Run from source

Python 3.10+ and Node.js 20+ are required.

```bash
cp .env.example .env
./scripts/start.sh
```

On Windows, run `scripts/start.bat`. See the [desktop build guide](docs/DESKTOP_BUILD.md) for development, testing, and packaging details.

## Technology

- FastAPI, SQLAlchemy, and SQLite/FTS5
- React, TypeScript, and Vite
- pywebview and PyInstaller
- Local Tool Registry, permission/approval boundaries, and audit logs
- Incremental SQLite migrations with pre-migration backups

If you try PaperMorrow, I would love to hear what feels awkward, what breaks, and what you genuinely want a research tool to do. Please never attach API keys, unpublished papers, real patient data, or other sensitive information to an issue.
