import { newPeer, getIceServers, setCodecPreferencesH264 } from './webrtc'

let execute: ((cmd: string, args?: any) => Promise<any>) | null = null
let pc: RTCPeerConnection | null = null
let stream: MediaStream | null = null
let pendingIce: any[] = []
let pendingMove: any = null
let moveScheduled = false
let pollTimer: any = null
let listenerActive = false
let currentDataChannel: any = null

const qualityConfig = { maxWidth: 1920, maxHeight: 1080, maxFrameRate: 30 }
let cachedSources: any[] | null = null
let cachedDisplays: any[] | null = null
let cacheTime = 0
const CACHE_TTL = 5000
let currentDisplay: any = null
let currentSourceId = ''

async function getCachedSources() {
  const now = Date.now()
  if (cachedSources && now - cacheTime < CACHE_TTL) return { sources: cachedSources, displays: cachedDisplays }
  cachedSources = await (window as any).mqbox.remote.getDesktopSources()
  cachedDisplays = await (window as any).mqbox.remote.getAllDisplays()
  cacheTime = now
  return { sources: cachedSources, displays: cachedDisplays }
}

function matchDisplay(src: any, displays: any[]) {
  if (!src) return displays[0] || null
  return displays.find((d: any) => String(d.id) === String(src.display_id)) || displays[0] || null
}

async function flushMove() {
  if (!pendingMove || !currentDisplay) return
  const m = pendingMove
  pendingMove = null
  const d = currentDisplay
  const sf = d.scaleFactor || 1
  const x = Math.round((d.bounds.x + (Number(m.x) || 0) * d.bounds.width) * sf)
  const y = Math.round((d.bounds.y + (Number(m.y) || 0) * d.bounds.height) * sf)
  await (window as any).mqbox.remote.injectInput({ type: 'mouseMove', x, y })
}

async function handleInput(ev: any) {
  try {
    if (ev.type === 'mouseMove') {
      pendingMove = ev
      if (!moveScheduled) {
        moveScheduled = true
        requestAnimationFrame(async () => {
          moveScheduled = false
          await flushMove()
        })
      }
    } else if (ev.type === 'mouseDown' || ev.type === 'mouseUp' || ev.type === 'wheel' || ev.type === 'keyDown' || ev.type === 'keyUp') {
      await (window as any).mqbox.remote.injectInput(ev)
    }
  } catch {}
}

async function handleOffer(payload: any) {
  if (pc) { try { pc.close() } catch {} ; pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  currentDataChannel = null
  try {
    const { sources: srcList, displays: allDisplays } = await getCachedSources()
    if (!srcList.length) return
    currentDisplay = matchDisplay(srcList[0], allDisplays)
    currentSourceId = srcList[0].id
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: 'desktop',
          chromeMediaSourceId: srcList[0].id,
          maxFrameRate: qualityConfig.maxFrameRate,
          maxWidth: qualityConfig.maxWidth,
          maxHeight: qualityConfig.maxHeight,
        } as any,
      },
    })
    pc = newPeer(await getIceServers())
    setCodecPreferencesH264(pc)
    pc.ondatachannel = (e) => {
      currentDataChannel = e.channel
      e.channel.onopen = () => {
        try {
          ;(window as any).mqbox.remote.getDesktopSources().then((srcs: any[]) => {
            e.channel.send(JSON.stringify({ type: 'screens', list: srcs.map(s => ({ id: s.id, name: s.name })) }))
            e.channel.send(JSON.stringify({ type: 'activeScreen', id: currentSourceId }))
          })
        } catch {}
      }
      e.channel.onmessage = async (msg) => {
        try {
          const ev = JSON.parse(msg.data)
          if (ev.type === 'switchScreen') { await switchScreen(ev.sourceId, e.channel); return }
          if (ev.type === 'setQuality') {
            Object.assign(qualityConfig, ev)
            const newStream = await navigator.mediaDevices.getUserMedia({
              audio: false,
              video: {
                mandatory: {
                  chromeMediaSource: 'desktop',
                  chromeMediaSourceId: currentSourceId,
                  maxFrameRate: qualityConfig.maxFrameRate,
                  maxWidth: qualityConfig.maxWidth,
                  maxHeight: qualityConfig.maxHeight,
                } as any,
              },
            })
            const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
            if (sender && pc) await sender.replaceTrack(newStream.getVideoTracks()[0])
            if (stream) stream.getTracks().forEach(t => t.stop())
            stream = newStream
            return
          }
          await handleInput(ev)
        } catch {}
      }
    }
    stream.getTracks().forEach(t => pc!.addTrack(t, stream!))
    await pc.setRemoteDescription({ type: 'offer', sdp: payload.sdp })
    for (const c of pendingIce) { try { await pc.addIceCandidate(c) } catch {} }
    pendingIce = []
    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    execute?.('sendSignal', { type: 'answer', payload: answer })
    pc.onicecandidate = (e) => {
      if (e.candidate) execute?.('sendSignal', { type: 'ice', payload: e.candidate })
    }
    pc.oniceconnectionstatechange = () => {
      if (pc && (pc.iceConnectionState === 'failed' || pc.iceConnectionState === 'closed')) {
        cleanupPeer()
        execute?.('syncHostState', { peerConnected: false })
      }
    }
    execute?.('syncHostState', { peerConnected: true })
    execute?.('clearPendingOffer')
  } catch (e) {
    execute?.('clearPendingOffer')
  }
}

