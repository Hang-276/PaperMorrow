import { createRequire } from "node:module";
import type PptxGenJSClass from "pptxgenjs";
import type { ContentBlock, DeckSpec, EvidenceSource, SlideSpec } from "./schema.js";
import type { Box } from "./layout.js";
import { CONTENT, layoutBlocks } from "./layout.js";
import { createTheme, SLIDE, type AcademicTheme } from "./theme.js";
import { latexToSvgDataUri } from "./formula.js";
import { assertValidDeck } from "./validation.js";

const pt = (points: number) => points;
// PptxGenJS 4's ESM export is not interpreted consistently by Node 18 when
// loaded through a parent application's dynamic import. The maintained CJS
// entry is fully compatible and keeps the studio usable in PaperMorrow's
// current Node 18 desktop runtime.
const require = createRequire(import.meta.url);
const PptxGenJS = require("pptxgenjs") as typeof PptxGenJSClass;
type PptxSlide = ReturnType<PptxGenJSClass["addSlide"]>;

// PptxGenJS writes selected package metadata fields without XML escaping.
// Normalize those fields at the compiler boundary so a harmless lab name such
// as "Vision & Agent Lab" cannot make PowerPoint reject the whole package.
function safePackageMetadata(value: string): string {
  return value.replaceAll("&", " and ").replace(/[<>]/g, "").replace(/\s+/g, " ").trim();
}

function addHeader(slide: PptxSlide, spec: DeckSpec, item: SlideSpec, theme: AcademicTheme, page: number): void {
  slide.addText(item.title, {
    x: CONTENT.x, y: 0.36, w: 11.2, h: 0.74,
    fontFace: theme.font, fontSize: pt(35), bold: true, color: theme.ink,
    margin: 0, breakLine: false, fit: "shrink"
  });
  if (item.keyMessage) slide.addText(item.keyMessage, {
    x: CONTENT.x, y: 1.22, w: CONTENT.w, h: 0.3,
    fontFace: theme.font, fontSize: pt(15), color: theme.secondaryInk, margin: 0, fit: "shrink"
  });
  slide.addShape("line", { x: CONTENT.x, y: 1.58, w: CONTENT.w, h: 0, line: { color: theme.line, width: 1 } });
  slide.addText(`${String(page).padStart(2, "0")}  ·  ${spec.metadata.kind.replaceAll("-", " ")}`, {
    x: 10.55, y: 7.08, w: 1.96, h: 0.18, fontFace: theme.font, fontSize: 8, color: theme.muted, align: "right", margin: 0
  });
}

function addBlockTitle(slide: PptxSlide, title: string | undefined, box: Box, theme: AcademicTheme): number {
  if (!title) return box.y;
  slide.addText(title, { x: box.x, y: box.y, w: box.w, h: 0.4, fontFace: theme.font, fontSize: 24, bold: true, color: theme.ink, margin: 0, fit: "shrink" });
  return box.y + 0.52;
}

function addBullets(slide: PptxSlide, block: Extract<ContentBlock, { type: "bullets" }>, box: Box, theme: AcademicTheme): void {
  const y = addBlockTitle(slide, block.title, box, theme);
  const runs = block.items.map((text) => ({ text, options: { bullet: { indent: 14 }, hanging: 4, breakLine: true } }));
  slide.addText(runs, { x: box.x, y, w: box.w, h: box.h - (y - box.y), fontFace: theme.font, fontSize: 16, color: theme.secondaryInk, breakLine: true, margin: 0.12, paraSpaceAfter: 10, valign: "middle", fit: "shrink", lineSpacingMultiple: 1.08 });
}

function addParagraph(slide: PptxSlide, block: Extract<ContentBlock, { type: "paragraph" }>, box: Box, theme: AcademicTheme): void {
  const y = addBlockTitle(slide, block.title, box, theme);
  slide.addText(block.text, { x: box.x, y, w: box.w, h: box.h - (y - box.y), fontFace: theme.font, fontSize: 16, color: theme.secondaryInk, margin: 0.14, breakLine: false, valign: "middle", fit: "shrink", lineSpacingMultiple: 1.08 });
}

