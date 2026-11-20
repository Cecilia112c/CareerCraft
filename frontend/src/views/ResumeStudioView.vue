<template>
  <div class="studio">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-button text @click="$router.push('/resumes')">← 返回</el-button>
      <div class="grow ellipsis title">{{ resume?.title || '简历' }}
        <el-tag v-if="viewVersion" size="small" class="ml8">v{{ viewVersion }}</el-tag>
        <el-tag v-if="dirty" size="small" type="warning" class="ml8">有未保存的修改</el-tag>
      </div>
      <el-radio-group v-model="mode" :disabled="!isLatest || !doc" @change="sendMode">
        <el-radio-button value="target">指定修改</el-radio-button>
        <el-radio-button value="edit">直接编辑</el-radio-button>
        <el-radio-button value="view">预览</el-radio-button>
      </el-radio-group>
      <el-button type="primary" :disabled="!dirty" :loading="saving" :class="{ pulse: dirty }" @click="save">保存版本</el-button>
      <el-dropdown :disabled="!viewVersion" @command="doExport">
        <el-button :loading="exporting">导出</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="pdf">下载 PDF</el-dropdown-item>
            <el-dropdown-item command="html">下载 HTML</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button :disabled="!viewVersion" @click="openSync">更新到我的资料</el-button>
    </div>

    <div v-if="gen.running.value || (!doc && !failed && !waitingWorkflow)" class="center">
      <div class="card gen-card">
        <h3>正在按 STAR 法则生成定向简历…</h3>
        <TaskProgress :running="true" :progress="gen.progress.value" :stage="gen.stage.value || '准备中'" />
        <p class="muted">每个项目单独润色并做事实校验，通常需要 20~60 秒</p>
      </div>
    </div>
    <div v-else-if="waitingWorkflow" class="center">
      <div class="card gen-card">
        <h3>岗位要求有 {{ waitingWorkflow.missing_req_ids.length }} 处缺少依据</h3>
        <p class="muted">可以先到资料库回答待补充问题，确认事实后再继续；也可以跳过缺口，先生成草稿。</p>
        <div class="row mt16"><el-button @click="$router.push('/knowledge')">去补充资料</el-button><el-button type="primary" @click="continueGeneration">跳过并继续生成</el-button></div>
      </div>
    </div>
    <div v-else-if="failed" class="center">
      <el-result icon="error" title="简历生成失败" :sub-title="failed">
        <template #extra><el-button type="primary" @click="$router.push('/resumes')">返回列表</el-button></template>
      </el-result>
    </div>

    <div v-else class="body">
      <!-- 左：版本 + 模块 -->
      <aside class="left">
        <div class="panel">
          <div class="panel-title">版本记录</div>
          <div v-for="v in resume.versions" :key="v.version" class="version" :class="{ active: v.version === viewVersion }" @click="openVersion(v.version)">
            <div class="row"><b>v{{ v.version }}</b><span class="grow ellipsis muted">{{ v.note }}</span></div>
            <div class="muted small">{{ v.created_at.slice(5, 16).replace('T', ' ') }}</div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-title">显示的模块</div>
          <div v-for="o in outlineItems" :key="o.id" class="outline" :style="{ paddingLeft: 8 + o.level * 14 + 'px' }">
            <el-checkbox :model-value="!hidden.has(o.id)" :disabled="!isLatest" @change="(v: boolean) => toggleHidden(o.id, v)">
              <span class="ellipsis">{{ o.label }}</span>
            </el-checkbox>
          </div>
        </div>
      </aside>

      <!-- 中：A4 预览 -->
      <section class="center-pane">
        <el-alert v-if="resume?.artifact_status === 'stale'" type="warning" :closable="false" class="mb8">
          <template #title>资料或岗位要求已更新，这份简历的依据可能过期。<el-button text type="primary" :loading="refreshTask.running.value" @click="checkAndRefresh">检查并更新</el-button></template>
        </el-alert>
        <el-alert v-if="!isLatest" type="info" :closable="false" class="mb8">
          <template #title>
            正在查看历史版本 v{{ viewVersion }}。
            <el-button size="small" type="primary" link @click="rollback">以此版本创建新版本（回滚）</el-button>
            <el-button size="small" link @click="openVersion(resume.current_version)">回到最新版</el-button>
          </template>
        </el-alert>
        <div v-else class="hint">
          <template v-if="mode === 'target'">👆 点击简历中的<b>模块</b>（项目、经历、教育、个人简介）指定修改范围；也可以<b>拖选几句话</b>精确指定。按住 Ctrl/Shift 可以多选。</template>
          <template v-else-if="mode === 'edit'">✏️ 点击任意文字直接修改，回车或点击别处完成；编辑模式下点击证件照框可上传照片。改完记得“保存版本”。</template>
          <template v-else>👀 预览模式。切换到“指定修改”让 AI 帮你改，或“直接编辑”自己改。</template>
        </div>
        <iframe ref="frame" class="frame" :srcdoc="html" sandbox="allow-scripts allow-modals" />
        <div v-if="hoverCitation" class="evidence-popover" :style="{ left: `${hoverPosition.left}px`, top: `${hoverPosition.top}px` }">
          <b>这句话的依据</b><div class="small mt8">{{ hoverCitation.text }}</div>
          <div v-if="!hoverCitation.citations?.length" class="muted mt8">暂无逐句依据</div>
          <div v-for="source in hoverCitation.citations" :key="source.id" class="muted mt8">{{ source.valid ? '已确认' : '已失效' }} · {{ source.statement || source.id }}</div>
        </div>
      </section>

      <!-- 右：AI 修改助手 -->
      <aside class="right">
        <el-tabs v-model="rightTab">
          <el-tab-pane label="AI 修改" name="ai">
            <!-- 1. 修改范围 -->
            <div class="step-title"><span class="no">1</span>修改范围</div>
            <div v-if="!targets.length" class="scope-empty">
              <div>在左侧简历上点击要改的模块，或拖选几句话。</div>
              <el-select class="mt8 w100" placeholder="也可以从这里选择模块" filterable :model-value="''" @change="pickBlock">
                <el-option v-for="b in blockOptions" :key="b.id" :value="b.id" :label="b.label" />
              </el-select>
              <el-button v-if="mode !== 'target'" size="small" class="mt8" :disabled="!isLatest" @click="mode = 'target'; sendMode()">切换到“指定修改”</el-button>
            </div>
            <div v-else class="scope">
              <el-tag v-for="t in targets" :key="t.key" closable class="scope-tag" @close="removeTarget(t.key)">{{ t.label }}</el-tag>
              <el-button text size="small" @click="clearTargets">清空</el-button>
              <div v-if="selectionText" class="quote selected">{{ selectionText }}</div>
            </div>

            <!-- 2. 指令 -->
            <div class="step-title mt16"><span class="no">2</span>告诉 AI 怎么改</div>
            <div class="quick">
              <button v-for="q in quickActions" :key="q.mode" class="chip" :class="{ active: quickMode === q.mode }" @click="toggleQuick(q)">{{ q.label }}</button>
            </div>
            <el-input ref="instructionInput" v-model="instruction" type="textarea" :autosize="{ minRows: 3, maxRows: 7 }" class="mt8"
                      placeholder="例如：突出我在高并发方面的工作，语气更专业一些。&#10;说“以后都……”“记住……”，AI 会把它记成长期偏好。"
                      @keydown.ctrl.enter="runAgent" @keydown.meta.enter="runAgent" />
            <div class="row mt8 memory-line">
              <span class="muted grow">🧠 会遵守你的 {{ activeMemory }} 条长期偏好<span v-if="workingTurns"> · 记得本简历最近 {{ workingTurns }} 轮修改</span></span>
              <router-link to="/memory" class="small">管理记忆</router-link>
            </div>
            <el-button type="primary" class="mt8 w100" size="large" :loading="pol.running.value" :disabled="!targets.length || !isLatest" @click="runAgent">
              让 AI 修改{{ targets.length ? `（${targets.length} 处范围）` : '' }}
            </el-button>
            <div class="muted small mt8 center-text">Ctrl + Enter 发送 · AI 只改你指定的范围，新增的数字或技术词会被拦截</div>
            <TaskProgress class="mt8" :running="pol.running.value" :progress="pol.progress.value" :stage="pol.stage.value" />

            <!-- 3. 结果 -->
            <div v-if="runs.length" class="step-title mt24"><span class="no">3</span>修改结果 <span class="muted">点“替换”后会更新到简历上</span></div>
            <div v-for="run in runs" :key="run.key" class="run-card">
              <div class="run-head">
                <div class="run-ins">“{{ run.instruction }}”</div>
                <div class="muted small">{{ run.scopeLabel }} · {{ run.time }}</div>
              </div>
              <div v-for="ev in run.memory" :key="ev.id" class="mem-ev" :class="ev.status">
                <template v-if="ev.status === 'active'">🧠 已记住：{{ ev.value }} <a class="small" @click="forgetMemory(ev)">撤销</a></template>
                <template v-else-if="ev.status === 'proposed'">🧠 AI 建议记住：{{ ev.value }}
                  <a class="small" @click="confirmMemory(ev)">确认</a> <a class="small muted" @click="forgetMemory(ev)">忽略</a></template>
                <template v-else>🧠 {{ ev.status === 'forgotten' ? '已忽略' : '已确认' }}：{{ ev.value }}</template>
              </div>
              <el-alert v-for="w in run.rejected" :key="w" :title="w" type="warning" :closable="false" class="mb8" />
              <el-alert v-for="w in run.needs" :key="w" :title="'需要你补充信息：' + w" type="info" :closable="false" class="mb8" />
              <div v-if="!run.patches.length && !run.rejected.length" class="muted">AI 认为当前内容不需要修改，可以换个说法再试。</div>

              <div v-for="p in run.patches" :key="p.id" class="patch" :class="p.state"
                   @mouseenter="previewPatch(p)" @mouseleave="clearPreview">
                <div class="muted small ellipsis">{{ p.context }}</div>
                <div class="old">{{ p.old }}</div>
                <el-input v-if="p.editing" v-model="p.new" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" class="mt8" />
                <div v-else class="new">{{ p.new }}</div>
                <div v-if="p.reason" class="muted small mt8">💡 {{ p.reason }}</div>
                <div class="row mt8 patch-actions">
                  <template v-if="p.state === 'applied'">
                    <span class="applied">✓ 已替换</span>
                    <el-button size="small" text @click="undoPatch(p)">撤销</el-button>
                  </template>
                  <template v-else-if="p.state === 'skipped'">
                    <span class="muted small">已忽略</span>
                    <el-button size="small" text @click="p.state = 'pending'">恢复</el-button>
                  </template>
                  <template v-else>
                    <el-button size="small" type="primary" @click="applyPatch(p)">替换</el-button>
                    <el-button size="small" @click="p.editing = !p.editing">{{ p.editing ? '完成编辑' : '编辑后替换' }}</el-button>
                    <el-dropdown trigger="click" @command="(reason: string) => skipPatch(p, reason)"><el-button size="small" text>不用</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="verbose">太啰嗦</el-dropdown-item><el-dropdown-item command="tone">语气不合适</el-dropdown-item><el-dropdown-item command="unfaithful">个人贡献不准确</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
                  </template>
                </div>
              </div>
              <div v-if="run.patches.some((p: any) => p.state === 'pending')" class="row mt8">
                <el-button size="small" type="primary" plain @click="applyAll(run)">全部替换</el-button>
                <el-button size="small" text @click="reuseRun(run)">在此基础上继续改</el-button>
              </div>
            </div>

            <!-- 工作记忆 -->
            <details v-if="working.summary || working.turns.length" class="working mt24">
              <summary>本简历的 AI 对话记忆（{{ working.turns.length }} 轮{{ working.summary ? ' + 摘要' : '' }}）</summary>
              <div v-if="working.summary" class="muted mt8">摘要：{{ working.summary }}</div>
              <div v-for="(t, k) in working.turns" :key="k" class="turn" :class="t.role">
                <b>{{ t.role === 'user' ? '你' : 'AI' }}：</b>{{ t.content }}
              </div>
              <el-button size="small" text type="danger" class="mt8" @click="clearWorking">清空这份简历的对话记忆</el-button>
            </details>
          </el-tab-pane>

          <el-tab-pane label="JD 匹配" name="jd">
            <div v-if="!job" class="muted">这份简历没有关联目标岗位（通用简历）。</div>
            <template v-else>
              <div><b>{{ job.title }}</b></div>
              <div class="muted">{{ job.company }} · {{ job.city }}</div>
              <div class="mt16"><b>关键词覆盖 {{ kwCovered.length }}/{{ jobKeywords.length }}</b></div>
              <el-progress :percentage="jobKeywords.length ? Math.round(kwCovered.length * 100 / jobKeywords.length) : 0" class="mt8" />
              <div class="mt8">
                <el-tag v-for="k in kwCovered" :key="k" type="success" class="tag">{{ k }}</el-tag>
                <el-tag v-for="k in kwMissing" :key="k" type="warning" class="tag">{{ k }}</el-tag>
              </div>
              <div class="muted small mt8">黄色关键词在简历中没有出现。确实有相关经历的话，先在“我的资料”中补充，再指定对应项目让 AI “贴合 JD”；没有的经历不要硬加。</div>
            </template>
          </el-tab-pane>

          <el-tab-pane label="依据" name="evidence">
            <div v-if="!citations.length" class="muted">这份简历暂无逐句依据记录。</div>
            <div v-for="entry in citations" :key="entry.sentence_id" class="citation-card">
              <b>{{ entry.text }}</b>
              <div v-for="source in entry.citations" :key="source.id" class="muted mt8">
                <span :class="{ 'citation-stale': !source.valid }">{{ source.valid ? '依据' : '依据已失效' }}：</span>{{ source.statement || source.id }}
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="`信息不足${gapRequests.length ? ` (${gapRequests.length})` : ''}`" name="gaps">
            <div v-if="!gapRequests.length" class="muted">当前没有待补充的资料。</div>
            <div v-for="request in gapRequests" :key="request.id" class="citation-card">
              <b>{{ request.question }}</b>
              <div class="muted mt8">{{ request.priority === 'high' ? '高优先级' : '待补充' }}</div>
              <el-input v-model="gapAnswers[request.id]" type="textarea" :rows="2" placeholder="根据真实经历回答" class="mt8" />
              <div class="row mt8"><el-button size="small" type="primary" @click="answerGap(request.id)">保存事实</el-button><el-button size="small" text @click="$router.push('/knowledge')">去资料库上传材料</el-button></div>
            </div>
          </el-tab-pane>
          <el-tab-pane label="工作流" name="workflow"><WorkflowTimeline :subject="`resume_id:${id}`" /></el-tab-pane>

          <el-tab-pane label="样式" name="style">
            <div class="mb8"><b>主题色</b></div>
            <el-color-picker v-model="accent" :predefine="colors" :disabled="!isLatest" @change="onAccent" />
            <div class="muted small mt16">模板：ASU 风格技术简历（A4）。证件照：切换到“直接编辑”后点击右上角照片框上传。</div>
            <el-button v-if="doc?.presentation?.photo" size="small" class="mt8" :disabled="!isLatest" @click="removePhoto">移除证件照</el-button>
          </el-tab-pane>
        </el-tabs>
      </aside>
    </div>

    <!-- 回写资料 -->
    <el-dialog v-model="syncOpen" title="把简历中的修改更新到“我的资料”" width="760px">
      <div class="muted mb8">只列出与资料不同的句子；姓名、联系方式、公司、时间等身份信息不会被修改。默认都不勾选。</div>
      <el-empty v-if="!diffs.length" description="当前版本与资料一致" :image-size="60" />
      <div v-for="df in diffs" :key="df.key" class="sync-row">
        <el-checkbox v-model="syncChecked[df.key]" />
        <div class="grow">
          <div class="muted small">{{ df.context }}</div>
          <div v-if="df.old" class="old">{{ df.old }}</div>
          <div class="new">{{ df.new }}</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="syncOpen = false">取消</el-button>
        <el-button type="primary" :disabled="!syncKeys.length" @click="doSync">更新 {{ syncKeys.length }} 处</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/api'
