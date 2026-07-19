import { z } from "zod";
import { evidenceSourceSchema, type DeckSpec } from "./schema.js";

const sourceRef = z.string().regex(/^[A-Z]+-[A-Za-z0-9._-]+$/);

export const outlineSlideSchema = z.object({
  id: z.string().regex(/^outline-slide-[a-z0-9-]+$/),
  title: z.string().min(1),
  purpose: z.string().min(1).max(240),
  takeaway: z.string().max(180).optional(),
  content: z.array(z.string().min(1).max(240)).max(6).default([]),
  visualIntent: z.enum(["statement", "content", "two-column", "data", "comparison", "timeline"]).default("content"),
  sourceRefs: z.array(sourceRef).default([]),
  speakerNotes: z.string().optional()
}).strict();

export const outlineSectionSchema = z.object({
  id: z.string().regex(/^section-[a-z0-9-]+$/),
  title: z.string().min(1),
  objective: z.string().max(240).optional(),
  includeDivider: z.boolean().default(false),
  slides: z.array(outlineSlideSchema).default([])
}).strict();

export const outlineSpecSchema = z.object({
  schemaVersion: z.literal("1.0"),
  metadata: z.object({
    title: z.string().min(1),
    subtitle: z.string().optional(),
    author: z.string().optional(),
    institution: z.string().optional(),
    language: z.enum(["zh-CN", "en-US"]).default("zh-CN"),
    kind: z.enum(["paper-report", "research-progress", "literature-review", "experiment-report"]),
    origin: z.enum(["ai", "manual"]).default("manual")
  }).strict(),
  theme: z.object({
    accentColor: z.string().regex(/^[0-9A-Fa-f]{6}$/).default("1677FF"),
    fontFamily: z.string().default("Arial"),
    monoFontFamily: z.string().default("Menlo")
  }).strict().default({}),
  sources: z.array(evidenceSourceSchema).default([]),
  sections: z.array(outlineSectionSchema).default([])
}).strict().superRefine((outline, context) => {
  const ids = new Set(outline.sources.map((source) => source.id));
  outline.sections.forEach((section, sectionIndex) => section.slides.forEach((slide, slideIndex) => {
    slide.sourceRefs.forEach((ref, refIndex) => {
      if (!ids.has(ref)) context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["sections", sectionIndex, "slides", slideIndex, "sourceRefs", refIndex],
        message: `Outline source reference ${ref} has no evidence source`
      });
    });
  }));
});

export type OutlineSpec = z.infer<typeof outlineSpecSchema>;
export type OutlineSlide = z.infer<typeof outlineSlideSchema>;

export function parseOutlineSpec(input: unknown): OutlineSpec {
  return outlineSpecSchema.parse(input);
}

function slideBlocks(slide: OutlineSlide): DeckSpec["slides"][number]["blocks"] {
  const content = slide.content.length ? slide.content : [slide.purpose];
  if (slide.visualIntent === "statement") {
    return [{ type: "quote", text: slide.takeaway ?? content[0], attribution: "本页核心结论" }];
  }
  if (slide.visualIntent === "two-column" && content.length >= 2) {
    const split = Math.ceil(content.length / 2);
    return [
      { type: "bullets", items: content.slice(0, split) },
      { type: "bullets", items: content.slice(split) }
    ];
  }
  return [{ type: "bullets", items: content }];
}

/**
 * Compiles an approved outline into a safe first DeckSpec draft.
 * It never invents evidence, metrics, formulas, or chart values. A later Deck
 * Planner may replace semantic blocks while preserving slide ids and citations.
 */
export function compileOutline(outline: OutlineSpec): DeckSpec {
  const outlinedSlides = outline.sections.flatMap((section) => section.slides);
  if (!outlinedSlides.length) throw new Error("The outline has no slides. Add or generate at least one outline slide before compiling.");
  const slides: DeckSpec["slides"] = [{
    id: "slide-title",
    layout: "title",
    title: outline.metadata.title,
    subtitle: outline.metadata.subtitle,
    blocks: [],
    citations: []
  }];
  for (const section of outline.sections) {
    if (section.includeDivider && section.slides.length) slides.push({
      id: `slide-${section.id}`,
      layout: "section",
      title: section.title,
      subtitle: section.objective,
      blocks: [],
      citations: []
    });
    for (const outlineSlide of section.slides) {
      slides.push({
        id: outlineSlide.id.replace("outline-", ""),
        layout: outlineSlide.visualIntent === "two-column" ? "two-column" : outlineSlide.visualIntent === "data" ? "data" : outlineSlide.visualIntent === "comparison" ? "comparison" : outlineSlide.visualIntent === "timeline" ? "timeline" : outlineSlide.visualIntent === "statement" ? "statement" : "content",
        title: outlineSlide.title,
        keyMessage: outlineSlide.takeaway,
        blocks: slideBlocks(outlineSlide),
        citations: outlineSlide.sourceRefs,
        speakerNotes: outlineSlide.speakerNotes
      });
    }
  }
  const cited = new Set(outlinedSlides.flatMap((slide) => slide.sourceRefs));
  if (cited.size) slides.push({
    id: "slide-bibliography",
    layout: "bibliography",
    title: outline.metadata.language === "zh-CN" ? "证据与引用" : "Evidence and references",
    blocks: [],
    citations: [...cited]
  });
  return {
    schemaVersion: "1.0",
    metadata: {
      title: outline.metadata.title,
      subtitle: outline.metadata.subtitle,
      author: outline.metadata.author,
      institution: outline.metadata.institution,
      language: outline.metadata.language,
      kind: outline.metadata.kind
    },
    theme: outline.theme,
    sources: outline.sources,
    slides
  };
}
