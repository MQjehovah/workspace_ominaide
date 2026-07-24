import Panel from './Panel.vue'
import Page from './Page.vue'
import { ImapClient } from './imap'

interface MailAccount {
  id: string
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
  accountId: string
  subject: string
  from: string
  date: string
  flags: string[]
  preview: string
}

const accountsKey = 'mail_accounts'
let pluginCtx: any = null

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    pluginCtx = context

    context.registerCommand('getPanelData', async () => {
      const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
      const allEmails: EmailSummary[] = []

      for (const acc of accounts) {
        const emails = await fetchInbox(acc)
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
      return (await context.storage?.get(accountsKey)) || []
    })

    context.registerCommand('addAccount', async (args: any) => {
      const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
      const acc: MailAccount = {
        id: Date.now().toString(36),
        name: args.name || '',
        email: args.email || '',
        imapHost: args.imapHost || '',
        imapPort: args.imapPort || 993,
        imapTls: args.imapTls !== false,
        smtpHost: args.smtpHost || '',
        smtpPort: args.smtpPort || 465,
        smtpTls: args.smtpTls !== false,
        username: args.username || args.email || '',
        password: args.password || '',
      }
      accounts.push(acc)
      await context.storage?.set(accountsKey, accounts)
      return { success: true, account: acc }
    })

    context.registerCommand('removeAccount', async (args: any) => {
      let accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
      accounts = accounts.filter(a => a.id !== args?.id)
      await context.storage?.set(accountsKey, accounts)
      return { success: true }
    })

    context.registerCommand('fetchEmails', async (args: any) => {
      const accounts: MailAccount[] = (await context.storage?.get(accountsKey)) || []
      const acc = accounts.find(a => a.id === args?.accountId)
      if (!acc) return { success: false, error: 'Account not found' }
      const emails = await fetchInbox(acc)
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
