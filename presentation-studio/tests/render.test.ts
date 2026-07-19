import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import JSZip from "jszip";
import { parseDeckSpec } from "../src/schema.js";
import { renderDeck } from "../src/renderer.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

test("paper fixture compiles to a non-empty editable PPTX package", async () => {
  const raw = JSON.parse(await readFile(resolve(root, "fixtures/paper-report.json"), "utf8"));
  const output = resolve(tmpdir(), `papermorrow-presentation-${process.pid}.pptx`);
  await renderDeck(parseDeckSpec(raw), output);
  const info = await stat(output);
  const header = await readFile(output).then((data) => data.subarray(0, 2).toString());
  assert.equal(header, "PK");
  assert.ok(info.size > 20_000);
});

test("XML-sensitive metadata is normalized before package generation", async () => {
  const raw = JSON.parse(await readFile(resolve(root, "fixtures/paper-report.json"), "utf8"));
  raw.metadata.institution = "Vision & Agent <Lab>";
  const output = resolve(tmpdir(), `papermorrow-presentation-metadata-${process.pid}.pptx`);
  await renderDeck(parseDeckSpec(raw), output);
  const data = await readFile(output);
  const archive = await JSZip.loadAsync(data);
  const xmlFiles = Object.values(archive.files).filter((entry) => entry.name.endsWith(".xml"));
  assert.ok(xmlFiles.length > 10);
  for (const entry of xmlFiles) {
    const xml = await entry.async("text");
    assert.doesNotMatch(xml, /&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-f]+;)/i, `bare XML entity in ${entry.name}`);
  }
});

test("research progress uses editable tables for metrics, timeline and comparisons", async () => {
  const raw = JSON.parse(await readFile(resolve(root, "fixtures/research-progress.json"), "utf8"));
  const output = resolve(tmpdir(), `papermorrow-presentation-tables-${process.pid}.pptx`);
  await renderDeck(parseDeckSpec(raw), output);
  const archive = await JSZip.loadAsync(await readFile(output));
  const slides = Object.values(archive.files).filter((entry) => /^ppt\/slides\/slide\d+\.xml$/.test(entry.name));
  const xml = (await Promise.all(slides.map((entry) => entry.async("text")))).join("\n");
  assert.ok((xml.match(/<a:tbl>/g) ?? []).length >= 3);
  assert.doesNotMatch(xml, /prst="roundRect"/);
});
