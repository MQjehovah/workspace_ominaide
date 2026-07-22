import type { RpcRequest, RpcResponse } from '../../shared/types'

let idCounter = 0
function nextId(): string {
  return `${Date.now().toString(36)}-${(++idCounter).toString(36)}`
}

export function createRequest(command: string, args?: unknown): RpcRequest {
  return { id: nextId(), type: 'execute', command, args }
}

export function createStateRequest(type: 'getState' | 'setState', key?: string, value?: unknown): RpcRequest {
  return { id: nextId(), type, key, value }
}

export function encodeMessage(msg: RpcRequest | RpcResponse): string {
  return JSON.stringify(msg) + '\n'
}

export function decodeMessage(data: string): (RpcRequest | RpcResponse)[] {
  return data
    .split('\n')
    .filter(line => line.trim())
    .map(line => JSON.parse(line))
}
