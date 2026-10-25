import client from '@/api/client'
import { apiUrl } from '@/api/base'
import { configureNotesEditor, type EditorHttp } from '@omniaide/editor'

function flatten(nodes: any[]): any[] {
  const out: any[] = []
  for (const n of nodes || []) {
    out.push(n)
    if (n.children?.length) out.push(...flatten(n.children))
  }
  return out
}

async function uploadNote(file: File): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post('/files/upload/note/direct', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  const key = res.data?.object_key || ''
  return {
    url: key ? apiUrl(`/files/note/${key}`) : '',
    name: file.name,
    size: file.size,
    mime: file.type || 'application/octet-stream',
    object_key: key,
  }
}

const http: EditorHttp = {
  async get(url, config) {
    if (url === '/api/pages') {
      const res = await client.get('/plugins/notes/tree')
      const items = flatten(res.data).map((n: any) => ({
        id: String(n.id),
        title: n.title || '无标题',
        updated_at: n.updated_at || '',
      }))
      return { data: { items } }
    }
    if (url.startsWith('/api/pages/')) {
      const id = url.split('/').pop()
      const res = await client.get(`/plugins/notes/${id}`)
      return { data: { ...res.data, id: String(res.data.id) } }
    }
    if (url === '/api/auth/users') {
      return { data: [] }
    }
    if (url.startsWith('/api/wiki/')) {
      throw Object.assign(new Error('Wiki not available in OmniAide'), { response: { status: 404 } })
    }
    return client.get(url, config)
  },
  async post(url, data, config) {
    if (url === '/api/upload/image' || url === '/api/upload/attachment') {
      const file = (data as FormData).get('file') as File
      const uploaded = await uploadNote(file)
      return { data: uploaded }
    }
    if (url === '/api/upload/images/sign') {
      return { data: { urls: (data as any)?.urls || [] } }
    }
    if (url === '/api/search') {
      const res = await client.post('/plugins/notes/rag/search', {
        q: data?.query || '',
        top_k: data?.top_k || 8,
      })
      const results = (res.data?.results || []).map((r: any) => ({
        id: String(r.note_id),
        title: r.title || '无标题',
        content: r.content || r.snippet || '',
        score: r.score || 0,
        kind: 'note',
      }))
      return { data: { results } }
    }
    if (url === '/api/editor/ai' || url === '/api/editor/ai/complete') {
      const actionPrompts: Record<string, string> = {
        rewrite: '请改写下面的文字，保持原意但更自然流畅，只返回改写后的内容。',
        polish: '请润色下面的文字，只返回润色后的内容。',
        summarize: '请用简洁的中文总结下面的内容，只返回总结。',
        translate: '请把下面的内容翻译成中文，只返回译文。',
        continue: '请自然续写下面的内容，只返回续写部分。',
        expand: '请扩写下面的内容，只返回扩写后的内容。',
      }
      const action = String(data?.action || '')
      const instruction = String(data?.instruction || data?.prompt || data?.system || actionPrompts[action] || '')
      const source = String(data?.text || data?.content || data?.selection || data?.before || data?.context || '')
      const message = [instruction, source].filter(Boolean).join('\n\n')
      const res = await client.post('/chat', { message }, { timeout: 120000 })
      return { data: { result: res.data?.reply || res.data?.content || '' } }
    }
    return client.post(url, data, config)
  },
}

export function installOmniAideEditorAdapter() {
  configureNotesEditor({
    http,
    apiBase: (import.meta.env.BASE_URL || '/').replace(/\/$/, ''),
    getToken: () => localStorage.getItem('token'),
  })
}
