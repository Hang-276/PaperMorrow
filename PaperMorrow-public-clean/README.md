# PaperMorrow

<p align="center">
  <img src="frontend/public/papermorrow-logo.png" width="112" alt="PaperMorrow logo" />
</p>

<p align="center"><strong>把论文、证据、实验与写作，组织成可持续推进的研究工作流。</strong></p>

<p align="center">
  <a href="README_EN.md">English</a> ·
  <a href="../../releases/latest">最新版本</a> ·
  <a href="DESKTOP_BUILD.md">构建说明</a>
</p>

> [!IMPORTANT]
> PaperMorrow 目前处于 **Beta 测试阶段**。请先备份重要科研资料；模型输出必须由研究者核验，不能替代原论文、实验记录或专业判断。

## 下载桌面版

安装包由 GitHub Releases 直接托管，不使用第三方网盘。

| 平台 | 下载 | 说明 |
|---|---|---|
| macOS 12+ | [下载 DMG](../../releases/latest/download/PaperMorrow-macOS.dmg) | 当前本地发布包面向 Apple silicon；尚未完成 Apple 公证 |
| Windows 10/11 x64 | [下载安装版](../../releases/latest/download/PaperMorrow-Windows-Setup.exe) | 由 GitHub Windows runner 构建；发布前仍需真实 Windows 设备终检 |
| Windows 10/11 x64 | [下载便携版](../../releases/latest/download/PaperMorrow-Windows-Portable.zip) | 解压后运行，不写入系统级目录 |

未签名的 Beta 安装包可能触发 macOS Gatekeeper 或 Windows SmartScreen。发布页同时提供文件哈希；请只从本仓库 Releases 下载。

## 为谁而做

PaperMorrow 面向研究生、本科科研参与者、博士后和需要长期管理证据链的研究人员。它不是另一个“把问题发给聊天机器人”的页面，而是一套本地优先的科研桌面工作台：

- 在最新论文中保持广度，同时持续追踪自己的细分研究问题。
- 把论文事实、作者主张、个人记录和 AI 推断明确分开。
- 用项目串联阅读队列、项目笔记、专题调研、实验记录和代码 Wiki。
- 让 AI 先给出可编辑计划，再在明确授权和审批下完成一个个步骤。
- 将成果继续整理为 Markdown、研究报告、数据表和可编辑演示文稿。

## 核心体验

### AI 协作：面向科研的本地 Cowork Agent

选择论文、文件或文件夹，描述目标，PaperMorrow 会建立可编辑计划并持续展示进度、来源、工具调用、审批与产物。主 Agent 可按需委派文献证据、研究综合和项目规划专家；每个专家只获得完成子任务所需的最小资料与工具预算。

- 支持暂停、继续、取消、单步重试和检查点恢复。
- 文件访问默认拒绝，只允许用户选择的根目录；阻止路径穿越、符号链接逃逸、隐藏密钥和 `.env` 读取。
- 写入、覆盖、批量导入和外部操作遵循预览与审批。
- 内置少量高价值科研 Skill，并支持查看来源、许可证、版本和工具权限后再导入。
- 普通页面的“问 AI”复用同一交互方式，但只读取当前可见页面，不会默认扫描全部资料。

### 论文发现与证据化阅读

- 支持广度推荐、方向聚焦和“聚焦 + 探索”混合推荐。
- 聚合 arXiv、Semantic Scholar、OpenAlex、Crossref、PubMed、Europe PMC 等学术来源。
- 以 DOI、arXiv ID、Semantic Scholar ID 和标题指纹永久去重。
- 中英文摘要与分析按需生成；只有摘要时明确标注“仅摘要”，不伪造页码。
- PDF 阅读器支持视口懒渲染、选中文本翻译/提问/引用、框选插图写入笔记。

### 项目、实验与知识关系

- 每个项目拥有独立的论文队列、项目笔记、专题调研、实验时间线与 AI 检索范围。
- 每个项目建立自己的证据化知识关系，不混入其他项目内容。
- 关系必须保存来源、证据与置信度，不默认制造“语义相似”边。
- 实验分析引用实验编号，比较配置、指标、观察与产物，并明确未验证的推断。
- DeepWiki 在不执行第三方代码的前提下，把仓库结构、关键模块和源码证据整理为本地 Wiki。

### 笔记、PPT 与研究产物

- 统一管理论文笔记和独立笔记，支持 Markdown、LaTeX、可视化编辑与源码编辑。
- 演示文稿先生成可编辑大纲，再输出 `.pptx`；每页可关联论文、笔记与实验来源。
- Cowork 产物区集中管理报告、表格、PPT、笔记和导入论文。
- 模型调用记录只保存用途、模型与 Token 数量，不保存提示词正文、回复正文或 API Key。

## 本地优先与数据安全

数据库、API Key、论文、PDF、笔记、Wiki、项目和实验记录默认只保存在本机：

- macOS：`~/Library/Application Support/PaperMorrow`
- Windows：`%APPDATA%\PaperMorrow`

PaperMorrow 使用 SQLite、FTS5 与 BM25 完成本地检索，不要求独立向量数据库、云端账户或常驻远程服务。模型 API 只在用户主动使用 AI 功能时调用；发送范围会在界面中说明。卸载或升级应用不会主动删除用户资料。

## 无模型也能使用

未配置 API Key 时，应用仍可启动，并使用学习库、项目、笔记、实验记录、DDL、基础论文检索和本地知识整理。AI 分析与 Cowork 专家会明确暂停或降级，不会伪造执行结果。

可在“设置 → 模型 API”保存多个 LLM Profile 并切换。兼容 OpenAI、Anthropic Claude、GLM、DeepSeek 及用户自定义的 OpenAI 兼容接口；模型名称和能力以服务商实际支持为准。

## 从源码运行

需要 Python 3.10+ 与 Node.js 20+。

```bash
cp .env.example .env
./start.sh
```

Windows 可双击 `start.bat`。开发、测试和桌面构建细节见 [DESKTOP_BUILD.md](DESKTOP_BUILD.md)。

## 发布与验证状态

每个 `v*` 标签会触发 GitHub Actions：在 macOS 与 Windows 上安装依赖、运行后端测试、执行前端正式构建、生成安装包，再将三个文件上传到 GitHub Releases。当前边界如下：

- macOS 本地包已进行启动、健康检查和浏览器界面验证；使用临时签名，尚未公证。
- Windows 安装包由原生 Windows runner 构建；在真实 Windows 设备终检完成前保持 Beta 标记。
- 网络测试使用 mock，不在测试中读取真实用户笔记或调用真实模型服务。
- AI、Skill 与文档生成结果仍需要用户核查来源、格式和学术准确性。

## 技术结构

- FastAPI + SQLAlchemy + SQLite/FTS5 后端
- React + TypeScript + Vite 前端
- pywebview + PyInstaller 桌面封装
- 本地 Tool Registry、权限/审批和审计日志
- 增量 SQLite 迁移与迁移前备份

欢迎通过 Issues 报告可复现问题。请勿上传 API Key、未公开论文、真实患者资料或其他敏感数据。