function addMetrics(slide: PptxSlide, block: Extract<ContentBlock, { type: "metrics" }>, box: Box, theme: AcademicTheme): void {
  const y = addBlockTitle(slide, block.title, box, theme);
  const rows = [
    block.items.map((item) => ({ text: item.label, options: { fill: { color: theme.surface }, bold: true, color: theme.secondaryInk } })),
    block.items.map((item) => ({ text: item.value, options: { bold: true, color: theme.ink } })),
    block.items.map((item) => ({
      text: item.delta ?? "—",
      options: { color: item.sentiment === "positive" ? theme.positive : item.sentiment === "negative" ? theme.negative : theme.muted }
    }))
  ];
  slide.addTable(rows, {
    x: box.x, y, w: box.w, h: box.h - (y - box.y),
    border: { type: "solid", color: theme.line, pt: 0.8 },
    color: theme.secondaryInk, fontFace: theme.font, fontSize: 15,
    margin: 0.1, valign: "middle", align: "left",
    rowH: [0.34, 0.47, 0.31]
  });
}

function addChart(slide: PptxSlide, pptx: PptxGenJSClass, block: Extract<ContentBlock, { type: "chart" }>, box: Box, theme: AcademicTheme): void {
  const y = addBlockTitle(slide, block.title, box, theme);
  if (block.chartType !== "line") {
    const rows = [
      [{ text: block.valueLabel ?? (theme.language === "zh-CN" ? "项目" : "Item"), options: { bold: true, fill: { color: theme.surface } } }, ...block.series.map((series) => ({ text: series.name, options: { bold: true, fill: { color: theme.surface } } }))],
      ...block.labels.map((label, index) => [{ text: label }, ...block.series.map((series) => ({ text: String(series.values[index]) }))])
    ];
    slide.addTable(rows, {
      x: box.x, y, w: box.w, h: box.h - (y - box.y),
      border: { type: "solid", color: theme.line, pt: 0.8 },
      color: theme.secondaryInk, fontFace: theme.font, fontSize: 14,
      margin: 0.1, valign: "middle", align: "left"
    });
    return;
  }
  const colors = [theme.accent, "65A7FF", "54B399", "F0A44B", "8957E5", "C85A75"];
  const data = block.series.map((series) => ({ name: series.name, labels: block.labels, values: series.values }));
  const chartType = pptx.ChartType.line;
  slide.addChart(chartType, data, {
    x: box.x, y, w: box.w, h: box.h - (y - box.y),
    catAxisLabelFontFace: theme.font, catAxisLabelFontSize: 11,
    valAxisLabelFontFace: theme.font, valAxisLabelFontSize: 10,
    chartColors: colors, showLegend: block.showLegend, legendFontFace: theme.font, legendFontSize: 9,
    legendPos: "b", showTitle: false, showValue: false,
    valGridLine: { color: theme.line, size: 0.7 },
    catAxisLineShow: true, valAxisLineShow: true,
    showSerName: false, lineSize: 2
  });
}

function addComparison(slide: PptxSlide, block: Extract<ContentBlock, { type: "comparison" }>, box: Box, theme: AcademicTheme): void {
  const y = addBlockTitle(slide, block.title, box, theme);
  const headings = block.columns.map((column) => ({
    text: column.heading,
      options: { bold: true, fill: { color: theme.surface }, color: column.accent ? theme.accent : theme.ink }
  }));
  const body = block.columns.map((column) => ({ text: column.items.map((item) => `• ${item}`).join("\n") }));
  slide.addTable([headings, body], {
    x: box.x, y, w: box.w, h: box.h - (y - box.y),
    border: { type: "solid", color: theme.line, pt: 0.8 },
    color: theme.secondaryInk, fontFace: theme.font, fontSize: 15,
    margin: 0.16, valign: "top", align: "left",
    rowH: [0.58, box.h - (y - box.y) - 0.58]
  });
}

