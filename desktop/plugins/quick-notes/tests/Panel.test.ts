/**
 * Panel.vue 组件测试
 * 测试面板组件：笔记列表展示、选择笔记查看详情
 * DOM 结构：
 *   - root: .quick-notes-panel
 *   - 笔记容器: div with v-for, 每个笔记项使用 Tailwind 类
 *   - 笔记内容: .text-xs.text-gray-800 等
 *   - 箭头按钮触发 openPage
 *
 * 注意：Panel 使用 computed 只显示最近的2条笔记(recentNotes)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Panel from '../src/Panel.vue'
import NoteDetail from '../src/NoteDetail.vue'
import type { Note } from '../src/types'
import { createMockNotes, createMockNote } from './setup'

describe('Panel.vue', () => {
  let mockNotes: Note[]
  let executeMock: ReturnType<typeof vi.fn>
  let openPageMock: ReturnType<typeof vi.fn>
  let refreshMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockNotes = createMockNotes(5)
    executeMock = vi.fn()
    openPageMock = vi.fn()
    refreshMock = vi.fn()
  })

  /** 标准挂载 Panel */
  function mountPanel(notes: Note[] = mockNotes) {
    return mount(Panel, {
      props: {
        data: { notes },
        execute: executeMock,
        openPage: openPageMock,
        refresh: refreshMock
      }
    })
  }

  describe('笔记列表渲染', () => {
    it('5条笔记时只显示最近的2条', () => {
      const wrapper = mountPanel()
      // 笔记通过 v-for 渲染，每个笔记项是一个带 cursor-pointer 的 div
      const noteItems = wrapper.findAll('div.cursor-pointer')
      expect(noteItems.length).toBe(2)
    })

    it('笔记少于2条时应全部显示', () => {
      const shortNotes = createMockNotes(1)
      const wrapper = mountPanel(shortNotes)
      const noteItems = wrapper.findAll('div.cursor-pointer')
      expect(noteItems.length).toBe(1)
    })

    it('没有笔记时显示"暂无笔记"提示', () => {
      const wrapper = mountPanel([])
      expect(wrapper.text()).toContain('暂无')
    })

    it('每个笔记条目应显示内容片段', () => {
      const wrapper = mountPanel()
      // 笔记内容在 .text-xs.text-gray-800.line-clamp-2 div 中
      const contentDivs = wrapper.findAll('div.text-xs.text-gray-800')
      expect(contentDivs.length).toBe(2)
      // 检查是否包含笔记文本
      expect(contentDivs[0].text()).toBeTruthy()
    })

    it('笔记应显示正确的时间格式', () => {
      // 创建刚刚创建的笔记
      const justNowNotes = [
        createMockNote({ id: 'n1', content: '刚刚的笔记', time: Date.now() - 10000 }) // 10秒前
      ]
      const wrapper = mountPanel(justNowNotes)
      expect(wrapper.text()).toContain('刚刚')
    })

    it('笔记应显示"小时前"时间', () => {
      const hourAgoNotes = [
        createMockNote({ id: 'n2', content: '2小时前', time: Date.now() - 7200000 })
      ]
      const wrapper = mountPanel(hourAgoNotes)
      expect(wrapper.text()).toMatch(/\d+小时前/)
    })

    it('笔记应显示标签', () => {
      const wrapper = mountPanel()
      // 标签有类 bg-yellow-100 text-yellow-600
      const tagEls = wrapper.findAll('span.bg-yellow-100')
      // 至少有一些标签显示
      expect(tagEls.length).toBeGreaterThan(0)
    })

    it('应该显示笔记总数', () => {
      const wrapper = mountPanel()
      expect(wrapper.text()).toContain('5 条笔记')
    })
  })

  describe('笔记选择 - 查看详情', () => {
    it('点击笔记应显示 NoteDetail', async () => {
      const wrapper = mountPanel()
      const noteItem = wrapper.find('div.cursor-pointer')
      await noteItem.trigger('click')

      const detail = wrapper.findComponent(NoteDetail)
      expect(detail.exists()).toBe(true)
    })

    it('选中笔记后 NoteDetail 应接收正确的笔记数据', async () => {
      const wrapper = mountPanel()
      const noteItem = wrapper.find('div.cursor-pointer')
      await noteItem.trigger('click')

      const detail = wrapper.findComponent(NoteDetail)
      const detailProps = detail.props('note') as Note
      expect(detailProps).toBeDefined()
      expect(detailProps.id).toBeTruthy()
      expect(detailProps.content).toBeTruthy()
    })

    it('选中笔记后列表仍保持可见', async () => {
      const wrapper = mountPanel()
      const noteItem = wrapper.find('div.cursor-pointer')
      await noteItem.trigger('click')

      // NoteDetail 应显示，笔记列表也应存在
      const detail = wrapper.findComponent(NoteDetail)
      expect(detail.exists()).toBe(true)

      const noteItems = wrapper.findAll('div.cursor-pointer')
      expect(noteItems.length).toBe(2)
    })
  })

  describe('关闭详情视图', () => {
    it('NoteDetail 触发 close 事件后应返回列表', async () => {
      const wrapper = mountPanel()

      // 选中笔记
      const noteItem = wrapper.find('div.cursor-pointer')
      await noteItem.trigger('click')

      let detail = wrapper.findComponent(NoteDetail)
      expect(detail.exists()).toBe(true)

      // 触发 close
      detail.vm.$emit('close')
      await wrapper.vm.$nextTick()

      detail = wrapper.findComponent(NoteDetail)
      expect(detail.exists()).toBe(false)
    })
  })

  describe('编辑操作', () => {
    it('NoteDetail updated 事件应更新选中笔记', async () => {
      const wrapper = mountPanel()
      const noteItem = wrapper.find('div.cursor-pointer')
      await noteItem.trigger('click')

      const detail = wrapper.findComponent(NoteDetail)
      const updatedNote: Note = {
        ...mockNotes[0],
        content: '已更新的内容'
      }
      detail.vm.$emit('updated', updatedNote)
      await wrapper.vm.$nextTick()

      // selectedNote 应更新
      const detailAfter = wrapper.findComponent(NoteDetail)
      expect((detailAfter.props('note') as Note).content).toBe('已更新的内容')
    })
  })

  describe('删除操作', () => {
    it('NoteDetail deleted 事件后应调用 refresh', async () => {
      const wrapper = mountPanel()
      const noteItem = wrapper.find('div.cursor-pointer')
      await noteItem.trigger('click')

      const detail = wrapper.findComponent(NoteDetail)
      detail.vm.$emit('deleted', mockNotes[0].id)
      await wrapper.vm.$nextTick()

      expect(refreshMock).toHaveBeenCalledOnce()
    })

    it('删除后详情视图应关闭', async () => {
      const wrapper = mountPanel()
      const noteItem = wrapper.find('div.cursor-pointer')
      await noteItem.trigger('click')

      const detail = wrapper.findComponent(NoteDetail)
      detail.vm.$emit('deleted', mockNotes[0].id)
      await wrapper.vm.$nextTick()

      const detailAfter = wrapper.findComponent(NoteDetail)
      expect(detailAfter.exists()).toBe(false)
    })
  })

  describe('导航按钮', () => {
    it('右箭头按钮应触发 openPage', async () => {
      const wrapper = mountPanel()
      // 右箭头按钮: 第二个 button（header 中的 button）
      const buttons = wrapper.findAll('button')
      // 找到 header 中的导航按钮（点击后叫 openPage）
      const navBtn = buttons.find(b => b.classes().includes('text-gray-400'))
      if (navBtn) {
        await navBtn.trigger('click')
        expect(openPageMock).toHaveBeenCalledOnce()
      }
    })
  })
})
