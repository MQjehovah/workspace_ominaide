import { defineStore } from 'pinia'
import client from '@/api/client'

export interface WorkspaceItem {
  id: number
  user_id: number
  name: string
  description: string | null
  bucket: string
  sync_enabled: boolean
  local_path: string | null
  created_at: string
  updated_at: string
}

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    workspaces: [] as WorkspaceItem[],
    loading: false
  }),
  actions: {
    async fetchWorkspaces() {
      this.loading = true
      try {
        const res = await client.get<WorkspaceItem[]>('/workspaces')
        this.workspaces = res.data
      } finally {
        this.loading = false
      }
    },
    async create(data: { name: string; description?: string; sync_enabled?: boolean }) {
      const res = await client.post<WorkspaceItem>('/workspaces', data)
      this.workspaces.unshift(res.data)
      return res.data
    },
    async update(id: number, data: { name?: string; description?: string }) {
      const res = await client.put<WorkspaceItem>(`/workspaces/${id}`, data)
      const idx = this.workspaces.findIndex(w => w.id === id)
      if (idx !== -1) this.workspaces[idx] = res.data
      return res.data
    },
    async delete(id: number) {
      await client.delete(`/workspaces/${id}`)
      this.workspaces = this.workspaces.filter(w => w.id !== id)
    }
  }
})