function addTimeline(slide: PptxSlide, block: Extract<ContentBlock, { type: "timeline" }>, box: Box, theme: AcademicTheme): void {
  const y = addBlockTitle(slide, block.title, box, theme);
  const statusLabel = theme.language === "zh-CN"
    ? { completed: "完成", current: "进行中", planned: "计划", failed: "未通过" } as const
    : { completed: "Completed", current: "In progress", planned: "Planned", failed: "Failed" } as const;
  const headings = theme.language === "zh-CN"
    ? ["日期", "实验 / 阶段", "记录", "状态"]
    : ["Date", "Experiment / stage", "Record", "Status"];
  const rows = [
    headings.map((text) => ({ text, options: { bold: true, fill: { color: theme.surface } } })),
    ...block.events.map((event) => [event.date, event.title, event.detail ?? "—", statusLabel[event.status]].map((text) => ({ text })))
  ];
  slide.addTable(rows, {
    x: box.x, y, w: box.w, h: box.h - (y - box.y),
    colW: [1.25, 2.45, 6.65, 1.34],
    border: { type: "solid", color: theme.line, pt: 0.8 },
    color: theme.secondaryInk, fontFace: theme.font, fontSize: 14,
    margin: 0.1, valign: "middle", align: "left"
  });
}

function addFormula(slide: PptxSlide, block: Extract<ContentBlock, { type: "formula" }>, box: Box, theme: AcademicTheme): void {
  const y = addBlockTitle(slide, block.title, box, theme);
  const captionHeight = block.caption ? 0.4 : 0;
  slide.addImage({ data: latexToSvgDataUri(block.latex), x: box.x + 0.2, y: y + 0.1, w: box.w - 0.4, h: box.h - (y - box.y) - captionHeight - 0.2, altText: `LaTeX: ${block.latex}` });
  if (block.caption) slide.addText(block.caption, { x: box.x, y: box.y + box.h - 0.32, w: box.w, h: 0.22, align: "center", fontFace: theme.font, fontSize: 9, color: theme.muted, margin: 0 });
}

function addQuote(slide: PptxSlide, block: Extract<ContentBlock, { type: "quote" }>, box: Box, theme: AcademicTheme): void {
  slide.addShape("line", { x: box.x, y: box.y, w: 0, h: box.h, line: { color: theme.accent, width: 2 } });
  slide.addText(block.text, { x: box.x + 0.34, y: box.y + 0.1, w: box.w - 0.34, h: box.h - 0.62, fontFace: theme.font, fontSize: 20, bold: true, color: theme.ink, margin: 0, valign: "middle", fit: "shrink" });
  if (block.attribution) slide.addText(block.attribution, { x: box.x + 0.34, y: box.y + box.h - 0.35, w: box.w - 0.34, h: 0.2, fontFace: theme.font, fontSize: 9, color: theme.muted, margin: 0, align: "right" });
}

function renderBlock(slide: PptxSlide, pptx: PptxGenJSClass, block: ContentBlock, box: Box, theme: AcademicTheme): void {
  switch (block.type) {
    case "bullets": return addBullets(slide, block, box, theme);
    case "paragraph": return addParagraph(slide, block, box, theme);
    case "metrics": return addMetrics(slide, block, box, theme);
    case "chart": return addChart(slide, pptx, block, box, theme);
    case "comparison": return addComparison(slide, block, box, theme);
    case "timeline": return addTimeline(slide, block, box, theme);
    case "formula": return addFormula(slide, block, box, theme);
    case "quote": return addQuote(slide, block, box, theme);
  }
}

function sourceLabel(source: EvidenceSource): string {
  const authors = source.authors?.length ? `${source.authors.slice(0, 3).join(", ")}${source.authors.length > 3 ? " et al." : ""}. ` : "";
  const year = source.year ? ` (${source.year}).` : "";
  const locator = source.locator ? ` ${source.locator}.` : "";
  return `[${source.id}] ${authors}${source.title}${year}${locator}${source.doi ? ` DOI: ${source.doi}` : ""}`;
}

function addCitations(slide: PptxSlide, slideSpec: SlideSpec, sources: Map<string, EvidenceSource>, theme: AcademicTheme): void {
  if (!slideSpec.citations.length) return;
  const labels = slideSpec.citations.map((id) => {
    const source = sources.get(id)!;
    return `[${id}] ${source.title}${source.locator ? ` · ${source.locator}` : ""}`;
  });
  slide.addText(labels.join("   "), { x: CONTENT.x, y: 6.7, w: 9.5, h: 0.22, fontFace: theme.font, fontSize: 7.5, color: theme.muted, margin: 0, fit: "shrink" });
}

