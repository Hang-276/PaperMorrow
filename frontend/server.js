const express = require('express');
const fs = require('fs');
const path = require('path');
const { marked } = require('marked');
const app = express();
const PORT = 3000;

// 设置模板引擎
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// 静态文件服务
app.use(express.static(path.join(__dirname, 'public')));

// 配置marked以支持代码高亮和mermaid，同时防止XML注入
marked.setOptions({
  highlight: function(code, lang) {
    // 对于mermaid代码块，我们需要保留原样，让前端的mermaid.js来渲染
    return code;
  },
  breaks: true,
  gfm: true,
  langPrefix: '', // 移除语言前缀，避免干扰mermaid渲染
  // 安全设置
  sanitize: false, // 使用自定义的清理逻辑，因为marked的内置sanitize已弃用
  xhtml: true // 确保输出的HTML是有效的XHTML
});

// 安全清理函数，防止XML注入
function sanitizeContent(content) {
  // 转义潜在的XML注入字符
  return content
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/\$/g, '&#36;')
    .replace(/\*/g, '&#42;');
}

// 安全的代码块渲染，只允许特定的安全标签和属性
function safeCodeRender(code, language) {
  // 对于mermaid代码块，我们需要特殊处理，但仍然要防止注入
  if (language && language.toLowerCase() === 'mermaid') {
    // 清理mermaid代码，移除潜在的危险内容
    const safeCode = sanitizeContent(code)
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/javascript:/gi, '')
      .replace(/on\w+\s*=/gi, '');
    
    return `<div class="mermaid">
${safeCode}
</div>`;
  }
  // 对于其他代码块，同样进行清理
  const safeCode = sanitizeContent(code);
  return `<pre><code class="language-${language}">${safeCode}</code></pre>`;
}

// 自定义渲染器，确保mermaid代码块被正确处理并防止XML注入
const renderer = new marked.Renderer();

// 重写代码块渲染方法
renderer.code = function(code, language) {
  return safeCodeRender(code, language);
};

// 重写其他可能存在风险的渲染方法
renderer.link = function(href, title, text) {
  // 验证链接，防止危险URL
  if (href && (href.startsWith('javascript:') || href.startsWith('data:'))) {
    return `<span class="invalid-link">[${text}]</span>`;
  }
  
  const safeHref = href ? sanitizeContent(href) : '';
  const safeTitle = title ? ` title="${sanitizeContent(title)}"` : '';
  const safeText = sanitizeContent(text);
  
  return `<a href="${safeHref}"${safeTitle}>${safeText}</a>`;
};

renderer.html = function(html) {
  // 过滤HTML内容，只允许安全的标签
  const allowedTags = ['b', 'i', 'u', 'strong', 'em', 'br', 'p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'table', 'tr', 'td', 'th'];
  
  // 移除所有脚本和事件处理程序
  let safeHtml = html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/on\w+\s*=/gi, '')
    .replace(/javascript:/gi, '');
  
  // 只保留允许的标签
  allowedTags.forEach(tag => {
    const regex = new RegExp(`<(/?)${tag}[^>]*>`, 'gi');
    safeHtml = safeHtml.replace(regex, `<$1${tag}>`);
  });
  
  return safeHtml;
};

// 主路由 - 显示项目列表
app.get('/', (req, res) => {
  const wikiDir = path.join(__dirname, 'wiki');
  try {
    const projects = fs.readdirSync(wikiDir).filter(file => {
      return fs.statSync(path.join(wikiDir, file)).isDirectory();
    });
    res.render('index', { projects });
  } catch (err) {
    res.status(500).send('读取项目列表失败: ' + err.message);
  }
});

// 项目页面路由 - 显示项目中的页面列表
app.get('/:project', (req, res) => {
  const project = req.params.project;
  const structurePath = path.join(__dirname, 'wiki', project, 'wiki_structure.json');
  
  try {
    if (!fs.existsSync(structurePath)) {
      return res.status(404).send('项目不存在');
    }
    
    const structure = JSON.parse(fs.readFileSync(structurePath, 'utf8'));
    res.render('project', { project, structure });
  } catch (err) {
    res.status(500).send('读取项目结构失败: ' + err.message);
  }
});

// 页面内容路由 - 渲染markdown内容
app.get('/:project/page/:pageId', (req, res) => {
  const { project, pageId } = req.params;
  const mdPath = path.join(__dirname, 'wiki', project, 'pages', `${pageId}.md`);
  const structurePath = path.join(__dirname, 'wiki', project, 'wiki_structure.json');
  
  try {
    if (!fs.existsSync(mdPath)) {
      return res.status(404).send('页面不存在');
    }
    
    const markdown = fs.readFileSync(mdPath, 'utf8');
    let html;
    
    // 先进行基本的输入验证
    if (markdown.includes('<![CDATA[') || markdown.includes(']]>') || 
        markdown.includes('<?xml') || markdown.includes('<!DOCTYPE')) {
      // 记录潜在的XML注入尝试
      console.warn(`潜在的XML注入尝试被检测到: ${pageId}`);
      // 清理输入
      const sanitizedMarkdown = markdown
        .replace(/<!\[CDATA\[/g, '&lt;![CDATA[')
        .replace(/\]\]>/g, ']]&gt;')
        .replace(/<\?xml/g, '&lt;?xml')
        .replace(/<!DOCTYPE/g, '&lt;!DOCTYPE');
      html = marked(sanitizedMarkdown, { renderer: renderer });
    } else {
      html = marked(markdown, { renderer: renderer });
    }
    
    // 获取页面标题等信息
    let pageTitle = pageId;
    let structure = null;
    
    if (fs.existsSync(structurePath)) {
      structure = JSON.parse(fs.readFileSync(structurePath, 'utf8'));
      const pageInfo = structure.pages.find(p => p.id === pageId);
      if (pageInfo) {
        pageTitle = pageInfo.title;
      }
    }
    
    res.render('page', { 
      project, 
      pageId, 
      currentPageId: pageId,
      pageTitle, 
      content: html,
      structure 
    });
  } catch (err) {
    res.status(500).send('渲染页面失败: ' + err.message);
  }
});

// 启动服务器
app.listen(PORT, () => {
  console.log(`服务器运行在 http://localhost:${PORT}`);
});