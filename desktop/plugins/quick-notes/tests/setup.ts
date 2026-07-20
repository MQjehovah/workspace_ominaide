/**
 * 测试环境初始化
 * 提供通用的 mock 数据和辅助函数
 */

import type { Note } from '../src/types'

/** 生成测试笔记数据 */
export function createMockNote(overrides: Partial<Note> = {}): Note {
  return {
    id: `note-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    content: '这是一条测试笔记内容',
    tags: ['test'],
    time: Date.now(),
    ...overrides
  }
}

/** 生成一组测试笔记 */
export function createMockNotes(count: number = 5): Note[] {
  const notes: Note[] = []
  const contents = [
    '开会讨论项目进度安排',
    '购买生日礼物 - 妈妈的生日是下周五',
    '修复登录页面的样式问题',
    '整理读书笔记 - 《设计模式》',
    '预约牙医 - 周三下午3点',
    '更新API文档 - 新增用户接口',
    '准备周五的团队分享PPT',
    '服务器迁移 - 检查所有服务状态',
    '学习Vue3组合式API',
    '写周报 - 本周完成情况汇总'
  ]
  const tags = ['工作', '个人', '学习', '健康', '重要']

  for (let i = 0; i < count; i++) {
    notes.push({
      id: `note-${i + 1}`,
      content: contents[i % contents.length],
      tags: [tags[i % tags.length]],
      time: Date.now() - i * 3600000 // 每笔记间隔1小时
    })
  }
  return notes
}
