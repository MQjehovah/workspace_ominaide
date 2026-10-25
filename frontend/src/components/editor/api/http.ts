import axios, { type AxiosInstance } from 'axios'
import { getEditorApiBase, getEditorHttp, getEditorToken } from '../config'

const fallback: AxiosInstance = axios.create({ timeout: 60000 })

fallback.interceptors.request.use((cfg) => {
  const token = getEditorToken()
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

fallback.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      try {
        localStorage.removeItem('rag_token')
        localStorage.removeItem('token')
      } catch { /* ignore */ }
    }
    return Promise.reject(error)
  },
)

function client(): AxiosInstance {
  const custom = getEditorHttp() as AxiosInstance | undefined
  if (custom) return custom
  fallback.defaults.baseURL = getEditorApiBase()
  return fallback
}

const http = {
  get<T = any>(url: string, config?: any) {
    return client().get<T>(url, config)
  },
  post<T = any>(url: string, data?: any, config?: any) {
    return client().post<T>(url, data, config)
  },
}

export default http
