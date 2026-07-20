# PaperMorrow Research Cowork

## Boundary

Cowork is an incremental module inside the existing FastAPI + SQLite desktop application. It does not introduce another service, vector database, container platform, or background daemon. Existing papers, notes, projects, experiments, presentations and DeepWiki records remain owned by their original services; Cowork stores references and audit events in separate tables.

Context sent to a model is bounded to recent messages, plan state, user-selected material and retrieved excerpts. External text is always untrusted data. API keys, hidden credential files and unauthorized paths are excluded before model assembly.

## Persistence and rollback

Migration `010_cowork_foundation` creates only new `cowork_*` tables. The existing migration runner copies a non-empty SQLite database to `data/backups/` before applying pending migrations. To roll back application code, return to checkpoint commit `ebf2858`; to restore pre-migration data, stop PaperMorrow and restore the matching `paper_radar-pre-010_cowork_foundation-*.db` backup. Do not drop tables in a live user database.

Phase commits:

- `0410889` — persistence, permission grants and redacted audit log
- `46abbd7` — strict internal tool registry
- `1ddec6e` — recoverable runtime and file sandbox
- `b6f6859` — reviewed lazy research skills
- `b4c045f` — complete Cowork workspace and desktop picker
- `85ec487` — editable plan and note-saving workflow

## Controlled multi-agent group

Migration `011_cowork_multi_agent` adds a supervisor, bounded expert instances and auditable delegations. The supervisor can assemble up to three experts at once from five research roles: literature/evidence, experiment analysis, research synthesis, documents/presentations and project planning. Each delegation freezes one objective, a server-validated context-reference list, a read-only tool subset, an output schema, iteration limits and an independent Token budget.

Experts do not share scratchpads or hidden reasoning. They receive only their work packet and return an `AgentResult` whose findings distinguish paper facts, author claims, user records and AI inference. Non-inference findings must cite a source assigned to that expert. The UI exposes the queue, minimum context, budgets, status, result summary and per-agent or group stop controls.

Expert execution is server-owned. Clients may assemble and run a team, but cannot post an arbitrary completed result. Model responses arriving after pause or cancellation are discarded. Expert tools are read-only; writes remain proposals for the supervisor and are not executable through the former boolean approval shortcut.

## Reference review and licensing

The implementation was written for PaperMorrow and does not copy third-party code.

- The official Model Context Protocol specification informed the separation between model-neutral tool descriptions, strict input schemas and tool execution boundaries: https://github.com/modelcontextprotocol/modelcontextprotocol
- Accomplish informed the product pattern of a local desktop task workspace, explicit file scope and visible long-running progress. Its repository is MIT licensed: https://github.com/accomplish-ai/accomplish
- Anthropic's public Skills repository informed the folder-based, lazy instruction structure. Its repository mixes Apache-2.0 examples with source-available document skills, so PaperMorrow did not copy those document skills or their scripts: https://github.com/anthropics/skills

All bundled PaperMorrow Skill instructions in `backend/cowork_skills/` are original, small, MIT-labelled manifests. They declare only PaperMorrow internal tools and cannot request shell, implicit network access or arbitrary folders.

## Security decisions

- Default deny for notes, projects, reading history and files.
- Canonical real paths are checked against selected roots; traversal, symlink escape, hidden paths and credential file names/suffixes are rejected.
- Schema validation occurs before a `ToolCall` can execute.
- Writes produce approval records; deletion, overwrite, shell, dependency installation, Git writes and uploads are intentionally absent from the default registry.
- Cancel marks every pending/running/paused step cancelled. Interrupted `running` sessions recover as `paused` on restart.
- SQLite connections enable foreign keys, WAL and a bounded busy timeout. Expert database commits are deliberately serialized in this version.
- Audit details redact secret-looking keys and values and omit full file bodies.

## Known implementation limits

- The multi-agent runtime is a supervised expert group, not an unbounded recursive swarm. Expert model calls in one batch are currently serialized to keep SQLite writes deterministic; `max_parallel_agents` is a hard admission limit, not a claim of simultaneous provider requests.
- The approval boundary now rejects `approved=True`, but a complete hash-bound approval execution API has not yet been exposed. Consequently expert agents are read-only and write tools remain proposal-only rather than silently bypassing approval.
- The built-in registry currently exposes the safest local paper/note/project reads and recoverable draft/task writes. Existing PaperMorrow presentation generation remains available, but DOCX/PDF/XLSX generation is not claimed as fully integrated until dedicated renderers and visual verification are added.
- External literature search continues to use the existing PaperMorrow search endpoint and always presents candidates before import. Network tests remain mocked/offline.
- macOS and Windows packaging configurations include Cowork resources, but release installers were not built or signed in this development environment.
