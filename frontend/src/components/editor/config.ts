import type { AxiosInstance } from 'axios'

export interface EditorHttp {
  get<T = any>(url: string, config?: any): Promise<{ data: T }>
  post<T = any>(url: string, data?: any, config?: any): Promise<{ data: T }>
}

export interface NotesEditorConfig {
  http?: EditorHttp | AxiosInstance
  apiBase?: string
  getToken?: () => string | null
}

const defaultGetToken = () => {
  try {
    return localStorage.getItem('rag_token') || localStorage.getItem('token')
  } catch {
    return null
  }
}

let config: NotesEditorConfig = {
  apiBase: '',
  getToken: defaultGetToken,
}

export function configureNotesEditor(next: NotesEditorConfig): void {
  config = { ...config, ...next }
}

export function getNotesEditorConfig(): NotesEditorConfig {
  return config
}

export function getEditorHttp(): EditorHttp | AxiosInstance | undefined {
  return config.http
}

export function getEditorApiBase(): string {
  return (config.apiBase || '').replace(/\/$/, '')
}

export function getEditorToken(): string | null {
  return (config.getToken || defaultGetToken)()
}
