import Panel from './Panel.vue'
import Page from './Page.vue'
import { ImapClient } from './imap'

interface MailAccount {
  id: string | number
  name: string
  email: string
  imapHost: string
  imapPort: number
  imapTls: boolean
  smtpHost: string
  smtpPort: number
  smtpTls: boolean
  username: string
  password: string
}

interface EmailSummary {
  uid: number
  accountId: string | number
  subject: string
  from: string
  date: string
  flags: string[]
  preview: string
  text: string
}

const accountsKey = 'mail_accounts'
let pluginCtx: any = null

async function getAccounts(): Promise<MailAccount[]> {
  // Prefer backend accounts, fall back to local storage.
  try {
    const data = await pluginCtx?.api?.get('/plugins/mail/accounts')
    const list = Array.isArray(data) ? data : data?.accounts
    if (list && list.length) return list.map(mapResponseToAccount)
  } catch { /* ignore */ }
  return (await pluginCtx?.storage?.get(accountsKey)) || []
}

// In-memory email cache per account (key=accountId, value={emails, time})
const emailCache = new Map<string | number, { emails: EmailSummary[]; time: number }>()
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

function cacheKey(id: string | number) {
  return `mail_cache_v3_${id}`
}

async function readStorageCache(id: string | number): Promise<{ emails: EmailSummary[]; time: number } | null> {
  try {
    return (await pluginCtx?.storage?.get(cacheKey(id))) || null
  } catch {
    return null
  }
}

async function writeStorageCache(id: string | number, entry: { emails: EmailSummary[]; time: number }) {
  try {
    await pluginCtx?.storage?.set(cacheKey(id), entry)
  } catch { /* ignore */ }
}

async function getCachedOrFetch(acc: MailAccount, force = false): Promise<EmailSummary[]> {
  const now = Date.now()
  if (!force) {
    const mem = emailCache.get(acc.id)
    if (mem && now - mem.time < CACHE_TTL) return mem.emails
    const stored = await readStorageCache(acc.id)
    if (stored && now - stored.time < CACHE_TTL) {
      emailCache.set(acc.id, stored)
      return stored.emails
    }
  }
  const emails = await fetchInbox(acc)
  const entry = { emails, time: now }
  emailCache.set(acc.id, entry)
  await writeStorageCache(acc.id, entry)
  return emails
}

function createImapClient(acc: MailAccount) {
  return new ImapClient({
    host: acc.imapHost,
    port: acc.imapPort,
    user: acc.username,
    password: acc.password,
    tls: acc.imapTls,
  })
}

// ---- New-email detection & cloud reporting ----

async function reportNewEmails(acc: MailAccount, emails: EmailSummary[]) {
  const seenKey = `mail_seen_${acc.id}`
  let seen: number[] = []
  try {
    seen = (await pluginCtx?.storage?.get(seenKey)) || []
  } catch { /* ignore */ }
  const seenSet = new Set(seen)
  let changed = false
  for (const email of emails) {
    if (seenSet.has(email.uid)) continue
    seenSet.add(email.uid)
    changed = true
    // Report every new email to the cloud; the LLM decides importance there.
    try {
      await pluginCtx?.api?.post('/plugins/mail/events', {
        account_id: String(acc.id),
        uid: email.uid,
        subject: email.subject,
        from_address: email.from,
        date: email.date,
        preview: email.preview,
        content: email.text,
      })
    } catch (e: any) {
      console.error('[mail] report to cloud failed:', e?.message || e)
    }
  }
  if (changed) {
    try {
      await pluginCtx?.storage?.set(seenKey, Array.from(seenSet).slice(-500))
    } catch { /* ignore */ }
  }
}

