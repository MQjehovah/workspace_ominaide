import { defineStore } from 'pinia'
import client from '@/api/client'

export interface FileItem {
  id: number
  user_id: number
  bucket: string
  object_key: string
  original_name: string
  is_folder: boolean
  folder_path: string | null
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
    search: '',
    folderPath: '/',
    status: 'active',
    sortBy: 'updated_at' as 'name' | 'size' | 'created_at' | 'updated_at',
    sortOrder: 'desc' as 'asc' | 'desc',
    stats: null as { active_count: number; active_size: number; trash_count: number; trash_size: number } | null
  }),
  actions: {
    async fetchFiles(params?: { status?: string; page?: number; search?: string; folder_path?: string | null }) {
      this.loading = true
      try {
        const status = params?.status || this.status
        const folderParam = params && 'folder_path' in params ? params.folder_path : this.folderPath
        const res = await client.get<FileListResponse>('/files', {
          params: {
            page: params?.page || this.page,
            page_size: this.pageSize,
            status,
            search: params?.search !== undefined ? params.search : this.search || undefined,
            folder_path: folderParam === undefined ? undefined : folderParam,
            sort_by: this.sortBy,
            sort_order: this.sortOrder,
          }
        })
        this.files = res.data.files
        this.total = res.data.total
        this.page = res.data.page
        this.status = status
      } finally {
        this.loading = false
      }
    },
    async getUploadUrl(filename: string, folderPath?: string) {
      const path = folderPath ?? this.folderPath
      const res = await client.post('/files/upload-url', {
        filename,
        folder_path: path || '/',
      })
      return res.data as { upload_url: string; file_id: number; object_key: string }
    },
    async confirmUpload(fileId: number) {
      const res = await client.post('/files/confirm', { file_id: fileId })
      return res.data
    },
    async createFolder(name: string, parentPath?: string) {
      const path = parentPath ?? this.folderPath
      const res = await client.post('/files/folder', {
        name,
        parent_path: path || '/',
      })
      await this.fetchFiles()
      return res.data as FileItem
    },
    async renameFile(id: number, newName: string) {
      const res = await client.put(`/files/${id}/rename`, { new_name: newName })
      await this.fetchFiles()
      return res.data as FileItem
    },
    async moveFile(id: number, newFolderPath: string) {
      const res = await client.put(`/files/${id}/move`, { new_folder_path: newFolderPath })
      await this.fetchFiles()
      return res.data as FileItem
    },
    async deleteFile(id: number) {
      await client.delete(`/files/${id}`)
      await this.fetchFiles()
    },
    async restoreFile(id: number) {
      await client.post(`/files/${id}/restore`)
      await this.fetchFiles()
    },
    async deletePermanent(id: number) {
      await client.delete(`/files/${id}/permanent`)
      await this.fetchFiles()
    },
    async batchTrash(ids: number[]) {
      const res = await client.post('/files/batch/trash', { ids })
      return res.data as { success: number; failed: any[] }
    },
    async batchRestore(ids: number[]) {
      const res = await client.post('/files/batch/restore', { ids })
      return res.data as { success: number; failed: any[] }
    },
    async batchPermanent(ids: number[]) {
      const res = await client.post('/files/batch/permanent', { ids })
      return res.data as { success: number; failed: any[] }
    },
    async batchMove(ids: number[], folderPath: string) {
      const res = await client.post('/files/batch/move', { ids, folder_path: folderPath })
      return res.data as { success: number; failed: any[] }
    },
    async emptyTrash() {
      const res = await client.delete('/files/trash')
      return res.data as { removed: number }
    },
    async fetchStats() {
      const res = await client.get('/files/stats')
      this.stats = res.data
      return this.stats
    },
    async toggleFavorite(id: number) {
      const res = await client.post(`/files/${id}/favorite`)
      const idx = this.files.findIndex(f => f.id === id)
      if (idx !== -1) this.files[idx] = res.data
    },
    formatSize(bytes: number): string {
      if (!bytes) return '0 B'
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
    },
    getFileIcon(mime: string | null): string {
      if (!mime) return 'Document'
      if (mime.startsWith('image/')) return 'Picture'
      if (mime.startsWith('video/')) return 'VideoCamera'
      if (mime.startsWith('audio/')) return 'Headset'
      if (mime.includes('pdf')) return 'Reading'
      if (mime.includes('zip') || mime.includes('rar') || mime.includes('7z')) return 'FolderDelete'
      return 'Document'
    }
  }
})