import { errMsg, showError } from '@/api/http'
import { useTask } from '@/composables/useTask'
import TaskProgress from '@/components/TaskProgress.vue'
import WorkflowTimeline from '@/components/WorkflowTimeline.vue'
import { allText, downloadBlob, getText, outline, setText, textItems } from '@/utils/doc'

type Mode = 'view' | 'edit' | 'target'
interface Target { key: string; label: string; ids: string[]; kind: 'block' | 'items' }

const route = useRoute()
const id = Number(route.params.id)
const resume = ref<any>(null)
const doc = ref<any>(null)
const citations = ref<any[]>([])
const hoverCitation = ref<any>(null)
const hoverPosition = ref({ left: 0, top: 0 })
const gapRequests = ref<any[]>([])
const gapAnswers = ref<Record<number, string>>({})
const viewVersion = ref(0)
const dirty = ref(false)
const failed = ref('')
const waitingWorkflow = ref<any>(null)
const html = ref('')
const mode = ref<Mode>('target')
const frame = ref<HTMLIFrameElement | null>(null)
const saving = ref(false)
const exporting = ref(false)
const rightTab = ref('ai')
const job = ref<any>(null)
const gen = useTask()
const pol = useTask()
const refreshTask = useTask()

const isLatest = computed(() => !!resume.value && viewVersion.value === resume.value.current_version)
const hidden = computed(() => new Set<string>(doc.value?.presentation?.hidden_ids || []))
const outlineItems = computed(() => (doc.value ? outline(doc.value) : []))
const blockOptions = computed(() => {
  const opts = doc.value?.basic?.summary ? [{ id: 'basic.summary', label: '个人简介' }] : []
  return [...opts, ...outlineItems.value.map((o) => ({ id: o.id, label: o.label }))]
})

