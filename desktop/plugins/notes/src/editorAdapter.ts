import { configureNotesEditor, type EditorHttp } from '../../../../frontend/src/components/editor/index'

function flatten(nodes: any[]): any[] {
  const out: any[] = []
  for (const n of nodes || []) {
    out.push(n)
    if (n.children?.length) out.push(...flatten(n.children))
  }
  return out
}

async function serverUrl(): Promise<string> {
  try {
    return (await (window as any).mqbox?.config?.get('serverUrl')) || 'https://mqgeek.com/ominaide'
  } catch {
    return 'https://mqgeek.com/ominaide'
  }
}

async function token(): Promise<string> {
  try {
    return (await (window as any).mqbox?.config?.get('token')) || localStorage.getItem('token') || ''
  } catch {
    return localStorage.getItem('token') || ''
  }
}

async function uploadNote(file: File): Promise<any> {
  const base = await serverUrl()
  const tk = await token()
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${base}/api/files/upload/note/direct`, {
    method: 'POST',
    headers: tk ? { Authorization: `Bearer ${tk}` } : undefined,
    body: form,
  })
  const data = await res.json()
  const key = data?.object_key || ''
  return {
    url: key ? `${base}/api/files/note/${key}` : '',
    name: file.name,
    size: file.size,
    mime: file.type || 'application/octet-stream',
  }
}

const http: EditorHttp = {
  async get(url, config) {
    if (url === '/api/pages') {
      const res = await (window as any).mqbox?.api?.get('/plugins/notes/tree') || []
      const items = flatten(Array.isArray(res) ? res : []).map((n: any) => ({
        id: String(n.id),
        title: n.title || '无标题',
        updated_at: n.updated_at || '',
      }))
      return { data: { items } }
    }
    if (url.startsWith('/api/pages/')) {
      const id = url.split('/').pop()
      const res = await (window as any).mqbox?.api?.get(`/plugins/notes/${id}`) || {}
      return { data: { ...res, id: String(res.id) } }
    }
    if (url === '/api/auth/users') return { data: [] }
    if (url.startsWith('/api/wiki/')) throw new Error('Wiki not available')
    return { data: await (window as any).mqbox?.api?.get(url, config?.params) }
  },
  async post(url, data, config) {
    if (url === '/api/upload/image' || url === '/api/upload/attachment') {
      return { data: await uploadNote((data as FormData).get('file') as File) }
    }
    if (url === '/api/upload/images/sign') {
      return { data: { urls: (data as any)?.urls || [] } }
    }
    if (url === '/api/search') {
      const res = await (window as any).mqbox?.api?.post('/plugins/notes/rag/search', {
        q: data?.query || '',
        top_k: data?.top_k || 8,
      }) || {}
      const results = (res.results || []).map((r: any) => ({
        id: String(r.note_id),
        title: r.title || '无标题',
        content: r.content || r.snippet || '',
        score: r.score || 0,
        kind: 'note',
      }))
      return { data: { results } }
    }
    if (url === '/api/editor/ai' || url === '/api/editor/ai/complete') {
      const instruction = String(data?.instruction || data?.prompt || data?.system || '')
      const source = String(data?.content || data?.text || data?.selection || data?.before || '')
      const res = await (window as any).mqbox?.api?.post('/chat', {
        message: [instruction, source].filter(Boolean).join('\n\n'),
      }) || {}
      return { data: { result: res.reply || res.content || '' } }
    }
    return { data: await (window as any).mqbox?.api?.post(url, data, config) }
  },
}

export function installDesktopEditorAdapter() {
  configureNotesEditor({
    http,
    apiBase: localStorage.getItem('serverUrl') || '',
    getToken: () => localStorage.getItem('token'),
  })
}