function renderTitle(slide: PptxSlide, spec: DeckSpec, item: SlideSpec, theme: AcademicTheme): void {
  slide.addText(item.title, { x: CONTENT.x, y: 1.55, w: CONTENT.w, h: 1.65, fontFace: theme.font, fontSize: 50, bold: true, color: theme.ink, margin: 0, fit: "shrink", breakLine: false });
  const subtitle = item.subtitle ?? spec.metadata.subtitle;
  if (subtitle) slide.addText(subtitle, { x: CONTENT.x, y: 3.42, w: 10.8, h: 0.6, fontFace: theme.font, fontSize: 18, color: theme.secondaryInk, margin: 0, fit: "shrink" });
  const byline = [spec.metadata.author, spec.metadata.institution].filter(Boolean).join("  ·  ");
  if (byline) slide.addText(byline, { x: CONTENT.x, y: 5.95, w: 10.8, h: 0.25, fontFace: theme.font, fontSize: 11, color: theme.muted, margin: 0 });
  slide.addText(spec.metadata.kind.replaceAll("-", " ").toUpperCase(), { x: CONTENT.x, y: 1.18, w: 5, h: 0.24, fontFace: theme.font, fontSize: 10, bold: true, charSpacing: 1.5, color: theme.accent, margin: 0 });
  slide.addShape("line", { x: CONTENT.x, y: 4.34, w: 1.15, h: 0, line: { color: theme.accent, width: 2 } });
}

function renderSection(slide: PptxSlide, item: SlideSpec, theme: AcademicTheme): void {
  slide.addText(item.title, { x: CONTENT.x, y: 2.25, w: CONTENT.w, h: 1.1, fontFace: theme.font, fontSize: 44, bold: true, color: theme.ink, align: "left", margin: 0, fit: "shrink" });
  if (item.subtitle) slide.addText(item.subtitle, { x: CONTENT.x, y: 3.55, w: 10.5, h: 0.55, fontFace: theme.font, fontSize: 16, color: theme.secondaryInk, align: "left", margin: 0, fit: "shrink" });
  slide.addShape("line", { x: CONTENT.x, y: 4.42, w: CONTENT.w, h: 0, line: { color: theme.line, width: 1 } });
}

function renderBibliography(slide: PptxSlide, spec: DeckSpec, item: SlideSpec, theme: AcademicTheme, page: number): void {
  addHeader(slide, spec, item, theme, page);
  const lines = spec.sources.map(sourceLabel);
  slide.addText(lines.map((text) => ({ text, options: { bullet: { indent: 12 }, hanging: 3, breakLine: true } })), {
    x: 0.78, y: 1.75, w: 11.7, h: 4.95, fontFace: theme.font, fontSize: 11, color: theme.secondaryInk, margin: 0.08, paraSpaceAfter: 8, fit: "shrink"
  });
}

export async function renderDeck(spec: DeckSpec, outputPath: string): Promise<void> {
  assertValidDeck(spec);
  const pptx = new PptxGenJS();
  const theme = createTheme(spec);
  const sourceMap = new Map(spec.sources.map((source) => [source.id, source]));
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = safePackageMetadata(spec.metadata.author ?? "PaperMorrow");
  pptx.company = safePackageMetadata(spec.metadata.institution ?? "PaperMorrow");
  pptx.subject = safePackageMetadata(spec.metadata.kind);
  pptx.title = safePackageMetadata(spec.metadata.title);
  pptx.theme = { headFontFace: theme.font, bodyFontFace: theme.font };
  pptx.defineSlideMaster({ title: "ACADEMIC_WHITE", background: { color: theme.background }, objects: [] });

  spec.slides.forEach((item, index) => {
    const slide = pptx.addSlide("ACADEMIC_WHITE");
    slide.background = { color: theme.background };
    if (item.layout === "title") renderTitle(slide, spec, item, theme);
    else if (item.layout === "section") renderSection(slide, item, theme);
    else if (item.layout === "bibliography") renderBibliography(slide, spec, item, theme, index + 1);
    else {
      addHeader(slide, spec, item, theme, index + 1);
      layoutBlocks(item).forEach(({ block, box }) => renderBlock(slide, pptx, block, box, theme));
      addCitations(slide, item, sourceMap, theme);
    }
    if (item.speakerNotes) slide.addNotes(item.speakerNotes);
  });
  await pptx.writeFile({ fileName: outputPath });
}
