import * as net from 'net'
import * as tls from 'tls'
import { EventEmitter } from 'events'

interface ImapConfig {
  host: string
  port: number
  user: string
  password: string
  tls: boolean
}

interface ImapMessage {
  uid: number
  seq: number
  flags: string[]
  date: Date
  subject: string
  from: { name: string; address: string }[]
  to: { name: string; address: string }[]
  text: string
  html: string
  attachments: { filename: string; contentType: string; size: number }[]
}

export class ImapClient extends EventEmitter {
  private config: ImapConfig
  private socket: net.Socket | tls.TLSSocket | null = null
  private tag = 0
  private buffer = ''
  private pending: Map<string, { resolve: (lines: string[]) => void; reject: (err: Error) => void }> = new Map()
  private selectedMailbox = ''
  private authenticated = false

  constructor(config: ImapConfig) {
    super()
    this.config = config
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const connectOpts = { host: this.config.host, port: this.config.port }
      this.socket = this.config.tls
        ? tls.connect(connectOpts)
        : net.connect(connectOpts)

      this.socket.setEncoding('utf-8')
      this.socket.setTimeout(30000)

      this.socket.on('connect', () => { })
      this.socket.on('data', (data: string) => this.onData(data))
      this.socket.on('timeout', () => { this.socket?.destroy(); reject(new Error('IMAP connection timeout')) })
      this.socket.on('error', (err) => reject(err))
      this.socket.on('close', () => { this.emit('close') })

      // Wait for greeting
      const onGreeting = (data: string) => {
        if (data.includes('* OK')) {
          this.socket?.removeListener('data', onGreeting)
          resolve()
        }
      }
      this.socket.on('data', onGreeting)
      setTimeout(() => reject(new Error('IMAP greeting timeout')), 10000)
    })
  }

  async login(): Promise<void> {
    const tag = this.nextTag()
    await this.sendCommand(`${tag} LOGIN "${this.escape(this.config.user)}" "${this.escape(this.config.password)}"`)
    this.authenticated = true
  }

  async listMailboxes(): Promise<string[]> {
    const tag = this.nextTag()
    const lines = await this.sendCommand(`${tag} LIST "" "*"`)
    const mailboxes: string[] = []
    for (const line of lines) {
      const m = line.match(/^\* LIST\s*\(.*?\)\s+"([^"]*)"\s+"([^"]+)"/)
      if (m) mailboxes.push(m[2])
    }
    return mailboxes
  }

  async selectMailbox(name: string): Promise<{ exists: number; recent: number; uidValidity: number; uidNext: number }> {
    const tag = this.nextTag()
    const lines = await this.sendCommand(`${tag} SELECT "${this.escape(name)}"`)
    this.selectedMailbox = name
    let exists = 0, recent = 0, uidValidity = 0, uidNext = 0
    for (const line of lines) {
      const em = line.match(/^\* (\d+) EXISTS/)
      if (em) exists = parseInt(em[1])
      const rm = line.match(/^\* (\d+) RECENT/)
      if (rm) recent = parseInt(rm[1])
      const vm = line.match(/\[UIDVALIDITY (\d+)\]/)
      if (vm) uidValidity = parseInt(vm[1])
      const nm = line.match(/\[UIDNEXT (\d+)\]/)
      if (nm) uidNext = parseInt(nm[1])
    }
    return { exists, recent, uidValidity, uidNext }
  }

  async searchEmails(criteria: string[]): Promise<number[]> {
    const tag = this.nextTag()
    const cmd = `${tag} UID SEARCH ${criteria.join(' ')}`
    const lines = await this.sendCommand(cmd)
    const uids: number[] = []
    for (const line of lines) {
      const m = line.match(/^\* SEARCH (.+)$/)
      if (m) uids.push(...m[1].split(' ').filter(Boolean).map(Number))
    }
    return uids
  }

  async fetchEmails(uids: number[]): Promise<ImapMessage[]> {
    if (uids.length === 0) return []
    const tag = this.nextTag()
    const uidStr = uids.join(',')
    const cmd = `${tag} UID FETCH ${uidStr} (FLAGS BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE TO)] BODY.PEEK[TEXT])`
    const lines = await this.sendCommand(cmd)
    return this.parseFetchResponse(lines)
  }

  private parseFetchResponse(lines: string[]): ImapMessage[] {
    const messages: ImapMessage[] = []
    let current: Partial<ImapMessage> | null = null
    let readingText = false
    let textBuffer = ''

    for (const line of lines) {
      if (line.startsWith('* ')) {
        if (current && current.uid) {
          current.text = textBuffer.trim()
          messages.push(current as ImapMessage)
        }
        current = {
          uid: 0, seq: 0, flags: [], date: new Date(),
          subject: '', from: [], to: [], text: '', html: '', attachments: []
        }
        readingText = false
        textBuffer = ''

        const fm = line.match(/^\* (\d+) FETCH/)
        if (fm) current.seq = parseInt(fm[1])

        const um = line.match(/UID (\d+)/)
        if (um) current.uid = parseInt(um[1])

        const flags = line.match(/FLAGS \(([^)]*)\)/)
        if (flags) current.flags = flags[1].split(' ').filter(Boolean)

        const subj = line.match(/SUBJECT\s+(?:\?=\?)?([^\n]*)/i)
        if (subj) current.subject = this.decodeMime(subj[1].trim())

        const from = line.match(/FROM\s+([^\n]+)/i)
        if (from) current.from = this.parseAddresses(from[1])

        const to = line.match(/TO\s+([^\n]+)/i)
        if (to) current.to = this.parseAddresses(to[1])
      } else if (readingText) {
        if (line === ')') {
          readingText = false
        } else {
          textBuffer += line + '\n'
        }
      } else if (line.includes('BODY[TEXT]')) {
        readingText = true
        textBuffer = ''
      }
    }
    if (current && current.uid) {
      current.text = textBuffer.trim()
      messages.push(current as ImapMessage)
    }
    return messages
  }

  async logout(): Promise<void> {
    if (!this.socket) return
    try {
      const tag = this.nextTag()
      await this.sendCommand(`${tag} LOGOUT`)
    } catch {}
    this.socket.destroy()
    this.socket = null
    this.authenticated = false
  }

  private nextTag(): string {
    return `A${String(++this.tag).padStart(3, '0')}`
  }

  private sendCommand(cmd: string): Promise<string[]> {
    return new Promise((resolve, reject) => {
      const tag = cmd.split(' ')[0]
      this.pending.set(tag, { resolve, reject })
      this.socket?.write(cmd + '\r\n')
    })
  }

  private onData(data: string) {
    this.buffer += data
    const lines = this.buffer.split('\r\n')
    this.buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.trim()) continue
      const tag = line.split(' ')[0]
      const pending = this.pending.get(tag)
      if (pending) {
        // Collect all lines for this tagged response
        const allLines = [line]
        pending.resolve(allLines)
        this.pending.delete(tag)
      }
    }
  }

  private escape(s: string): string {
    return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  }

  private decodeMime(s: string): string {
    return s.replace(/=\?([^?]+)\?([BQ])\?([^?]*)\?=/g, (_, charset, encoding, text) => {
      try {
        if (encoding === 'B') {
          const buf = Buffer.from(text, 'base64')
          return buf.toString(charset as BufferEncoding)
        } else if (encoding === 'Q') {
          const buf = Buffer.from(text.replace(/_/g, ' '), 'base64')
          return buf.toString(charset as BufferEncoding)
        }
      } catch {}
      return text
    })
  }

  private parseAddresses(s: string): { name: string; address: string }[] {
    const results: { name: string; address: string }[] = []
    const re = /(?:(\S+)\s+)?<([^>]+)>/g
    let m
    while ((m = re.exec(s)) !== null) {
      results.push({ name: (m[1] || '').replace(/^"+|"+$/g, ''), address: m[2] })
    }
    if (results.length === 0 && s.includes('@')) {
      const clean = s.replace(/^["(]+|[")\s]+$/g, '')
      results.push({ name: '', address: clean })
    }
    return results
  }
}
