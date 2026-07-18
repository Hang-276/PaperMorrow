import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft, ArrowRight, BookOpen, ChevronRight, CircleDashed, ExternalLink,
  FileCode2, Home, ListTree, RefreshCw, X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import { api } from './api'
import type { DeepWikiJob } from './types'
import './wiki.css'

const MermaidDiagram = lazy(() => import('./MermaidDiagram'))

type WikiPage = {
  id: string
  title: string
  description: string
  importance: 'high' | 'medium' | 'low'
  relevant_files: string[]
  related_pages: string[]
  parent_section?: string | null
}

type WikiSection = { id: string; title: string; pages: string[]; subsections?: string[] }
type WikiStructure = {
  title: string
  description: string
  sections: WikiSection[]
  pages: WikiPage[]
  generator?: string
  schema_version?: number
}

const wikiSanitizeSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames || []), 'details', 'summary'],
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code || []), ['className']],
  },
}

const importanceLabel = { high: '高', medium: '中', low: '低' }

export default function WikiWorkspace({
  job,
  fontSize,
  onFontSizePreview,
  onFontSizeSave,
  onClose,
  onRetry,
}: {
  job: DeepWikiJob
  fontSize: number
  onFontSizePreview: (value: number) => void
  onFontSizeSave: (value: number) => Promise<void>
  onClose: () => void
  onRetry: () => Promise<void>
}) {
  const [structure, setStructure] = useState<WikiStructure | null>(null)
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [pageLoading, setPageLoading] = useState(false)
  const [error, setError] = useState('')
  const mainRef = useRef<HTMLElement>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    api<WikiStructure>(`/api/deepwiki/jobs/${job.id}/wiki`)
      .then(value => { if (active) { setStructure(value); setError('') } })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Wiki 加载失败') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [job.id])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const pagesById = useMemo(
    () => new Map((structure?.pages || []).map(page => [page.id, page])),
    [structure],
  )
  const currentPage = currentId ? pagesById.get(currentId) || null : null
  const currentIndex = currentId ? (structure?.pages || []).findIndex(page => page.id === currentId) : -1

  const openPage = async (pageId: string) => {
    setCurrentId(pageId)
    setContent('')
    setError('')
    setPageLoading(true)
    mainRef.current?.scrollTo({ top: 0 })
    try {
      const value = await api<{ id: string; content: string }>(`/api/deepwiki/jobs/${job.id}/wiki/pages/${pageId}`)
      if (!value.content.trim()) throw new Error('Wiki 页面正文为空')
      setContent(value.content)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '页面加载失败')
    } finally {
      setPageLoading(false)
    }
  }

  const openIndex = () => {
    setCurrentId(null)
    setContent('')
    setError('')
    mainRef.current?.scrollTo({ top: 0 })
  }

  const changeFontSize = (value: number) => {
    const next = Math.max(13, Math.min(20, value))
    onFontSizePreview(next)
    void onFontSizeSave(next)
  }

  if (loading) return <div className="wiki-workspace wiki-centered"><CircleDashed className="spin"/><span>正在打开完整代码知识库…</span></div>

  if (!structure) return <div className="wiki-workspace wiki-centered"><FileCode2/><h2>Wiki 暂时不可用</h2><p>{error}</p><div><button className="secondary" onClick={onClose}>返回</button><button className="primary" onClick={onRetry}><RefreshCw size={16}/>重新生成</button></div></div>

  return <div className="wiki-workspace">
    <header className="wiki-topbar">
      <button className="wiki-icon-button" onClick={onClose} title="返回 PaperMorrow"><ArrowLeft/></button>
      <div className="wiki-brand"><img src="/papermorrow-logo.png" alt=""/><div><span>PaperMorrow DeepWiki</span><strong>{structure.title}</strong></div></div>
      <nav className="wiki-breadcrumbs">
        <button onClick={openIndex}><Home size={14}/>知识库</button>
        {currentPage && <><ChevronRight size={14}/><span>{currentPage.title}</span></>}
      </nav>
      <div className="wiki-top-actions">
        <div className="wiki-font-control" title="调整主页面与 DeepWiki 的全局字号">
          <span>字号</span>
          <button aria-label="减小字号" disabled={fontSize <= 13} onClick={() => changeFontSize(fontSize - 1)}>A−</button>
          <input
            aria-label="DeepWiki 字号"
            type="range"
            min="13"
            max="20"
            step="1"
            value={fontSize}
            onInput={event => onFontSizePreview(Number((event.target as HTMLInputElement).value))}
            onPointerUp={event => void onFontSizeSave(Number((event.target as HTMLInputElement).value))}
            onKeyUp={event => void onFontSizeSave(Number((event.target as HTMLInputElement).value))}
          />
          <button aria-label="增大字号" disabled={fontSize >= 20} onClick={() => changeFontSize(fontSize + 1)}>A+</button>
          <output>{fontSize}px</output>
        </div>
        <a href={job.repository_url} target="_blank" rel="noreferrer"><ExternalLink size={15}/>GitHub</a>
        <button className="wiki-icon-button" onClick={onClose} title="关闭 Wiki"><X/></button>
      </div>
    </header>

    {currentPage ? <div className="wiki-reader-layout">
      <aside className="wiki-nav">
        <button className="wiki-index-button" onClick={openIndex}><ListTree size={16}/>目录总览</button>
        <div className="wiki-nav-scroll">{structure.sections.map(section => <section key={section.id}>
          <h3>{section.title}</h3>
          {(section.pages || []).map(pageId => pagesById.get(pageId)).filter(Boolean).map(page => <button key={page!.id} className={page!.id === currentId ? 'active' : ''} onClick={() => openPage(page!.id)}>{page!.title}</button>)}
        </section>)}</div>
      </aside>
      <main className="wiki-page-scroll" ref={mainRef}>
        <div className="wiki-page-heading">
          <span>{structure.title}</span>
          <h1>{currentPage.title}</h1>
          <p>{currentPage.description}</p>
        </div>
        <article className="wiki-markdown-card">
          {pageLoading ? <div className="wiki-page-loading"><CircleDashed className="spin"/><span>正在读取完整页面…</span></div> : error ? <div className="wiki-page-error"><FileCode2/><h2>页面读取失败</h2><p>{error}</p><button className="primary" onClick={() => openPage(currentPage.id)}><RefreshCw size={16}/>重试</button></div> : <WikiMarkdown content={content} repositoryUrl={job.repository_url}/>} 
        </article>
        {!pageLoading && !error && <footer className="wiki-page-footer">
          <button disabled={currentIndex <= 0} onClick={() => openPage(structure.pages[currentIndex - 1].id)}><ArrowLeft size={15}/>{currentIndex > 0 ? structure.pages[currentIndex - 1].title : '已经是第一页'}</button>
          <button disabled={currentIndex < 0 || currentIndex >= structure.pages.length - 1} onClick={() => openPage(structure.pages[currentIndex + 1].id)}>{currentIndex < structure.pages.length - 1 ? structure.pages[currentIndex + 1].title : '已经是最后一页'}<ArrowRight size={15}/></button>
        </footer>}
      </main>
    </div> : <main className="wiki-index-scroll" ref={mainRef}>
      <div className="wiki-index-hero">
        <span>CODEBASE LEARNING WIKI</span>
        <h1>{structure.title}</h1>
        <p>{structure.description}</p>
        <div><span><BookOpen size={15}/>{structure.pages.length} 个深入主题</span><span><ListTree size={15}/>{structure.sections.length} 个知识分区</span></div>
      </div>
      {job.needs_regeneration && <div className="wiki-legacy-warning"><div><strong>当前是旧版三页静态结果</strong><p>它没有运行完整的原版 DeepWiki 研究图，不能作为最终代码学习资料。</p></div><button className="primary" onClick={onRetry}><RefreshCw size={16}/>生成完整 Wiki</button></div>}
      <div className="wiki-index-sections">{structure.sections.map(section => <section key={section.id}>
        <header><span>{section.title}</span><small>{(section.pages || []).length} 页</small></header>
        <div>{(section.pages || []).map(pageId => pagesById.get(pageId)).filter(Boolean).map(page => <button key={page!.id} onClick={() => openPage(page!.id)}>
          <span>{page!.title}<i className={`importance-${page!.importance}`}>{importanceLabel[page!.importance]}</i></span>
          <p>{page!.description}</p>
          <small>{page!.relevant_files?.length || 0} 个相关源文件</small>
          <ChevronRight size={18}/>
        </button>)}</div>
      </section>)}</div>
    </main>}
  </div>
}

