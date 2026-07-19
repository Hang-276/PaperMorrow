# PaperMorrow Presentation Studio

Presentation Studio is an independent, replaceable research presentation compiler. It turns a strict, evidence-aware `DeckSpec` JSON document into an editable `.pptx`. Language models may plan the research narrative and populate semantic blocks, but they cannot emit coordinates or PowerPoint XML.

Every generated presentation begins as an editable `OutlineSpec`. Users can review an AI draft or start with a blank manual outline. Each outline page owns its purpose, takeaway, content hints, visual intent, and explicit paper/note/experiment source references. Only an approved outline is deterministically compiled into a `DeckSpec`.

## Design contract

- **Editable output:** text, native charts, tables, and basic shapes remain editable in PowerPoint.
- **Evidence first:** factual slides cite stable PaperMorrow source ids; missing sources stop export.
- **Deterministic layout:** a small academic layout system owns every coordinate, font size, and safe area.
- **Local first:** fixture generation and all core tests use no API key and no network.
- **Replaceable boundary:** PaperMorrow integrates through `DeckSpec` and the CLI/library API, so this implementation can evolve or be replaced without migrating project data.
- **No silent compression:** unsafe content density is rejected and should be split by the planning agent.

## Quick start

```bash
npm install
npm test
npm run generate:paper
npm run generate:progress
```

Or compile any validated deck:

```bash
npm run build
node dist/src/cli.js ./deck.json ./output/deck.pptx
```

The same CLI accepts an approved `OutlineSpec` and compiles it through the deterministic outline-to-deck step automatically:

```bash
node dist/src/cli.js ./approved-outline.json ./output/deck.pptx
```

## Multi-agent integration boundary

The planned application workflow has four independently testable roles:

1. **Evidence Agent** builds a cited evidence pack from selected notes, papers, project records, and experiments.
2. **Narrative Agent** selects the group-meeting story: paper report, research progress, literature review, or experiment report.
3. **Outline Agent** emits editable `OutlineSpec`; the same schema supports a blank user-written outline. References are validated before approval.
4. **Deck Planner** compiles the approved outline and may enrich only semantic blocks. It cannot control coordinates.
5. **Presentation Critic** inspects validation results and rendered slide images, then requests a bounded revision such as splitting a dense slide or changing a semantic layout.

Only the last deterministic compiler writes the `.pptx`. The agent boundary intentionally remains outside this package; it allows PaperMorrow to use any configured LLM or a fixture planner without coupling the presentation engine to an API provider.

## Supported semantic blocks

- paragraphs and bullets
- evidence-aware metric cards
- editable line, bar, and column charts
- two/three-way comparisons
- experiment and method timelines
- LaTeX formulas rendered as print-safe SVG
- quotations and speaker notes
- bibliography generated from evidence sources

The first theme is deliberately restrained: 16:9 white academic slides, dark text, one accent color, stable typography, and a persistent evidence footer.
