<template>
  <div>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px">
      <h2 style="margin:0">工作空间</h2>
      <el-button type="primary" :icon="Plus" @click="showCreate = true">创建工作空间</el-button>
    </div>

    <div v-if="store.loading" style="text-align:center; padding:40px">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
    </div>

    <el-row v-else :gutter="16">
      <el-col v-for="ws in store.workspaces" :key="ws.id" :span="8" :xs="24" :sm="12" :md="8" :lg="6" style="margin-bottom:16px">
        <el-card shadow="hover">
          <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px">
            <el-icon :size="32" color="#409EFF"><FolderOpened /></el-icon>
            <div>
              <div style="font-weight:600">{{ ws.name }}</div>
              <div style="font-size:12px; color:#909399">{{ ws.bucket }}</div>
            </div>
          </div>
          <p v-if="ws.description" style="font-size:13px; color:#606266; margin:8px 0">
            {{ ws.description }}
          </p>
          <div style="display:flex; gap:16px; font-size:12px; color:#909399; margin:8px 0">
            <span>
              <el-tag :type="ws.sync_enabled ? 'success' : 'info'" size="small">
                {{ ws.sync_enabled ? '同步中' : '未同步' }}
              </el-tag>
            </span>
          </div>
          <div style="display:flex; gap:8px; margin-top:12px">
            <el-button size="small" @click="openWorkspace(ws.id)">打开</el-button>
            <el-button size="small" :icon="Edit" text @click="editWorkspace(ws)" />
            <el-button size="small" :icon="Delete" text type="danger" @click="handleDelete(ws)" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreate" title="创建工作空间" width="400px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="工作空间名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore, WorkspaceItem } from '@/stores/core/workspace'
import { Plus, Loading, FolderOpened, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'

const router = useRouter()
const store = useWorkspaceStore()
const showCreate = ref(false)
const submitting = ref(false)
const form = ref({ name: '', description: '' })

async function handleCreate() {
  if (!form.value.name) return
  submitting.value = true
  try {
    await store.create({ name: form.value.name, description: form.value.description })
    showCreate.value = false
    form.value = { name: '', description: '' }
    ElMessage.success('工作空间创建成功')
  } finally {
    submitting.value = false
  }
}

function openWorkspace(id: number) {
  router.push({ path: '/files', query: { workspace_id: String(id) } })
}

function editWorkspace(ws: WorkspaceItem) {
  form.value = { name: ws.name, description: ws.description || '' }
  showCreate.value = true
}

async function handleDelete(ws: WorkspaceItem) {
  try {
    await ElMessageBox.confirm(`确定删除工作空间"${ws.name}"？此操作不可恢复。`, '确认删除')
    await store.delete(ws.id)
    ElMessage.success('工作空间已删除')
  } catch {
    // cancelled
  }
}

onMounted(() => store.fetchWorkspaces())
</script>