function WikiMarkdown({ content, repositoryUrl }: { content: string; repositoryUrl: string }) {
  const sourceHref = (href: string | undefined, label: string) => {
    if (href && /^(https?:|#)/.test(href)) return href
    const raw = (href || label).replace(/^\.\//, '')
    const match = raw.match(/^([^:]+)(?::(\d+)(?:-(\d+))?)?$/)
    if (!match) return href || undefined
    const [, path, start, end] = match
    const anchor = start ? `#L${start}${end ? `-L${end}` : ''}` : ''
    return `${repositoryUrl}/blob/HEAD/${path}${anchor}`
  }

  return <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    rehypePlugins={[rehypeRaw, [rehypeSanitize, wikiSanitizeSchema]]}
    components={{
      code({ className, children, ...props }: any) {
        const language = /language-([\w-]+)/.exec(className || '')?.[1]
        const source = String(children).replace(/\n$/, '')
        if (language === 'mermaid') return <Suspense fallback={<div className="mermaid-loading">正在绘制架构图…</div>}><MermaidDiagram source={source}/></Suspense>
        return <code className={className} {...props}>{children}</code>
      },
      a({ href, children, ...props }: any) {
        const label = String(children)
        const resolved = sourceHref(href, label)
        return <a {...props} href={resolved} target={resolved?.startsWith('http') ? '_blank' : undefined} rel={resolved?.startsWith('http') ? 'noreferrer' : undefined}>{children}</a>
      },
      img({ src, alt, ...props }: any) {
        const resolved = src && !/^(https?:|data:)/.test(src) ? `${repositoryUrl}/raw/HEAD/${String(src).replace(/^\.\//, '')}` : src
        return <img {...props} src={resolved} alt={alt || ''}/>
      },
    }}
  >{content}</ReactMarkdown>
}
