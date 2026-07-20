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
- Audit details redact secret-looking keys and values and omit full file bodies.

## Known implementation limits

- The initial runtime is one Agent with a deterministic 5-step plan. Specialist delegation is represented in Skill boundaries but is not a free-running multi-agent swarm.
- The built-in registry currently exposes the safest local paper/note/project reads and recoverable draft/task writes. Existing PaperMorrow presentation generation remains available, but DOCX/PDF/XLSX generation is not claimed as fully integrated until dedicated renderers and visual verification are added.
- External literature search continues to use the existing PaperMorrow search endpoint and always presents candidates before import. Network tests remain mocked/offline.
- macOS and Windows packaging configurations include Cowork resources, but release installers were not built or signed in this development environment.
