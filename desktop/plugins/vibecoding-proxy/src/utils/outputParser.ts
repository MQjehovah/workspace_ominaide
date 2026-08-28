export interface ParsedEvent {
  kind: 'tool' | 'file'
  name?: string
  detail?: string
  path?: string
  action?: 'created' | 'modified' | 'read' | 'deleted'
}

const MAX_SEEN = 500

export class OutputParser {
  private lineBuf = ''
  private seen = new Set<string>()

  feed(chunk: string): ParsedEvent[] {
    this.lineBuf += chunk
    const events: ParsedEvent[] = []
    let idx: number
    while ((idx = this.lineBuf.indexOf('\n')) !== -1) {
      const line = this.lineBuf.slice(0, idx).replace(/\r$/, '')
      this.lineBuf = this.lineBuf.slice(idx + 1)
      this.parseLine(line, events)
    }
    return events
  }

  flush(): ParsedEvent[] {
    const events: ParsedEvent[] = []
    if (this.lineBuf) {
      this.parseLine(this.lineBuf, events)
      this.lineBuf = ''
    }
    return events
  }

  private emit(events: ParsedEvent[], ev: ParsedEvent) {
    const key = `${ev.kind}|${ev.name || ''}|${ev.path || ''}|${ev.action || ''}`
    if (this.seen.has(key)) return
    if (this.seen.size >= MAX_SEEN) this.seen.clear()
    this.seen.add(key)
    events.push(ev)
  }

  private parseLine(line: string, events: ParsedEvent[]) {
    const s = line.trim()
    if (!s || s.length > 400) return

    const bullet = s.match(/^[⏺●▶•]\s*(Read|Write|Edit|Update|MultiEdit|Bash|Grep|Glob|Task|WebFetch|WebSearch|NotebookEdit)\s*\((.+)\)\s*$/)
    if (bullet) {
      const verb = bullet[1]
      const arg = bullet[2].trim()
      if (verb === 'Read' || verb === 'Grep' || verb === 'Glob') {
        this.emit(events, { kind: 'file', path: this.firstPath(arg), action: 'read' })
      } else if (verb === 'Write' || verb === 'Edit' || verb === 'Update' || verb === 'MultiEdit' || verb === 'NotebookEdit') {
        this.emit(events, { kind: 'file', path: this.firstPath(arg), action: verb === 'Write' ? 'created' : 'modified' })
      } else {
        this.emit(events, { kind: 'tool', name: verb.toLowerCase(), detail: arg.slice(0, 200) })
      }
      return
    }

    const patch = s.match(/^\*\*\*\s+(Add|Update|Delete)\s+File:\s*(.+)$/)
    if (patch) {
      const action = patch[1] === 'Add' ? 'created' : patch[1] === 'Delete' ? 'deleted' : 'modified'
      this.emit(events, { kind: 'file', path: patch[2].trim(), action })
      return
    }

    const exec = s.match(/^(?:exec|\$)\s+(.{2,200})$/)
    if (exec) {
      this.emit(events, { kind: 'tool', name: 'bash', detail: exec[1].trim().slice(0, 200) })
      return
    }

    const generic = s.match(/\b(created?|wrote|written|edited?|updated?|modified|deleted?|removed?|reading?)\b[^:]{0,60}?((?:[A-Za-z]:)?[\w\-./\\]+\.[A-Za-z0-9]{1,8})\s*$/i)
    if (generic) {
      const verb = generic[1].toLowerCase()
      const action = /creat|writ/.test(verb) ? 'created' : /delet|remov/.test(verb) ? 'deleted' : /read/.test(verb) ? 'read' : 'modified'
      this.emit(events, { kind: 'file', path: generic[2], action })
    }
  }

  private firstPath(arg: string): string {
    const m = arg.match(/(?:[A-Za-z]:)?[\w\-./\\]+\.[A-Za-z0-9]{1,8}/)
    return m ? m[0] : arg.slice(0, 200)
  }
}
