import type { Summary } from './types'

export type AnalysisLanguage = 'zh'|'en'

export function hasBilingualSummary(summary?: Summary|null): boolean {
  if (!summary) return false
  return Boolean(summary.research_problem_zh && summary.research_problem_en && summary.method_zh && summary.method_en)
}

export function localizedSummary(summary: Summary, language: AnalysisLanguage): Summary {
  const pick = <T,>(field: keyof Summary): T|undefined => {
    const localized = summary[`${String(field)}_${language}` as keyof Summary] as T|undefined
    return localized ?? summary[field] as T|undefined
  }
  return {
    one_sentence:pick<string>('one_sentence'),
    research_problem:pick<string>('research_problem'),
    method:pick<string>('method'),
    innovations:pick<string[]>('innovations'),
    value:pick<string[]>('value'),
    evidence:pick<string>('evidence'),
    limitations:pick<string[]>('limitations'),
    recommended_for:pick<string[]>('recommended_for'),
  }
}

export const analysisLabels = {
  zh:{analysis:'论文摘要与分析',abstract:'摘要',researchProblem:'研究问题',method:'核心方法',innovations:'主要创新',value:'研究价值',limitations:'局限与风险',audience:'适合谁阅读',abstractOnly:'仅摘要分析',fullText:'全文证据分析',abstractScope:'不显示或推测页码；需要全文后才能提升证据范围',fullScope:'结论可绑定 PDF 页码和章节',upgrade:'补全双语分析'},
  en:{analysis:'Abstract & analysis',abstract:'Abstract',researchProblem:'Research question',method:'Core method',innovations:'Key contributions',value:'Research value',limitations:'Limitations & risks',audience:'Recommended for',abstractOnly:'Abstract-only analysis',fullText:'Full-text evidence analysis',abstractScope:'No page numbers are inferred; full text is required for stronger evidence.',fullScope:'Claims can be linked to PDF pages and sections.',upgrade:'Complete bilingual analysis'},
} as const
