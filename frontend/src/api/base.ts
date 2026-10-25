// Deployment-aware API/app base paths.
// - Vite root deploy:      API_BASE=/api,        APP_BASE=/
// - Sub-path deploy:       API_BASE=/ominaide/api, APP_BASE=/ominaide/
export const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '')
export const APP_BASE = import.meta.env.BASE_URL || '/'

export function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? '' : '/'}${path}`
}

export function appUrl(path: string): string {
  return `${APP_BASE.replace(/\/$/, '')}/${path.replace(/^\//, '')}`
}
