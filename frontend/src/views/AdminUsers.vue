<template>
  <div class="page-wrapper">
    <div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
      <h2>用户管理</h2>
      <el-button type="primary" @click="showAdd = true">添加用户</el-button>
    </div>
    <div class="page-card">
      <div class="page-card-body">
        <div style="display:flex;gap:12px;margin-bottom:16px">
          <el-input v-model="search" placeholder="搜索用户名或邮箱" prefix-icon="Search" style="max-width:300px" clearable />
          <span style="font-size:13px;color:#909399;line-height:36px">共 {{ filtered.length }} 条</span>
        </div>
        <el-table :data="filtered" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="username" label="用户名" min-width="140" />
          <el-table-column prop="email" label="邮箱" min-width="200" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-switch :model-value="row.is_active" :loading="togglingId === row.id" @change="(v:boolean) => toggleActive(row,v)" />
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="170" />
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="editUser(row)">编辑</el-button>
              <el-popconfirm title="确定删除此用户？" @confirm="deleteUser(row.id)">
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- Add Dialog -->
    <el-dialog v-model="showAdd" title="添加用户" width="420px">
      <el-form ref="addFormRef" :model="addForm" label-width="80px" :rules="rules">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="addForm.username" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="addForm.email" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="addForm.password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>

    <!-- Edit Dialog -->
    <el-dialog v-model="showEdit" title="编辑用户" width="420px">
      <el-form ref="editFormRef" :model="editForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="editForm.username" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="editLoading" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

interface AdminUser { id: number; username: string; email: string; is_active: boolean; created_at: string | null }
const users = ref<AdminUser[]>([])
const loading = ref(false)
const search = ref('')
const togglingId = ref<number | null>(null)

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return q ? users.value.filter(u => u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)) : users.value
})

async function fetchUsers() { loading.value = true; try { const r = await client.get('/auth/users'); users.value = r.data } finally { loading.value = false } }
async function toggleActive(row: AdminUser, val: boolean) {
  togglingId.value = row.id
  try { await client.put(`/auth/users/${row.id}/toggle-active`, { is_active: val }); row.is_active = val; ElMessage.success(val ? '已启用' : '已禁用') }
  catch { ElMessage.error('操作失败') } finally { togglingId.value = null }
}

// Add
const showAdd = ref(false)
const addLoading = ref(false)
const addForm = ref({ username: '', email: '', password: '' })
const rules = { username: [{ required: true, message: '必填' }], email: [{ required: true, message: '必填' }], password: [{ required: true, message: '必填' }] }
async function handleAdd() {
  if (!addForm.value.username || !addForm.value.email || !addForm.value.password) return ElMessage.warning('请填写完整')
  addLoading.value = true
  try { await client.post('/auth/register', addForm.value); ElMessage.success('已添加'); showAdd.value = false; fetchUsers(); addForm.value = { username: '', email: '', password: '' } }
  catch (e: any) { ElMessage.error(e.response?.data?.detail || '添加失败') } finally { addLoading.value = false }
}

// Edit
const showEdit = ref(false)
const editLoading = ref(false)
const editForm = ref({ id: 0, username: '', email: '' })
function editUser(row: AdminUser) { editForm.value = { id: row.id, username: row.username, email: row.email }; showEdit.value = true }
async function handleEdit() {
  if (!editForm.value.username || !editForm.value.email) return ElMessage.warning('请填写完整')
  editLoading.value = true
  try { await client.put(`/auth/users/${editForm.value.id}`, { username: editForm.value.username, email: editForm.value.email }); ElMessage.success('已保存'); showEdit.value = false; fetchUsers() }
  catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') } finally { editLoading.value = false }
}

// Delete
async function deleteUser(id: number) {
  try { await client.delete(`/auth/users/${id}`); ElMessage.success('已删除'); fetchUsers() }
  catch { ElMessage.error('删除失败') }
}

onMounted(fetchUsers)
</script>
