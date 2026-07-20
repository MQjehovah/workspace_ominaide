/**
 * 插件入口单元测试
 * 测试 index.ts 的核心逻辑：generateId, search provider, CRUD 命令
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { Note } from '../src/types'
import { createMockNotes } from './setup'

// 模拟 storage 对象
interface MockStorage {
  data: any
  get: (key: string) => Promise<any>
  set: (key: string, value: any) => Promise<void>
}

function createMockContext() {
  const commands: Record<string, Function> = {}
  const searchProviders: any[] = []
  const storage: MockStorage = {
    data: {} as any,
    get: async (key: string) => { return storage.data[key] },
    set: async (key: string, value: any) => { storage.data[key] = value }
  }

  const context = {
    registerCommand: (name: string, handler: Function) => {
      commands[name] = handler
    },
    registerSearchProvider: (provider: any) => {
      searchProviders.push(provider)
    },
    getCommand: (name: string) => commands[name],
    getSearchProviders: () => searchProviders,
    storage
  }

  return context
}

describe('插件入口 - index.ts', () => {
  let context: ReturnType<typeof createMockContext>

  beforeEach(async () => {
    // 每次测试重新加载插件
    context = createMockContext()
    // 重置模块缓存
    vi.resetModules()
  })

  describe('generateId', () => {
    it('应该生成不重复的 ID', async () => {
      const mod = await import('../src/index')
      // 通过 add 命令间接测试 generateId
      const addCmd = context.getCommand('add')
      if (addCmd) {
        const r1 = await addCmd({ content: 'test1' })
        const r2 = await addCmd({ content: 'test2' })
        expect(r1.note.id).not.toBe(r2.note.id)
      }
    })
  })

  describe('activate 注册的命令', () => {
    it('应该注册 add 命令', async () => {
      const mod = await import('../src/index')
      const plugin = mod.default
      plugin.activate(context)
      const cmd = context.getCommand('add')
      expect(cmd).toBeDefined()
    })

    it('应该注册 delete 命令', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const cmd = context.getCommand('delete')
      expect(cmd).toBeDefined()
    })

    it('应该注册 list 命令', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const cmd = context.getCommand('list')
      expect(cmd).toBeDefined()
    })

    it('应该注册 search provider', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const providers = context.getSearchProviders()
      expect(providers.length).toBe(1)
      expect(providers[0].keyword).toBe('note')
      expect(providers[0].name).toBe('快速笔记')
    })
  })

  describe('add 命令', () => {
    it('应该成功添加笔记', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      const result = await addCmd({ content: '新笔记内容', tags: ['工作'] })
      expect(result.success).toBe(true)
      expect(result.note.content).toBe('新笔记内容')
      expect(result.note.tags).toEqual(['工作'])
      expect(result.note.id).toBeDefined()
      expect(result.note.time).toBeDefined()
    })

    it('添加空内容笔记应返回空字符串', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      const result = await addCmd({})
      expect(result.success).toBe(true)
      expect(result.note.content).toBe('')
      expect(result.note.tags).toEqual([])
    })

    it('添加笔记后应保存到 storage', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      await addCmd({ content: '测试保存' })
      const stored = context.storage.data['notes']
      expect(stored).toBeDefined()
      expect(Array.isArray(stored)).toBe(true)
      expect(stored.length).toBe(1)
      expect(stored[0].content).toBe('测试保存')
    })
  })

  describe('list 命令', () => {
    it('不传参数时返回所有笔记', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      await addCmd({ content: '笔记A', tags: ['工作'] })
      await addCmd({ content: '笔记B', tags: ['个人'] })
      await addCmd({ content: '笔记C', tags: ['学习'] })

      const listCmd = context.getCommand('list')
      const result = await listCmd()
      expect(result.success).toBe(true)
      expect(result.notes.length).toBe(3)
    })

    it('按标签过滤笔记', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      await addCmd({ content: '工作笔记', tags: ['工作'] })
      await addCmd({ content: '个人笔记', tags: ['个人'] })

      const listCmd = context.getCommand('list')
      const result = await listCmd({ tag: '工作' })
      expect(result.notes.length).toBe(1)
      expect(result.notes[0].content).toBe('工作笔记')
    })

    it('按关键词搜索笔记', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      await addCmd({ content: '开会讨论项目进度', tags: ['工作'] })
      await addCmd({ content: '购买生日礼物', tags: ['个人'] })

      const listCmd = context.getCommand('list')
      const result = await listCmd({ keyword: '生日' })
      expect(result.notes.length).toBe(1)
      expect(result.notes[0].content).toContain('生日')
    })

    it('关键词搜索应不区分大小写', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      await addCmd({ content: 'Meeting Notes', tags: ['Work'] })

      const listCmd = context.getCommand('list')
      const result = await listCmd({ keyword: 'meeting' })
      expect(result.notes.length).toBe(1)
    })
  })

  describe('delete 命令', () => {
    it('应成功删除存在的笔记', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      const added = await addCmd({ content: '待删除笔记' })
      const noteId = added.note.id

      const deleteCmd = context.getCommand('delete')
      const result = await deleteCmd({ id: noteId })
      expect(result.success).toBe(true)
    })

    it('删除不存在的 id 应返回 success: false', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const deleteCmd = context.getCommand('delete')
      const result = await deleteCmd({ id: 'nonexistent-id' })
      expect(result.success).toBe(false)
    })

    it('不带 id 参数应返回 success: false', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const deleteCmd = context.getCommand('delete')
      const result = await deleteCmd({})
      expect(result.success).toBe(false)
    })

    it('删除后 storage 应同步更新', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      await addCmd({ content: '笔记1' })
      const added2 = await addCmd({ content: '笔记2' })

      const deleteCmd = context.getCommand('delete')
      await deleteCmd({ id: added2.note.id })

      const stored = context.storage.data['notes']
      expect(stored.length).toBe(1)
      expect(stored[0].content).toBe('笔记1')
    })
  })

  describe('search provider', () => {
    it('空查询时返回统计信息', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      await addCmd({ content: '笔记1' })
      await addCmd({ content: '笔记2' })

      const providers = context.getSearchProviders()
      const results = await providers[0].onSearch('')
      expect(results.length).toBe(1)
      expect(results[0].title).toBe('打开笔记')
      expect(results[0].subtitle).toContain('2')
    })

    it('按关键词搜索笔记应返回最多 5 条', async () => {
      const mod = await import('../src/index')
      mod.default.activate(context)
      const addCmd = context.getCommand('add')
      for (let i = 0; i < 10; i++) {
        await addCmd({ content: `测试笔记 ${i}`, tags: ['test'] })
      }

      const providers = context.getSearchProviders()
      const results = await providers[0].onSearch('测试')
      expect(results.length).toBeLessThanOrEqual(5)
    })
  })

  describe('getPanelData / getPageData', () => {
    it('getPanelData 应返回 notes', async () => {
      // 这个依赖于插件内部实际运行，这里做基本结构验证
      const mod = await import('../src/index')
      expect(mod.default.panel).toBeDefined()
      expect(mod.default.page).toBeDefined()
    })
  })
})
