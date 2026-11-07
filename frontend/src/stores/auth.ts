import { defineStore } from 'pinia'
import client from '@/api/client'
import { clearTokens, getAccessToken, setTokens } from '@/api/tokens'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getAccessToken(),
    user: null as any
  }),
  actions: {
    async login(username: string, password: string) {
      const res = await client.post('/auth/login', { username, password })
      this.token = res.data.access_token
      setTokens(res.data.access_token, res.data.refresh_token)
      await this.fetchUser()
    },
    async fetchUser() {
      const res = await client.get('/auth/me')
      this.user = res.data
    },
    logout() {
      this.token = ''
      this.user = null
      clearTokens()
    }
  }
})