// ------------------------------------------------ loading & rendering
async function load(preferVersion?: number) {
  resume.value = await api.getResume(id)
  loadGapRequests()
  if (!resume.value.current) {
    const taskId = route.query.task as string
    if (!taskId) { failed.value = '这份简历还没有生成成功的版本，请删除后重新生成。'; return }
    try {
      const res = await gen.waitFor(taskId)
      if (res?.waiting_user) { waitingWorkflow.value = res; return }
      res?.warnings?.forEach((w: string) => ElMessage({ message: w, type: 'warning', duration: 6000 }))
      resume.value = await api.getResume(id)
    } catch (e: any) { failed.value = e?.message || '生成失败'; return }
  }
  const v = preferVersion || resume.value.current_version
  const data = v === resume.value.current?.version ? resume.value.current.data : (await api.getVersion(id, v)).data
  setDoc(data, v)
  if (resume.value.job_id && !job.value) {
    try { job.value = (await api.getJob(resume.value.job_id)).detail } catch { job.value = null }
  }
}

async function loadGapRequests() {
  try { const rows = await api.listMaterialRequests('open'); gapRequests.value = rows.filter((row: any) => row.target?.resume_id === id || (resume.value?.job_id && row.target?.job_id === resume.value.job_id)) }
  catch { gapRequests.value = [] }
}

