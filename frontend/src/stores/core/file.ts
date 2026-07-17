import { defineStore } from 'pinia'
import client from '@/api/client'

export interface FileItem {
  id: number
  user_id: number
  workspace_id: number | null
  bucket: string
  object_key: string
  original_name: string
  size: number
  mime_type: string | null
  tags: string[] | null
  is_favorite: boolean
  status: string
  created_at: string
  updated_at: string
}

interface FileListResponse {
  files: FileItem[]
  total: number
  page: number
  page_size: number
}

export const useFileStore = defineStore('file', {
  state: () => ({
    files: [] as FileItem[],
    total: 0,
    page: 1,
    pageSize: 50,
    loading: false,
    viewMode: 'grid' as 'grid' | 'list',
    currentWorkspaceId: null as number | null
  }),
  actions: {
    async fetchFiles(params?: { workspace_id?: number; status?: string; page?: number }) {
      this.loading = true
      try {
        const res = await client.get<FileListResponse>('/files', {
          params: {
            page: params?.page || this.page,
            page_size: this.pageSize,
            status: params?.status || 'active',
            workspace_id: params?.workspace_id || this.currentWorkspaceId
          }
        })
        this.files = res.data.files
        this.total = res.data.total
        this.page = res.data.page
      } finally {
        this.loading = false
      }
    },
    async getUploadUrl(filename: string, workspaceId?: number) {
      const res = await client.post('/files/upload-url', {
        filename,
        workspace_id: workspaceId || this.currentWorkspaceId
      })
      return res.data as { upload_url: string; file_id: number; object_key: string }
    },
    async confirmUpload(fileId: number) {
      const res = await client.post('/files/confirm', { file_id: fileId })
      return res.data
    },
    async deleteFile(id: number) {
      await client.delete(`/files/${id}`)
      await this.fetchFiles()
    },
    async toggleFavorite(id: number) {
      const res = await client.post(`/files/${id}/favorite`)
      const idx = this.files.findIndex(f => f.id === id)
      if (idx !== -1) this.files[idx] = res.data
    },
    formatSize(bytes: number): string {
      if (bytes === 0) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
    },
    getFileIcon(mime: string | null): string {
      if (!mime) return 'Document'
      if (mime.startsWith('image/')) return 'Picture'
      if (mime.startsWith('video/')) return 'VideoCamera'
      if (mime.startsWith('audio/')) return 'Headset'
      if (mime.includes('pdf')) return 'Reading'
      if (mime.includes('zip') || mime.includes('rar')) return 'FolderDelete'
      return 'Document'
    }
  }
})
