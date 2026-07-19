import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Bold, BookOpen, CheckSquare, Code2, FileCode2, Heading1, Heading2, Heading3,
  ImagePlus, Italic, Link2, List, ListOrdered, Minus, Pilcrow, Quote, Sigma,
  Strikethrough, Table2,
} from 'lucide-react'

type EditorAction =
  | 'paragraph' | 'h1' | 'h2' | 'h3' | 'bold' | 'italic' | 'strike' | 'inline-code'
  | 'code-block' | 'bullet' | 'ordered' | 'task' | 'quote' | 'link' | 'table'
  | 'formula' | 'image' | 'divider'

type ContextMenuState = { x: number; y: number; line: number } | null

const blockPrefix = /^(?:#{1,6}\s+|>\s+|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+\.\s+)/

function lineIsInsideFence(lines: string[], index: number) {
  let inside = false
  for (let cursor = 0; cursor < index; cursor += 1) {
    if (/^\s*```/.test(lines[cursor])) inside = !inside
  }
  return inside
}

function RenderedLine({ line, index, lines }: { line: string; index: number; lines: string[] }) {
  if (!line.trim()) return <div className="notes-live-empty" aria-hidden="true">&nbsp;</div>
  const fence = line.match(/^\s*```\s*([^\s]*)/)
  if (fence) return <div className="notes-live-fence">{fence[1] || '代码'}</div>
  if (lineIsInsideFence(lines, index)) return <pre className="notes-live-code"><code>{line || ' '}</code></pre>
  if (/^\s*\|.+\|\s*$/.test(line)) {
    if (/^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/.test(line)) return <div className="notes-live-table-separator" />
    return <div className="notes-live-table-row">{line.trim().slice(1, -1).split('|').map((cell, cellIndex) => <span key={cellIndex}>{cell.trim()}</span>)}</div>
  }
  return <div className="notes-live-rendered"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ children, href }) => <a href={href} onClick={event => event.preventDefault()}>{children}</a> }}>{line}</ReactMarkdown></div>
}

function ToolButton({ title, action, run, children }: { title: string; action: EditorAction; run: (action: EditorAction) => void; children: React.ReactNode }) {
  return <button type="button" title={title} aria-label={title} onMouseDown={event => event.preventDefault()} onClick={() => run(action)}>{children}</button>
}