async function answerGap(requestId: number) {
  if (!gapAnswers.value[requestId]?.trim()) { ElMessage.warning('请填写真实经历'); return }
  try { await api.answerMaterialRequest(requestId, gapAnswers.value[requestId]); delete gapAnswers.value[requestId]; await loadGapRequests(); ElMessage.success('已保存为确认事实，可以重新检查或修改相关句子') }
  catch (error) { showError(error) }
}

async function checkAndRefresh() {
  try {
    const result = await refreshTask.run(() => api.refreshResume(id))
    runs.value.unshift(reactive({ key: ++runSeq, instruction: '根据最新依据检查并更新', scopeLabel: '过期简历',
      time: new Date().toLocaleTimeString().slice(0, 5), targets: [], rejected: result.rejected || [],
      needs: result.needs_confirmation || [], memory: [],
      patches: (result.patches || []).map((patch: any): PatchView => ({ id: patch.id, old: patch.old, new: patch.new,
        original: patch.new, context: patch.context, reason: patch.reason || '', evidence_ids: patch.evidence_ids || [],
        state: 'pending', editing: false })) }))
    rightTab.value = 'ai'
    await loadGapRequests()
  } catch (error) { showError(error) }
}

async function continueGeneration() {
  if (!waitingWorkflow.value) return
  try {
    const response = await api.resumeWorkflow(waitingWorkflow.value.workflow_id)
    waitingWorkflow.value = null
    const result = await gen.waitFor(response.task_id)
    result?.warnings?.forEach((warning: string) => ElMessage({ message: warning, type: 'warning', duration: 6000 }))
    await load()
  } catch (error: any) { failed.value = error?.message || '继续生成失败'; waitingWorkflow.value = null }
}

