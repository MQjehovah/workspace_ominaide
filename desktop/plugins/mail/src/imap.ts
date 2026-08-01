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
  _contentType?: string
}
export class ImapClient extends EventEmitter {
  private config: ImapConfig
  private socket: net.Socket | tls.TLSSocket | null = null
  private tag = 0
  private buffer = ''
  private pending: Map<string, { resolve: (lines: string[]) => void; reject: (err: Error) => void }> = new Map()
  private selectedMailbox = ''
  private authenticated = false
  private responseLines: string[] = []
  private literalRemaining = 0

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

  async setSeen(uids: number[]): Promise<void> {
    if (uids.length === 0) return
    const tag = this.nextTag()
    const uidStr = uids.join(',')
    await this.sendCommand(`${tag} UID STORE ${uidStr} +FLAGS.SILENT (\\Seen)`)
  }

  async fetchEmails(uids: number[]): Promise<ImapMessage[]> {
    if (uids.length === 0) return []
    const tag = this.nextTag()
    const uidStr = uids.join(',')
    const cmd = `${tag} UID FETCH ${uidStr} (FLAGS BODY.PEEK[HEADER] BODY.PEEK[TEXT])`
    const lines = await this.sendCommand(cmd)
    return this.parseFetchResponse(lines)
  }

  private parseFetchResponse(lines: string[]): ImapMessage[] {
    const messages: ImapMessage[] = []
    let current: Partial<ImapMessage> | null = null
    let section = ''
    let headerLines: string[] = []
    let textBuffer = ''

    for (const line of lines) {
      if (line.startsWith('* ')) {
        if (current && current.uid) {
          this.applyHeaders(headerLines, current)
          current.text = this.extractText(textBuffer.trim(), current._contentType)
          messages.push(current as ImapMessage)
        }
        current = { uid: 0, seq: 0, flags: [], date: new Date(), subject: '', from: [], to: [], text: '', html: '', attachments: [] }
        section = ''
        headerLines = []
        textBuffer = ''

        const fm = line.match(/^\* (\d+) FETCH/)
        if (fm) current.seq = parseInt(fm[1])
        const um = line.match(/UID (\d+)/)
        if (um) current.uid = parseInt(um[1])
        const flags = line.match(/FLAGS \(([^)]*)\)/)
        if (flags) current.flags = flags[1].split(' ').filter(Boolean)

        if (/BODY\[HEADER/i.test(line)) section = 'header'
      } else if (line === ')') {
        if (current && current.uid) {
          this.applyHeaders(headerLines, current)
          current.text = this.extractText(textBuffer.trim(), current._contentType)
          messages.push(current as ImapMessage)
        }
        current = null; section = ''; headerLines = []; textBuffer = ''
      } else if (section === 'header') {
        if (/BODY\[TEXT\]/i.test(line)) { section = 'text'; textBuffer = '' }
        else headerLines.push(line)
      } else if (section === 'text') {
        textBuffer += line + '\n'
      }
    }
    if (current && current.uid) {
      this.applyHeaders(headerLines, current)
      current.text = this.extractText(textBuffer.trim(), current._contentType)
      messages.push(current as ImapMessage)
    }
    return messages
  }

  private applyHeaders(lines: string[], msg: Partial<ImapMessage>): void {
    let subject = '', from = '', date = '', to = ''
    for (const line of lines) {
      const lower = line.toLowerCase()
      // Folded/continuation header lines (start with space/tab) belong to the
      // previous header — e.g. "Content-Type: multipart/..." + "\tboundary=..."
      if (/^[ \t]/.test(line)) {
        if (msg._contentType && !lower.startsWith('content-type:')) {
          msg._contentType += ' ' + line.trim()
        }
        continue
      }
      if (lower.startsWith('subject:')) subject = line.slice(8).trim()
      else if (lower.startsWith('from:')) from = line.slice(5).trim()
      else if (lower.startsWith('date:')) date = line.slice(5).trim()
      else if (lower.startsWith('to:')) to = line.slice(3).trim()
      else if (lower.startsWith('content-type:')) msg._contentType = line.slice(13).trim()
    }
    msg.subject = this.decodeMime(subject)
    if (date) msg.date = new Date(date)
    if (from) msg.from = this.parseAddresses(from)
    if (to) msg.to = this.parseAddresses(to)
  }

