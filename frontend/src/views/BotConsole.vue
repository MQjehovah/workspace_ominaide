<template>
  <div class="page-wrapper bot-console">
    <div class="page-header console-header">
      <div>
        <h2>助手管理</h2>
        <p class="sub">管理 Bot 身份、例程、记忆、运行记录与审批</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openBotDialog()">新建 Bot</el-button>
      </div>
    </div>

    <div class="console-grid">
      <aside class="page-card bot-list">
        <div class="panel-title">
          <span>Bots</span>
          <span class="count">{{ bots.length }}</span>
        </div>
        <button
          v-for="b in bots"
          :key="b.id"
          class="bot-item"
          :class="{ active: b.id === selectedId }"
          @click="selectBot(b.id)"
        >
          <span class="bot-avatar">{{ b.avatar || '🤖' }}</span>
          <span class="bot-meta">
            <span class="bot-name">
              {{ b.name }}
              <el-tag v-if="b.is_default" size="small" type="success" effect="plain">默认</el-tag>
            </span>
            <span class="bot-role">{{ b.role || b.slug }}</span>
          </span>
        </button>
        <div v-if="bots.length === 0" class="empty-hint">还没有 Bot，点右上角新建。</div>
      </aside>

      <section v-if="selectedBot" class="bot-main">
        <div class="page-card bot-head">
          <div class="bot-identity">
            <span class="big-avatar">{{ selectedBot.avatar || '🤖' }}</span>
            <div>
              <h3>{{ selectedBot.name }}</h3>
              <p>{{ selectedBot.role || '未设置职责' }} · <code>{{ selectedBot.slug }}</code></p>
            </div>
          </div>
          <div class="head-actions">
            <el-button v-if="!selectedBot.is_default" @click="makeDefault">设为默认</el-button>
            <el-button :icon="Edit" @click="openBotDialog(selectedBot)">编辑</el-button>
            <el-popconfirm
              v-if="!selectedBot.is_default"
              title="归档这个 Bot？归档后不再出现在列表里。"
              @confirm="archiveBot"
            >
              <template #reference>
                <el-button type="danger" plain>归档</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>

        <el-tabs v-model="tab" class="bot-tabs" @tab-change="onTabChange">
          <el-tab-pane label="设置" name="settings">
            <div class="page-card">
              <div class="page-card-body">
                <el-form :model="botForm" label-width="120px" class="bot-form">
                  <div class="form-grid">
                    <el-form-item label="名称">
                      <el-input v-model="botForm.name" placeholder="例如：写作助手" />
                    </el-form-item>
                    <el-form-item label="头像">
                      <el-input v-model="botForm.avatar" placeholder="emoji 或图片 URL" />
                    </el-form-item>
                    <el-form-item label="职责">
                      <el-input v-model="botForm.role" placeholder="一句话描述这个 Bot 负责什么" />
                    </el-form-item>
                    <el-form-item label="模型">
                      <el-input v-model="botForm.model" placeholder="留空使用全局 LLM_MODEL" />
                    </el-form-item>
                    <el-form-item label="温度">
                      <el-input-number v-model="botForm.temperature" :min="0" :max="2" :step="0.1" />
                    </el-form-item>
                    <el-form-item label="最大轮次">
                      <el-input-number v-model="botForm.max_turns" :min="1" :max="50" />
                    </el-form-item>
                    <el-form-item label="允许的工具" class="span-2">
                      <el-input v-model="botForm.allowed_tools" placeholder="留空 = 全部工具；多个用逗号分隔" />
                    </el-form-item>
                    <el-form-item label="风险策略" class="span-2">
                      <el-input
                        v-model="botForm.risk_policy"
                        type="textarea"
                        :rows="3"
                        placeholder='JSON，例如 {"exec":"ask","external":"ask","tools":{"shell.exec":"deny"}}'
                      />
                    </el-form-item>
                    <el-form-item label="System Prompt" class="span-2">
                      <el-input v-model="botForm.system_prompt" type="textarea" :rows="7" />
                    </el-form-item>
                    <el-form-item label="设为默认">
                      <el-switch v-model="botForm.is_default" />
                    </el-form-item>
                  </div>
                  <div class="form-actions">
                    <el-button @click="resetBotForm">重置</el-button>
                    <el-button type="primary" :loading="savingBot" @click="saveBot">保存设置</el-button>
                  </div>
                </el-form>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="例程" name="routines">
            <div class="page-card">
              <div class="page-card-body">
                <div class="section-head">
                  <div>
                    <h4>触发器</h4>
                    <p>定时或事件触发后，Bot 会创建一条 run。</p>
                  </div>
                  <div style="display:flex;gap:8px;flex-wrap:wrap">
                    <el-button :icon="Grid" @click="openTemplates">模板</el-button>
                    <el-button :icon="MagicStick" @click="openNL">一句话创建</el-button>
                    <el-button type="primary" :icon="Plus" @click="openRoutineDialog()">新建例程</el-button>
                  </div>
                </div>
                <el-table :data="routines" size="small" empty-text="还没有例程">
                  <el-table-column prop="name" label="名称" min-width="140" />
                  <el-table-column label="触发" min-width="150">
                    <template #default="{ row }">
                      <el-tag size="small" :type="row.trigger_type === 'cron' ? 'primary' : 'warning'">
                        {{ row.trigger_type }}
                      </el-tag>
                      <span class="mono muted">{{ row.cron_expr || row.event_type || '' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="启用" width="80">
                    <template #default="{ row }">
                      <el-switch v-model="row.enabled" @change="onRoutineToggle(row, $event)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="下次运行" min-width="150">
                    <template #default="{ row }">{{ fmtLocal(row.next_run_at) }}</template>
                  </el-table-column>
                  <el-table-column label="上次状态" width="100">
                    <template #default="{ row }">
                      <el-tag v-if="row.last_status" size="small" :type="row.last_status === 'error' ? 'danger' : 'info'">
                        {{ row.last_status }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="300" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="primary" :icon="VideoPlay" @click="runRoutine(row)">运行</el-button>
                      <el-button link @click="openDryRun(row)">试运行</el-button>
                      <el-button link @click="openRoutineRuns(row)">记录</el-button>
                      <el-button link @click="openRoutineDialog(row)">编辑</el-button>
                      <el-popconfirm title="删除这个例程？" @confirm="deleteRoutine(row)">
                        <template #reference><el-button link type="danger">删除</el-button></template>
                      </el-popconfirm>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="记忆" name="memories">
            <div class="page-card">
              <div class="page-card-body">
                <div class="section-head">
                  <div>
                    <h4>长期记忆</h4>
                    <p>只属于当前 Bot；共享事实仍在用户画像里。</p>
                  </div>
                  <el-button type="primary" :icon="Plus" @click="openMemoryDialog">添加记忆</el-button>
                </div>
                <el-table :data="memories" size="small" empty-text="还没有记忆">
                  <el-table-column prop="kind" label="类型" width="110" />
                  <el-table-column prop="content" label="内容" min-width="320" show-overflow-tooltip />
                  <el-table-column prop="importance" label="权重" width="80" />
                  <el-table-column label="创建" width="150">
                    <template #default="{ row }">{{ fmt(row.created_at) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="80">
                    <template #default="{ row }">
                      <el-popconfirm title="删除这条记忆？" @confirm="deleteMemory(row)">
                        <template #reference><el-button link type="danger">删除</el-button></template>
                      </el-popconfirm>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="运行" name="runs">
            <div class="page-card">
              <div class="page-card-body">
                <div class="section-head">
                  <div>
                    <h4>运行记录</h4>
                    <p>每次对话、例程、手动触发都会留下一条 run。</p>
                  </div>
                  <div class="section-actions">
                    <el-button :icon="Refresh" @click="loadRuns">刷新</el-button>
                    <el-button type="primary" :icon="Plus" @click="openQuickRun">发起运行</el-button>
                  </div>
                </div>
                <el-table :data="runs" size="small" empty-text="还没有运行记录" @row-click="openRun">
                  <el-table-column prop="id" label="#" width="60" />
                  <el-table-column label="状态" width="130">
                    <template #default="{ row }">
                      <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="trigger" label="触发" width="90" />
                  <el-table-column prop="input" label="输入" min-width="220" show-overflow-tooltip />
                  <el-table-column label="输出" min-width="220" show-overflow-tooltip>
                    <template #default="{ row }">{{ row.output || row.error || '' }}</template>
                  </el-table-column>
                  <el-table-column label="时间" width="150">
                    <template #default="{ row }">{{ fmt(row.created_at) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="110" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="primary" @click.stop="openRun(row)">详情</el-button>
                      <el-button
                        v-if="!isTerminal(row.status)"
                        link
                        type="danger"
                        @click.stop="cancelRun(row)"
                      >取消</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane name="approvals">
            <template #label>
              审批
              <el-badge v-if="pendingApprovals" :value="pendingApprovals" class="tab-badge" />
            </template>
            <div class="page-card">
              <div class="page-card-body">
                <div class="section-head">
                  <div>
                    <h4>待审批动作</h4>
                    <p>exec / external 类工具默认会暂停，等待你允许或拒绝。</p>
                  </div>
                  <el-button :icon="Refresh" @click="loadApprovals">刷新</el-button>
                </div>
                <el-table :data="approvals" size="small" empty-text="没有待审批动作">
                  <el-table-column label="Bot" width="120">
                    <template #default="{ row }">{{ botName(row.bot_id) }}</template>
                  </el-table-column>
                  <el-table-column prop="run_id" label="Run" width="70" />
                  <el-table-column prop="tool_name" label="工具" min-width="150" />
                  <el-table-column prop="risk_level" label="风险" width="90">
                    <template #default="{ row }">
                      <el-tag size="small" type="danger" effect="plain">{{ row.risk_level }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="参数" min-width="240">
                    <template #default="{ row }">
                      <code class="args">{{ compactArgs(row.arguments) }}</code>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="160" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="success" @click="decide(row, true)">允许</el-button>
                      <el-button link type="success" @click="decide(row, true, true)">总是允许</el-button>
                      <el-button link type="danger" @click="decide(row, false)">拒绝</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>

      <section v-else class="page-card empty-main">
        <el-icon :size="32"><MagicStick /></el-icon>
        <h3>选择或新建一个 Bot</h3>
        <p>每个 Bot 有独立人格、记忆、工具权限和例程。</p>
      </section>
    </div>

    <!-- Bot dialog -->
    <el-dialog v-model="botDialog" :title="editingBotId ? '编辑 Bot' : '新建 Bot'" width="640px">
      <el-form :model="botForm" label-width="110px">
        <el-form-item label="名称"><el-input v-model="botForm.name" /></el-form-item>
        <el-form-item label="头像"><el-input v-model="botForm.avatar" placeholder="🤖" /></el-form-item>
        <el-form-item label="职责"><el-input v-model="botForm.role" /></el-form-item>
        <el-form-item label="模型"><el-input v-model="botForm.model" placeholder="留空使用全局模型" /></el-form-item>
        <el-form-item label="温度"><el-input-number v-model="botForm.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
        <el-form-item label="最大轮次"><el-input-number v-model="botForm.max_turns" :min="1" :max="50" /></el-form-item>
        <el-form-item label="System Prompt">
          <el-input v-model="botForm.system_prompt" type="textarea" :rows="5" />
        </el-form-item>
        <el-form-item label="默认 Bot"><el-switch v-model="botForm.is_default" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="botDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingBot" @click="saveBot">保存</el-button>
      </template>
    </el-dialog>

    <!-- Routine dialog -->
    <el-dialog v-model="routineDialog" :title="editingRoutineId ? '编辑例程' : '新建例程'" width="560px">
      <el-form :model="routineForm" label-width="100px">
        <el-form-item label="名称"><el-input v-model="routineForm.name" /></el-form-item>
        <el-form-item label="触发方式">
          <el-radio-group v-model="routineForm.trigger_type">
            <el-radio-button label="cron">定时</el-radio-button>
            <el-radio-button label="event">事件</el-radio-button>
            <el-radio-button label="manual">手动</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="routineForm.trigger_type === 'cron'" label="cron">
          <el-input v-model="routineForm.cron_expr" placeholder="30 7 * * *（每天 7:30）" />
        </el-form-item>
        <el-form-item v-if="routineForm.trigger_type === 'event'" label="事件类型">
          <el-input v-model="routineForm.event_type" placeholder="例如 schedule.created" />
        </el-form-item>
        <el-form-item v-if="routineForm.trigger_type === 'event'" label="事件过滤">
          <el-input v-model="routineForm.event_filter" placeholder='可选 JSON，例如 {"provider":"rss"}' />
        </el-form-item>
        <el-form-item label="Prompt">
          <el-input v-model="routineForm.prompt" type="textarea" :rows="5" placeholder="触发时交给 Bot 的任务" />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="routineForm.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="routineDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingRoutine" @click="saveRoutine">保存</el-button>
      </template>
    </el-dialog>

    <!-- Automation templates -->
    <el-dialog v-model="templateDialog" title="自动化模板" width="760px">
      <p class="muted" style="margin-top:0">选择一个模板，立即为当前 Bot 创建例程；创建后可在列表中调整时间和 Prompt。</p>
      <div v-loading="loadingTemplates" class="tpl-grid">
        <div v-for="t in templates" :key="t.key" class="tpl-card" @click="useTemplate(t)">
          <div class="tpl-head">
            <span class="tpl-name">{{ t.name }}</span>
            <el-tag size="small" :type="t.trigger_type === 'cron' ? 'primary' : 'warning'">
              {{ t.trigger_type === 'cron' ? t.cron_expr : t.event_type }}
            </el-tag>
          </div>
          <div class="tpl-desc">{{ t.description }}</div>
          <div class="tpl-action">点击创建 →</div>
        </div>
      </div>
    </el-dialog>

    <!-- Natural-language rule -->
    <el-dialog v-model="nlDialog" title="用一句话创建自动化" width="580px">
      <el-input
        v-model="nlText"
        type="textarea"
        :rows="3"
        placeholder="例如：每天 8:30 帮我总结今天的日程和待办；每次上传文件后帮我生成摘要"
      />
      <div v-if="nlDraft" class="nl-preview">
        <div><b>{{ nlDraft.name }}</b></div>
        <div class="muted">
          {{ nlDraft.trigger_type === 'cron' ? `定时：${nlDraft.cron_expr}` : `事件：${nlDraft.event_type || '手动'}` }}
          <span v-if="nlDraft.explanation"> · {{ nlDraft.explanation }}</span>
        </div>
        <div class="nl-prompt">{{ nlDraft.prompt }}</div>
      </div>
      <template #footer>
        <el-button @click="nlDialog = false">取消</el-button>
        <el-button :loading="parsingNL" @click="parseNL">解析</el-button>
        <el-button type="primary" :disabled="!nlDraft" @click="applyNLDraft">继续编辑并保存</el-button>
      </template>
    </el-dialog>

    <!-- Dry run -->
    <el-dialog v-model="dryDialog" title="试运行（不会执行）" width="620px">
      <div v-if="dryResult">
        <el-alert type="warning" :closable="false" show-icon
          title="试运行只生成执行计划，不会调用工具、读取文件或修改数据。" />
        <div class="detail-block" style="margin-top:14px">
          <div class="muted">触发条件</div>
          <div>{{ dryResult.trigger }}</div>
        </div>
        <div v-if="dryResult.schedule?.next_runs?.length" class="detail-block">
          <div class="muted">接下来三次</div>
          <div v-for="t in dryResult.schedule.next_runs" :key="t">{{ t }}</div>
        </div>
        <div class="detail-block">
          <div class="muted">任务</div>
          <pre>{{ dryResult.prompt }}</pre>
        </div>
        <div class="detail-block">
          <div class="muted">执行计划</div>
          <pre>{{ dryResult.plan }}</pre>
        </div>
      </div>
    </el-dialog>

    <!-- Routine run history -->
    <el-drawer v-model="routineRunsDrawer" :title="`例程记录 · ${routineRunsTitle}`" size="620px">
      <div v-loading="routineRunsLoading">
        <div class="muted" style="margin-bottom:10px">
          近 30 天：{{ routineRunStats.total || 0 }} 次
          <span v-for="(cnt, st) in routineRunStats.by_status || {}" :key="st"> · {{ st }} {{ cnt }}</span>
        </div>
        <el-table :data="routineRuns" size="small" empty-text="还没有运行记录" @row-click="openRun">
          <el-table-column prop="id" label="#" width="70" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="trigger" label="触发" width="90" />
          <el-table-column label="时间" width="160">
            <template #default="{ row }">{{ fmt(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="输出" min-width="160">
            <template #default="{ row }">
              <span class="muted">{{ (row.output || row.error || '').slice(0, 80) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <!-- Memory dialog -->
    <el-dialog v-model="memoryDialog" title="添加记忆" width="520px">
      <el-form :model="memoryForm" label-width="80px">
        <el-form-item label="内容">
          <el-input v-model="memoryForm.content" type="textarea" :rows="4" placeholder="一条独立、自含的事实或偏好" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="memoryForm.kind" style="width:100%">
            <el-option value="fact" label="事实" />
            <el-option value="preference" label="偏好" />
            <el-option value="summary" label="摘要" />
            <el-option value="skill" label="技能" />
          </el-select>
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="memoryForm.importance" :min="0" :max="1" :step="0.1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memoryDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingMemory" @click="saveMemory">保存</el-button>
      </template>
    </el-dialog>

    <!-- Quick run dialog -->
    <el-dialog v-model="runDialog" title="发起一次运行" width="520px">
      <el-form :model="runForm" label-width="80px">
        <el-form-item label="任务">
          <el-input v-model="runForm.prompt" type="textarea" :rows="4" placeholder="交给这个 Bot 的任务" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingRun" @click="createRun">开始</el-button>
      </template>
    </el-dialog>

    <!-- Run drawer -->
    <el-drawer v-model="runDrawer" :title="`Run #${runDetail?.id || ''}`" size="680px">
      <template v-if="runDetail">
        <div class="run-summary">
          <el-tag :type="statusType(runDetail.status)">{{ runDetail.status }}</el-tag>
          <span class="muted">触发：{{ runDetail.trigger }}</span>
          <span class="muted">创建：{{ fmt(runDetail.created_at) }}</span>
          <span class="muted">结束：{{ fmt(runDetail.finished_at) }}</span>
          <el-button
            v-if="!isTerminal(runDetail.status)"
            size="small"
            type="danger"
            plain
            @click="cancelRun(runDetail)"
          >取消</el-button>
        </div>
        <div class="detail-block">
          <h4>输入</h4>
          <pre>{{ runDetail.input || '(空)' }}</pre>
        </div>
        <div v-if="runDetail.error" class="detail-block">
          <h4>错误</h4>
          <pre class="error">{{ runDetail.error }}</pre>
        </div>
        <div class="detail-block">
          <h4>输出</h4>
          <pre>{{ runDetail.output || '(还没有输出)' }}</pre>
        </div>
        <div class="detail-block">
          <h4>步骤</h4>
          <el-table :data="runDetail.steps || []" size="small" empty-text="没有工具调用">
            <el-table-column prop="seq" label="#" width="50" />
            <el-table-column prop="type" label="类型" width="90" />
            <el-table-column prop="tool_name" label="工具" min-width="130" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="result" label="结果" min-width="240" show-overflow-tooltip />
          </el-table>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Edit, Grid, MagicStick, Plus, Refresh, VideoPlay,
} from '@element-plus/icons-vue'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'

type TabName = 'settings' | 'routines' | 'memories' | 'runs' | 'approvals'

const route = useRoute()

const bots = ref<any[]>([])
const selectedId = ref<number | null>(null)
const tab = ref<TabName>('settings')
const routines = ref<any[]>([])
const memories = ref<any[]>([])
const runs = ref<any[]>([])
const approvals = ref<any[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const selectedBot = computed(() => bots.value.find(b => b.id === selectedId.value) || null)
const pendingApprovals = computed(() => approvals.value.length)

const botDialog = ref(false)
const editingBotId = ref<number | null>(null)
const savingBot = ref(false)
const botForm = reactive({
  name: '', avatar: '🤖', role: '', system_prompt: '', model: '',
  temperature: 0.7, max_turns: 30, allowed_tools: '', risk_policy: '',
  is_default: false,
})

const routineDialog = ref(false)
const editingRoutineId = ref<number | null>(null)
const savingRoutine = ref(false)
const routineForm = reactive({
  name: '', trigger_type: 'cron', cron_expr: '30 7 * * *',
  event_type: '', event_filter: '', prompt: '', enabled: true,
})

const templateDialog = ref(false)
const templates = ref<any[]>([])
const loadingTemplates = ref(false)
const nlDialog = ref(false)
const nlText = ref('')
const nlDraft = ref<any>(null)
const parsingNL = ref(false)
const dryDialog = ref(false)
const dryResult = ref<any>(null)
const routineRunsDrawer = ref(false)
const routineRuns = ref<any[]>([])
const routineRunsTitle = ref('')
const routineRunsLoading = ref(false)
const routineRunStats = ref<any>({})

const memoryDialog = ref(false)
const savingMemory = ref(false)
const memoryForm = reactive({ content: '', kind: 'fact', importance: 0.5 })

const runDialog = ref(false)
const savingRun = ref(false)
const runForm = reactive({ prompt: '' })

const runDrawer = ref(false)
const runDetail = ref<any>(null)

function fmt(value: string | null | undefined) {
  return value ? formatBackendDate(value) : '—'
}

function fmtLocal(value: string | null | undefined) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function statusType(status: string) {
  return ({
    done: 'success',
    failed: 'danger',
    running: 'warning',
    waiting_approval: 'warning',
    queued: 'info',
    cancelled: 'info',
  } as Record<string, string>)[status] || 'info'
}

function isTerminal(status: string) {
  return ['done', 'failed', 'cancelled'].includes(status)
}

function botName(id: number) {
  return bots.value.find(b => b.id === id)?.name || `#${id}`
}

function compactArgs(args: any) {
  try {
    const text = JSON.stringify(args || {})
    return text.length > 180 ? text.slice(0, 180) + '…' : text
  } catch {
    return String(args)
  }
}

async function loadBots() {
  const r = await client.get('/bots')
  bots.value = r.data || []
  const saved = Number(localStorage.getItem('bot_console_id') || 0)
  if (!selectedId.value || !bots.value.some(b => b.id === selectedId.value)) {
    selectedId.value = bots.value.find(b => b.id === saved)?.id
      || bots.value.find(b => b.is_default)?.id
      || bots.value[0]?.id
      || null
  }
  if (selectedId.value) localStorage.setItem('bot_console_id', String(selectedId.value))
}

function selectBot(id: number) {
  selectedId.value = id
  localStorage.setItem('bot_console_id', String(id))
  loadTab()
}

function resetBotForm() {
  const b = selectedBot.value
  if (!b) return
  editingBotId.value = b.id
  Object.assign(botForm, {
    name: b.name || '',
    avatar: b.avatar || '🤖',
    role: b.role || '',
    system_prompt: b.system_prompt || '',
    model: b.model || '',
    temperature: b.temperature ?? 0.7,
    max_turns: b.max_turns ?? 30,
    allowed_tools: (b.allowed_tools || []).join(', '),
    risk_policy: b.risk_policy ? JSON.stringify(b.risk_policy, null, 2) : '',
    is_default: !!b.is_default,
  })
}

function openBotDialog(bot?: any) {
  editingBotId.value = bot?.id || null
  if (bot) {
    Object.assign(botForm, {
      name: bot.name || '',
      avatar: bot.avatar || '🤖',
      role: bot.role || '',
      system_prompt: bot.system_prompt || '',
      model: bot.model || '',
      temperature: bot.temperature ?? 0.7,
      max_turns: bot.max_turns ?? 30,
      allowed_tools: (bot.allowed_tools || []).join(', '),
      risk_policy: bot.risk_policy ? JSON.stringify(bot.risk_policy, null, 2) : '',
      is_default: !!bot.is_default,
    })
  } else {
    Object.assign(botForm, {
      name: '', avatar: '🤖', role: '', system_prompt: '', model: '',
      temperature: 0.7, max_turns: 30, allowed_tools: '', risk_policy: '',
      is_default: false,
    })
  }
  botDialog.value = true
}

async function saveBot() {
  if (!botForm.name.trim()) {
    ElMessage.warning('Bot 名称不能为空')
    return
  }
  let risk: any = null
  if (botForm.risk_policy.trim()) {
    try {
      risk = JSON.parse(botForm.risk_policy)
    } catch {
      ElMessage.error('风险策略不是合法 JSON')
      return
    }
  }
  const tools = botForm.allowed_tools.trim()
    ? botForm.allowed_tools.split(',').map(x => x.trim()).filter(Boolean)
    : null
  const payload: any = {
    name: botForm.name.trim(),
    avatar: botForm.avatar || null,
    role: botForm.role || null,
    system_prompt: botForm.system_prompt || null,
    model: botForm.model || null,
    temperature: botForm.temperature,
    max_turns: botForm.max_turns,
    allowed_tools: tools,
    risk_policy: risk,
    is_default: botForm.is_default,
  }
  savingBot.value = true
  try {
    if (editingBotId.value) {
      await client.patch(`/bots/${editingBotId.value}`, payload)
      ElMessage.success('已保存')
    } else {
      const r = await client.post('/bots', payload)
      selectedId.value = r.data.id
      ElMessage.success('Bot 已创建')
    }
    botDialog.value = false
    await loadBots()
    await loadTab()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingBot.value = false
  }
}

async function makeDefault() {
  if (!selectedBot.value) return
  try {
    await client.patch(`/bots/${selectedBot.value.id}`, { is_default: true })
    await loadBots()
    ElMessage.success('已设为默认 Bot')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '设置失败')
  }
}

async function archiveBot() {
  if (!selectedBot.value) return
  try {
    await client.delete(`/bots/${selectedBot.value.id}`)
    selectedId.value = null
    await loadBots()
    await loadTab()
    ElMessage.success('已归档')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '归档失败')
  }
}

async function loadRoutines() {
  if (!selectedId.value) return
  const r = await client.get(`/bots/${selectedId.value}/routines`)
  routines.value = r.data || []
}

async function loadMemories() {
  if (!selectedId.value) return
  const r = await client.get(`/bots/${selectedId.value}/memories?limit=200`)
  memories.value = r.data || []
}

async function loadRuns() {
  if (!selectedId.value) return
  const r = await client.get(`/bots/${selectedId.value}/runs?limit=50`)
  runs.value = r.data || []
}

async function loadApprovals() {
  const r = await client.get('/approvals?status=pending')
  approvals.value = r.data || []
}

async function loadTab() {
  if (!selectedId.value) return
  try {
    if (tab.value === 'settings') resetBotForm()
    else if (tab.value === 'routines') await loadRoutines()
    else if (tab.value === 'memories') await loadMemories()
    else if (tab.value === 'runs') await loadRuns()
    else if (tab.value === 'approvals') await loadApprovals()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  }
}

function onTabChange() {
  loadTab()
}

async function refreshAll() {
  await loadBots()
  await loadTab()
  await loadApprovals()
}

function openRoutineDialog(routine?: any) {
  editingRoutineId.value = routine?.id || null
  Object.assign(routineForm, routine ? {
    name: routine.name || '',
    trigger_type: routine.trigger_type || 'cron',
    cron_expr: routine.cron_expr || '30 7 * * *',
    event_type: routine.event_type || '',
    event_filter: routine.event_filter ? JSON.stringify(routine.event_filter, null, 2) : '',
    prompt: routine.prompt || '',
    enabled: routine.enabled !== false,
  } : {
    name: '', trigger_type: 'cron', cron_expr: '30 7 * * *',
    event_type: '', event_filter: '', prompt: '', enabled: true,
  })
  routineDialog.value = true
}

async function saveRoutine() {
  if (!routineForm.name.trim()) {
    ElMessage.warning('例程名称不能为空')
    return
  }
  let filter: any = null
  if (routineForm.event_filter.trim()) {
    try {
      filter = JSON.parse(routineForm.event_filter)
    } catch {
      ElMessage.error('事件过滤不是合法 JSON')
      return
    }
  }
  const payload: any = {
    name: routineForm.name.trim(),
    trigger_type: routineForm.trigger_type,
    cron_expr: routineForm.trigger_type === 'cron' ? routineForm.cron_expr : null,
    event_type: routineForm.trigger_type === 'event' ? routineForm.event_type : null,
    event_filter: routineForm.trigger_type === 'event' ? filter : null,
    prompt: routineForm.prompt || null,
    enabled: routineForm.enabled,
  }
  savingRoutine.value = true
  try {
    if (editingRoutineId.value) {
      await client.patch(`/bots/${selectedId.value}/routines/${editingRoutineId.value}`, payload)
    } else {
      await client.post(`/bots/${selectedId.value}/routines`, payload)
    }
    routineDialog.value = false
    await loadRoutines()
    ElMessage.success('例程已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingRoutine.value = false
  }
}

async function toggleRoutine(row: any, enabled: boolean) {
  try {
    await client.patch(`/bots/${selectedId.value}/routines/${row.id}`, { enabled })
  } catch (e: any) {
    row.enabled = !enabled
    ElMessage.error(e?.response?.data?.detail || '更新失败')
  }
}

function onRoutineToggle(row: any, value: any) {
  toggleRoutine(row, !!value)
}

async function runRoutine(row: any) {
  try {
    const r = await client.post(`/bots/${selectedId.value}/routines/${row.id}/run`)
    ElMessage.success(`已创建 Run #${r.data.id}`)
    tab.value = 'runs'
    await loadRuns()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '触发失败')
  }
}

async function deleteRoutine(row: any) {
  try {
    await client.delete(`/bots/${selectedId.value}/routines/${row.id}`)
    await loadRoutines()
    ElMessage.success('已删除')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

async function openTemplates() {
  templateDialog.value = true
  if (templates.value.length) return
  loadingTemplates.value = true
  try {
    const r = await client.get('/automation/templates')
    templates.value = r.data?.templates || []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载模板失败')
  } finally {
    loadingTemplates.value = false
  }
}

async function useTemplate(t: any) {
  if (!selectedId.value) return
  try {
    await client.post('/automation/from-template', {
      bot_id: selectedId.value,
      template_key: t.key,
    })
    templateDialog.value = false
    await loadRoutines()
    ElMessage.success(`已创建「${t.name}」`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  }
}

function openNL() {
  nlText.value = ''
  nlDraft.value = null
  nlDialog.value = true
}

async function parseNL() {
  if (!nlText.value.trim()) {
    ElMessage.warning('先描述一下这条自动化')
    return
  }
  parsingNL.value = true
  try {
    const r = await client.post('/automation/parse', { text: nlText.value.trim() })
    nlDraft.value = r.data?.draft || null
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '解析失败')
  } finally {
    parsingNL.value = false
  }
}

function applyNLDraft() {
  if (!nlDraft.value) return
  const d = nlDraft.value
  nlDialog.value = false
  openRoutineDialog({
    name: d.name,
    trigger_type: d.trigger_type,
    cron_expr: d.cron_expr,
    event_type: d.event_type,
    event_filter: d.event_filter,
    prompt: d.prompt,
    enabled: true,
  })
}

async function openDryRun(row: any) {
  try {
    const r = await client.post(`/automation/routines/${row.id}/dry-run`)
    dryResult.value = r.data
    dryDialog.value = true
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '试运行失败')
  }
}

async function openRoutineRuns(row: any) {
  routineRunsTitle.value = row.name || `#${row.id}`
  routineRunsDrawer.value = true
  routineRunsLoading.value = true
  try {
    const [runsRes, statsRes] = await Promise.all([
      client.get(`/automation/routines/${row.id}/runs`, { params: { limit: 50 } }),
      client.get(`/automation/routines/${row.id}/stats`, { params: { days: 30 } }),
    ])
    routineRuns.value = runsRes.data || []
    routineRunStats.value = statsRes.data || {}
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载记录失败')
    routineRuns.value = []
    routineRunStats.value = {}
  } finally {
    routineRunsLoading.value = false
  }
}

function openMemoryDialog() {
  memoryForm.content = ''
  memoryForm.kind = 'fact'
  memoryForm.importance = 0.5
  memoryDialog.value = true
}

async function saveMemory() {
  if (!memoryForm.content.trim()) {
    ElMessage.warning('记忆内容不能为空')
    return
  }
  savingMemory.value = true
  try {
    await client.post(`/bots/${selectedId.value}/memories`, {
      content: memoryForm.content.trim(),
      kind: memoryForm.kind,
      importance: memoryForm.importance,
    })
    memoryDialog.value = false
    await loadMemories()
    ElMessage.success('已记住')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingMemory.value = false
  }
}

async function deleteMemory(row: any) {
  try {
    await client.delete(`/bots/${selectedId.value}/memories/${row.id}`)
    await loadMemories()
    ElMessage.success('已删除')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

function openQuickRun() {
  runForm.prompt = ''
  runDialog.value = true
}

async function createRun() {
  if (!runForm.prompt.trim()) {
    ElMessage.warning('任务不能为空')
    return
  }
  savingRun.value = true
  try {
    const r = await client.post(`/bots/${selectedId.value}/runs`, {
      prompt: runForm.prompt.trim(),
      auto_start: true,
    })
    runDialog.value = false
    tab.value = 'runs'
    await loadRuns()
    ElMessage.success(`Run #${r.data.id} 已创建`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  } finally {
    savingRun.value = false
  }
}

async function openRun(row: any) {
  try {
    const r = await client.get(`/runs/${row.id}`)
    runDetail.value = r.data
    runDrawer.value = true
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  }
}

async function cancelRun(row: any) {
  try {
    await client.post(`/runs/${row.id}/cancel`)
    ElMessage.success('已取消')
    await loadRuns()
    if (runDetail.value?.id === row.id) {
      const r = await client.get(`/runs/${row.id}`)
      runDetail.value = r.data
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '取消失败')
  }
}

async function decide(row: any, approved: boolean, remember = false) {
  try {
    await client.post(`/approvals/${row.id}/decision`, { approved, remember })
    ElMessage.success(approved ? (remember ? '已允许并记住' : '已允许') : '已拒绝')
    await loadApprovals()
    await loadRuns()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '审批失败')
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(() => {
    if (tab.value === 'runs' || tab.value === 'approvals') {
      if (tab.value === 'runs') loadRuns().catch(() => {})
      loadApprovals().catch(() => {})
    }
  }, 10000)
}

onMounted(async () => {
  const q = String(route.query.tab || '')
  if (['settings', 'routines', 'memories', 'runs', 'approvals'].includes(q)) {
    tab.value = q as TabName
  }
  await loadBots()
  await loadTab()
  await loadApprovals()
  startPolling()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

watch(() => route.query.tab, (value) => {
  const q = String(value || '')
  if (['settings', 'routines', 'memories', 'runs', 'approvals'].includes(q) && q !== tab.value) {
    tab.value = q as TabName
    loadTab()
  }
})
</script>

<style scoped>
.console-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.console-header .sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.header-actions { display: flex; gap: 8px; flex-shrink: 0; }
.console-grid { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 16px; align-items: start; }
.bot-list { padding: 12px; position: sticky; top: 12px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; font-size: 12px; font-weight: 700; color: #606266; padding: 4px 6px 10px; letter-spacing: .5px; }
.panel-title .count { background: #f0f2f5; color: #909399; border-radius: 10px; padding: 1px 7px; font-size: 11px; }
.bot-item {
  width: 100%; display: flex; gap: 10px; align-items: center; text-align: left;
  padding: 10px; border: 1px solid transparent; border-radius: 10px; background: transparent;
  cursor: pointer; transition: background .15s, border-color .15s;
}
.bot-item:hover { background: #f7f9fc; }
.bot-item.active { background: #eef4ff; border-color: #c6d9ff; }
.bot-avatar { width: 34px; height: 34px; border-radius: 10px; background: #f2f4f8; display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0; }
.bot-meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.bot-name { font-size: 13px; color: #2c3550; font-weight: 600; display: flex; align-items: center; gap: 6px; }
.bot-role { font-size: 11px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty-hint { font-size: 12px; color: #909399; text-align: center; padding: 24px 8px; }
.bot-main { min-width: 0; }
.bot-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 18px; margin-bottom: 12px; }
.bot-identity { display: flex; align-items: center; gap: 14px; min-width: 0; }
.big-avatar { width: 48px; height: 48px; border-radius: 14px; background: #f2f4f8; display: flex; align-items: center; justify-content: center; font-size: 26px; flex-shrink: 0; }
.bot-identity h3 { margin: 0; font-size: 17px; color: #1a1a2e; }
.bot-identity p { margin: 4px 0 0; font-size: 12px; color: #909399; }
.bot-identity code { background: #f2f4f8; border-radius: 4px; padding: 1px 5px; font-size: 11px; }
.head-actions { display: flex; gap: 8px; flex-shrink: 0; }
.bot-tabs :deep(.el-tabs__header) { margin-bottom: 12px; }
.tab-badge { margin-left: 6px; transform: translateY(-1px); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.form-grid .span-2 { grid-column: 1 / -1; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; padding-top: 8px; }
.section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.section-head h4 { margin: 0; font-size: 14px; color: #1a1a2e; }
.section-head p { margin: 4px 0 0; font-size: 12px; color: #909399; }
.section-actions { display: flex; gap: 8px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.muted { color: #909399; font-size: 12px; }
.args { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: #606266; }
.empty-main { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; min-height: 320px; color: #909399; }
.empty-main h3 { margin: 4px 0 0; color: #606266; font-size: 15px; }
.empty-main p { margin: 0; font-size: 12px; }
.run-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.detail-block { margin-bottom: 18px; }
.detail-block h4 { margin: 0 0 6px; font-size: 13px; color: #2c3550; }
.detail-block pre { margin: 0; background: #f7f9fc; border: 1px solid #edf0f5; border-radius: 8px; padding: 10px 12px; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; color: #2c3550; max-height: 260px; overflow: auto; }
.detail-block pre.error { background: #fff5f5; border-color: #ffd6d6; color: #c45656; }
.tpl-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; min-height: 120px; }
.tpl-card { border: 1px solid #edf0f5; border-radius: 10px; padding: 12px 14px; cursor: pointer; transition: border-color .15s, box-shadow .15s, transform .15s; background: #fff; }
.tpl-card:hover { border-color: #b9d4ff; box-shadow: 0 4px 14px rgba(64,158,255,.12); transform: translateY(-1px); }
.tpl-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.tpl-name { font-size: 14px; font-weight: 600; color: #1a1a2e; }
.tpl-desc { font-size: 12px; color: #606266; line-height: 1.7; margin-top: 8px; }
.tpl-action { font-size: 12px; color: #409eff; margin-top: 10px; }
.nl-preview { margin-top: 14px; padding: 12px 14px; border-radius: 8px; background: #f5f9ff; border: 1px solid #d9e9ff; }
.nl-prompt { margin-top: 8px; font-size: 13px; color: #303133; line-height: 1.7; white-space: pre-wrap; }
@media (max-width: 980px) {
  .console-grid { grid-template-columns: 1fr; }
  .bot-list { position: static; }
  .form-grid { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
  .console-header { flex-direction: column; align-items: stretch; }
  .header-actions { flex-wrap: wrap; }
  .bot-list { display: flex; gap: 8px; overflow-x: auto; }
  .bot-list .panel-title { display: none; }
  .bot-item { min-width: 180px; }
  .bot-head { flex-direction: column; align-items: flex-start; }
  .head-actions { flex-wrap: wrap; }
  .bot-tabs :deep(.el-tabs__nav-wrap) { overflow-x: auto; }
  .section-head { flex-direction: column; align-items: stretch; }
  .section-actions { flex-wrap: wrap; }
}
</style>