async function refreshAndReport() {
  const accounts = await getAccounts()
  for (const acc of accounts) {
    try {
      const emails = await getCachedOrFetch(acc, true)
      await reportNewEmails(acc, emails)
    } catch (e: any) {
      console.error('[mail] refresh error:', e?.message || e)
    }
  }
  // The cloud LLM reviews all events periodically and pushes important-item
  // notifications via WebSocket; the host shows them as system notifications.
  try {
    await pluginCtx?.signal?.('panel:updated')
  } catch { /* ignore */ }
}

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    pluginCtx = context

    context.registerCommand('getPanelData', async () => {
      const accounts = await getAccounts()
      const allEmails: EmailSummary[] = []
      for (const acc of accounts) {
        const emails = await getCachedOrFetch(acc)
        allEmails.push(...emails.slice(0, 5).map(e => ({ ...e, accountId: acc.id })))
      }
      allEmails.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
      return {
        title: '邮件',
        subtitle: `${accounts.length} 个邮箱 · ${allEmails.length} 封最新`,
        items: allEmails.slice(0, 5).map(e => ({
          title: e.subject || '(无主题)',
          subtitle: `${e.from} · ${formatTime(e.date)}`,
          action: 'openPage',
        })),
      }
    })

    context.registerCommand('getPageData', async () => {
      const accounts = await getAccounts()
      return { accounts }
    })

    context.registerCommand('listAccounts', async () => {
      try {
        const data = await context.api?.get('/plugins/mail/accounts')
        if (data) return data
      } catch {}
      return (await context.storage?.get(accountsKey)) || []
    })

    context.registerCommand('addAccount', async (args: any) => {
      const payload = {
        name: args.name || '',
        email: args.email || '',
        imap_host: args.imapHost || '',
        imap_port: args.imapPort || 993,
        imap_tls: args.imapTls !== false,
        smtp_host: args.smtpHost || '',
        smtp_port: args.smtpPort || 465,
        smtp_tls: args.smtpTls !== false,
        username: args.username || args.email || '',
        password: args.password || '',
      }
      try {
        const acc = await context.api?.post('/plugins/mail/accounts', payload)
        if (acc) return { success: true, account: mapResponseToAccount(acc) }
      } catch {}
      // offline fallback
      const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
      const acc: MailAccount = {
        id: Date.now().toString(36),
        ...args,
        username: args.username || args.email || '',
      }
      accounts.push(acc)
      await context.storage?.set(accountsKey, accounts)
      return { success: true, account: acc }
    })

    context.registerCommand('removeAccount', async (args: any) => {
      try {
        await context.api?.delete(`/plugins/mail/accounts/${args?.id}`)
        return { success: true }
      } catch {}
      let accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
      accounts = accounts.filter(a => a.id !== args?.id)
      await context.storage?.set(accountsKey, accounts)
      return { success: true }
    })

    context.registerCommand('updateAccount', async (args: any) => {
      const payload: any = {}
      if (args.name !== undefined) payload.name = args.name
      if (args.email !== undefined) payload.email = args.email
      if (args.imapHost !== undefined) payload.imap_host = args.imapHost
      if (args.imapPort !== undefined) payload.imap_port = args.imapPort
      if (args.imapTls !== undefined) payload.imap_tls = args.imapTls
      if (args.smtpHost !== undefined) payload.smtp_host = args.smtpHost
      if (args.smtpPort !== undefined) payload.smtp_port = args.smtpPort
      if (args.smtpTls !== undefined) payload.smtp_tls = args.smtpTls
      if (args.username !== undefined) payload.username = args.username
      if (args.password !== undefined) payload.password = args.password
      try {
        const acc = await context.api?.put(`/plugins/mail/accounts/${args?.id}`, payload)
        if (acc) {
          emailCache.delete(args.id)
          return { success: true, account: mapResponseToAccount(acc) }
        }
      } catch {}
      const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
      const idx = accounts.findIndex(a => a.id === args?.id)
      if (idx === -1) return { success: false, error: 'Account not found' }
      accounts[idx] = { ...accounts[idx], ...args }
      await context.storage?.set(accountsKey, accounts)
      emailCache.delete(args.id)
      return { success: true, account: accounts[idx] }
    })

    context.registerCommand('fetchEmails', async (args: any) => {
      const accounts = await getAccounts()
      const acc = accounts.find(a => a.id === args?.accountId || a.id === Number(args?.accountId))
      if (!acc) return { success: false, error: 'Account not found' }
      const emails = await getCachedOrFetch(acc, !!args?.force)
      return { success: true, emails: emails.slice(0, 50) }
    })

    context.registerCommand('preloadEmails', async () => {
      const accounts = await getAccounts()
      const results: Record<string, number> = {}
      for (const acc of accounts) {
        try {
          const emails = await getCachedOrFetch(acc)
          results[String(acc.id)] = emails.length
        } catch { /* ignore */ }
      }
      return { success: true, counts: results }
    })

    context.registerCommand('markEmailRead', async (args: any) => {
      const accounts = await getAccounts()
      const acc = accounts.find(a => a.id === args?.accountId || a.id === Number(args?.accountId))
      if (!acc || !args?.uid) return { success: false, error: 'Account not found' }
      try {
        const client = createImapClient(acc)
        await client.connect()
        await client.login()
        await client.selectMailbox('INBOX')
        await client.setSeen([args.uid])
        await client.logout()
        // Update local flags so the UI reflects read state immediately.
        const cached = emailCache.get(acc.id) || (await readStorageCache(acc.id))
        if (cached) {
          const emails = cached.emails.map(e =>
            e.uid === args.uid && !e.flags?.includes('\\Seen')
              ? { ...e, flags: [...(e.flags || []), '\\Seen'] }
              : e,
          )
          const entry = { emails, time: cached.time }
          emailCache.set(acc.id, entry)
          await writeStorageCache(acc.id, entry)
        }
        return { success: true }
      } catch (e: any) {
        return { success: false, error: e?.message || 'Failed to mark read' }
      }
    })

    context.registerCommand('sendEmail', async (args: any) => {
      try {
        const { createTransport } = require('nodemailer')
        const accounts = await getAccounts()
        const acc = accounts.find(a => a.id === args?.accountId || a.id === Number(args?.accountId))
        if (!acc) return { success: false, error: 'Account not found' }

        const transporter = createTransport({
          host: acc.smtpHost,
          port: acc.smtpPort,
          secure: acc.smtpTls,
          auth: { user: acc.username, pass: acc.password },
        })

        await transporter.sendMail({
          from: `"${acc.name}" <${acc.email}>`,
          to: args.to,
          subject: args.subject || '',
          text: args.text || '',
          html: args.html || '',
        })

        return { success: true }
      } catch (e: any) {
        return { success: false, error: e.message }
      }
    })

    // Periodic refresh: detect new mail, report to cloud, notify for important items.
    const REFRESH_INTERVAL = 5 * 60 * 1000
    refreshTimer = setInterval(() => {
      refreshAndReport().catch(() => {})
    }, REFRESH_INTERVAL)
    // Initial background check (skip if accounts not configured yet)
    setTimeout(() => {
      refreshAndReport().catch(() => {})
    }, 15000)
  },
  deactivate() {
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  },
}

