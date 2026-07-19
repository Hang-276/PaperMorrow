import assert from "node:assert/strict";
import test from "node:test";
import { parseDeckSpec } from "../src/schema.js";
import { resolveFontFamily } from "../src/theme.js";

const chineseDeck = parseDeckSpec({
  schemaVersion: "1.0",
  metadata: { title: "字体回退", language: "zh-CN", kind: "research-progress" },
  theme: { fontFamily: "Arial" },
  sources: [],
  slides: [{ id: "slide-title", layout: "title", title: "字体回退", blocks: [], citations: [] }]
});

test("Chinese decks use deterministic offline platform font fallbacks", () => {
  assert.equal(resolveFontFamily(chineseDeck, "darwin"), "Hiragino Sans GB");
  assert.equal(resolveFontFamily(chineseDeck, "win32"), "Microsoft YaHei");
  assert.equal(resolveFontFamily(chineseDeck, "linux"), "Noto Sans CJK SC");
});

test("explicit user fonts are preserved", () => {
  const custom = { ...chineseDeck, theme: { ...chineseDeck.theme, fontFamily: "Source Han Sans SC" } };
  assert.equal(resolveFontFamily(custom, "darwin"), "Source Han Sans SC");
});