function cleanupPeer() {
  if (pc) { try { pc.close() } catch {} ; pc = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  stream = null
  pendingIce = []
  currentDataChannel = null
}

async function switchScreen(sourceId: string, dc: any) {
  try {
    const newStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: 'desktop',
          chromeMediaSourceId: sourceId,
          maxFrameRate: qualityConfig.maxFrameRate,
          maxWidth: qualityConfig.maxWidth,
          maxHeight: qualityConfig.maxHeight,
        } as any,
      },
    })
    const sender = pc?.getSenders().find((s: any) => s.track?.kind === 'video')
    if (sender && pc) await sender.replaceTrack(newStream.getVideoTracks()[0])
    if (stream) stream.getTracks().forEach(t => t.stop())
    stream = newStream
    currentSourceId = sourceId
    const { sources: srcs, displays: allDisplays } = await getCachedSources()
    currentDisplay = matchDisplay(srcs.find((s: any) => s.id === sourceId), allDisplays)
    dc.send(JSON.stringify({ type: 'activeScreen', id: sourceId }))
  } catch {}
}

function revokePeer() {
  execute?.('sendSignal', { type: 'revoked' })
  cleanupPeer()
  execute?.('syncHostState', { peerConnected: false })
}

async function syncState() {
  if (!execute) return
  try {
    const st = await execute('getState')
    if (!st?.hostState) return
    const h = st.hostState

    // Handle pending WebRTC offer from child process
    if (h.pendingOffer && !listenerActive) {
      listenerActive = true
      pendingIce = h.pendingIce || []
      await handleOffer(h.pendingOffer)
      listenerActive = false
    }

    // Clean up if host disabled
    if (!h.enabled && (pc || stream)) {
      cleanupPeer()
    }
  } catch {}
}

// --- Public API ---

export function init(executeFn: (cmd: string, args?: any) => Promise<any>) {
  execute = executeFn
}

export function ensureStarted() {
  if (pollTimer) return // already polling
  pollTimer = setInterval(syncState, 1500)
  syncState()
}

export function stop() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  cleanupPeer()
  currentDisplay = null
  currentSourceId = ''
  cachedSources = null
  cachedDisplays = null
  cacheTime = 0
  listenerActive = false
}

export function isConnected() {
  return pc !== null
}

export function getPeerConnected() {
  return pc !== null && (pc.iceConnectionState === 'connected' || pc.iceConnectionState === 'completed')
}

export { revokePeer }
