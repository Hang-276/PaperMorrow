#!/usr/bin/env node
import { readFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { parseDeckSpec } from "./schema.js";
import { compileOutline, parseOutlineSpec } from "./outline.js";
import { renderDeck } from "./renderer.js";
import { validateDeck } from "./validation.js";

async function main(): Promise<void> {
  const [inputArg, outputArg] = process.argv.slice(2);
  if (!inputArg || !outputArg) {
    console.error("Usage: papermorrow-ppt <deck-spec.json> <output.pptx>");
    process.exitCode = 2;
    return;
  }
  const inputPath = resolve(inputArg);
  const outputPath = resolve(outputArg);
  const raw = JSON.parse(await readFile(inputPath, "utf8")) as unknown;
  const spec = typeof raw === "object" && raw !== null && "sections" in raw
    ? compileOutline(parseOutlineSpec(raw))
    : parseDeckSpec(raw);
  const warnings = validateDeck(spec).filter((issue) => issue.severity === "warning");
  warnings.forEach((warning) => console.warn(`warning [${warning.code}] ${warning.slideId ?? "deck"}: ${warning.message}`));
  await mkdir(dirname(outputPath), { recursive: true });
  await renderDeck(spec, outputPath);
  console.log(`Generated ${outputPath} (${spec.slides.length} slides, ${spec.sources.length} evidence sources)`);
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
