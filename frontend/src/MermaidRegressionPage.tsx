import MermaidDiagram from './MermaidDiagram'
import './wiki.css'

const cases = [
  {
    name: 'Flowchart · 并列分组与跨组连线',
    source: `flowchart TB
      subgraph Input[输入层]
        A[论文 PDF] --> B[正文解析]
        C[研究笔记] --> D[证据提取]
      end
      subgraph Analysis[并列分析层]
        E[问题识别] --> F[方法归纳]
        G[实验核验] --> H[局限分析]
      end
      subgraph Output[输出层]
        I[证据化结论]
        J[下一篇阅读建议]
      end
      B --> E
      D --> G
      F --> I
      H --> I
      I --> J`,
  },
  {
    name: 'Sequence Diagram · 多参与者与长消息',
    source: `sequenceDiagram
      autonumber
      participant U as 研究者
      participant P as PaperMorrow
      participant F as SQLite FTS5
      participant W as DeepWiki
      U->>P: 提问当前项目中的方法差异
      P->>F: 只检索项目内论文、笔记和证据化分析
      F-->>P: 返回带来源范围的 BM25 候选
      P->>W: 检索当前项目关联的代码知识页
      W-->>P: 返回文件与实现证据
      P-->>U: 区分论文事实、笔记、Wiki 与 AI 推断`,
  },
  {
    name: 'Class Diagram · 继承、组合与并列关系',
    source: `classDiagram
      class CandidateSource {
        <<interface>>
        +collect(profile) Candidate[]
      }
      class CandidateFilter {
        +excludeSeen(candidates)
      }
      class Ranker {
        <<interface>>
        +rank(candidates) Scored[]
      }
      class Reranker {
        <<interface>>
        +rerank(scored) Scored[]
      }
      class Selector {
        +select(scored) RecommendationResult
      }
      class RecommendationResult {
        +items
        +provenance
        +degraded
      }
      CandidateSource --> CandidateFilter
      CandidateFilter --> Ranker
      Ranker --> Reranker
      Reranker --> Selector
      Selector *-- RecommendationResult`,
  },
]

export default function MermaidRegressionPage() {
  return <main className="mermaid-regression-page">
    <header>
      <span>PAPERMORROW · FIXED REGRESSION</span>
      <h1>DeepWiki Mermaid 完整性回归页</h1>
      <p>连续渲染三种图形，覆盖并列分组、长标签、多个参与者和复杂类关系。</p>
    </header>
    <div className="wiki-markdown-card">
      {cases.map((item, index) => <section key={item.name} data-regression-case={index + 1}>
        <h2>{index + 1}. {item.name}</h2>
        <MermaidDiagram source={item.source}/>
      </section>)}
    </div>
  </main>
}