export default function MarkdownLiveEditor({
  value,
  mode,
  onChange,
  onInsertPaper,
}: {
  value: string
  mode: 'standard' | 'professional'
  onChange: (value: string) => void
  onInsertPaper: () => void
}) {
  const lines = useMemo(() => value.replace(/\r\n?/g, '\n').split('\n'), [value])
  const [activeLine, setActiveLine] = useState(0)
  const [menu, setMenu] = useState<ContextMenuState>(null)
  const sourceRef = useRef<HTMLTextAreaElement>(null)
  const documentRef = useRef<HTMLDivElement>(null)

  const commit = (nextLines: string[]) => onChange(nextLines.join('\n'))
  const focusLine = (line: number, caret?: number) => {
    const bounded = Math.max(0, Math.min(line, Math.max(lines.length - 1, 0)))
    setActiveLine(bounded)
    window.requestAnimationFrame(() => {
      const source = sourceRef.current
      if (!source) return
      source.focus()
      const point = caret ?? source.value.length
      source.setSelectionRange(point, point)
    })
  }

  useEffect(() => {
    if (activeLine >= lines.length) setActiveLine(Math.max(0, lines.length - 1))
  }, [activeLine, lines.length])

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest('.notes-live-context')) setMenu(null)
    }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenu(null) }
    window.addEventListener('pointerdown', close)
    window.addEventListener('keydown', escape)
    return () => { window.removeEventListener('pointerdown', close); window.removeEventListener('keydown', escape) }
  }, [])

  const replaceLine = (index: number, replacement: string[], nextActive = index, caret?: number) => {
    const next = [...lines]
    next.splice(index, 1, ...replacement)
    commit(next)
    window.requestAnimationFrame(() => focusLine(nextActive, caret))
  }

  const changeActiveLine = (nextValue: string) => {
    const replacement = nextValue.replace(/\r/g, '').split('\n')
    replaceLine(activeLine, replacement, activeLine + replacement.length - 1)
  }

  const wrapSelection = (before: string, after = before, fallback = '文本') => {
    const source = sourceRef.current
    const line = lines[activeLine] || ''
    const start = source?.selectionStart ?? line.length
    const end = source?.selectionEnd ?? start
    const selected = line.slice(start, end) || fallback
    const next = `${line.slice(0, start)}${before}${selected}${after}${line.slice(end)}`
    replaceLine(activeLine, [next], activeLine, start + before.length + selected.length + after.length)
    window.requestAnimationFrame(() => sourceRef.current?.setSelectionRange(start + before.length, start + before.length + selected.length))
  }

  const setPrefix = (prefix: string) => {
    const line = lines[activeLine] || ''
    const clean = line.replace(blockPrefix, '')
    const next = line.startsWith(prefix) ? clean : `${prefix}${clean}`
    replaceLine(activeLine, [next], activeLine, next.length)
  }

  const insertBlock = (block: string[]) => {
    const current = lines[activeLine] || ''
    const replacement = current.trim() ? [current, ...block] : block
    const firstInserted = activeLine + (current.trim() ? 1 : 0)
    replaceLine(activeLine, replacement, firstInserted, block[0]?.length || 0)
  }

  const run = (action: EditorAction) => {
    setMenu(null)
    if (action === 'paragraph') setPrefix('')
    else if (action === 'h1') setPrefix('# ')
    else if (action === 'h2') setPrefix('## ')
    else if (action === 'h3') setPrefix('### ')
    else if (action === 'bold') wrapSelection('**')
    else if (action === 'italic') wrapSelection('*')
    else if (action === 'strike') wrapSelection('~~')
    else if (action === 'inline-code') wrapSelection('`', '`', 'code')
    else if (action === 'bullet') setPrefix('- ')
    else if (action === 'ordered') setPrefix('1. ')
    else if (action === 'task') setPrefix('- [ ] ')
    else if (action === 'quote') setPrefix('> ')
    else if (action === 'link') wrapSelection('[', '](https://)', '链接文字')
    else if (action === 'formula') wrapSelection('$', '$', 'E = mc^2')
    else if (action === 'image') insertBlock(['![图片说明](图片地址)'])
    else if (action === 'divider') insertBlock(['---'])
    else if (action === 'code-block') insertBlock(['```python', '# 在这里输入代码', '```'])
    else if (action === 'table') insertBlock(['| 项目 | 内容 |', '| --- | --- |', '| 示例 | 说明 |'])
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const source = event.currentTarget
    const line = lines[activeLine] || ''
    if (event.key === 'Enter') {
      event.preventDefault()
      const before = line.slice(0, source.selectionStart)
      const after = line.slice(source.selectionEnd)
      const continuation = line.match(/^(\s*(?:[-*+] |\d+\. |> |[-*+] \[[ xX]\] ))/)?.[1] || ''
      replaceLine(activeLine, [before, `${continuation}${after}`], activeLine + 1, continuation.length)
    } else if (event.key === 'Backspace' && source.selectionStart === 0 && source.selectionEnd === 0 && activeLine > 0) {
      event.preventDefault()
      const previous = lines[activeLine - 1]
      const next = [...lines]
      next.splice(activeLine - 1, 2, previous + line)
      commit(next)
      window.requestAnimationFrame(() => focusLine(activeLine - 1, previous.length))
    } else if (event.key === 'ArrowUp' && source.selectionStart === 0 && activeLine > 0) {
      event.preventDefault(); focusLine(activeLine - 1)
    } else if (event.key === 'ArrowDown' && source.selectionEnd === line.length && activeLine < lines.length - 1) {
      event.preventDefault(); focusLine(activeLine + 1, 0)
    } else if (event.key === 'Tab') {
      event.preventDefault()
      const start = source.selectionStart
      const next = `${line.slice(0, start)}  ${line.slice(source.selectionEnd)}`
      replaceLine(activeLine, [next], activeLine, start + 2)
    }
  }

  const toolbar = mode === 'standard' && <div className="notes-live-toolbar" aria-label="Markdown 格式工具">
    <div><ToolButton title="正文" action="paragraph" run={run}><Pilcrow /></ToolButton><ToolButton title="一级标题" action="h1" run={run}><Heading1 /></ToolButton><ToolButton title="二级标题" action="h2" run={run}><Heading2 /></ToolButton><ToolButton title="三级标题" action="h3" run={run}><Heading3 /></ToolButton></div>
    <div><ToolButton title="加粗" action="bold" run={run}><Bold /></ToolButton><ToolButton title="斜体" action="italic" run={run}><Italic /></ToolButton><ToolButton title="删除线" action="strike" run={run}><Strikethrough /></ToolButton><ToolButton title="行内代码" action="inline-code" run={run}><Code2 /></ToolButton><ToolButton title="代码块" action="code-block" run={run}><FileCode2 /></ToolButton></div>
    <div><ToolButton title="项目列表" action="bullet" run={run}><List /></ToolButton><ToolButton title="编号列表" action="ordered" run={run}><ListOrdered /></ToolButton><ToolButton title="任务列表" action="task" run={run}><CheckSquare /></ToolButton><ToolButton title="引用" action="quote" run={run}><Quote /></ToolButton></div>
    <div><ToolButton title="链接" action="link" run={run}><Link2 /></ToolButton><ToolButton title="表格" action="table" run={run}><Table2 /></ToolButton><ToolButton title="公式" action="formula" run={run}><Sigma /></ToolButton><ToolButton title="图片" action="image" run={run}><ImagePlus /></ToolButton><ToolButton title="分隔线" action="divider" run={run}><Minus /></ToolButton><button type="button" title="引用论文" aria-label="引用论文" onMouseDown={event => event.preventDefault()} onClick={onInsertPaper}><BookOpen /></button></div>
  </div>

  return <div className={`notes-markdown-live ${mode}`}>
    {toolbar}
    <div
      ref={documentRef}
      className="notes-live-document"
      onContextMenu={event => {
        if (mode !== 'standard') return
        const target = (event.target as Element).closest<HTMLElement>('[data-note-line]')
        if (!target) return
        event.preventDefault()
        const line = Number(target.dataset.noteLine || 0)
        setActiveLine(line)
        const documentElement = documentRef.current
        const bounds = documentElement?.getBoundingClientRect()
        const rawX = event.clientX - (bounds?.left || 0) + (documentElement?.scrollLeft || 0)
        const rawY = event.clientY - (bounds?.top || 0) + (documentElement?.scrollTop || 0)
        setMenu({
          x: Math.max(8, Math.min(rawX, (documentElement?.scrollWidth || rawX + 246) - 246)),
          y: Math.max(8, Math.min(rawY, (documentElement?.scrollHeight || rawY + 390) - 390)),
          line,
        })
      }}
    >
      {lines.map((line, index) => <div
        className={`notes-live-line ${index === activeLine ? 'editing' : ''}`}
        data-note-line={index}
        key={index}
        onClick={() => { if (index !== activeLine) focusLine(index) }}
      >
        {index === activeLine
          ? <textarea
              ref={sourceRef}
              className="notes-line-source"
              value={line}
              rows={1}
              spellCheck
              aria-label={`第 ${index + 1} 行 Markdown 源码`}
              onFocus={event => { event.currentTarget.style.height = 'auto'; event.currentTarget.style.height = `${Math.max(30, event.currentTarget.scrollHeight)}px` }}
              onInput={event => { event.currentTarget.style.height = 'auto'; event.currentTarget.style.height = `${Math.max(30, event.currentTarget.scrollHeight)}px` }}
              onChange={event => changeActiveLine(event.target.value)}
              onKeyDown={onKeyDown}
            />
          : <RenderedLine line={line} index={index} lines={lines} />}
      </div>)}
      {menu && <div className="notes-live-context" role="menu" style={{ left: menu.x, top: menu.y }} onPointerDown={event => event.stopPropagation()}>
        <span>段落样式</span><div><button onClick={() => run('paragraph')}><Pilcrow />正文</button><button onClick={() => run('h1')}><Heading1 />一级标题</button><button onClick={() => run('h2')}><Heading2 />二级标题</button><button onClick={() => run('h3')}><Heading3 />三级标题</button></div>
        <span>文本格式</span><div><button onClick={() => run('bold')}><Bold />加粗</button><button onClick={() => run('italic')}><Italic />斜体</button><button onClick={() => run('strike')}><Strikethrough />删除线</button><button onClick={() => run('inline-code')}><Code2 />行内代码</button></div>
        <span>插入内容</span><div><button onClick={() => run('bullet')}><List />项目列表</button><button onClick={() => run('ordered')}><ListOrdered />编号列表</button><button onClick={() => run('task')}><CheckSquare />任务列表</button><button onClick={() => run('quote')}><Quote />引用</button><button onClick={() => run('link')}><Link2 />链接</button><button onClick={() => run('table')}><Table2 />表格</button><button onClick={() => run('formula')}><Sigma />公式</button><button onClick={() => run('code-block')}><FileCode2 />代码块</button><button onClick={onInsertPaper}><BookOpen />引用论文</button></div>
      </div>}
    </div>
  </div>
}