function setDoc(data: any, version: number) {
  hoverCitation.value = null
  doc.value = JSON.parse(JSON.stringify(data))
  doc.value.presentation = doc.value.presentation || { accent_color: '#2f67a7', hidden_ids: [], photo: '' }
  viewVersion.value = version
  api.resumeCitations(id, version).then((rows: any[]) => { if (viewVersion.value === version) citations.value = rows }).catch(() => { citations.value = [] })
  dirty.value = false
  accent.value = doc.value.presentation.accent_color || '#2f67a7'
  if (!isLatest.value) mode.value = 'view'
  clearTargets()
  render()
}

async function render() {
  try { html.value = await api.render(doc.value, true) } catch (e) { showError(e) }
}

function post(msg: any) { frame.value?.contentWindow?.postMessage(msg, '*') }
function sendMode() { post({ type: 'cc-mode', mode: mode.value }) }

function onMessage(e: MessageEvent) {
  if (!frame.value || e.source !== frame.value.contentWindow) return
  const msg = e.data || {}
  if (msg.source !== 'careercraft') return
  if (msg.type === 'cc-citation') {
    hoverCitation.value = citations.value.find((entry: any) => entry.sentence_id === msg.id) || { text: getText(doc.value, msg.id) || '', citations: [] }
    const frameRect = frame.value.getBoundingClientRect()
    hoverPosition.value = { left: Math.min(window.innerWidth - 340, Math.max(12, frameRect.left + msg.rect.right + 12)),
      top: Math.min(window.innerHeight - 180, Math.max(12, frameRect.top + msg.rect.top)) }
  }
  if (msg.type === 'cc-citation-hide') hoverCitation.value = null
  if (msg.type === 'cc-ready') { sendMode(); highlight() }
  if (msg.type === 'cc-edit' && isLatest.value) {
    if (setText(doc.value, msg.id, msg.text)) dirty.value = true
  }
  if (msg.type === 'cc-select') {
    const ids: string[] = [...msg.ids]
    addTarget({ key: 'items:' + ids.join(','), label: `选中的 ${ids.length} 句`, ids, kind: 'items' }, !!msg.append)
    selectionText.value = msg.text
  }
  if (msg.type === 'cc-target') {
    addTarget({ key: msg.block, label: msg.label || msg.block, ids: [msg.block], kind: 'block' }, !!msg.append)
  }
  if (msg.type === 'cc-photo' && isLatest.value) {
    doc.value.presentation.photo = msg.dataUrl
    dirty.value = true
    render()
  }
}

onMounted(async () => {
  window.addEventListener('message', onMessage)
  window.addEventListener('beforeunload', beforeUnload)
  try { await load() } catch (e) { showError(e) }
  loadMemoryInfo()
})
onBeforeUnmount(() => {
  window.removeEventListener('message', onMessage)
  window.removeEventListener('beforeunload', beforeUnload)
})
function beforeUnload(e: BeforeUnloadEvent) { if (dirty.value) { e.preventDefault(); e.returnValue = '' } }

// ------------------------------------------------ 修改范围
const targets = ref<Target[]>([])
const selectionText = ref('')
function addTarget(t: Target, append: boolean) {
  if (!isLatest.value) { ElMessage.info('历史版本不能修改，请先回到最新版或回滚'); return }
  rightTab.value = 'ai'
  if (!append) targets.value = []
  if (!targets.value.some((x) => x.key === t.key)) targets.value.push(t)
  if (t.kind === 'block') selectionText.value = ''
  highlight(true)
}
function removeTarget(key: string) { targets.value = targets.value.filter((t) => t.key !== key); highlight() }
function clearTargets() { targets.value = []; selectionText.value = ''; highlight() }
function pickBlock(blockId: string) {
  const opt = blockOptions.value.find((b) => b.id === blockId)
  if (opt) addTarget({ key: opt.id, label: opt.label, ids: [opt.id], kind: 'block' }, true)
}
function highlight(scroll = false) {
  post({ type: 'cc-highlight', scroll,
         ids: targets.value.filter((t) => t.kind === 'items').flatMap((t) => t.ids),
         blocks: targets.value.filter((t) => t.kind === 'block').flatMap((t) => t.ids) })
}

// ------------------------------------------------ 指令 & 运行
const quickActions = [
  { mode: 'polish', label: '更专业', text: '让表达更专业、有力，不改变事实' },
  { mode: 'star', label: 'STAR 化', text: '按 STAR 补齐背景、我的动作和结果' },
  { mode: 'concise', label: '精简', text: '精简篇幅，保留技术和数字' },
  { mode: 'align_jd', label: '贴合 JD', text: '用目标岗位的关键词改写，突出相关经历' },
  { mode: 'quantify', label: '突出成果', text: '把已有的结果和数字前置写清楚' },
]
const quickMode = ref('custom')
const instruction = ref('')
const instructionInput = ref<any>(null)
function toggleQuick(q: { mode: string; text: string }) {
  if (quickMode.value === q.mode) { quickMode.value = 'custom'; if (instruction.value === q.text) instruction.value = ''; return }
  const prev = quickActions.find((x) => x.mode === quickMode.value)
  quickMode.value = q.mode
  if (!instruction.value.trim() || instruction.value === prev?.text) instruction.value = q.text
}

