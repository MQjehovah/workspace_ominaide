/**
 * types.ts 类型定义测试
 * 验证 Note 类型结构的完整性
 */
import { describe, it, expect } from 'vitest'
import type { Note } from '../src/types'

describe('Note 类型', () => {
  it('应支持构建完整的笔记对象', () => {
    const note: Note = {
      id: 'test-id',
      content: '测试内容',
      tags: ['工作'],
      time: Date.now()
    }
    expect(note.id).toBe('test-id')
    expect(note.content).toBe('测试内容')
    expect(note.tags).toEqual(['工作'])
    expect(note.time).toBeGreaterThan(0)
  })

  it('tags 应为数组类型', () => {
    const note: Note = {
      id: 'test',
      content: '内容',
      tags: [],
      time: 0
    }
    expect(Array.isArray(note.tags)).toBe(true)
  })

  it('id 应为字符串类型', () => {
    const note: Note = {
      id: 'test',
      content: '内容',
      tags: [],
      time: 0
    }
    expect(typeof note.id).toBe('string')
  })

  it('time 应为数字类型（时间戳）', () => {
    const note: Note = {
      id: 'test',
      content: '内容',
      tags: [],
      time: 1700000000000
    }
    expect(typeof note.time).toBe('number')
    // 时间戳应为毫秒级 13 位数
    expect(note.time.toString().length).toBeGreaterThanOrEqual(12)
  })
})
