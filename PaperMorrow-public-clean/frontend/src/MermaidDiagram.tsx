import { useEffect, useId, useRef, useState } from 'react'
import mermaid from 'mermaid'

function numericSvgLength(value: string | null) {
  if (!value || value.trim().endsWith('%')) return null
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

export default function MermaidDiagram({ source }: { source: string }) {
  const reactId = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const [svg, setSvg] = useState('')
  const [error, setError] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let active = true
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'default',
      themeVariables: {
        fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif',
        fontSize: '16px',
      },
      flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        wrappingWidth: 260,
        diagramPadding: 24,
        nodeSpacing: 54,
        rankSpacing: 64,
      },
    })
    mermaid.render(`wiki-mermaid-${reactId}`, source).then(result => {
      if (active) { setSvg(result.svg); setError('') }
    }).catch(reason => {
      if (active) { setSvg(''); setError(reason instanceof Error ? reason.message : 'Mermaid 图表无法渲染') }
    })
    return () => { active = false }
  }, [reactId, source])

  useEffect(() => {
    const host = containerRef.current
    const svgElement = host?.querySelector('svg')
    if (!host || !svgElement || svgElement.hasAttribute('viewBox')) return

    // Mermaid normally emits a complete native viewBox. This fallback only
    // considers the root SVG itself; never infer bounds from an internal group.
    const frame = window.requestAnimationFrame(() => {
      try {
        const width = numericSvgLength(svgElement.getAttribute('width'))
        const height = numericSvgLength(svgElement.getAttribute('height'))
        if (width && height) {
          svgElement.setAttribute('viewBox', `0 0 ${width} ${height}`)
          return
        }
        const bounds = svgElement.getBBox()
        if (bounds.width > 0 && bounds.height > 0) {
          svgElement.setAttribute('viewBox', `${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`)
        }
      } catch {
        // The unmodified Mermaid SVG remains usable if root measurement is unavailable.
      }
    })
    return () => window.cancelAnimationFrame(frame)
  }, [svg])

  if (error) return <div className="mermaid-error"><span>图表源码</span><pre><code>{source}</code></pre><small>{error}</small></div>
  if (!svg) return <div className="mermaid-loading">正在绘制架构图…</div>
  return <div ref={containerRef} className="mermaid-diagram" data-mermaid-diagram dangerouslySetInnerHTML={{ __html: svg }}/>
}