interface PatchView { id: string; old: string; new: string; original: string; context: string; reason: string;
  evidence_ids: string[]; state: 'pending' | 'applied' | 'skipped'; editing: boolean }
const runs = ref<any[]>([])
let runSeq = 0

async function runAgent() {
  if (!targets.value.length) { ElMessage.warning('请先在简历上指定修改范围'); return }
  if (!instruction.value.trim() && quickMode.value === 'custom') { ElMessage.warning('请告诉 AI 怎么改，或选一个快捷方式'); return }
  const ids = [...new Set(targets.value.flatMap((t) => t.ids))]
  const scopeLabel = targets.value.map((t) => t.label).join('、').slice(0, 80)
  const ins = instruction.value.trim()
  try {
    const res = await pol.run(() => api.polish(id, {
      version: viewVersion.value, ids, mode: quickMode.value, instruction: ins, scope_label: scopeLabel, data: doc.value,
    }))
    runs.value.unshift(reactive({
      key: ++runSeq, instruction: ins || quickActions.find((q) => q.mode === quickMode.value)?.text || '',
      scopeLabel, time: new Date().toLocaleTimeString().slice(0, 5), targets: [...targets.value],
      rejected: res.rejected || [], needs: res.needs_confirmation || [],
      memory: (res.memory_events || []).map((e: any) => ({ ...e.item })),
      patches: (res.patches || []).map((p: any): PatchView => ({ id: p.id, old: p.old, new: p.new, original: p.new,
        context: p.context, reason: p.reason || '', evidence_ids: p.evidence_ids || [], state: 'pending', editing: false })),
    }))
    if ((res.memory_events || []).length) loadMemoryInfo()
    else loadWorking()
    if (!(res.patches || []).length) ElMessage.info('没有可替换的修改，看看下方提示')
  } catch (e) { showError(e) }
}

function currentText(pid: string) { return getText(doc.value, pid) ?? '' }

async function applyPatch(p: PatchView, silent = false) {
  if (!p.new.trim()) { ElMessage.warning('内容不能为空'); return false }
  const now = currentText(p.id)
  if (now !== p.old && !silent) {
    try { await ElMessageBox.confirm('这句话在 AI 修改之后又被改动过，仍然用 AI 的版本替换吗？', '提示', { type: 'warning' }) }
    catch { return false }
  }
  p.old = now
  if (!setText(doc.value, p.id, p.new.trim())) { ElMessage.error('找不到这句话，可能已被删除'); return false }
  for (const item of textItems(doc.value)) if (item.id === p.id) item.evidence_ids = [...p.evidence_ids]
  if (p.id === 'basic.headline') doc.value.basic.headline_evidence_ids = [...p.evidence_ids]
  if (p.id === 'basic.summary') doc.value.basic.summary_evidence_ids = [...p.evidence_ids]
  p.state = 'applied'
  p.editing = false
  dirty.value = true
  clearPreview()
  await render()
  if (!silent) ElMessage.success('已替换到简历上，满意的话记得“保存版本”')
  return true
}
async function skipPatch(p: PatchView, reason: string) {
  p.state = 'skipped'
  try {
    const feedback = await api.resumePatchFeedback(id, p.id, reason)
    if (feedback.preference_proposal?.status === 'proposed') ElMessage.info('已根据多次反馈提出写作偏好，可到“AI 记忆”确认')
  } catch (error) { showError(error) }
}
async function applyAll(run: any) {
  let n = 0
  for (const p of run.patches) if (p.state === 'pending' && (await applyPatch(p, true))) n++
  if (n) ElMessage.success(`已替换 ${n} 处，记得“保存版本”`)
}
async function undoPatch(p: PatchView) {
  if (currentText(p.id) !== p.new.trim()) { ElMessage.warning('这句话之后又被改过，无法自动撤销'); return }
  setText(doc.value, p.id, p.old)
  p.state = 'pending'
  dirty.value = true
  await render()
}
function previewPatch(p: PatchView) {
  if (p.state !== 'pending' || p.editing) return
  post({ type: 'cc-preview', items: { [p.id]: p.new } })
}
function clearPreview() { post({ type: 'cc-preview', items: {} }) }
function reuseRun(run: any) {
  targets.value = [...run.targets]
  highlight(true)
  instruction.value = ''
  nextTick(() => instructionInput.value?.focus?.())
}

