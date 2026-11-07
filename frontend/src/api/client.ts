import axios from 'axios'
import { API_BASE, apiUrl, appUrl } from './base'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from './tokens'

const client = axios.create({ baseURL: API_BASE })

client.interceptors.request.use(config => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken()
  if (!refresh) return null
  try {
    // Use a bare axios call so this request does not pass through the
    // response interceptor and cause a refresh loop.
    const res = await axios.post(apiUrl('/auth/refresh'), {
      refresh_token: refresh,
    })
    const access = res.data?.access_token || ''
    const nextRefresh = res.data?.refresh_token || refresh
    if (!access) return null
    setTokens(access, nextRefresh)
    return access
  } catch {
    return null
  }
}

function redirectToLogin(): void {
  clearTokens()
  if (!window.location.pathname.endsWith('/login')) {
    window.location.href = appUrl('login')
  }
}

client.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config || {}
    const status = error.response?.status
    const url = String(original.url || '')

    if (status !== 401 || original._retry) {
      return Promise.reject(error)
    }
    if (url.includes('/auth/login') || url.includes('/auth/refresh')) {
      return Promise.reject(error)
    }

    original._retry = true
    refreshing = refreshing || refreshAccessToken().finally(() => {
      refreshing = null
    })
    const token = await refreshing
    if (!token) {
      redirectToLogin()
      return Promise.reject(error)
    }
    original.headers = original.headers || {}
    original.headers.Authorization = `Bearer ${token}`
    return client(original)
  },
)

export default client
