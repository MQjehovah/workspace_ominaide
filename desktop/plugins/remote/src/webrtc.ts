export async function getServer(): Promise<{ serverUrl: string; token: string }> {
  const w = window as any
  const serverUrl = (await w.mqbox.config.get('serverUrl')) || 'http://localhost:8000'
  const token = (await w.mqbox.config.get('token')) || ''
  return { serverUrl, token }
}

export function openSignal(roomId: string, onMsg: (m: any) => void): Promise<WebSocket> {
  return getServer().then(({ serverUrl, token }) => {
    const wsUrl = serverUrl.replace(/^http/, 'ws') + `/ws/remote/${roomId}?token=${encodeURIComponent(token)}`
    console.log('[signal] connecting to:', wsUrl)
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (e) => { try { onMsg(JSON.parse(e.data)) } catch {} }
    return new Promise<WebSocket>((res, rej) => {
      ws.onopen = () => { console.log('[signal] WS opened'); res(ws) }
      ws.onerror = () => { console.log('[signal] WS error'); rej(new Error('信令连接失败')) }
      ws.onclose = () => { console.log('[signal] WS closed before open'); rej(new Error('信令连接关闭')) }
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
    cachedIce = (r && r.iceServers) || [{ urls: 'stun:stun.l.google.com:19302' }]
  } catch {
    cachedIce = [{ urls: 'stun:stun.l.google.com:19302' }]
  }
  return cachedIce!
}

export function newPeer(iceServers?: any[], opts?: { relay?: boolean }): RTCPeerConnection {
  const config: any = { iceServers: iceServers || [{ urls: 'stun:stun.l.google.com:19302' }] }
  if (opts?.relay) config.iceTransportPolicy = 'relay'
  return new RTCPeerConnection(config)
}

export function setCodecPreferencesH264(pc: RTCPeerConnection) {
  try {
    const transceivers = pc.getTransceivers?.()
    if (!transceivers) return
    const videoTransceiver = transceivers.find(t => t.kind === 'video')
    if (!videoTransceiver?.setCodecPreferences) return
    const caps = (RTCRtpSender as any).getCapabilities?.('video')
    if (!caps?.codecs) return
    const h264 = caps.codecs.filter((c: any) => c.mimeType.toLowerCase().includes('h264'))
    if (h264.length > 0) videoTransceiver.setCodecPreferences(h264)
  } catch {}
}

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const { token } = await getServer()
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}
