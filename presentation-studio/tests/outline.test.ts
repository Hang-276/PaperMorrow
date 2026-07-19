import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { compileOutline, parseOutlineSpec } from "../src/outline.js";
import { parseDeckSpec } from "../src/schema.js";
import { validateDeck } from "../src/validation.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("approved outline compiles deterministically into a valid cited DeckSpec", async () => {
  const raw = JSON.parse(await readFile(resolve(root, "fixtures/paper-report-outline.json"), "utf8"));
  const outline = parseOutlineSpec(raw);
  const first = compileOutline(outline);
  const second = compileOutline(outline);
  assert.deepEqual(first, second);
  assert.equal(validateDeck(parseDeckSpec(first)).some((issue) => issue.severity === "error"), false);
  assert.deepEqual(first.slides.find((slide) => slide.id === "slide-method")?.citations, ["PAPER-001", "NOTE-001"]);
});

test("outline page cannot cite a paper or note outside its source catalog", () => {
  assert.throws(() => parseOutlineSpec({
    schemaVersion: "1.0",
    metadata: { title: "Manual outline", language: "zh-CN", kind: "paper-report", origin: "manual" },
    theme: {}, sources: [], sections: [{ id: "section-main", title: "Main", slides: [{ id: "outline-slide-one", title: "Claim", purpose: "Explain claim", content: [], visualIntent: "content", sourceRefs: ["PAPER-404"] }] }]
  }), /has no evidence source/i);
});

test("blank manual outline is editable but cannot be compiled prematurely", () => {
  const outline = parseOutlineSpec({
    schemaVersion: "1.0",
    metadata: { title: "Blank outline", language: "zh-CN", kind: "research-progress", origin: "manual" },
    theme: {}, sources: [], sections: []
  });
  assert.throws(() => compileOutline(outline), /has no slides/i);
});
