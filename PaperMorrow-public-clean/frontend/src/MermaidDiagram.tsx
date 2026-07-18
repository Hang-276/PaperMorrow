import { useEffect, useId, useRef, useState } from 'react'
import mermaid from 'mermaid'

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
    const graph = svgElement?.querySelector<SVGGElement>('g')
    if (!host || !svgElement || !graph) return
    let observer: ResizeObserver | null = null
    let fittedWidth = 0
    let fittedHeight = 0
    const fitDiagram = () => {
      if (!fittedWidth || !fittedHeight) return
      const style = window.getComputedStyle(host)
      const horizontalPadding = Number.parseFloat(style.paddingLeft) + Number.parseFloat(style.paddingRight)
      const availableWidth = Math.max(220, host.clientWidth - horizontalPadding)
      const availableHeight = Math.max(320, window.innerHeight * .76)
      const scale = Math.min(1, availableWidth / fittedWidth, availableHeight / fittedHeight)
      svgElement.style.width = `${Math.floor(fittedWidth * scale)}px`
      svgElement.style.height = `${Math.floor(fittedHeight * scale)}px`
      svgElement.style.maxWidth = '100%'
      svgElement.style.maxHeight = '76vh'
    }
    const frame = window.requestAnimationFrame(() => {
      try {
        svgElement.querySelectorAll<SVGForeignObjectElement>('foreignObject').forEach(node => {
          node.style.overflow = 'visible'
          const label = node.firstElementChild as HTMLElement | null
          if (label) {
            label.style.overflow = 'visible'
          }
        })
        const bounds = graph.getBBox()
        const padding = 28
        const width = Math.ceil(bounds.width + padding * 2)
        const height = Math.ceil(bounds.height + padding * 2)
        fittedWidth = width
        fittedHeight = height
        svgElement.setAttribute('viewBox', `${Math.floor(bounds.x - padding)} ${Math.floor(bounds.y - padding)} ${width} ${height}`)
        svgElement.setAttribute('preserveAspectRatio', 'xMidYMid meet')
        svgElement.removeAttribute('height')
        svgElement.removeAttribute('width')
        svgElement.style.overflow = 'visible'
        fitDiagram()
        observer = new ResizeObserver(fitDiagram)
        observer.observe(host)
        window.addEventListener('resize', fitDiagram)
      } catch {
        // Mermaid output remains usable even when a browser cannot measure SVG BBox.
      }
    })
    return () => {
      window.cancelAnimationFrame(frame)
      observer?.disconnect()
      window.removeEventListener('resize', fitDiagram)
    }
  }, [svg])

  if (error) return <div className="mermaid-error"><span>图表源码</span><pre><code>{source}</code></pre><small>{error}</small></div>
  if (!svg) return <div className="mermaid-loading">正在绘制架构图…</div>
  return <div ref={containerRef} className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }}/>
}