// ------------------------------------------------ 记忆
const activeMemory = ref(0)
const working = ref<{ summary: string; turns: any[] }>({ summary: '', turns: [] })
const workingTurns = computed(() => working.value.turns.filter((t) => t.role === 'user').length)
async function loadWorking() {
  try { working.value = await api.workingMemory('resume', `resume:${id}`) } catch { /* ignore */ }
}
async function loadMemoryInfo() {
  try { activeMemory.value = (await api.listMemory()).items.filter((m: any) => m.status === 'active').length } catch { /* ignore */ }
  loadWorking()
}
async function confirmMemory(ev: any) {
  try { Object.assign(ev, await api.confirmMemory(ev.id)); loadMemoryInfo() } catch (e) { showError(e) }
}
async function forgetMemory(ev: any) {
  try { await api.forgetMemory(ev.id); ev.status = 'forgotten'; loadMemoryInfo() } catch (e) { showError(e) }
}
async function clearWorking() {
  try { await api.clearWorkingMemory('resume', `resume:${id}`); await loadWorking(); ElMessage.success('已清空') } catch (e) { showError(e) }
}

// ------------------------------------------------ versions
async function confirmDiscard(): Promise<boolean> {
  if (!dirty.value) return true
  try { await ElMessageBox.confirm('当前修改还没有保存，确定放弃吗？', '提示', { type: 'warning' }); return true } catch { return false }
}
async function openVersion(v: number) {
  if (v === viewVersion.value || !(await confirmDiscard())) return
  try { setDoc((await api.getVersion(id, v)).data, v) } catch (e) { showError(e) }
}
async function save() {
  saving.value = true
  try {
    const applied = runs.value.flatMap((r) => r.patches).filter((p: any) => p.state === 'applied').length
    await api.saveVersion(id, resume.value.current_version, doc.value, applied ? `AI 修改（${applied} 处）+ 手动调整` : '手动编辑')
    ElMessage.success('已保存为新版本')
    runs.value.forEach((r) => r.patches.forEach((p: any) => { if (p.state === 'applied') p.state = 'skipped' }))
    runs.value = runs.value.filter((r) => r.patches.some((p: any) => p.state === 'pending'))
    await load()
  } catch (e) { showError(e) } finally { saving.value = false }
}
async function rollback() {
  try { await api.rollback(id, viewVersion.value); ElMessage.success('已基于该版本创建新版本'); await load() } catch (e) { showError(e) }
}
function toggleHidden(itemId: string, visible: boolean) {
  const ids = new Set<string>(doc.value.presentation.hidden_ids || [])
  if (visible) ids.delete(itemId); else ids.add(itemId)
  doc.value.presentation.hidden_ids = [...ids]
  dirty.value = true
  render()
}

// ------------------------------------------------ style
const colors = ['#2f67a7', '#1f5eff', '#0e7c66', '#7b4fd6', '#c2410c', '#334155']
const accent = ref('#2f67a7')
function onAccent(v: string | null) { doc.value.presentation.accent_color = v || '#2f67a7'; dirty.value = true; render() }
function removePhoto() { doc.value.presentation.photo = ''; dirty.value = true; render() }

// ------------------------------------------------ JD keywords
const jobKeywords = computed<string[]>(() => (job.value?.keywords || []).slice(0, 15))
const docText = computed(() => (doc.value ? allText(doc.value).toLowerCase() : ''))
const kwCovered = computed(() => jobKeywords.value.filter((k) => docText.value.includes(k.toLowerCase())))
const kwMissing = computed(() => jobKeywords.value.filter((k) => !docText.value.includes(k.toLowerCase())))

