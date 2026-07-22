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

function getState() {
  return { hosting: hostState.enabled, hostState }
}

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    pluginCtx = context
    await getDeviceId(context)
    // Load persisted autoAccept
    hostState.autoAccept = !!(await context.storage?.get('autoAccept'))

    // --- Host Management ---

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

        ws.on('open', () => {
          ws.send(JSON.stringify({ type: 'join' }))
          hostState.enabled = true
          hostState.status = '允许控制中（等待主控连接）'
        })

        ws.on('message', (data: Buffer) => {
          try { handleSignal(JSON.parse(data.toString())) } catch {}
        })

        ws.on('close', () => {
          hostWs = null
          // Auto-reconnect if host was intentionally enabled (not stopped by user)
          if (hostState.enabled) {
            hostState.status = '信令断开，5秒后重连…'
            clearTimeout(reconnectTimer)
            reconnectTimer = setTimeout(() => connectWs(id, roomId), 5000)
          }
        })

        ws.on('error', (err: Error) => {
          console.error('[remote] WS error:', err.message)
        })

        hostWs = ws
        return true
      } catch (e: any) {
        hostState.status = '连接失败: ' + (e?.message || e)
        return false
      }
    }

    context.registerCommand('startHost', async () => {
      if (hostWs) {
        // WS already exists, update online + code
        try {
          const pairData = await context.api.post('/remote/pair', { device_id: deviceId!, room_id: `u_${deviceId!}` })
          if (pairData?.code) hostState.code = pairData.code
        } catch {}
        return getState()
      }
      try {
        hostState.status = '启动中…'
        const id = deviceId!
        const roomId = `u_${id}`
        const hostname = require('os').hostname()

        // Register online
        await context.api.post('/remote/online', { device_id: id, name: hostname, room_id: roomId })

        // Get initial pair code
        const pairData = await context.api.post('/remote/pair', { device_id: id, room_id: roomId })
        hostState.code = pairData?.code || ''

        // Connect WS
        await connectWs(id, roomId)

        // Refresh code every 4 min
        clearInterval(codeTimer)
        codeTimer = setInterval(async () => {
          try {
            const d = await context.api.post('/remote/pair', { device_id: id, room_id: roomId })
            if (d?.code) hostState.code = d.code
          } catch {}
        }, 240000)

        // Heartbeat every 30s
        clearInterval(heartbeatTimer)
        heartbeatTimer = setInterval(async () => {
          try { await context.api.post('/remote/heartbeat', { device_id: id }) } catch {}
        }, 30000)

      } catch (e: any) {
        hostState.status = '启动失败: ' + (e?.message || e)
      }
      return getState()
    })

    context.registerCommand('stopHost', async () => {
      clearTimeout(reconnectTimer)
      try { await context.api.delete('/remote/online') } catch {}
      if (hostWs) { try { hostWs.close() } catch {} }
      hostWs = null
      clearInterval(codeTimer)
      clearInterval(heartbeatTimer)
      Object.assign(hostState, { enabled: false, code: '', status: '', peerConnected: false })
      return getState()
    })

    function handleSignal(msg: any) {
      if (msg.type === 'requestControl') {
        if (hostState.autoAccept) {
          hostWs?.send(JSON.stringify({ type: 'controlAllowed' }))
          hostState.status = '已自动授权'
        } else {
          hostWs?.send(JSON.stringify({ type: 'controlDenied' }))
          hostState.status = '已拒绝（未开启自动接受）'
        }
      } else if (msg.type === 'offer') {
        hostState.status = '正在建立连接…'
      } else if (msg.type === 'answer') {
        hostState.status = '连接已建立'
        hostState.peerConnected = true
      } else if (msg.type === 'revoked') {
        hostState.status = '连接已断开'
        hostState.peerConnected = false
      } else if (msg.type === 'error') {
        hostState.status = '错误: ' + (msg.message || '未知')
      }
    }

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
      if (args) Object.assign(hostState, args)
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
    clearInterval(heartbeatTimer)
  },
}

async function getServerUrl(): Promise<string> {
  try { return (await pluginCtx.config.get('serverUrl')) || 'http://localhost:8000' } catch { return 'http://localhost:8000' }
}

async function getToken(): Promise<string> {
  try { return (await pluginCtx.config.get('token')) || '' } catch { return '' }
}
