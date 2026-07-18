import { useEffect, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import './reader.css'
import { BookOpen, Bot, Check, ChevronLeft, Crop, FileText, Languages, MessageCircle, Minus, NotebookPen, Plus, RefreshCw, Send, Sparkles, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from './api'
import type { ChatMessage, ChatSession, Paper } from './types'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

type SideMode = 'chat'|'note'|'both'
type TextSelection = { text:string; page:number; x:number; y:number }
type CropState = { page:number; x:number; y:number; width:number; height:number }

export default function ReaderWorkspace({ paper, configured, onClose, onSaved }: { paper:Paper; configured:boolean; onClose:()=>void; onSaved:()=>Promise<void> }) {
  const [pages,setPages] = useState(0)
  const [scale,setScale] = useState(1.05)
  const [mode,setMode] = useState<SideMode>('both')
  const [note,setNote] = useState(paper.note||'')
  const [saved,setSaved] = useState(true)
  const [selection,setSelection] = useState<TextSelection|null>(null)
  const [translation,setTranslation] = useState('')
  const [translating,setTranslating] = useState(false)
  const [pendingQuestion,setPendingQuestion] = useState('')
  const [figureMode,setFigureMode] = useState(false)
  const [crop,setCrop] = useState<CropState|null>(null)
  const [status,setStatus] = useState('')
  const readerRef = useRef<HTMLDivElement>(null)

  const saveNote = async () => { setSaved(false); await api(`/api/papers/${paper.id}/note`,{method:'PUT',body:JSON.stringify({content:note})}); setSaved(true) }
  const closeReader = async () => { try { await saveNote(); await onSaved(); onClose() } catch (error) { setStatus(error instanceof Error ? error.message : '笔记保存失败') } }

  useEffect(()=>{ const timer=window.setTimeout(()=>saveNote().catch(error=>setStatus(error instanceof Error?error.message:'笔记保存失败')),700); return()=>window.clearTimeout(timer) },[note,paper.id])

  const captureSelection = () => {
    if (figureMode) return
    const selected=window.getSelection(); const text=(selected?.toString()||'').replace(/\s+/g,' ').trim()
    if (!selected||!text||selected.rangeCount===0) return setSelection(null)
    const range=selected.getRangeAt(0); const node=range.commonAncestorContainer.nodeType===3?range.commonAncestorContainer.parentElement:range.commonAncestorContainer as Element
    if (!node||!readerRef.current?.contains(node)) return
    const pageEl=node.closest('[data-reader-page]') as HTMLElement|null; const rect=range.getBoundingClientRect()
    setTranslation(''); setSelection({text,page:Number(pageEl?.dataset.readerPage||1),x:Math.min(window.innerWidth-310,Math.max(12,rect.left)),y:Math.max(70,rect.top-48)})
  }
  const translate = async () => { if(!selection||!configured)return; setTranslating(true); try{const result=await api<{translation:string}>(`/api/papers/${paper.id}/reader/translate`,{method:'POST',body:JSON.stringify({text:selection.text,page:selection.page,target_language:'zh'})});setTranslation(result.translation)}catch(err){setStatus(err instanceof Error?err.message:'翻译失败')}finally{setTranslating(false)} }
  const appendQuote = () => { if(!selection)return; const block=`\n\n## Page ${selection.page} — 阅读摘录\n\n> ${selection.text.replace(/\n/g,'\n> ')}${translation?`\n\n**翻译：**\n\n${translation}`:''}\n\n**我的思考：**\n\n`; setNote(current=>current+block); setMode('note'); setSelection(null); setStatus('已引用到笔记') }
  const askSelection = () => { if(!selection)return; setPendingQuestion(`请结合论文全文解释并分析下面这段内容（Page ${selection.page}）：\n\n> ${selection.text}`); setMode('chat'); setSelection(null) }

  const cropStart = (event:React.MouseEvent<HTMLDivElement>,page:number) => { const rect=event.currentTarget.getBoundingClientRect(); setCrop({page,x:event.clientX-rect.left,y:event.clientY-rect.top,width:0,height:0}) }
  const cropMove = (event:React.MouseEvent<HTMLDivElement>,page:number) => { if(!crop||crop.page!==page)return; const rect=event.currentTarget.getBoundingClientRect(); setCrop(current=>current?{...current,width:event.clientX-rect.left-current.x,height:event.clientY-rect.top-current.y}:current) }
  const cropEnd = async (event:React.MouseEvent<HTMLDivElement>,page:number) => {
    if(!crop||crop.page!==page)return
    const overlay=event.currentTarget; const pageEl=overlay.parentElement; const canvas=pageEl?.querySelector('canvas'); const overlayRect=overlay.getBoundingClientRect()
    const x=Math.min(crop.x,crop.x+crop.width), y=Math.min(crop.y,crop.y+crop.height), width=Math.abs(crop.width), height=Math.abs(crop.height)
    if(!canvas||width<24||height<24){setCrop(null);return}
    const ratioX=canvas.width/overlayRect.width, ratioY=canvas.height/overlayRect.height
    const output=document.createElement('canvas'); output.width=Math.round(width*ratioX); output.height=Math.round(height*ratioY)
    output.getContext('2d')?.drawImage(canvas,x*ratioX,y*ratioY,width*ratioX,height*ratioY,0,0,output.width,output.height)
    setStatus('正在保存插图…')
    try{const result=await api<{markdown:string}>(`/api/papers/${paper.id}/reader/figures`,{method:'POST',body:JSON.stringify({data_url:output.toDataURL('image/png'),page,caption:`论文插图 Page ${page}`})});setNote(current=>`${current}\n\n## Page ${page} — 论文插图\n\n${result.markdown}\n\n**我的思考：**\n\n`);setMode('note');setStatus('插图已加入笔记')}catch(err){setStatus(err instanceof Error?err.message:'插图保存失败')}finally{setCrop(null);setFigureMode(false)}
  }

  return <div className="reader-workspace">
    <header className="reader-header"><button className="icon-button" onClick={closeReader}><ChevronLeft/></button><div><span>SMART READER</span><h1>{paper.title_en}</h1></div><div className="reader-controls"><button onClick={()=>setScale(Math.max(.65,scale-.1))}><Minus size={15}/></button><strong>{Math.round(scale*100)}%</strong><button onClick={()=>setScale(Math.min(1.8,scale+.1))}><Plus size={15}/></button><button className={figureMode?'active':''} onClick={()=>{setFigureMode(!figureMode);setSelection(null)}}><Crop size={15}/>{figureMode?'拖动框选插图':'框选插图'}</button><span>{pages||'—'} 页</span></div><button className="icon-button" aria-label="关闭阅读器" onClick={closeReader}><X/></button></header>
    <main className={`reader-layout side-${mode}`}><section className={`pdf-pane ${figureMode?'cropping':''}`} ref={readerRef} onMouseUp={captureSelection}><Document file={`/api/papers/${paper.id}/reader/pdf`} loading={<div className="reader-loading"><RefreshCw className="spin"/>正在准备论文 PDF…</div>} error={<div className="reader-loading error">无法读取公开 PDF，请使用论文原始链接。</div>} onLoadSuccess={({numPages})=>setPages(numPages)}>{Array.from({length:pages},(_,index)=>{const page=index+1;return <LazyReaderPage key={page} page={page} scale={scale} rootRef={readerRef} figureMode={figureMode} crop={crop} onCropStart={cropStart} onCropMove={cropMove} onCropEnd={cropEnd}/>})}</Document></section>
      <aside className="reader-side"><nav><button className={mode==='chat'?'active':''} onClick={()=>setMode('chat')}><MessageCircle size={15}/>Chat</button><button className={mode==='note'?'active':''} onClick={()=>setMode('note')}><NotebookPen size={15}/>笔记</button><button className={mode==='both'?'active':''} onClick={()=>setMode('both')}><BookOpen size={15}/>同时显示</button></nav><div className={`reader-side-content ${mode}`}>{mode!=='note'&&<ReaderChat paper={paper} configured={configured} queued={pendingQuestion} onConsumed={()=>setPendingQuestion('')}/>} {mode!=='chat'&&<ReaderNotes note={note} setNote={setNote} saved={saved}/>}</div></aside>
    </main>
    {selection&&<div className="selection-tools" style={{left:selection.x,top:selection.y}}><button disabled={!configured||translating} onClick={translate}><Languages size={14}/>{translating?'翻译中':'翻译'}</button><button disabled={!configured} onClick={askSelection}><Bot size={14}/>问 AI</button><button onClick={appendQuote}><FileText size={14}/>引用到笔记</button><button onClick={()=>setSelection(null)}><X size={14}/></button>{translation&&<div className="selection-translation"><span>Page {selection.page} · 中文翻译</span><p>{translation}</p><button onClick={appendQuote}><Check size={13}/>原文与翻译加入笔记</button></div>}</div>}
    {status&&<div className="reader-toast" onClick={()=>setStatus('')}>{status}</div>}
  </div>
}

function LazyReaderPage({page,scale,rootRef,figureMode,crop,onCropStart,onCropMove,onCropEnd}:{
  page:number; scale:number; rootRef:React.RefObject<HTMLDivElement|null>; figureMode:boolean; crop:CropState|null;
  onCropStart:(event:React.MouseEvent<HTMLDivElement>,page:number)=>void;
  onCropMove:(event:React.MouseEvent<HTMLDivElement>,page:number)=>void;
  onCropEnd:(event:React.MouseEvent<HTMLDivElement>,page:number)=>void;
}) {
  const pageRef=useRef<HTMLDivElement>(null)
  const [visible,setVisible]=useState(page<=2)
  const [size,setSize]=useState({width:612*scale,height:792*scale})

  useEffect(()=>{
    const target=pageRef.current
    if(!target||typeof IntersectionObserver==='undefined'){setVisible(true);return}
    const observer=new IntersectionObserver(entries=>setVisible(entries.some(entry=>entry.isIntersecting)),{
      root:rootRef.current,
      rootMargin:'1400px 0px',
      threshold:0,
    })
    observer.observe(target)
    return()=>observer.disconnect()
  },[rootRef])

  const rememberSize=()=>window.requestAnimationFrame(()=>{
    const canvas=pageRef.current?.querySelector('canvas')
    if(canvas) setSize({width:canvas.clientWidth,height:canvas.clientHeight})
  })

  return <div className="reader-page" data-reader-page={page} ref={pageRef}>
    {visible?<Page pageNumber={page} scale={scale} renderTextLayer renderAnnotationLayer onRenderSuccess={rememberSize}/>:<div className="reader-page-placeholder" style={{width:size.width,height:size.height}}>Page {page}</div>}
    <span className="page-index">{page}</span>
    {visible&&figureMode&&<div className="figure-crop-overlay" onMouseDown={event=>onCropStart(event,page)} onMouseMove={event=>onCropMove(event,page)} onMouseUp={event=>onCropEnd(event,page)}>{crop?.page===page&&<i style={{left:Math.min(crop.x,crop.x+crop.width),top:Math.min(crop.y,crop.y+crop.height),width:Math.abs(crop.width),height:Math.abs(crop.height)}}/>}</div>}
  </div>
}

function ReaderNotes({note,setNote,saved}:{note:string;setNote:(value:string)=>void;saved:boolean}){return <section className="reader-notes"><header><div><FileText size={16}/><strong>Markdown 学习笔记</strong></div><span>{saved?<><Check size={12}/>已保存</>:<><RefreshCw className="spin" size={12}/>保存中</>}</span></header><div className="reader-note-split"><textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="# 研究问题\n\n从 PDF 选择文字或插图，也可以直接记录你的思考。"/><article><ReactMarkdown remarkPlugins={[remarkGfm]}>{note||'*笔记预览*'}</ReactMarkdown></article></div></section>}

function ReaderChat({paper,configured,queued,onConsumed}:{paper:Paper;configured:boolean;queued:string;onConsumed:()=>void}){
  const [sessions,setSessions]=useState<ChatSession[]>([]),[sessionId,setSessionId]=useState<string|null>(null),[messages,setMessages]=useState<ChatMessage[]>([]),[input,setInput]=useState(''),[sending,setSending]=useState(false),[error,setError]=useState('')
  useEffect(()=>{api<ChatSession[]>(`/api/papers/${paper.id}/chat/sessions`).then(async items=>{setSessions(items);if(items.length){setSessionId(items[0].id);setMessages(await api(`/api/papers/${paper.id}/chat/sessions/${items[0].id}/messages`))}})},[paper.id])
  const send=async(contentArg?:string)=>{const content=(contentArg||input).trim();if(!content||sending||!configured)return;setInput('');setSending(true);setError('');setMessages(current=>[...current,{role:'user',content}]);try{const response=await api<{session_id:string;answer:string}>(`/api/papers/${paper.id}/chat`,{method:'POST',body:JSON.stringify({message:content,session_id:sessionId})});setSessionId(response.session_id);setMessages(current=>[...current,{role:'assistant',content:response.answer}]);setSessions(await api(`/api/papers/${paper.id}/chat/sessions`))}catch(err){setError(err instanceof Error?err.message:'对话失败')}finally{setSending(false)}}
  useEffect(()=>{if(queued){send(queued);onConsumed()}},[queued])
  return <section className="reader-chat"><header><div><Sparkles size={16}/><strong>论文对话</strong></div>{sessions.length?<select value={sessionId||''} onChange={async e=>{setSessionId(e.target.value||null);setMessages(e.target.value?await api(`/api/papers/${paper.id}/chat/sessions/${e.target.value}/messages`):[])}}><option value="">新对话</option>{sessions.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select>:<span>全文优先</span>}</header><div className="reader-chat-messages">{!configured?<div className="reader-chat-placeholder"><Bot/><p>请先在设置中连接一个模型。</p></div>:messages.length?messages.map((message,index)=><div key={message.id||index} className={`reader-bubble ${message.role}`}><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>):<div className="reader-chat-placeholder"><MessageCircle/><p>选择 PDF 文字后点“问 AI”，或直接针对全文提问。</p></div>}{sending&&<div className="reader-bubble assistant"><RefreshCw className="spin" size={15}/>正在阅读上下文…</div>}</div>{error&&<div className="chat-error">{error}</div>}<footer><textarea disabled={!configured} value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}} placeholder="针对论文提问…"/><button disabled={!configured||!input.trim()||sending} onClick={()=>send()}><Send size={16}/></button></footer></section>
}
