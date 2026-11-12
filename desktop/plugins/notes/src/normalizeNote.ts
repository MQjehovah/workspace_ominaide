import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { defaultMarkdownSerializer } from 'prosemirror-markdown'

/** Convert HTML to Markdown so old web/imported notes render correctly. */
function htmlToMarkdown(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const blocks: string[] = []
  for (const node of Array.from(doc.body.childNodes)) {
    const value = renderNode(node).trim()
    if (value) blocks.push(value)
  }
  return blocks.join('\n\n')
}

function renderNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return (node.textContent || '').replace(/\s+/g, ' ').trim()
  }
  if (!(node instanceof HTMLElement)) return ''
  const tag = node.tagName.toLowerCase()
  const inner = () =>
    Array.from(node.childNodes)
      .map(renderNode)
      .filter((part) => part.length > 0)
      .join('')
  switch (tag) {
    case 'h1':
      return `# ${inner()}`
    case 'h2':
      return `## ${inner()}`
    case 'h3':
      return `### ${inner()}`
    case 'h4':
      return `#### ${inner()}`
    case 'h5':
      return `##### ${inner()}`
    case 'h6':
      return `###### ${inner()}`
    case 'p':
    case 'div':
      return inner()
    case 'br':
      return '\n'
    case 'strong':
    case 'b':
      return `**${inner()}**`
    case 'em':
    case 'i':
      return `*${inner()}*`
    case 'del':
    case 's':
      return `~~${inner()}~~`
    case 'code':
      return `\`${node.textContent || ''}\``
    case 'pre':
      return '```\n' + (node.textContent || '').trim() + '\n```'
    case 'blockquote':
      return inner()
        .split('\n')
        .map((line) => `> ${line}`)
        .join('\n')
    case 'a': {
      const href = node.getAttribute('href') || ''
      return href ? `[${inner()}](${href})` : inner()
    }
    case 'img': {
      const src = node.getAttribute('src') || ''
      const alt = node.getAttribute('alt') || ''
      return src ? `![${alt}](${src})` : ''
    }
    case 'ul':
      return Array.from(node.children)
        .map((child) => `- ${renderNode(child).trim()}`)
        .join('\n')
    case 'ol':
      return Array.from(node.children)
        .map((child, index) => `${index + 1}. ${renderNode(child).trim()}`)
        .join('\n')
    case 'li':
      return inner()
    case 'table': {
      const rows = Array.from(node.querySelectorAll('tr')).map((row) =>
        Array.from(row.querySelectorAll('th,td')).map((cell) =>
          (cell.textContent || '').replace(/\s+/g, ' ').trim(),
        ),
      )
      if (!rows.length) return ''
      const width = Math.max(...rows.map((row) => row.length))
      const normalized = rows.map((row) => [
        ...row,
        ...Array.from({ length: width - row.length }, () => ''),
      ])
      const header = normalized[0]
      const divider = header.map(() => '---')
      const body = normalized.slice(1)
      return [header, divider, ...body]
        .map((row) => `| ${row.join(' | ')} |`)
        .join('\n')
    }
    default:
      return inner()
  }
}

/** Convert stored note content to Markdown for the shared editor. */
export function normalizeStoredContent(raw: string | null | undefined): string {
  const text = raw || ''
  const trimmed = text.trim()
  if (!trimmed) return ''

  // Legacy desktop editor stored TipTap JSON.
  if (trimmed.startsWith('{')) {
    try {
      const editor = new Editor({
        extensions: [StarterKit],
        content: JSON.parse(trimmed),
      })
      const markdown = defaultMarkdownSerializer.serialize(editor.state.doc)
      editor.destroy()
      return markdown || text
    } catch {
      return text
    }
  }

  // Some imported notes were stored as HTML; the Markdown editor would show
  // the tags or drop blocks. Convert before handing it to the editor.
  if (
    /^\s*<(?:!doctype|html|body|p|div|h[1-6]|ul|ol|table|blockquote|section|article)\b/i.test(
      trimmed,
    )
  ) {
    try {
      const markdown = htmlToMarkdown(trimmed)
      if (markdown.trim()) return markdown
    } catch {
      return text
    }
  }
  return text
}
