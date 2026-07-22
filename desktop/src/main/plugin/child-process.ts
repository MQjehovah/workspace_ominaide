import { fork, ChildProcess } from 'child_process'
import { join } from 'path'
import { EventEmitter } from 'events'
import type { PluginInfo, RpcRequest, RpcResponse } from '../../shared/types'
import { encodeMessage, decodeMessage } from './rpc'

interface PendingRequest {
  resolve: (value: unknown) => void
  reject: (reason: Error) => void
  timer: NodeJS.Timeout
}

const COMMAND_TIMEOUT = 30000

export class PluginChildProcess extends EventEmitter {
  public readonly pluginId: string
  private proc: ChildProcess | null = null
  private buffer = ''
  private pending = new Map<string, PendingRequest>()
  private _searchProviders: Array<{ keyword: string; name: string; priority?: number }> = []
  private _commandHandlers = new Map<string, Function>()
  private bridgeHandlers: Map<string, (args: any[]) => Promise<any>> = new Map()
  private rpcBuffer = ''

  private _exitCode: number | null = null
  private _readyResolve: (() => void) | null = null
  private _readyPromise: Promise<void>

  constructor(private info: PluginInfo) {
    super()
    this.pluginId = info.id
    this._readyPromise = new Promise((resolve) => {
      this._readyResolve = resolve
    })
  }

  start(): void {
    if (this.proc) return

    const entryPath = join(__dirname, 'child-entry.js')
    this.proc = fork(entryPath, [], {
      silent: true,
      env: {
        ...process.env,
        OMNIAIDE_PLUGIN_ID: this.pluginId,
        OMNIAIDE_PLUGIN_PATH: this.info.path,
      },
    })

    this.proc.stdout?.on('data', (chunk: Buffer) => this.handleOutgoing(chunk.toString()))
    this.proc.stderr?.on('data', (chunk: Buffer) => {
      const msg = chunk.toString().trim()
      if (msg) {
        console.error(`[plugin:${this.pluginId}]`, msg)
        this.emit('stderr', msg)
      }
    })
    this.proc.on('exit', (code) => {
      this._exitCode = code
      console.log(`[plugin:${this.pluginId}] exited with code ${code}`)
      this.emit('exit', code)
      this.proc = null
    })
    this.proc.on('error', (err) => {
      console.error(`[plugin:${this.pluginId}] error:`, err.message)
      this.emit('error', err)
    })
  }

  async waitForReady(timeoutMs = 10000): Promise<boolean> {
    const result = await Promise.race([
      this._readyPromise.then(() => true),
      new Promise<boolean>((resolve) => setTimeout(() => resolve(false), timeoutMs)),
    ])
    if (!result) {
      console.warn(`[plugin:${this.pluginId}] ready timeout after ${timeoutMs}ms`)
      if (this._exitCode !== null) {
        console.warn(`[plugin:${this.pluginId}] process already exited with code ${this._exitCode}`)
      }
    }
    return result
  }

  stop(): void {
    if (!this.proc) return
    try { this.proc.kill('SIGTERM') } catch {}
    this.proc = null
    this.rejectAll(new Error('Plugin process terminated'))
  }

  restart(): void {
    this.stop()
    this.start()
  }

  isRunning(): boolean {
    return this.proc !== null && !this.proc.killed
  }

  registerBridgeHandler(method: string, handler: (args: any[]) => Promise<any>): void {
    this.bridgeHandlers.set(method, handler)
  }

  get searchProviders() { return this._searchProviders }
  get commandHandlers() { return this._commandHandlers }

  async executeCommand(command: string, args?: unknown): Promise<unknown> {
    if (!this.isRunning()) throw new Error(`Plugin ${this.pluginId} is not running`)
    const req = { id: this.nextId(), type: 'execute' as const, command, args }
    return this.sendRequest(req)
  }

  private nextId(): string {
    return `${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 8)}`
  }

  private sendRequest(req: RpcRequest): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(req.id)
        reject(new Error(`Command ${req.command || req.type} timed out after ${COMMAND_TIMEOUT}ms`))
      }, COMMAND_TIMEOUT)
      this.pending.set(req.id, { resolve, reject, timer })
      this.writeToChild(req)
    })
  }

  private writeToChild(msg: unknown): void {
    if (this.proc?.stdin?.writable) {
      this.proc.stdin.write(encodeMessage(msg as any))
    }
  }

  private handleOutgoing(chunk: string): void {
    this.rpcBuffer += chunk
    const lines = this.rpcBuffer.split('\n')
    this.rpcBuffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
      const msg = JSON.parse(trimmed)
      if ((msg as any).id === 'ready') {
        this._readyResolve?.()
        this.emit('ready')
      } else if (msg.type === 'result' || msg.type === 'error') {
        this.handleResponse(msg as RpcResponse)
      } else if (msg.type === 'parent-rpc') {
        this.handleParentRpc(msg as any)
      }
      } catch (e) {
        console.error(`[plugin:${this.pluginId}] invalid message from child:`, (e as Error).message)
      }
    }
  }

  private handleResponse(res: RpcResponse): void {
    const pending = this.pending.get(res.id)
    if (!pending) return
    clearTimeout(pending.timer)
    this.pending.delete(res.id)
    if (res.type === 'error') {
      pending.reject(new Error(res.error || 'Unknown error'))
    } else {
      pending.resolve(res.data)
    }
  }

  private handleParentRpc(msg: any): void {
    const handler = this.bridgeHandlers.get(msg.method)
    if (!handler) {
      this.writeToChild({ id: msg.id, type: 'error', error: `Unknown bridge method: ${msg.method}` })
      return
    }
    handler(msg.args || [])
      .then(result => this.writeToChild({ id: msg.id, type: 'result', data: result }))
      .catch(err => this.writeToChild({ id: msg.id, type: 'error', error: err.message }))
  }

  private rejectAll(err: Error): void {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer)
      pending.reject(err)
    }
    this.pending.clear()
  }
}

export class PluginProcessManager extends EventEmitter {
  private processes = new Map<string, PluginChildProcess>()

  async startPlugin(info: PluginInfo): Promise<PluginChildProcess> {
    if (this.processes.has(info.id)) return this.processes.get(info.id)!

    const proc = new PluginChildProcess(info)
    proc.start()
    this.processes.set(info.id, proc)

    proc.on('exit', (code) => this.emit('plugin:exit', info.id, code))
    proc.on('error', (err) => this.emit('plugin:error', info.id, err))

    return proc
  }

  stopPlugin(id: string): void {
    const proc = this.processes.get(id)
    if (proc) {
      proc.stop()
      this.processes.delete(id)
    }
  }

  stopAll(): void {
    for (const [id] of this.processes) this.stopPlugin(id)
  }

  getProcess(id: string): PluginChildProcess | undefined {
    return this.processes.get(id)
  }

  getRunningPlugins(): string[] {
    return Array.from(this.processes.keys())
  }
}
