import assert from "node:assert/strict";
import test from "node:test";
import { parseDeckSpec } from "../src/schema.js";
import { validateDeck } from "../src/validation.js";

test("missing citations are hard errors", () => {
  const deck = parseDeckSpec({
    schemaVersion: "1.0",
    metadata: { title: "Evidence", language: "zh-CN", kind: "paper-report" },
    theme: {}, sources: [],
    slides: [{ id: "slide-evidence", layout: "content", title: "Evidence", blocks: [], citations: ["PAPER-404"] }]
  });
  assert.equal(validateDeck(deck).some((issue) => issue.code === "MISSING_SOURCE" && issue.severity === "error"), true);
});

test("overfull academic slides fail before PPTX generation", () => {
  const deck = parseDeckSpec({
    schemaVersion: "1.0",
    metadata: { title: "Dense", language: "zh-CN", kind: "research-progress" },
    theme: {}, sources: [],
    slides: [{ id: "slide-dense", layout: "content", title: "Dense", blocks: [{ type: "paragraph", text: "内容".repeat(270) }], citations: [] }]
  });
  assert.equal(validateDeck(deck).some((issue) => issue.code === "CONTENT_OVERFLOW"), true);
});
