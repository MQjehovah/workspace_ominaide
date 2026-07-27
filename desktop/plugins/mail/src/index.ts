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
}

const accountsKey = 'mail_accounts'
let pluginCtx: any = null

// In-memory email cache per account (key=accountId, value={emails, time})
const emailCache = new Map<string | number, { emails: EmailSummary[]; time: number }>()
const CACHE_TTL = 60000 // 60 seconds

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    pluginCtx = context

    context.registerCommand('getPanelData', async () => {
      const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
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
      const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
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
      const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
      const acc = accounts.find(a => a.id === args?.accountId)
      if (!acc) return { success: false, error: 'Account not found' }
      const emails = await getCachedOrFetch(acc, true)
      return { success: true, emails: emails.slice(0, 50) }
    })

    context.registerCommand('sendEmail', async (args: any) => {
      try {
        const { createTransport } = require('nodemailer')
        const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
        const acc = accounts.find(a => a.id === args?.accountId)
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
  },
  deactivate() {},
}

async function getCachedOrFetch(acc: MailAccount, force = false): Promise<EmailSummary[]> {
  const cached = emailCache.get(acc.id)
  const now = Date.now()
  if (!force && cached && now - cached.time < CACHE_TTL) {
    return cached.emails
  }
  const emails = await fetchInbox(acc)
  emailCache.set(acc.id, { emails, time: now })
  return emails
}

async function fetchInbox(acc: MailAccount): Promise<EmailSummary[]> {
  try {
    const client = new ImapClient({
      host: acc.imapHost,
      port: acc.imapPort,
      user: acc.username,
      password: acc.password,
      tls: acc.imapTls,
    })

    await client.connect()
    await client.login()
    await client.selectMailbox('INBOX')
    const uids = await client.searchEmails(['ALL'])
    const recent = uids.slice(-20)
    const messages = await client.fetchEmails(recent)
    await client.logout()

    return messages.map(msg => ({
      uid: msg.uid,
      accountId: acc.id,
      subject: msg.subject || '(无主题)',
      from: msg.from?.[0]?.address || '',
      date: msg.date.toISOString(),
      flags: msg.flags,
      preview: (msg.text || '').slice(0, 200),
    }))
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
