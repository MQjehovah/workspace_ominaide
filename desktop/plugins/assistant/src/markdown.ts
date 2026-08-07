import { marked } from 'marked'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import shell from 'highlight.js/lib/languages/shell'
import css from 'highlight.js/lib/languages/css'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import sql from 'highlight.js/lib/languages/sql'
import go from 'highlight.js/lib/languages/go'
import rust from 'highlight.js/lib/languages/rust'
import java from 'highlight.js/lib/languages/java'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import csharp from 'highlight.js/lib/languages/csharp'
import markdown from 'highlight.js/lib/languages/markdown'
import diff from 'highlight.js/lib/languages/diff'
import 'highlight.js/styles/atom-one-dark.css'

const langs: [string, any][] = [
  ['javascript', javascript],
  ['js', javascript],
  ['typescript', typescript],
  ['ts', typescript],
  ['python', python],
  ['py', python],
  ['json', json],
  ['bash', bash],
  ['shell', shell],
  ['sh', shell],
  ['css', css],
  ['html', xml],
  ['xml', xml],
  ['svg', xml],
  ['yaml', yaml],
  ['yml', yaml],
  ['sql', sql],
  ['go', go],
  ['rust', rust],
  ['rs', rust],
  ['java', java],
  ['c', c],
  ['cpp', cpp],
  ['c++', cpp],
  ['csharp', csharp],
  ['cs', csharp],
  ['markdown', markdown],
  ['md', markdown],
  ['diff', diff],
]

const registered = new Set<string>()
for (const [name, lang] of langs) {
  if (!registered.has(name)) {
    hljs.registerLanguage(name, lang)
    registered.add(name)
  }
}

function stripUnsafe(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<(iframe|object|embed|link|meta)[\s\S]*?>/gi, '')
    .replace(/\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/\shref\s*=\s*["']?\s*javascript:[^"'>]*/gi, ' href="#/"')
}

export function escapeHtml(src: string): string {
  return (src || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const renderer = new marked.Renderer()
renderer.code = ({ text, lang }: { text: string; lang?: string }): string => {
  const langName = (lang || '').split(/\s+/)[0]
  let body = escapeHtml(text)
  if (langName && hljs.getLanguage(langName)) {
    try {
      body = hljs.highlight(text, { language: langName }).value
    } catch { /* keep escaped */ }
  }
  const cls = langName ? ` class="hljs language-${escapeHtml(langName)}"` : ' class="hljs"'
  const copy = `<button class="code-copy" data-code="${escapeHtml(text)}">复制</button>`
  return `<div class="code-wrap"><pre><code${cls}>${body}</code></pre>${copy}</div>`
}
marked.use({ renderer })

export function renderMarkdown(src: string): string {
  const html = marked.parse(src || '', {
    breaks: true,
    gfm: true,
  }) as string
  return stripUnsafe(html)
}
