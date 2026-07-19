import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { parseDeckSpec } from "../src/schema.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("paper and progress fixtures conform to strict DeckSpec", async () => {
  for (const file of ["paper-report.json", "research-progress.json"]) {
    const json = JSON.parse(await readFile(resolve(root, "fixtures", file), "utf8"));
    const deck = parseDeckSpec(json);
    assert.ok(deck.slides.length >= 5);
  }
});

test("unknown fields are rejected so agents cannot inject coordinates", () => {
  assert.throws(() => parseDeckSpec({
    schemaVersion: "1.0",
    metadata: { title: "Unsafe", language: "zh-CN", kind: "paper-report" },
    theme: {}, sources: [],
    slides: [{ id: "slide-unsafe", layout: "content", title: "Unsafe", blocks: [], citations: [], x: 1 }]
  }), /unrecognized_keys|Unrecognized key/i);
});

test("chart series must align with category labels", () => {
  assert.throws(() => parseDeckSpec({
    schemaVersion: "1.0",
    metadata: { title: "Chart", language: "zh-CN", kind: "experiment-report" },
    theme: {}, sources: [],
    slides: [{ id: "slide-chart", layout: "data", title: "Chart", citations: [], blocks: [{ type: "chart", chartType: "line", labels: ["A", "B"], series: [{ name: "score", values: [1] }] }] }]
  }), /one value per label/i);
});
