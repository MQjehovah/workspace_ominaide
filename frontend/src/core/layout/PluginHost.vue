<template>
  <div>
    <template v-if="pluginName === 'todo'">
      <h2 style="margin-bottom:16px">待办事项</h2>
      
      <!-- Create Form -->
      <div style="display:flex; gap:8px; margin-bottom:16px">
        <el-input v-model="newTitle" placeholder="添加待办... 按 Enter 创建" @keyup.enter="createTodo" clearable />
        <el-button type="primary" @click="createTodo" :icon="Plus">添加</el-button>
      </div>

      <!-- Kanban Columns -->
      <el-row :gutter="12">
        <el-col :span="8" v-for="col in columns" :key="col.status">
          <el-card shadow="never" style="min-height:300px">
            <template #header>
              <span style="font-weight:600">{{ col.label }}</span>
              <el-tag size="small" style="float:right">{{ todos.filter(t => t.status === col.status).length }}</el-tag>
            </template>
            <div
              v-for="todo in todos.filter(t => t.status === col.status)"
              :key="todo.id"
              class="todo-card"
              draggable="true"
              @dragstart="dragTodo = todo"
              @dragover.prevent
              @drop="moveTodo(todo, col.status)"
            >
              <div style="display:flex; justify-content:space-between; align-items:flex-start">
                <span :style="{ textDecoration: todo.status === 'done' ? 'line-through' : 'none' }">
                  {{ todo.title }}
                </span>
                <el-button text size="small" :icon="Delete" @click="deleteTodo(todo.id)" />
              </div>
              <div v-if="todo.priority > 0" style="margin-top:4px">
                <el-tag :type="priorityType(todo.priority)" size="small">
                  P{{ todo.priority }}
                </el-tag>
              </div>
              <div v-if="todo.tags" style="margin-top:4px; display:flex; gap:4px; flex-wrap:wrap">
                <el-tag v-for="tag in todo.tags" :key="tag" size="small" type="info">{{ tag }}</el-tag>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <div v-else>
      <h2>{{ pluginName }}</h2>
      <p style="color:#909399">插件页面加载中...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { Plus, Delete } from '@element-plus/icons-vue'
import client from '@/api/client'

const route = useRoute()
const pluginName = computed(() => route.params.pluginName as string)

interface TodoItem {
  id: number
  title: string
  status: string
  priority: number
  tags: string[] | null
  description: string | null
  created_at: string
}

const columns = [
  { status: 'pending', label: '待处理' },
  { status: 'in_progress', label: '进行中' },
  { status: 'done', label: '已完成' },
]

const todos = ref<TodoItem[]>([])
const newTitle = ref('')
const dragTodo = ref<TodoItem | null>(null)

async function fetchTodos() {
  try {
    const res = await client.get<TodoItem[]>('/plugins/todo/items')
    todos.value = res.data
  } catch (e) {
    console.warn('Failed to fetch todos (plugin may not be active)')
  }
}

async function createTodo() {
  if (!newTitle.value.trim()) return
  try {
    await client.post('/plugins/todo/items', { title: newTitle.value.trim() })
    newTitle.value = ''
    await fetchTodos()
  } catch (e) {
    console.error('Failed to create todo:', e)
  }
}

async function deleteTodo(id: number) {
  try {
    await client.delete(`/plugins/todo/items/${id}`)
    await fetchTodos()
  } catch (e) {
    console.error('Failed to delete todo:', e)
  }
}

async function moveTodo(todo: TodoItem, newStatus: string) {
  if (todo.status === newStatus) return
  try {
    await client.put(`/plugins/todo/items/${todo.id}`, { status: newStatus })
    await fetchTodos()
  } catch (e) {
    console.error('Failed to update todo status:', e)
  }
}

function priorityType(p: number): string {
  if (p >= 3) return 'danger'
  if (p >= 2) return 'warning'
  return 'info'
}

onMounted(fetchTodos)
</script>

<style scoped>
.todo-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: grab;
  transition: box-shadow 0.2s;
}
.todo-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
</style>
