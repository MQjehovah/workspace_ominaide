import Panel from './Panel.vue'
import Page from './Page.vue'

let pluginCtx: any = null
let deviceId: string | null = null
let hostState = { enabled: false, code: '', status: '', peerConnected: false, autoAccept: false }
let hostWs: any = null
let codeTimer: any = null
let heartbeatTimer: any = null
let reconnectTimer: any = null

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

    // Auto-reconnect if was enabled before restart
    if (saved?.enabled) {
      hostState.enabled = false // reset so executeStartHostDirectly doesn't skip
      try { await context.api.delete('/remote/online', { params: { device_id: id } }) } catch {} // cleanup stale registration
      executeStartHostDirectly().catch((e: any) => {
        console.error('[remote] auto-reconnect failed:', e?.message || e)
      })
    }

    // --- WebSocket signaling (child process owns WS) ---

    async function connectWs(id: string, roomId: string) {
      const serverUrl = await getServerUrl()
      const token = await getToken()
      if (!serverUrl || !token) {
        hostState.status = '配置错误: 服务器地址未设置'
        return false
      }
      try {
        const WebSocket = require('ws')
        const wsUrl = `${serverUrl.replace(/^http/, 'ws')}/ws/remote/${roomId}?token=${encodeURIComponent(token)}`
        const ws = new WebSocket(wsUrl)

        const result = await new Promise<boolean>((resolve) => {
          const timeout = setTimeout(() => {
            console.error('[remote] connectWs timeout after 10s')
            ws.close()
            resolve(false)
          }, 10000)

          ws.on('open', () => {
            ws.send(JSON.stringify({ type: 'join' }))
            if (!hostState.enabled) hostState.enabled = true
            hostState.status = '已在线'
            persistState()
            clearTimeout(timeout)
            resolve(true)
          })

          ws.on('message', (data: Buffer) => {
            const msg = JSON.parse(data.toString())
            console.error('[remote] WS received:', msg.type)
            try { handleSignal(msg, ws) } catch {}
          })

          ws.on('close', (code: number, reason: Buffer) => {
            console.error('[remote] WS closed:', code, reason?.toString())
            hostWs = null
            if (hostState.enabled) {
              hostState.status = '信令断开，5秒后重连…'
              persistState()
              clearTimeout(reconnectTimer)
              reconnectTimer = setTimeout(() => connectWs(id, roomId), 5000)
            }
          })

          ws.on('error', (err: Error) => {
            console.error('[remote] WS error:', err.message)
            clearTimeout(timeout)
            resolve(false)
          })
        })

        if (!result) {
          console.error('[remote] connectWs failed')
          hostState.status = '信令连接超时'
          return false
        }

        hostWs = ws
        console.error('[remote] connectWs OK, hostWs assigned')
        return true
      } catch (e: any) {
        hostState.status = '连接失败: ' + (e?.message || e)
        return false
      }
    }

    let hasNotifiedWindow = false

    function handleSignal(msg: any, ws: any) {
      if (msg.type === 'requestControl') {
        if (hostState.autoAccept) {
          ws.send(JSON.stringify({ type: 'controlAllowed' }))
          hostState.status = '已自动授权'
        } else {
          ws.send(JSON.stringify({ type: 'controlDenied' }))
          hostState.status = '已拒绝（未开启自动接受）'
        }
      } else if (msg.type === 'offer') {
        ;(hostState as any).pendingOffer = msg.payload
        ;(hostState as any).pendingIce = []
        hostState.status = '正在建立连接…'
        if (!hasNotifiedWindow) {
          hasNotifiedWindow = true
          console.error('[remote] sending signal remote:open-connection')
          context.signal('remote:open-connection', `u_${deviceId}`).catch((e: any) => {
            console.error('[remote] signal failed:', e)
          })
        }
      } else if (msg.type === 'ice') {
        const ice = (hostState as any).pendingIce
        if (ice) ice.push(msg.payload)
      } else if (msg.type === 'revoked') {
        hostState.status = '连接已断开'
        hostState.peerConnected = false
        hasNotifiedWindow = false
        delete (hostState as any).pendingOffer
        delete (hostState as any).pendingIce
      } else if (msg.type === 'error') {
        hostState.status = '错误: ' + (msg.message || '未知')
      }
    }

    // --- Host Management ---

    async function executeStartHostDirectly() {
      if (hostState.enabled) return
      try {
        hostState.status = '启动中…'
        const id = deviceId!
        const roomId = `u_${id}`
        const hostname = require('os').hostname()

        await context.api.post('/remote/online', { device_id: id, name: hostname, room_id: roomId })

        const pairData = await context.api.post('/remote/pair', { device_id: id, room_id: roomId })
        hostState.code = pairData?.code || ''

        hostState.enabled = true
        hostState.status = '允许控制中（等待主控连接）'
        await persistState()

        await connectWs(id, roomId)

        clearInterval(codeTimer)
        codeTimer = setInterval(async () => {
          try {
            const d = await context.api.post('/remote/pair', { device_id: id, room_id: roomId })
            if (d?.code) { hostState.code = d.code; persistState() }
          } catch {}
        }, 240000)

        async function doHeartbeat() {
          try { await context.api.post('/remote/heartbeat', { device_id: id }) } catch {}
          heartbeatTimer = setTimeout(doHeartbeat, 30000)
        }
        clearTimeout(heartbeatTimer)
        heartbeatTimer = setTimeout(doHeartbeat, 30000)

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
      try { await context.api.delete('/remote/online', { params: { device_id: deviceId } }) } catch {}
      if (hostWs) { try { hostWs.close() } catch {} }
      hostWs = null
      clearInterval(codeTimer)
      clearTimeout(heartbeatTimer)
      Object.assign(hostState, { enabled: false, code: '', status: '', peerConnected: false })
      await persistState()
      return getState()
    })

    // Renderer calls this to send WebRTC answer/ICE via WS
    context.registerCommand('sendSignal', async (args: any) => {
      console.error('[remote] sendSignal:', args?.type, 'hostWs:', !!hostWs)
      if (hostWs && args) {
        try { hostWs.send(JSON.stringify(args)) } catch (e) { console.error('[remote] sendSignal error:', e) }
      }
      return getState()
    })



    // --- State & Data Commands ---

    context.registerCommand('getPanelData', async () => {
      const st = { ...hostState }
      const items: any[] = []
      if (st.enabled && st.code) {
        items.push({ title: `配对码 ${st.code}`, subtitle: st.status || '等待连接' })
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
        // Don't overwrite pendingOffer from renderer
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
      try { return await context.api.get('/remote/devices') } catch { return { devices: [] } }
    })

    context.registerCommand('connectByCode', async (args: any) => {
      try { return await context.api.get(`/remote/pair/${args?.code}`) } catch { return null }
    })
  },
  deactivate() {
    clearTimeout(reconnectTimer)
    if (hostWs) { try { hostWs.close() } catch {} }
    hostWs = null
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
