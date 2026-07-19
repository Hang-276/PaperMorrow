import { z } from "zod";

const sourceId = z.string().regex(/^[A-Z]+-[A-Za-z0-9._-]+$/, "Use a stable source id such as PAPER-001 or EXP-024");

export const evidenceSourceSchema = z.object({
  id: sourceId,
  type: z.enum(["paper", "experiment", "note", "wiki", "project", "inference"]),
  title: z.string().min(1),
  authors: z.array(z.string()).optional(),
  year: z.number().int().min(1800).max(2200).optional(),
  locator: z.string().optional(),
  url: z.string().url().optional(),
  doi: z.string().optional(),
  evidence: z.string().optional(),
  confidence: z.number().min(0).max(1).default(1)
}).strict();

const bulletsBlock = z.object({
  type: z.literal("bullets"),
  title: z.string().optional(),
  items: z.array(z.string().min(1)).min(1).max(6)
}).strict();

const paragraphBlock = z.object({
  type: z.literal("paragraph"),
  title: z.string().optional(),
  text: z.string().min(1)
}).strict();

const metricsBlock = z.object({
  type: z.literal("metrics"),
  title: z.string().optional(),
  items: z.array(z.object({
    label: z.string().min(1),
    value: z.string().min(1),
    delta: z.string().optional(),
    sentiment: z.enum(["positive", "negative", "neutral"]).default("neutral")
  }).strict()).min(1).max(4)
}).strict();

const chartBlock = z.object({
  type: z.literal("chart"),
  title: z.string().optional(),
  chartType: z.enum(["line", "bar", "column"]),
  labels: z.array(z.string()).min(1),
  series: z.array(z.object({
    name: z.string().min(1),
    values: z.array(z.number())
  }).strict()).min(1).max(6),
  valueLabel: z.string().optional(),
  showLegend: z.boolean().default(true)
}).strict();

const comparisonBlock = z.object({
  type: z.literal("comparison"),
  title: z.string().optional(),
  columns: z.array(z.object({
    heading: z.string().min(1),
    accent: z.boolean().default(false),
    items: z.array(z.string().min(1)).min(1).max(5)
  }).strict()).min(2).max(3)
}).strict();

const timelineBlock = z.object({
  type: z.literal("timeline"),
  title: z.string().optional(),
  events: z.array(z.object({
    date: z.string().min(1),
    title: z.string().min(1),
    detail: z.string().optional(),
    status: z.enum(["completed", "current", "planned", "failed"]).default("completed")
  }).strict()).min(2).max(6)
}).strict();

const formulaBlock = z.object({
  type: z.literal("formula"),
  title: z.string().optional(),
  latex: z.string().min(1),
  caption: z.string().optional()
}).strict();

const quoteBlock = z.object({
  type: z.literal("quote"),
  text: z.string().min(1),
  attribution: z.string().optional()
}).strict();

export const contentBlockSchema = z.discriminatedUnion("type", [
  bulletsBlock,
  paragraphBlock,
  metricsBlock,
  chartBlock,
  comparisonBlock,
  timelineBlock,
  formulaBlock,
  quoteBlock
]);

export const slideSchema = z.object({
  id: z.string().regex(/^slide-[a-z0-9-]+$/),
  layout: z.enum(["title", "section", "statement", "content", "two-column", "data", "comparison", "timeline", "bibliography"]),
  title: z.string().min(1),
  subtitle: z.string().optional(),
  keyMessage: z.string().optional(),
  blocks: z.array(contentBlockSchema).max(4).default([]),
  citations: z.array(sourceId).default([]),
  speakerNotes: z.string().optional()
}).strict();

export const deckSpecSchema = z.object({
  schemaVersion: z.literal("1.0"),
  metadata: z.object({
    title: z.string().min(1),
    subtitle: z.string().optional(),
    author: z.string().optional(),
    institution: z.string().optional(),
    language: z.enum(["zh-CN", "en-US"]).default("zh-CN"),
    kind: z.enum(["paper-report", "research-progress", "literature-review", "experiment-report"]),
    generatedAt: z.string().datetime().optional()
  }).strict(),
  theme: z.object({
    accentColor: z.string().regex(/^[0-9A-Fa-f]{6}$/).default("1677FF"),
    fontFamily: z.string().default("Arial"),
    monoFontFamily: z.string().default("Menlo")
  }).strict().default({}),
  sources: z.array(evidenceSourceSchema).default([]),
  slides: z.array(slideSchema).min(1).max(60)
}).strict().superRefine((deck, context) => {
  deck.slides.forEach((slide, slideIndex) => slide.blocks.forEach((block, blockIndex) => {
    if (block.type !== "chart") return;
    block.series.forEach((series, seriesIndex) => {
      if (series.values.length !== block.labels.length) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["slides", slideIndex, "blocks", blockIndex, "series", seriesIndex, "values"],
          message: "Every series must have one value per label"
        });
      }
    });
  }));
});

export type DeckSpec = z.infer<typeof deckSpecSchema>;
export type SlideSpec = z.infer<typeof slideSchema>;
export type ContentBlock = z.infer<typeof contentBlockSchema>;
export type EvidenceSource = z.infer<typeof evidenceSourceSchema>;

export function parseDeckSpec(input: unknown): DeckSpec {
  return deckSpecSchema.parse(input);
}
