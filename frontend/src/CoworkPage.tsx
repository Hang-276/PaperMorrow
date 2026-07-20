import { Bot, FileLock2, FolderOpen, Paperclip, ShieldCheck, Sparkles, Wrench } from 'lucide-react'
import './cowork.css'

export default function CoworkPage({ onOpenAssistant }: { onOpenAssistant: () => void }) {
  return <section className="cowork-page page-content">
    <div className="cowork-hero"><div className="cowork-mark"><Bot/></div><span className="section-kicker">RESEARCH COWORK</span><h2>与 AI 一起推进完整研究工作</h2><p>这里将承载可授权的文件与项目协作：先说明目标，再选择允许访问的资料，由 Agent 规划步骤并在每次写入或调用工具前展示边界。</p><button className="primary" onClick={onOpenAssistant}><Sparkles/>先使用当前页面助手</button></div>
    <div className="cowork-capabilities">
      <article><FolderOpen/><div><strong>按范围授权</strong><span>选择文件或文件夹，笔记、阅读记录与项目资料均需逐类授权。</span></div></article>
      <article><Wrench/><div><strong>科研工具协作</strong><span>导入论文、整理笔记、生成 PPT、处理文档与调用 PaperMorrow 内置能力。</span></div></article>
      <article><ShieldCheck/><div><strong>操作可审阅</strong><span>读取、写入与外部调用分级确认，保留来源、结果与撤销线索。</span></div></article>
    </div>
    <div className="cowork-preview"><header><div><span>独立工作区</span><h3>完整 Cowork Agent 将在下一阶段接入</h3></div><em>设计已就绪</em></header><div><button disabled><Paperclip/>导入文件</button><button disabled><FolderOpen/>选择文件夹</button><button disabled><FileLock2/>调整权限</button></div><p>当前入口用于明确产品边界，不会在后台读取任何文件。页面级“问 AI”仍只在发送问题时读取当前可见内容。</p></div>
  </section>
}
