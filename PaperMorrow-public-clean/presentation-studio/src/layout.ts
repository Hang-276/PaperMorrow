import type { ContentBlock, SlideSpec } from "./schema.js";
import { SLIDE } from "./theme.js";

export interface Box { x: number; y: number; w: number; h: number }
export interface PositionedBlock { block: ContentBlock; box: Box }

/** Fixed 12-column academic grid with equal outer margins. */
export const CONTENT: Box = { x: 0.82, y: 1.72, w: 11.69, h: 4.76 };

export function layoutBlocks(slide: SlideSpec): PositionedBlock[] {
  const blocks = slide.blocks;
  if (!blocks.length) return [];
  if (slide.layout === "data" && blocks.length > 1) {
    const firstHeight = blocks[0].type === "metrics" ? 1.48 : 2.28;
    const remainingHeight = CONTENT.h - firstHeight - 0.28;
    const remaining = blocks.length - 1;
    const gap = remaining > 1 ? 0.22 : 0;
    const rowHeight = (remainingHeight - gap * (remaining - 1)) / remaining;
    return [
      { block: blocks[0], box: { ...CONTENT, h: firstHeight } },
      ...blocks.slice(1).map((block, index) => ({
        block,
        box: { x: CONTENT.x, y: CONTENT.y + firstHeight + 0.28 + index * (rowHeight + gap), w: CONTENT.w, h: rowHeight }
      }))
    ];
  }
  if (slide.layout === "two-column" || blocks.length === 2) {
    const gap = 0.36;
    const w = (CONTENT.w - gap) / 2;
    return blocks.map((block, index) => ({ block, box: { x: CONTENT.x + index * (w + gap), y: CONTENT.y, w, h: CONTENT.h } }));
  }
  if (["comparison", "timeline"].includes(slide.layout)) {
    return [{ block: blocks[0], box: CONTENT }];
  }
  const gap = 0.22;
  const h = Math.min(2.35, (CONTENT.h - gap * (blocks.length - 1)) / blocks.length);
  return blocks.map((block, index) => ({ block, box: { x: CONTENT.x, y: CONTENT.y + index * (h + gap), w: CONTENT.w, h } }));
}

export function isInsideSlide(box: Box): boolean {
  return box.x >= 0 && box.y >= 0 && box.w > 0 && box.h > 0 && box.x + box.w <= SLIDE.width + 0.001 && box.y + box.h <= SLIDE.height + 0.001;
}

export function boxesOverlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}
