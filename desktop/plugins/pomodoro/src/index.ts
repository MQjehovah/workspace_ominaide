import Page from './Page.vue'
import Panel from './Panel.vue'

let ctx: any = null

interface TimerState {
  running: boolean
  mode: 'focus' | 'break'
  focusMin: number
  breakMin: number
  endAt: number
}

let state: TimerState = {
  running: false,
  mode: 'focus',
  focusMin: 25,
  breakMin: 5,
  endAt: 0,
}

export default {
  panel: Panel,
  page: Page,

  activate(context: any) {
    ctx = context

    // Load persisted settings.
    context.storage?.get('pomodoro').then((d: any) => {
      if (d && typeof d.focusMin === 'number') state.focusMin = d.focusMin
      if (d && typeof d.breakMin === 'number') state.breakMin = d.breakMin
    })

    context.registerCommand('getPanelData', async () => {
      return {
        title: '番茄钟',
        subtitle: state.running ? `${state.mode === 'focus' ? '专注中' : '休息中'}` : '未开始',
        items: [{ title: state.running ? remainingLabel() : '准备开始', subtitle: `${state.focusMin} 分钟工作 / ${state.breakMin} 分钟休息` }],
        buttons: [{ label: state.running ? '打开番茄钟' : '开始专注', command: state.running ? 'open' : 'start' }],
      }
    })

    context.registerCommand('getPageData', async () => {
      return { state: { ...state, remainingMs: state.running ? Math.max(0, state.endAt - Date.now()) : 0 } }
    })

    context.registerCommand('start', async (args?: any) => {
      if (args?.focusMin) state.focusMin = args.focusMin
      if (args?.breakMin) state.breakMin = args.breakMin
      persist()
      state.running = true
      state.mode = 'focus'
      state.endAt = Date.now() + state.focusMin * 60000
      context.notification?.show('🍅 开始专注', `${state.focusMin} 分钟，加油！`)
      refresh()
      return { success: true }
    })

    context.registerCommand('pause', async () => {
      if (state.running) {
        const remaining = Math.max(0, state.endAt - Date.now())
        state.endAt = Date.now() + remaining // keep remaining on pause
      }
      return { success: true }
    })

    context.registerCommand('reset', async () => {
      state.running = false
      state.mode = 'focus'
      refresh()
      return { success: true }
    })

    context.registerCommand('setDuration', async (args?: any) => {
      if (args?.focusMin) state.focusMin = args.focusMin
      if (args?.breakMin) state.breakMin = args.breakMin
      persist()
      refresh()
      return { success: true }
    })

    context.registerCommand('open', async () => context.openPage('pomodoro'))

    // Ticker: detect session end → notify + report focus event.
    ticker = setInterval(() => {
      if (!state.running) return
      if (Date.now() >= state.endAt) {
        onSessionEnd()
      } else {
        refresh()
      }
    }, 1000)
  },

  deactivate() {
    if (ticker) { clearInterval(ticker); ticker = null }
  },
}

let ticker: any = null

function onSessionEnd() {
  const finished = state.mode
  if (finished === 'focus') {
    // Report the focus session to the event stream (feeds insights / activity).
    const minutes = state.focusMin
    try {
      ctx?.api?.post('/activities', {
        event_type: 'focus.completed',
        entity_type: 'focus',
        summary: `完成 ${minutes} 分钟专注`,
        details: { minutes, mode: 'pomodoro', end: new Date().toISOString() },
      }).catch(() => {})
    } catch { /* ignore */ }
    ctx?.notification?.show('🍅 专注完成！', `已专注 ${minutes} 分钟，休息一下吧`)
    state.mode = 'break'
    state.endAt = Date.now() + state.breakMin * 60000
  } else {
    ctx?.notification?.show('🍅 休息结束', '开始下一轮专注吧')
    state.mode = 'focus'
    state.endAt = Date.now() + state.focusMin * 60000
  }
  refresh()
}

function remainingLabel(): string {
  const ms = Math.max(0, state.endAt - Date.now())
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function persist() {
  try { ctx?.storage?.set('pomodoro', { focusMin: state.focusMin, breakMin: state.breakMin }) } catch { /* ignore */ }
}

function refresh() {
  try { ctx?.signal?.('panel:updated') } catch { /* ignore */ }
}