  private extractText(raw: string, contentType?: string): string {
    let text = (raw || '').replace(/\r\n/g, '\n')
    const topCt = (contentType || '').toLowerCase()
    const boundary = contentType?.match(/boundary="?([^";]+)"?/i)?.[1] || text.match(/^\s*--([^\s]+)/)?.[1]

    const parts: { ct: string; cte: string; charset: string; body: string }[] = []
    if (boundary) {
      parts.push(...this.parseMultipart(boundary, text))
    } else {
      const first = text.indexOf('\n\n')
      if (first !== -1) {
        const headers = this.parseHeaders(text.slice(0, first))
        parts.push(...this.parseMime(headers, text.slice(first + 2)))
      } else {
        parts.push({ ct: topCt || 'text/plain', cte: '', charset: this.getCharset(topCt), body: text })
      }
    }

    let plain: string | null = null
    let html: string | null = null
    for (const p of parts) {
      let content = p.body
      const cte = (p.cte || '').toLowerCase()
      let isBytes = false
      if (cte.includes('base64')) {
        try {
          content = Buffer.from(content.replace(/\s+/g, ''), 'base64').toString('latin1')
          isBytes = true
        } catch {
          content = ''
        }
      } else if (cte) {
        content = this.decodeQuotedPrintable(content)
        isBytes = true
      }
      const decoded = isBytes ? this.decodeCharset(Buffer.from(content, 'latin1'), p.charset) : content
      if (!decoded) continue
      if (p.ct.includes('text/plain') && plain === null) plain = decoded
      else if (p.ct.includes('text/html') && html === null) html = decoded
    }
    if (plain !== null) return this.cleanText(plain)
    if (html !== null) return this.stripHtml(html)
    // Fallback: whole body as text
    return this.cleanText(this.decodeCharset(Buffer.from(this.decodeQuotedPrintable(text), 'latin1'), 'utf-8'))
  }

  /** Split a multipart body by boundary into leaf parts (recursively). */
  private parseMultipart(boundary: string, body: string) {
    const segs = body.split('--' + boundary)
    const results: { ct: string; cte: string; charset: string; body: string }[] = []
    for (const seg of segs) {
      const t = seg.replace(/^\n+/, '').replace(/\n?--\s*$/, '')
      if (!t.trim()) continue
      const nidx = t.indexOf('\n\n')
      if (nidx === -1) continue
      const ph = this.parseHeaders(t.slice(0, nidx))
      const pb = t.slice(nidx + 2)
      // A segment with no headers at all is the multipart preamble (e.g.
      // "This is a multi-part message in MIME format.") — not a real part.
      if (Object.keys(ph).length === 0 && !pb.trim()) continue
      results.push(...this.parseMime(ph, pb))
    }
    return results
  }

  /** Handle a single MIME part; recurse if it is itself multipart. */
  private parseMime(
    headers: Record<string, string>,
    body: string,
  ): { ct: string; cte: string; charset: string; body: string }[] {
    const ct = (headers['content-type'] || 'text/plain').toLowerCase()
    const cte = headers['content-transfer-encoding'] || ''
    const charset = this.getCharset(headers['content-type'] || '')
    const boundary = ct.match(/boundary="?([^";]+)"?/i)?.[1]
    if (boundary) return this.parseMultipart(boundary, body)
    return [{ ct, cte, charset, body }]
  }

  private parseHeaders(block: string): Record<string, string> {
    const headers: Record<string, string> = {}
    let current = ''
    for (const line of block.split('\n')) {
      if (/^[ \t]/.test(line) && current) {
        headers[current] += ' ' + line.trim()
        continue
      }
      const idx = line.indexOf(':')
      if (idx === -1) continue
      current = line.slice(0, idx).trim().toLowerCase()
      headers[current] = line.slice(idx + 1).trim()
    }
    return headers
  }

  private getCharset(ct: string): string {
    return (ct.match(/charset="?([^";]+)"?/i)?.[1] || '').replace(/["']/g, '').trim()
  }

  private decodeQuotedPrintable(s: string): string {
    // Remove soft line breaks (=\n) first so =XX runs survive
    return s.replace(/=\r?\n/g, '').replace(/=([0-9A-F]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))
  }

  private decodeCharset(buf: Buffer, charset: string): string {
    const cs = (charset || 'utf-8').toLowerCase()
    if (!cs || cs === 'utf-8' || cs === 'utf8') return buf.toString('utf-8')
    if (cs === 'us-ascii' || cs === 'ascii' || cs === 'iso-8859-1' || cs === 'latin1') {
      return buf.toString('latin1')
    }
    try {
      return new TextDecoder(cs).decode(buf)
    } catch {
      return buf.toString('utf-8')
    }
  }

  private stripHtml(html: string): string {
    return this.cleanText(
      html
        .replace(/<style[\s\S]*?<\/style>/gi, '')
        .replace(/<script[\s\S]*?<\/script>/gi, '')
        .replace(/<br\s*\/?\s*>/gi, '\n')
        .replace(/<\/(p|div|tr|li|h\d|table|blockquote)>/gi, '\n')
        .replace(/<[^>]+>/g, ''),
    )
  }

  private cleanText(t: string): string {
    return t
      .replace(/&nbsp;/g, ' ')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
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
    this._processBuffer()
  }

  /**
   * Process the accumulated buffer, honoring IMAP literals ({NNN}).
   * Literal content is consumed byte-exactly (not line-split at stream level)
   * and blank lines are preserved so MIME structure survives.
   */
  private _processBuffer() {
    while (true) {
      if (this.literalRemaining > 0) {
        if (this.buffer.length < this.literalRemaining) return
        const lit = this.buffer.slice(0, this.literalRemaining)
        this.buffer = this.buffer.slice(this.literalRemaining)
        this.literalRemaining = 0
        // Literal content may contain \r\n; split into lines, preserving blank
        // lines so MIME header/body separators survive.
        for (const part of lit.split('\r\n')) {
          if (part === '') this.responseLines.push('')
          else this._handleLine(part)
        }
        continue
      }
      const nl = this.buffer.indexOf('\r\n')
      if (nl === -1) return
      const line = this.buffer.slice(0, nl)
      this.buffer = this.buffer.slice(nl + 2)
      const litMatch = line.match(/\{(\d+)\}\s*$/)
      if (litMatch) {
        this.literalRemaining = parseInt(litMatch[1])
        const head = line.replace(/\{(\d+)\}\s*$/, '')
        if (head.trim()) this._handleLine(head)
      } else {
        this._handleLine(line)
      }
    }
  }

  private _handleLine(line: string) {
    if (line === '') return
    this.responseLines.push(line)
    const firstWord = line.split(' ')[0]
    const pending = this.pending.get(firstWord)
    if (pending) {
      pending.resolve(this.responseLines.slice())
      this.pending.delete(firstWord)
      this.responseLines = []
    }
  }

  private escape(s: string): string {
    return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  }

  private decodeMime(s: string): string {
    return s.replace(/=\?([^?]+)\?([BQ])\?([^?]*)\?=/g, (_, charset, encoding, text) => {
      try {
        if (encoding === 'B') {
          return this.decodeCharset(Buffer.from(text, 'base64'), charset)
        } else if (encoding === 'Q') {
          const q = text.replace(/_/g, ' ').replace(/=([0-9A-F]{2})/g, (m, h) => String.fromCharCode(parseInt(h, 16)))
          return this.decodeCharset(Buffer.from(q, 'latin1'), charset)
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
