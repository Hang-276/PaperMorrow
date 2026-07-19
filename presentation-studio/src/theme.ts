import type { DeckSpec } from "./schema.js";

export const SLIDE = { width: 13.333, height: 7.5 } as const;

export interface AcademicTheme {
  background: string;
  surface: string;
  ink: string;
  secondaryInk: string;
  muted: string;
  line: string;
  accent: string;
  accentSoft: string;
  positive: string;
  negative: string;
  font: string;
  mono: string;
  language: DeckSpec["metadata"]["language"];
}

/**
 * PowerPoint has no portable CSS-style font stack.  Select a conservative
 * installed CJK family for the platform that creates the deck; Office and
 * LibreOffice can then apply their normal substitution when it is opened on a
 * different platform.  Custom user fonts are always respected.
 */
export function resolveFontFamily(spec: DeckSpec, platform: NodeJS.Platform = process.platform): string {
  const requested = spec.theme.fontFamily.trim();
  if (spec.metadata.language !== "zh-CN" || requested.toLowerCase() !== "arial") return requested;
  if (platform === "darwin") return "Hiragino Sans GB";
  if (platform === "win32") return "Microsoft YaHei";
  return "Noto Sans CJK SC";
}

export function createTheme(spec: DeckSpec): AcademicTheme {
  const font = resolveFontFamily(spec);
  return {
    background: "FFFFFF",
    surface: "F5F6F7",
    ink: "111827",
    secondaryInk: "374151",
    muted: "6B7280",
    line: "D1D5DB",
    accent: spec.theme.accentColor.toUpperCase(),
    accentSoft: "EFF4FA",
    positive: "16845B",
    negative: "C33C54",
    font,
    mono: spec.theme.monoFontFamily,
    language: spec.metadata.language
  };
}