let refreshTimer: any = null

async function fetchInbox(acc: MailAccount): Promise<EmailSummary[]> {
  try {
    const client = createImapClient(acc)

    await client.connect()
    await client.login()
    await client.selectMailbox('INBOX')
    const uids = await client.searchEmails(['ALL'])
    const recent = uids.slice(-20)
    const messages = await client.fetchEmails(recent)
    await client.logout()

    return messages.map(msg => {
      const text = msg.text || ''
      return {
        uid: msg.uid,
        accountId: acc.id,
        subject: msg.subject || '(无主题)',
        from: msg.from?.[0]?.address || '',
        date: msg.date.toISOString(),
        flags: msg.flags,
        preview: text.slice(0, 200),
        text,
      }
    })
  } catch (e) {
    console.error(`[mail] fetch inbox failed for ${acc.email}:`, e)
    return []
  }
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function mapResponseToAccount(r: any): MailAccount {
  return {
    id: r.id,
    name: r.name || '',
    email: r.email,
    imapHost: r.imap_host,
    imapPort: r.imap_port,
    imapTls: r.imap_tls,
    smtpHost: r.smtp_host,
    smtpPort: r.smtp_port,
    smtpTls: r.smtp_tls,
    username: r.username,
    password: r.password || '',
  }
}
