/**
 * NoteDetail.vue 组件测试
 * 测试笔记详情组件：查看、编辑、保存、删除功能
 *
 * DOM 结构：
 *   - root: .note-detail-card
 *   - header: .detail-header -> .detail-close-btn (关闭)
 *   - meta: .detail-meta -> span.text-xs.text-gray-400 (时间)
 *   - tags: .detail-tags -> span.bg-yellow-100 (标签)
 *   - body: .detail-body -> .detail-content (内容) / #detail-edit-input (编辑)
 *   - actions: .detail-actions -> .action-btn (按钮组)
 *   - 编辑按钮: .action-btn-edit
 *   - 保存按钮: .action-btn-save
 *   - 取消按钮: .action-btn-cancel
 *   - 删除按钮: .action-btn-delete
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import NoteDetail from '../src/NoteDetail.vue'
import type { Note } from '../src/types'
import { createMockNote } from './setup'

describe('NoteDetail.vue', () => {
  let mockNote: Note
  let executeMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockNote = createMockNote({
      id: 'test-note-1',
      content: '这是一条测试笔记内容，用于验证详情视图功能。',
      tags: ['工作', '重要'],
      time: Date.now() - 7200000 // 2小时前
    })
    executeMock = vi.fn()
  })

  /** 标准挂载 NoteDetail */
  function mountDetail(note: Note = mockNote) {
    return mount(NoteDetail, {
      props: {
        note,
        execute: executeMock
      }
    })
  }

  describe('笔记详情展示', () => {
    it('应该显示笔记的完整内容', () => {
      const wrapper = mountDetail()
      expect(wrapper.text()).toContain(mockNote.content)
    })

    it('应该显示笔记标签', () => {
      const wrapper = mountDetail()
      mockNote.tags.forEach(tag => {
        expect(wrapper.text()).toContain(tag)
      })
    })

    it('时间应显示相对时间（2小时前）', () => {
      const wrapper = mountDetail()
      // 时间在 span.text-xs.text-gray-400 中
      const timeSpan = wrapper.find('span.text-xs.text-gray-400')
      expect(timeSpan.exists()).toBe(true)
      const timeText = timeSpan.text()
      expect(timeText).toMatch(/刚刚|\d+分钟前|\d+小时前|\d+天前/)
    })

    it('标签应在 .detail-tags 容器中', () => {
      const wrapper = mountDetail()
      const tagsContainer = wrapper.find('.detail-tags')
      expect(tagsContainer.exists()).toBe(true)
    })
  })

  describe('视图模式切换', () => {
    it('初始状态应处于查看模式（无 textarea）', () => {
      const wrapper = mountDetail()
      expect(wrapper.find('textarea').exists()).toBe(false)
    })

    it('初始状态内容应在 .detail-content 中', () => {
      const wrapper = mountDetail()
      expect(wrapper.find('.detail-content').exists()).toBe(true)
      expect(wrapper.find('.detail-content').text()).toBe(mockNote.content)
    })

    it('点击编辑按钮应切换到编辑模式', async () => {
      const wrapper = mountDetail()
      const editBtn = wrapper.find('.action-btn-edit')
      expect(editBtn.exists()).toBe(true)
      await editBtn.trigger('click')

      // 编辑模式应有 textarea
      const textarea = wrapper.find('#detail-edit-input')
      expect(textarea.exists()).toBe(true)
      // 内容区域应消失
      expect(wrapper.find('.detail-content').exists()).toBe(false)
    })

    it('点击取消按钮应返回查看模式', async () => {
      const wrapper = mountDetail()
      await wrapper.find('.action-btn-edit').trigger('click')
      expect(wrapper.find('textarea').exists()).toBe(true)

      const cancelBtn = wrapper.find('.action-btn-cancel')
      expect(cancelBtn.exists()).toBe(true)
      await cancelBtn.trigger('click')

      expect(wrapper.find('textarea').exists()).toBe(false)
      expect(wrapper.find('.detail-content').exists()).toBe(true)
    })
  })

  describe('内容编辑', () => {
    it('编辑模式下 textarea 应填充当前内容', async () => {
      const wrapper = mountDetail()
      await wrapper.find('.action-btn-edit').trigger('click')
      const textarea = wrapper.find('#detail-edit-input')
      expect(textarea.exists()).toBe(true)
      expect(textarea.element.value).toBe(mockNote.content)
    })

    it('编辑模式下可以修改内容', async () => {
      const wrapper = mountDetail()
      await wrapper.find('.action-btn-edit').trigger('click')
      const textarea = wrapper.find('#detail-edit-input')
      await textarea.setValue('修改后的笔记内容')
      expect(textarea.element.value).toBe('修改后的笔记内容')
    })
  })

  describe('保存操作', () => {
    it('保存应调用 execute("update", { id, content })', async () => {
      executeMock.mockResolvedValue({ success: true })
      const wrapper = mountDetail()

      await wrapper.find('.action-btn-edit').trigger('click')
      const textarea = wrapper.find('#detail-edit-input')
      await textarea.setValue('修改后的内容')

      const saveBtn = wrapper.find('.action-btn-save')
      await saveBtn.trigger('click')
      await wrapper.vm.$nextTick()

      expect(executeMock).toHaveBeenCalledWith('update', {
        id: mockNote.id,
        content: '修改后的内容'
      })
    })

    it('保存后应触发 updated 事件', async () => {
      executeMock.mockResolvedValue({ success: true })
      const wrapper = mountDetail()

      await wrapper.find('.action-btn-edit').trigger('click')
      await wrapper.find('#detail-edit-input').setValue('新内容')

      await wrapper.find('.action-btn-save').trigger('click')
      await wrapper.vm.$nextTick()

      const updatedEvent = wrapper.emitted('updated')
      expect(updatedEvent).toBeTruthy()
      if (updatedEvent) {
        const updatedNote = updatedEvent[0][0] as Note
        expect(updatedNote.content).toBe('新内容')
        expect(updatedNote.id).toBe(mockNote.id)
      }
    })

    it('保存后应回到查看模式', async () => {
      executeMock.mockResolvedValue({ success: true })
      const wrapper = mountDetail()

      await wrapper.find('.action-btn-edit').trigger('click')
      await wrapper.find('#detail-edit-input').setValue('新内容')
      await wrapper.find('.action-btn-save').trigger('click')
      await wrapper.vm.$nextTick()

      // 编辑模式应退出（textarea 消失，查看模式恢复）
      expect(wrapper.find('textarea').exists()).toBe(false)
      expect(wrapper.find('.detail-content').exists()).toBe(true)
      // 内容显示的是当前的 note prop（单组件测试中 prop 未更新）
      expect(wrapper.find('.detail-content').text()).toBe(mockNote.content)
    })

    it('编辑后未保存取消应恢复到原内容', async () => {
      const wrapper = mountDetail()

      await wrapper.find('.action-btn-edit').trigger('click')
      await wrapper.find('#detail-edit-input').setValue('临时修改但取消')
      await wrapper.find('.action-btn-cancel').trigger('click')

      expect(wrapper.find('.detail-content').text()).toBe(mockNote.content)
    })
  })

  describe('删除操作', () => {
    it('删除按钮应调用 execute("delete", { id })', async () => {
      executeMock.mockResolvedValue({ success: true })
      const wrapper = mountDetail()

      const deleteBtn = wrapper.find('.action-btn-delete')
      expect(deleteBtn.exists()).toBe(true)
      await deleteBtn.trigger('click')
      await wrapper.vm.$nextTick()

      expect(executeMock).toHaveBeenCalledWith('delete', { id: mockNote.id })
    })

    it('删除成功应触发 deleted 事件', async () => {
      executeMock.mockResolvedValue({ success: true })
      const wrapper = mountDetail()

      await wrapper.find('.action-btn-delete').trigger('click')
      await wrapper.vm.$nextTick()

      const deletedEvent = wrapper.emitted('deleted')
      expect(deletedEvent).toBeTruthy()
      if (deletedEvent) {
        expect(deletedEvent[0][0]).toBe(mockNote.id)
      }
    })
  })

  describe('关闭操作', () => {
    it('关闭按钮应触发 close 事件', async () => {
      const wrapper = mountDetail()
      const closeBtn = wrapper.find('.detail-close-btn')
      expect(closeBtn.exists()).toBe(true)
      await closeBtn.trigger('click')

      const closeEvent = wrapper.emitted('close')
      expect(closeEvent).toBeTruthy()
    })

    it('按下 ESC 键应触发 close 事件', async () => {
      const wrapper = mountDetail()
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
      await wrapper.vm.$nextTick()

      const closeEvent = wrapper.emitted('close')
      expect(closeEvent).toBeTruthy()
    })

    it('编辑模式下 ESC 键应取消编辑，不触发 close', async () => {
      const wrapper = mountDetail()
      await wrapper.find('.action-btn-edit').trigger('click')
      expect(wrapper.find('textarea').exists()).toBe(true)

      // 编辑模式下 ESC
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
      await wrapper.vm.$nextTick()

      // 应取消编辑回到查看模式
      expect(wrapper.find('textarea').exists()).toBe(false)
      expect(wrapper.find('.detail-content').exists()).toBe(true)

      // 不应触发 close
      expect(wrapper.emitted('close')).toBeFalsy()
    })
  })

  describe('边界情况', () => {
    it('内容为空时仍能正常渲染', () => {
      const emptyNote = createMockNote({ content: '' })
      const wrapper = mountDetail(emptyNote)
      expect(wrapper.exists()).toBe(true)
    })

    it('无标签笔记应隐藏标签区域', () => {
      const noTagNote = createMockNote({ tags: [] })
      const wrapper = mountDetail(noTagNote)
      expect(wrapper.find('.detail-tags').exists()).toBe(false)
    })

    it('长内容笔记应正常显示', () => {
      const longContent = 'A'.repeat(10000)
      const longNote = createMockNote({ content: longContent })
      const wrapper = mountDetail(longNote)
      expect(wrapper.text()).toContain(longContent)
    })
  })
})
