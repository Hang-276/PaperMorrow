export { deckSpecSchema, parseDeckSpec } from "./schema.js";
export type { DeckSpec, SlideSpec, ContentBlock, EvidenceSource } from "./schema.js";
export { validateDeck, assertValidDeck } from "./validation.js";
export type { ValidationIssue } from "./validation.js";
export { renderDeck } from "./renderer.js";
export { outlineSpecSchema, outlineSectionSchema, outlineSlideSchema, parseOutlineSpec, compileOutline } from "./outline.js";
export type { OutlineSpec, OutlineSlide } from "./outline.js";
