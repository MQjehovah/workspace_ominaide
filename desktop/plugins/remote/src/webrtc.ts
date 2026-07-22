export async function getServer(): Promise<{ serverUrl: string; token: string }> {
  const w = window as any
  const serverUrl = (await w.mqbox.config.get('serverUrl')) || 'http://localhost:8000'
  const token = (await w.mqbox.config.get('token')) || ''
  return { serverUrl, token }
}

export function openSignal(roomId: string, onMsg: (m: any) => void): Promise<WebSocket> {
  return getServer().then(({ serverUrl, token }) => {
    const wsUrl = serverUrl.replace(/^http/, 'ws') + `/ws/remote/${roomId}?token=${encodeURIComponent(token)}`
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (e) => { try { onMsg(JSON.parse(e.data)) } catch {} }
    return new Promise<WebSocket>((res, rej) => {
      ws.onopen = () => res(ws)
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
    cachedIce = (r && r.iceServers) || [{ urls: 'stun:stun.l.google.com:19302' }]
  } catch {
    cachedIce = [{ urls: 'stun:stun.l.google.com:19302' }]
  }
  return cachedIce!
}

export function newPeer(iceServers?: any[]): RTCPeerConnection {
  return new RTCPeerConnection({ iceServers: iceServers || [{ urls: 'stun:stun.l.google.com:19302' }] })
}

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const { token } = await getServer()
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}
