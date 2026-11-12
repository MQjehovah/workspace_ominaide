/** Persistent chat sessions for CLI agents that do not expose a native
 * session API (Codex / Claude / Omniaide). OpenCode uses its own store. */

export interface AgentMessage {
  role: 'user' | 'assistant'
  text: string
  ts: number
  error?: boolean
}

export interface StoredAgentSession {
  id: string
  agent: string
  project: string
  title: string
  messages: AgentMessage[]
  streaming: string
  running: boolean
  createdAt: number
  updatedAt: number
}

const STORAGE_KEY = 'agent_sessions_v1'
const MAX_MESSAGES = 120
const MAX_SESSIONS = 120

export function createAgentSessionStore(storage: any) {
  let sessions: Record<string, StoredAgentSession> = {}
  let ready: Promise<void> | null = null
  let lastPersist = 0

  async function load(): Promise<void> {
    try {
      const raw = await storage.get(STORAGE_KEY)
      if (raw && typeof raw === 'object') {
        sessions = raw as Record<string, StoredAgentSession>
      }
    } catch {
      sessions = {}
    }
  }

  async function ensure(): Promise<void> {
    if (!ready) ready = load()
    await ready
  }

  async function persist(force = false): Promise<void> {
    const now = Date.now()
    if (!force && now - lastPersist < 700) return
    lastPersist = now
    try {
      await storage.set(STORAGE_KEY, sessions)
    } catch {
      // Storage is best effort.
    }
  }

  function trim(): void {
    const all = Object.values(sessions).sort((a, b) => b.updatedAt - a.updatedAt)
    if (all.length <= MAX_SESSIONS) return
    for (const session of all.slice(MAX_SESSIONS)) {
      delete sessions[session.id]
    }
  }

  return {
    async list(agent?: string, project?: string): Promise<StoredAgentSession[]> {
      await ensure()
      return Object.values(sessions)
        .filter((s) => (!agent || s.agent === agent) && (!project || s.project === project))
        .sort((a, b) => b.updatedAt - a.updatedAt)
    },

    async get(id: string): Promise<StoredAgentSession | null> {
      await ensure()
      return sessions[id] || null
    },

    async create(agent: string, project: string, title: string): Promise<StoredAgentSession> {
      await ensure()
      const now = Date.now()
      const id = `cs_${now.toString(36)}_${Math.random().toString(36).slice(2, 8)}`
      const session: StoredAgentSession = {
        id,
        agent,
        project,
        title: (title || '').trim() || '新会话',
        messages: [],
        streaming: '',
        running: false,
        createdAt: now,
        updatedAt: now,
      }
      sessions[id] = session
      trim()
      await persist(true)
      return session
    },

    async remove(id: string): Promise<boolean> {
      await ensure()
      if (!sessions[id]) return false
      delete sessions[id]
      await persist(true)
      return true
    },

    async appendMessage(id: string, message: AgentMessage): Promise<void> {
      await ensure()
      const session = sessions[id]
      if (!session) return
      session.messages.push(message)
      if (session.messages.length > MAX_MESSAGES) {
        session.messages = session.messages.slice(-MAX_MESSAGES)
      }
      session.updatedAt = Date.now()
      await persist(true)
    },

    async setRunning(id: string, running: boolean): Promise<void> {
      await ensure()
      const session = sessions[id]
      if (!session) return
      session.running = running
      if (!running) session.streaming = ''
      session.updatedAt = Date.now()
      await persist(true)
    },

    async setStreaming(id: string, text: string): Promise<void> {
      await ensure()
      const session = sessions[id]
      if (!session) return
      session.streaming = text.slice(-40_000)
      session.updatedAt = Date.now()
      await persist()
    },

    async finishRun(id: string, text: string, error?: string): Promise<void> {
      await ensure()
      const session = sessions[id]
      if (!session) return
      const body = (text || '').trim()
      if (body) {
        session.messages.push({
          role: 'assistant',
          text: body,
          ts: Date.now(),
          error: Boolean(error),
        })
        if (session.messages.length > MAX_MESSAGES) {
          session.messages = session.messages.slice(-MAX_MESSAGES)
        }
      } else if (error) {
        session.messages.push({
          role: 'assistant',
          text: error,
          ts: Date.now(),
          error: true,
        })
      }
      session.streaming = ''
      session.running = false
      session.updatedAt = Date.now()
      await persist(true)
    },

    async rename(id: string, title: string): Promise<void> {
      await ensure()
      const session = sessions[id]
      if (!session) return
      session.title = title.trim() || session.title
      await persist(true)
    },
  }
}

export type AgentSessionStore = ReturnType<typeof createAgentSessionStore>
