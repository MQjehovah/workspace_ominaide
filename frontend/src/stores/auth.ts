import { defineStore } from 'pinia'
import client from '@/api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: null as any
  }),
  actions: {
    async login(username: string, password: string) {
      const res = await client.post('/auth/login', { username, password })
      this.token = res.data.access_token
      localStorage.setItem('token', this.token)
      await this.fetchUser()
    },
    async fetchUser() {
      const res = await client.get('/auth/me')
      this.user = res.data
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
    }
  }
})
