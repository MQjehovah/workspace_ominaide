const FALLBACK_ICE = [
  { urls: 'stun:mqgeek.com:3478' },
  { urls: 'turn:mqgeek.com:3478', username: 'guest', credential: 'guest' },
  { urls: 'turn:mqgeek.com:3478?transport=tcp', username: 'guest', credential: 'guest' },
]

export async function getServer(): Promise<{ serverUrl: string; token: string }> {
  const w = window as any
  const serverUrl = (await w.mqbox.config.get('serverUrl')) || 'http://localhost:8000'
  const token = (await w.mqbox.config.get('token')) || ''
  return { serverUrl, token }
}

export function openSignal(roomId: string, onMsg: (m: any) => void): Promise<WebSocket> {
  return getServer().then(({ serverUrl, token }) => {
    const wsUrl = serverUrl.replace(/^http/, 'ws') + '/ws/remote'
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (e) => { try { onMsg(JSON.parse(e.data)) } catch {} }
    return new Promise<WebSocket>((res, rej) => {
      ws.onopen = () => {
        // Use unique viewer ID to avoid overwriting host's connection
        const viewerId = 'viewer_' + Date.now().toString(36) + '_' + roomId
        ws.send(JSON.stringify({ type: 'join', device_id: viewerId, name: '', token }))
        res(ws)
      }
      ws.onerror = () => rej(new Error('信令连接失败'))
      ws.onclose = () => rej(new Error('信令连接关闭'))
    })
  })
}

let cachedIce: any[] | null = null

export async function getIceServers(): Promise<any[]> {
  if (cachedIce) return cachedIce
  try {
    const { serverUrl } = await getServer()
    const headers = await getAuthHeaders()
    const r = await fetch(`${serverUrl}/api/remote/ice`, { headers }).then(r => r.json())
    cachedIce = (r && r.iceServers) || FALLBACK_ICE
  } catch {
    cachedIce = FALLBACK_ICE
  }
  return cachedIce!
}

export function newPeer(iceServers?: any[]): RTCPeerConnection {
  return new RTCPeerConnection({ iceServers: iceServers || FALLBACK_ICE })
}

export function setCodecPreferences(pc: RTCPeerConnection) {
  try {
    const caps = (RTCRtpSender as any).getCapabilities?.('video')
    if (!caps?.codecs) return
    const h264 = caps.codecs.filter((c: any) => c.mimeType.includes('H264'))
    const other = caps.codecs.filter((c: any) => !c.mimeType.includes('H264'))
    const preferred = [...h264, ...other]
    const tr = pc.getTransceivers?.()?.find((t: any) => t.kind === 'video')
    if (tr?.setCodecPreferences) tr.setCodecPreferences(preferred)
  } catch {}
}

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const { token } = await getServer()
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}
