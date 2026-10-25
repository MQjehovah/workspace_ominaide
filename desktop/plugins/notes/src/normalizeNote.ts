import { Editor } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { defaultMarkdownSerializer } from 'prosemirror-markdown'

/** Convert legacy desktop TipTap JSON notes to Markdown for the shared editor. */
export function normalizeStoredContent(raw: string | null | undefined): string {
  const text = raw || ''
  if (!text.trim().startsWith('{')) return text
  try {
    const editor = new Editor({
      extensions: [StarterKit],
      content: JSON.parse(text),
    })
    const markdown = defaultMarkdownSerializer.serialize(editor.state.doc)
    editor.destroy()
    return markdown || text
  } catch {
    return text
  }
}
