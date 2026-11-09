<template>
  <div class="page-wrapper">
    <div class="page-header">
      <h2>设备端</h2>
      <span class="muted">手机 / 嵌入式设备 · 实时通道 / 手势 / 固件</span>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="10">
        <el-card shadow="never" class="mb16">
          <template #header>固件更新</template>
          <div v-if="firmware.available">
            后端已发布 <b>v{{ firmware.version }}</b>（{{ Math.round((firmware.size || 0) / 1024) }} KB）
            <div class="muted mt8">设备设置页点两次「检查固件更新」即可升级。</div>
          </div>
          <div v-else class="muted">后端尚未发布固件。把 firmware.bin + version.txt 放到 backend/data/device_firmware/ 即可。</div>
          <el-button class="mt12" size="small" :loading="fwLoading" @click="loadFirmware">重新检查</el-button>
        </el-card>

        <el-card shadow="never">
          <template #header>发送到设备</template>
          <el-input v-model="push.title" placeholder="标题，例如：该喝水了" maxlength="120" />
          <el-input
            v-model="push.body"
            class="mt8"
            type="textarea"
            :rows="3"
            placeholder="正文（可选）"
            maxlength="400"
          />
          <el-button class="mt12" type="primary" :loading="pushLoading" @click="sendPush">推送到设备</el-button>
          <div class="muted mt8">设备会在 1 秒内收到并提示；断网时下次上线补推（保留最近 50 条）。</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-hd">
              <span>手势 → 动作</span>
              <el-tag :type="haConfigured ? 'success' : 'info'" size="small">
                {{ haConfigured ? 'Home Assistant 已配置' : 'Home Assistant 未配置' }}
              </el-tag>
            </div>
          </template>
          <div v-for="g in gestureList" :key="g.key" class="gesture-row">
            <div class="gesture-name">{{ g.label }}<span class="muted">（{{ g.key }}）</span></div>
            <el-input v-model="gestures[g.key].label" placeholder="展示名，例如：摇一摇 → 台灯" />
            <el-input v-model="gestures[g.key].tool" placeholder="MCP 工具名，例如 ha_call_service" />
            <el-input v-model="gestures[g.key].argsText" type="textarea" :rows="3" placeholder='参数 JSON，例如 {"domain":"light","service":"toggle","entity_id":"light.desk"}' />
          </div>
          <el-button class="mt12" type="primary" :loading="gestureSaving" @click="saveGestures">保存手势映射</el-button>
          <el-button class="mt12" @click="loadGestures">重置</el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import client from '@/api/client'

const gestureList = [
  { key: 'flip', label: '翻转' },
  { key: 'shake', label: '摇一摇' },
  { key: 'double_tap', label: '双击' },
  { key: 'pickup', label: '拿起' },
]

const firmware = reactive<any>({ available: false, version: '', size: 0 })
const fwLoading = ref(false)
const haConfigured = ref(false)
const gestures = reactive<Record<string, any>>(
  Object.fromEntries(gestureList.map((g) => [g.key, { label: '', tool: 'ha_call_service', argsText: '{}' }])),
)
const gestureSaving = ref(false)
const push = reactive({ title: '', body: '' })
const pushLoading = ref(false)

async function loadFirmware() {
  fwLoading.value = true
  try {
    const res = await client.get('/device/firmware/latest')
    Object.assign(firmware, res.data || {})
  } catch (e) {
    console.error(e)
  } finally {
    fwLoading.value = false
  }
}

async function loadGestures() {
  try {
    const res = await client.get('/device/gestures')
    const raw = res.data?.gestures || {}
    haConfigured.value = !!res.data?.ha_configured
    for (const g of gestureList) {
      const item = raw[g.key] || {}
      gestures[g.key] = {
        label: item.label || '',
        tool: item.tool || 'ha_call_service',
        argsText: JSON.stringify(item.args || {}, null, 2),
      }
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('加载手势配置失败')
  }
}

async function saveGestures() {
  gestureSaving.value = true
  try {
    const payload: Record<string, any> = {}
    for (const g of gestureList) {
      const item = gestures[g.key] || {}
      let args: any = {}
      try {
        args = item.argsText ? JSON.parse(item.argsText) : {}
      } catch {
        ElMessage.error(`${g.label} 的参数不是合法 JSON`)
        return
      }
      if (item.tool) payload[g.key] = { tool: item.tool, args, label: item.label || g.label }
    }
    await client.put('/device/gestures', { gestures: payload })
    ElMessage.success('手势映射已保存')
    await loadGestures()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    gestureSaving.value = false
  }
}

async function sendPush() {
  if (!push.title.trim()) return
  pushLoading.value = true
  try {
    await client.post('/device/push', { title: push.title.trim(), body: push.body.trim() })
    ElMessage.success('已发送到设备')
    push.title = ''
    push.body = ''
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '发送失败')
  } finally {
    pushLoading.value = false
  }
}

onMounted(() => {
  loadFirmware()
  loadGestures()
})
</script>

<style scoped>
.page-header { display: flex; align-items: baseline; gap: 12px; }
.muted { color: #909399; font-size: 12px; }
.mt8 { margin-top: 8px; }
.mt12 { margin-top: 12px; }
.mb16 { margin-bottom: 16px; }
.card-hd { display: flex; align-items: center; justify-content: space-between; }
.gesture-row { display: grid; grid-template-columns: 120px 1fr; gap: 8px; padding: 12px 0; border-bottom: 1px solid #f0f0f0; }
.gesture-row :deep(.el-input), .gesture-row :deep(.el-textarea) { grid-column: 2; }
.gesture-name { font-weight: 600; font-size: 13px; grid-row: span 3; }
</style>
