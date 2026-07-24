import Panel from './Panel.vue'
import Page from './Page.vue'

let pluginCtx: any = null
let deviceId: string | null = null
let hostState: any = { enabled: false, code: '', password: '', status: '', peerConnected: false, autoAccept: false }
let codeTimer: any = null
let heartbeatTimer: any = null
let reconnectTimer: any = null
let currentViewerId = ''

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

async function persistState() {
  try { await pluginCtx?.storage?.set('hostState', { enabled: hostState.enabled, code: hostState.code, status: hostState.status, autoAccept: hostState.autoAccept }) } catch {}
}

function getState() {
  return { hosting: hostState.enabled, hostState }
}

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    pluginCtx = context
    context.log('info', 'activate')
    await getDeviceId(context)
    const saved = await context.storage?.get('hostState')
    if (saved) {
      hostState.enabled = saved.enabled || false
      hostState.code = saved.code || ''
      hostState.status = saved.enabled ? '上次在线，点击重新开启' : ''
      hostState.peerConnected = false
    }
    hostState.autoAccept = !!(await context.storage?.get('autoAccept'))
    if (saved?.autoAccept != null) hostState.autoAccept = saved.autoAccept

    // Auto-reconnect if was enabled before restart — App.vue handles WS directly
    if (saved?.enabled) {
      context.log('info', 'auto-reconnect: saved.enabled was true, requesting pair code')
      hostState.enabled = true
      hostState.status = '允许控制中（等待主控连接）'
      // Request pair code via App.vue WS
      context.signal('remote:ws-send', { type: 'pair_request' })
      // Set up refresh timer
      clearInterval(codeTimer)
      codeTimer = setInterval(() => {
        context.signal('remote:ws-send', { type: 'pair_request' })
      }, 240000)
    } else {
      context.log('info', 'no saved host state, host disabled')
    }

    // --- WebSocket signaling (App.vue manages WS) ---

    async function connectWs(id: string) {
      context.log('info', `connectWs: id=${id}`)
      const serverUrl = await getServerUrl()
      const token = await getToken()
      if (!serverUrl || !token) {
        hostState.status = '配置错误: 服务器地址未设置'
        return false
      }
      context.log('info', 'connectWs: signaling App.vue to connect WS')
      const name = require('os').hostname()
      context.signal('remote:ws-connect', { serverUrl, token, deviceId: id, name })
      hostState.status = '已在线'
      persistState()
      return true
    }

    let hasNotifiedWindow = false

    function handleSignal(msg: any) {
      if (msg.type === 'pair_code') {
        context.log('info', 'received pair_code: ' + msg.code)
        hostState.code = msg.code || ''
        if (msg.password) hostState.password = msg.password
        persistState()
      } else if (msg.type === 'pair_success') {
        context.log('info', 'pair_success, host_deviceId=' + msg.host_deviceId)
        // Open viewer page to connect to the target host
        context.openPage('remote', 'mode=viewer&room=' + msg.host_deviceId)
      } else if (msg.type === 'pair_error') {
        context.log('error', 'pair_error: ' + msg.reason)
      } else if (msg.type === 'requestControl') {
        currentViewerId = msg.viewer_deviceId || ''
        context.log('info', 'requestControl from viewer=' + currentViewerId)
        hasNotifiedWindow = false
        delete (hostState as any).pendingOffer
        delete (hostState as any).pendingIce
        if (hostState.autoAccept) {
          context.signal('remote:ws-send', { type: 'controlAllowed', target_deviceId: currentViewerId })
          hostState.status = '已自动授权'
        } else {
          context.signal('remote:ws-send', { type: 'controlDenied', target_deviceId: currentViewerId })
          hostState.status = '已拒绝（未开启自动接受）'
        }
      } else if (msg.type === 'offer') {
        // Extract viewer ID from offer message if present
        if (msg.viewer_deviceId) currentViewerId = msg.viewer_deviceId
        ;(hostState as any).pendingOffer = msg.payload
        ;(hostState as any).pendingIce = []
        hostState.status = '正在建立连接…'
        context.log('info', 'offer received, pending viewer=' + currentViewerId)
        setTimeout(() => {
          if (!hostState.peerConnected) context.log('warn', '30s timeout: peer NOT connected')
        }, 30000)
        if (!hasNotifiedWindow) {
          hasNotifiedWindow = true
          context.log('info', 'sending signal remote:open-connection')
          context.signal('remote:open-connection', `u_${deviceId}`, currentViewerId).catch((e: any) => {
            context.log('error', 'signal failed: ' + String(e))
          })
        }
      } else if (msg.type === 'ice') {
        const ice = (hostState as any).pendingIce
        if (ice) {
          ice.push(msg.payload)
          if (ice.length % 5 === 0) context.log('info', 'received ' + ice.length + ' viewer ICE candidates')
        }
      } else if (msg.type === 'revoked') {
        hostState.status = '连接已断开'
        hostState.peerConnected = false
        hasNotifiedWindow = false
        delete (hostState as any).pendingOffer
        delete (hostState as any).pendingIce
      } else if (msg.type === 'error') {
        hostState.status = '错误: ' + (msg.message || '未知')
      } else if (msg.type === 'diag') {
        const level = msg.level || 'info'
        context.log(level, 'viewer| ' + msg.msg)
      }
    }

    // --- Host Management ---

    async function executeStartHostDirectly() {
      if (hostState.enabled) { context.log('warn', 'startHost skipped (already enabled)'); return }
      try {
        context.log('info', 'startHost begin')
        hostState.status = '启动中…'
        const id = deviceId!

        hostState.enabled = true
        hostState.status = '允许控制中（等待主控连接）'
        await persistState()

        await connectWs(id)

        // Request initial pair code
        context.signal('remote:ws-send', { type: 'pair_request' })

        // Refresh pair code every 4 minutes
        clearInterval(codeTimer)
        codeTimer = setInterval(() => {
          context.signal('remote:ws-send', { type: 'pair_request' })
        }, 240000)

      } catch (e: any) {
        hostState.status = '启动失败: ' + (e?.message || e)
      }
    }

    context.registerCommand('startHost', async () => {
      await executeStartHostDirectly()
      return getState()
    })

    context.registerCommand('stopHost', async () => {
      clearTimeout(reconnectTimer)
      context.signal('remote:ws-disconnect')
      clearInterval(codeTimer)
      clearTimeout(heartbeatTimer)
      Object.assign(hostState, { enabled: false, code: '', status: '', peerConnected: false })
      await persistState()
      return getState()
    })

    // Renderer calls this to send WebRTC answer/ICE via WS
    context.registerCommand('sendSignal', async (args: any) => {
      context.log('info', 'sendSignal: ' + (args?.type))
      if (args) {
        // Auto-add target_deviceId if not present
        if (!args.target_deviceId && currentViewerId) {
          args.target_deviceId = currentViewerId
        }
        context.log('info', 'sendSignal: sending via remote:ws-send')
        context.signal('remote:ws-send', args)
      }
      return getState()
    })

    context.registerCommand('handleSignal', async (msg: any) => {
      context.log('info', 'handleSignal command received: type=' + (msg?.type))
      handleSignal(msg)
      return getState()
    })

    context.registerCommand('getPanelData', async () => {
      const st = { ...hostState }
      const items: any[] = []
      if (st.enabled && st.code) {
        items.push({ title: `配对码 ${st.code}${st.password ? ` 密码 ${st.password}` : ''}`, subtitle: st.status || '等待连接' })
      }
      if (st.peerConnected) {
        items.push({ title: '主控已连接', subtitle: '远程控制中' })
      }
      if (!st.enabled) {
        items.push({ title: '未启用', subtitle: '点击打开远程控制面板' })
      }
      return {
        title: '远程控制',
        subtitle: st.enabled ? (st.peerConnected ? '已连接' : '等待连接') : '未启用',
        items,
      }
    })
    context.registerCommand('getPageData', async () => getState())
    context.registerCommand('open', async () => { context.openPage('remote') })
    context.registerCommand('getDeviceId', async () => deviceId)
    context.registerCommand('getHostName', async () => { const { hostname } = require('os'); return hostname() })
    context.registerCommand('getState', async () => getState())
    context.registerCommand('syncHostState', async (args: any) => {
      if (args) {
        const { pendingOffer, pendingIce, ...rest } = args
        Object.assign(hostState, rest)
      }
      await persistState()
      return getState()
    })
    context.registerCommand('setAutoAccept', async (args: any) => {
      hostState.autoAccept = !!args?.enabled
      await context.storage?.set('autoAccept', hostState.autoAccept)
      return getState()
    })
    context.registerCommand('getDevices', async () => {
      try { return await context.api.get('/remote/devices') } catch (e: any) {
        context.log('error', 'getDevices failed: ' + (e?.code || '') + ' ' + (e?.message?.slice(0, 80) || ''))
        try { return await context.api.get('/remote/devices') } catch { return { devices: [] } }
      }
    })
  },
  deactivate() {
    context.log('info', 'deactivate')
    clearTimeout(reconnectTimer)
    context.log('info', 'deactivate: sending remote:ws-disconnect')
    context.signal('remote:ws-disconnect')
    clearInterval(codeTimer)
    clearTimeout(heartbeatTimer)
    persistState()
  },
}

async function getServerUrl(): Promise<string> {
  try { return (await pluginCtx.config.get('serverUrl')) || 'http://localhost:8000' } catch { return 'http://localhost:8000' }
}

async function getToken(): Promise<string> {
  try { return (await pluginCtx.config.get('token')) || '' } catch { return '' }
}
