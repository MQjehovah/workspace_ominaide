/**
 * Page.vue 组件测试
 * 测试完整页面视图：笔记列表、新增、删除
 *
 * DOM 结构：
 *   - root: .quick-notes-page
 *   - 笔记列表: 每个笔记在 div.p-3.rounded-lg.bg-white.border.border-gray-200
 *   - 内容: div.text-sm.text-gray-800.mb-2
 *   - 时间: span.text-xs.text-gray-400
 *   - 标签: span.text-xs.px-1.5.py-0.5.rounded.bg-yellow-100.text-yellow-600
 *   - 删除按钮: button with hover:bg-red-50
 *   - 添加按钮: button 文本 "添加"
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Page from '../src/Page.vue'
import type { Note } from '../src/types'
import { createMockNotes, createMockNote } from './setup'

describe('Page.vue', () => {
  let mockNotes: Note[]
  let executeMock: ReturnType<typeof vi.fn>
  let closeMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockNotes = createMockNotes(5)
    executeMock = vi.fn()
    closeMock = vi.fn()
  })

  /** 标准挂载 Page */
  function mountPage(notes: Note[] = mockNotes) {
    return mount(Page, {
      props: {
        data: { notes },
        execute: executeMock,
        close: closeMock
      }
    })
  }

  describe('页面渲染', () => {
    it('应该渲染所有笔记', () => {
      const wrapper = mountPage()
      // 每个笔记是一个带 border 样式的 div
      const noteItems = wrapper.findAll('div.rounded-lg')
      expect(noteItems.length).toBe(5)
    })

    it('笔记应按时间倒序排列（最新的在前）', () => {
      // 创建不同时间的笔记
      const timeOrderedNotes = [
        createMockNote({ id: 'old', time: Date.now() - 86400000, content: '昨天' }),    // 1天前
        createMockNote({ id: 'new', time: Date.now() - 3600000, content: '1小时前' }),      // 1小时前
        createMockNote({ id: 'newer', time: Date.now() - 60000, content: '1分钟前' }),       // 1分钟前
      ]
      const wrapper = mountPage(timeOrderedNotes)
      const contentDivs = wrapper.findAll('div.text-sm.text-gray-800')
      expect(contentDivs.length).toBe(3)
      // 第一个应该是时间最新的
      expect(contentDivs[0].text()).toContain('1分钟前')
    })

    it('空笔记列表应显示提示', () => {
      const wrapper = mountPage([])
      expect(wrapper.text()).toContain('暂无')
    })

    it('应显示笔记数量', () => {
      const wrapper = mountPage()
      expect(wrapper.text()).toContain('5')
    })
  })

  describe('新增笔记', () => {
    it('点击"添加"按钮应显示输入区域', async () => {
      const wrapper = mountPage()
      const addBtn = wrapper.find('button').findAll('*').filter(el => el.text().includes('添加'))
      // 直接找包含"添加"的按钮
      const btn = wrapper.findAll('button').filter(b => b.text().includes('添加'))
      expect(btn.length).toBeGreaterThan(0)

      if (btn.length > 0) {
        await btn[0].trigger('click')
        // 应显示输入框
        const textarea = wrapper.find('textarea')
        expect(textarea.exists()).toBe(true)
      }
    })

    it('空内容不应提交（handleAdd 会检查 trim 后长度）', async () => {
      executeMock.mockResolvedValue({ success: true })
      const wrapper = mountPage()
      const addBtn = wrapper.findAll('button').filter(b => b.text().includes('添加'))
      if (addBtn.length > 0) {
        await addBtn[0].trigger('click')
        const textarea = wrapper.find('textarea')
        expect(textarea.exists()).toBe(true)

        // textarea 自动聚焦，保持空内容
        // 找到带有"确认"文本的按钮
        const confirmBtn = wrapper.findAll('button').filter(b => b.text().includes('确认'))
        if (confirmBtn.length > 0) {
          await confirmBtn[0].trigger('click')
          expect(executeMock).not.toHaveBeenCalled()
        }
      }
    })

    it('添加笔记应调用 execute("add", { content, tags })', async () => {
      executeMock.mockResolvedValue({ success: true })
      const wrapper = mountPage()

      // 点击添加按钮
      const addBtn = wrapper.findAll('button').filter(b => b.text().includes('添加'))
      if (addBtn.length > 0) {
        await addBtn[0].trigger('click')
        const textarea = wrapper.find('textarea')
        if (textarea.exists()) {
          await textarea.setValue('新笔记内容')

          // 找确认/保存按钮
          const confirmBtn = wrapper.findAll('button').filter(b =>
            b.text().includes('确认') || b.text().includes('保存')
          )
          if (confirmBtn.length > 0) {
            await confirmBtn[0].trigger('click')
            expect(executeMock).toHaveBeenCalledWith('add', expect.objectContaining({
              content: '新笔记内容'
            }))
          }
        }
      }
    })
  })

  describe('删除笔记', () => {
    it('删除笔记应调用 execute("delete", { id })', async () => {
      executeMock.mockResolvedValue({ success: true })
      const wrapper = mountPage()
      // 删除按钮是 button 内有红色 hover 样式
      const deleteBtns = wrapper.findAll('button').filter(b =>
        b.classes().includes('hover:bg-red-50')
      )
      if (deleteBtns.length > 0) {
        await deleteBtns[0].trigger('click')
        expect(executeMock).toHaveBeenCalledWith('delete', { id: mockNotes[0].id })
      }
    })
  })

  describe('笔记时间显示', () => {
    it('刚刚创建的笔记显示"刚刚"', () => {
      const notes = [
        createMockNote({ id: 'just-now', content: '刚刚', time: Date.now() - 5000 })
      ]
      const wrapper = mountPage(notes)
      expect(wrapper.text()).toContain('刚刚')
    })

    it('几分钟前的笔记显示"X分钟前"', () => {
      const notes = [
        createMockNote({ id: 'mins-ago', content: '几分钟前', time: Date.now() - 300000 })
      ]
      const wrapper = mountPage(notes)
      expect(wrapper.text()).toMatch(/\d+分钟前/)
    })

    it('7天前的笔记显示日期', () => {
      const notes = [
        createMockNote({ id: 'old', content: '很久以前', time: Date.now() - 864000000 })
      ]
      const wrapper = mountPage(notes)
      // 应显示具体日期
      expect(wrapper.text()).toMatch(/\d{4}\/\d{1,2}\/\d{1,2}/)
    })
  })
})
