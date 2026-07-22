import Panel from './Panel.vue'
import Page from './Page.vue'

let pluginCtx: any = null
let deviceId: string | null = null

async function getDeviceId(context: any): Promise<string> {
  if (deviceId) return deviceId
  let id = await context.storage?.get('deviceId')
  if (!id) {
    id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    await context.storage?.set('deviceId', id)
  }
  deviceId = id
  return id
}

function getState() {
  return { hosting: false }
}

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    pluginCtx = context
    await getDeviceId(context)
    context.registerCommand('getPanelData', async () => getState())
    context.registerCommand('getPageData', async () => getState())
    context.registerCommand('open', async () => { context.openPage('remote') })
    context.registerCommand('getDeviceId', async () => deviceId)
  },
  deactivate() {},
}