// ------------------------------------------------ export
async function doExport(format: 'pdf' | 'html') {
  if (dirty.value) ElMessage.warning('导出的是已保存的版本，未保存的修改不会包含在内')
  exporting.value = true
  try {
    const res = await api.exportResume(id, viewVersion.value, format)
    const name = `${doc.value.basic?.name || '简历'}_${resume.value.title}_v${viewVersion.value}.${format}`
    downloadBlob(res.data, name.replace(/[\\/:*?"<>|]/g, '-'))
  } catch (e: any) {
    let msg = errMsg(e)
    if (e?.response?.data instanceof Blob) {
      try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* ignore */ }
    }
    ElMessage({ message: msg, type: 'error', duration: 8000 })
  } finally { exporting.value = false }
}

// ------------------------------------------------ sync back to profile
const syncOpen = ref(false)
const diffs = ref<any[]>([])
const syncProposalId = ref('')
const syncChecked = reactive<Record<string, boolean>>({})
const syncKeys = computed(() => diffs.value.filter((d) => syncChecked[d.key]).map((d) => d.key))
async function openSync() {
  try {
    const proposal = await api.syncProposal(id, viewVersion.value)
    syncProposalId.value = proposal.id
    diffs.value = proposal.body.diffs
    Object.keys(syncChecked).forEach((k) => delete syncChecked[k])
    syncOpen.value = true
  } catch (e) { showError(e) }
}
async function doSync() {
  try {
    const res = await api.sync(id, viewVersion.value, syncKeys.value, syncProposalId.value)
    syncOpen.value = false
    ElMessage.success(`已更新 ${res.applied} 处资料`)
  } catch (e) { showError(e) }
}
</script>

<style scoped>
.studio { height: calc(100vh - var(--cc-header-h)); display: flex; flex-direction: column; }
.toolbar { display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-3) var(--sp-6); background: var(--cc-card); border-bottom: 1px solid var(--cc-border-light); }
.title { font-weight: 600; font-size: var(--fs-lg); }
.ml8 { margin-left: 8px; }
.pulse { box-shadow: 0 0 0 0 rgba(51, 112, 255, .5); animation: pulse 1.8s infinite; }
@keyframes pulse { 70% { box-shadow: 0 0 0 8px rgba(51, 112, 255, 0); } 100% { box-shadow: 0 0 0 0 rgba(51, 112, 255, 0); } }
.body { flex: 1; display: flex; min-height: 0; }
.left { width: 220px; flex: none; overflow: auto; background: var(--cc-card); border-right: 1px solid var(--cc-border-light); }
.right { width: 400px; flex: none; overflow: auto; background: var(--cc-card); border-left: 1px solid var(--cc-border-light); padding: 4px 20px 24px; }
.center-pane { flex: 1; min-width: 0; display: flex; flex-direction: column; padding: 12px 16px; background: var(--cc-bg); }
.frame { flex: 1; width: 100%; border: 0; border-radius: 8px; background: #f0eee6; }
.hint { font-size: var(--fs-sm); color: var(--cc-text-2); background: var(--cc-card); border: 1px solid var(--cc-border-light); padding: 8px 12px; border-radius: 8px; margin-bottom: 8px; }
.panel { padding: 12px; border-bottom: 1px solid var(--cc-border-light); }
.panel-title { font-weight: 600; margin-bottom: 8px; }
.version { padding: 8px; border-radius: 6px; cursor: pointer; }
.version:hover { background: var(--cc-bg); }
.version.active { background: var(--cc-primary-weak); }
.outline { padding: 2px 0; }
.small { font-size: var(--fs-xs); }
.center { flex: 1; display: flex; align-items: center; justify-content: center; }
.center-text { text-align: center; }
.gen-card { width: 480px; }
.w100 { width: 100%; }
.tag { margin: 0 6px 6px 0; }

.step-title { display: flex; align-items: center; gap: 8px; font-weight: 600; margin-bottom: 10px; }
.step-title .muted { font-weight: 400; font-size: var(--fs-xs); }
.no { width: 20px; height: 20px; border-radius: 50%; background: var(--cc-primary); color: var(--cc-card); font-size: 12px;
  display: inline-flex; align-items: center; justify-content: center; }
.scope-empty { padding: 12px 14px; border: 1px dashed var(--cc-primary-border); border-radius: 8px; background: var(--cc-primary-weak);
  color: var(--cc-text-2); font-size: var(--fs-sm); }
.scope { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.scope-tag { max-width: 100%; }
.selected { width: 100%; max-height: 120px; overflow: auto; }
.quick { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { border: 1px solid var(--cc-border); background: var(--cc-card); color: var(--cc-text-2); border-radius: 14px; padding: 3px 12px;
  cursor: pointer; font-size: var(--fs-sm); font-family: inherit; }
.chip:hover { color: var(--cc-primary); border-color: var(--cc-primary-border); }
.chip.active { color: var(--cc-primary); border-color: var(--cc-primary); background: var(--cc-primary-weak); }
.memory-line { font-size: var(--fs-xs); }

.run-card { margin-bottom: 14px; padding: 12px; border: 1px solid var(--cc-border-light); border-radius: 10px; background: var(--cc-bg-2); }
.run-head { margin-bottom: 8px; }
.run-ins { font-weight: 600; color: var(--cc-text-1); }
.mem-ev { margin-bottom: 8px; padding: 6px 10px; border-radius: 6px; background: var(--cc-primary-weak); font-size: var(--fs-sm); }
.mem-ev.proposed { background: #fff8ef; }
.mem-ev a { margin-left: 6px; cursor: pointer; }
.patch { padding: 10px; margin-top: 8px; border-radius: 8px; background: var(--cc-card); border: 1px solid var(--cc-border-light); transition: border-color .15s; }
.patch:hover { border-color: var(--cc-primary-border); }
.patch.applied { border-color: #b7eb8f; background: #f6ffed; }
.patch.skipped { opacity: .55; }
.old { margin-top: 4px; color: #c9302c; text-decoration: line-through; background: #fff1f0; padding: 4px 8px; border-radius: 4px; font-size: var(--fs-sm); }
.new { margin-top: 4px; color: #1a7f37; background: #f0fff4; padding: 4px 8px; border-radius: 4px; }
.patch.applied .old { display: none; }
.applied { color: #389e0d; font-weight: 600; font-size: var(--fs-sm); }
.patch-actions { gap: 4px; }
.working summary { cursor: pointer; color: var(--cc-text-2); }
.turn { margin-top: 6px; font-size: var(--fs-sm); color: var(--cc-text-2); }
.turn.assistant { color: var(--cc-text-3); }
.sync-row { display: flex; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--cc-border-light); }
.citation-card { padding: 14px; margin: 10px 0; border: 1px solid #dce8f7; border-radius: 14px; background: rgba(244,249,255,.8); line-height: 1.6; }
.citation-card b { font-size: 13px; font-weight: 600; }
.citation-stale { color: #c35a48; font-weight: 600; }
.evidence-popover { position: fixed; z-index: 50; width: 310px; max-height: 260px; overflow: auto; pointer-events: none;
  padding: 14px 16px; border: 1px solid rgba(189, 212, 244, .9); border-radius: 16px;
  background: rgba(246, 250, 255, .94); backdrop-filter: blur(18px); box-shadow: 0 16px 40px rgba(35, 77, 137, .16); }
</style>
