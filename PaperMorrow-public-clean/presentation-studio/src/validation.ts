import type { ContentBlock, DeckSpec, SlideSpec } from "./schema.js";
import { isInsideSlide, layoutBlocks } from "./layout.js";

export interface ValidationIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  slideId?: string;
}

function approximateCharacters(block: ContentBlock): number {
  switch (block.type) {
    case "bullets": return block.items.join("").length + (block.title?.length ?? 0);
    case "paragraph": return block.text.length + (block.title?.length ?? 0);
    case "metrics": return block.items.reduce((sum, item) => sum + item.label.length + item.value.length + (item.delta?.length ?? 0), 0);
    case "chart": return block.labels.join("").length + block.series.reduce((sum, series) => sum + series.name.length, 0);
    case "comparison": return block.columns.reduce((sum, column) => sum + column.heading.length + column.items.join("").length, 0);
    case "timeline": return block.events.reduce((sum, event) => sum + event.date.length + event.title.length + (event.detail?.length ?? 0), 0);
    case "formula": return block.latex.length + (block.caption?.length ?? 0);
    case "quote": return block.text.length + (block.attribution?.length ?? 0);
  }
}

function validateSlideDensity(slide: SlideSpec): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (slide.title.length > 58) issues.push({ severity: "warning", code: "LONG_TITLE", message: "Slide title may wrap to more than two lines", slideId: slide.id });
  if ((slide.keyMessage?.length ?? 0) > 110) issues.push({ severity: "warning", code: "LONG_KEY_MESSAGE", message: "Key message is too long for fast reading", slideId: slide.id });
  const total = slide.blocks.reduce((sum, block) => sum + approximateCharacters(block), 0);
  if (total > 520) issues.push({ severity: "error", code: "CONTENT_OVERFLOW", message: "Content exceeds the safe academic slide density; split this slide", slideId: slide.id });
  if (total > 360) issues.push({ severity: "warning", code: "CONTENT_DENSE", message: "Content is dense and may be difficult to read", slideId: slide.id });
  return issues;
}

export function validateDeck(spec: DeckSpec): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const sourceIds = new Set(spec.sources.map((source) => source.id));
  const slideIds = new Set<string>();
  const usedSources = new Set<string>();
  for (const slide of spec.slides) {
    if (slideIds.has(slide.id)) issues.push({ severity: "error", code: "DUPLICATE_SLIDE_ID", message: `Duplicate slide id: ${slide.id}`, slideId: slide.id });
    slideIds.add(slide.id);
    for (const citation of slide.citations) {
      usedSources.add(citation);
      if (!sourceIds.has(citation)) issues.push({ severity: "error", code: "MISSING_SOURCE", message: `Citation ${citation} has no evidence source`, slideId: slide.id });
    }
    for (const placement of layoutBlocks(slide)) {
      if (!isInsideSlide(placement.box)) issues.push({ severity: "error", code: "OUT_OF_BOUNDS", message: "A generated content region is outside the slide", slideId: slide.id });
    }
    issues.push(...validateSlideDensity(slide));
  }
  for (const source of spec.sources) {
    if (!usedSources.has(source.id)) issues.push({ severity: "warning", code: "UNUSED_SOURCE", message: `Evidence source ${source.id} is not cited by any slide` });
  }
  if (!spec.slides.some((slide) => slide.layout === "bibliography") && usedSources.size) {
    issues.push({ severity: "warning", code: "NO_BIBLIOGRAPHY", message: "The deck contains citations but no bibliography slide" });
  }
  return issues;
}

export function assertValidDeck(spec: DeckSpec): ValidationIssue[] {
  const issues = validateDeck(spec);
  const errors = issues.filter((issue) => issue.severity === "error");
  if (errors.length) throw new Error(errors.map((issue) => `[${issue.code}] ${issue.slideId ?? "deck"}: ${issue.message}`).join("\n"));
  return issues;
}
