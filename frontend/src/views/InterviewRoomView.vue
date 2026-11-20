<template>
  <div class="page">
    <div class="page-title">
      <div>
        <el-button text @click="$router.push('/interviews')">← 返回</el-button>
        <h1>{{ iv?.title || '模拟面试' }}</h1>
        <div class="sub">{{ iv?.source_label }}</div>
      </div>
      <el-button v-if="iv && iv.turns.length && iv.status !== 'finished'" type="primary" :loading="fin.running.value" @click="finish">
        结束并生成报告
      </el-button>
    </div>

    <el-result v-if="iv && (iv.status === 'failed' || prepError)" icon="error" title="准备失败" :sub-title="prepError || '请检查大模型配置后重新创建'" />
    <div v-else-if="!iv || iv.status === 'preparing'" class="card center">
      <h3>面试官正在阅读你的简历和 JD…</h3>
      <TaskProgress :running="true" :progress="prep.progress.value" :stage="prep.stage.value || '诊断简历、准备问题'" />
    </div>

    <el-tabs v-else v-model="tab">
      <!-- 诊断 -->
      <el-tab-pane label="简历诊断" name="gap">
        <div class="card">
          <div class="row">
            <div>匹配程度</div>
            <el-tag :type="fitType" size="large">{{ fitText }}</el-tag>
            <div class="grow"><el-progress :percentage="Math.round((gap.coverage_rate || 0) * 100)" /></div>
            <span class="muted">JD 要求覆盖率</span>
          </div>
          <div v-if="(gap.strengths || []).length" class="mt16">
            <b>亮点</b>
            <ul class="plain"><li v-for="s in gap.strengths" :key="s">{{ s }}</li></ul>
          </div>
        </div>
        <div class="card">
          <div class="card-title">JD 要求逐条对照</div>
          <el-table :data="gap.coverage || []" size="small">
            <el-table-column prop="requirement" label="JD 要求" />
            <el-table-column label="覆盖" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'covered' ? 'success' : row.status === 'partial' ? 'warning' : 'danger'">
                  {{ ({ covered: '已覆盖', partial: '部分', missing: '缺失' } as any)[row.status] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="quote" label="简历依据" />
          </el-table>
        </div>
        <div class="card">
          <div class="card-title">简历不足（{{ (gap.issues || []).length }}）</div>
          <div v-for="(it, k) in gap.issues || []" :key="k" class="issue">
            <div class="issue-head"><span class="issue-index">{{ String(k + 1).padStart(2, '0') }}</span><el-tag size="small" :type="it.severity === 'high' ? 'danger' : it.severity === 'medium' ? 'warning' : 'info'">{{ ({ high: '高风险', medium: '中风险', low: '低风险' } as any)[it.severity] }}</el-tag><el-tag size="small" type="info">{{ categoryText[it.category] || it.category }}</el-tag></div>
            <div class="issue-qa"><span class="qa-letter" title="Problem：简历问题">P</span><div><div class="qa-text">{{ it.problem }}</div><div v-if="it.quote" class="quote">{{ it.quote }}</div></div></div>
            <div class="issue-qa"><span class="qa-letter answer-letter" title="Advice：改进建议">A</span><div class="qa-text">{{ it.suggestion }}</div></div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 面试 -->
      <el-tab-pane label="项目深挖面试" name="chat">
        <div class="chat-layout">
          <aside class="card qlist">
            <div class="card-title">问题进度</div>
            <div v-for="(q, k) in iv.questions" :key="q.qid" class="q" :class="{ done: k < (iv.state?.index || 0), now: k === (iv.state?.index || 0) && iv.status === 'ongoing' }">
              <span class="lv">L{{ q.level }}</span><span class="ellipsis">{{ q.project }}</span>
            </div>
          </aside>
          <div class="card chat grow">
            <div ref="scroller" class="messages">
              <template v-for="(t, k) in iv.turns" :key="k">
                <div class="qa-pair">
                  <div class="qa-row"><span class="qa-letter">Q</span><div><div class="who">面试官 · {{ t.project }} {{ t.is_follow_up ? '· 追问' : '' }}</div><div class="qa-text">{{ t.question }}</div></div></div>
                  <div class="qa-row"><span class="qa-letter answer-letter">A</span><div class="qa-text">{{ t.answer || '已跳过' }}</div></div>
                </div>
                <div class="eval">
                  <div class="row">
                    <span v-for="d in dims" :key="d.key" class="dim">{{ d.label }} <b>{{ t.evaluation?.scores?.[d.key] ?? '-' }}</b></span>
                    <span class="grow" />
                    <span class="score" :class="(t.evaluation?.average || 0) >= 3 ? 'high' : (t.evaluation?.average || 0) >= 2 ? 'mid' : 'low'">{{ t.evaluation?.average }}</span>
                  </div>
                  <div class="mt8">{{ t.evaluation?.comment }}</div>
                  <div v-if="(t.evaluation?.weaknesses || []).length" class="muted mt8">待加强：{{ t.evaluation.weaknesses.join('；') }}</div>
                </div>
              </template>
              <div v-if="current" class="qa-pair current-question">
                <div class="qa-row"><span class="qa-letter">Q</span><div><div class="who">面试官 · {{ current.project }} {{ current.is_follow_up ? '· 追问' : `· L${current.level}` }}</div><div class="qa-text">{{ current.question }}</div><div v-if="current.anchor" class="muted small">针对简历：“{{ current.anchor }}”</div></div></div>
              </div>
              <el-alert v-if="iv.status === 'answered_all'" type="success" :closable="false" title="所有问题已回答完毕，点击右上角“结束并生成报告”" />
            </div>
            <div v-if="current" class="composer">
              <el-input v-model="answer" type="textarea" :rows="4" :disabled="ans.running.value"
                        placeholder="像真实面试一样作答：讲清楚背景、你做了什么、为什么这么做、结果如何（Ctrl+Enter 发送）"
                        @keydown.ctrl.enter="send" />
              <div class="row mt8">
                <TaskProgress class="grow" :running="ans.running.value" :progress="ans.progress.value" :stage="ans.stage.value" />
                <span class="grow" v-if="!ans.running.value" />
                <el-button :disabled="ans.running.value" @click="skip">跳过</el-button>
                <el-button type="primary" :loading="ans.running.value" @click="send">提交回答</el-button>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 报告 -->
      <el-tab-pane label="面试报告" name="report">
        <el-empty v-if="!iv.report || !iv.report.summary" description="答完题后点击“结束并生成报告”" />
        <template v-else>
          <div class="row mb16"><span class="pill blue">第 {{ iv.round || 1 }} 轮</span><span class="grow" /><el-button type="primary" plain @click="startNextRound">同一岗位再面一轮</el-button></div>
          <div v-if="previous?.report?.summary" class="card comparison">
            <div class="card-title">与上一轮对比</div>
            <div class="row"><span>上一轮 {{ previous.report.overall }} / 4</span><span>→</span><b>本轮 {{ iv.report.overall }} / 4</b></div>
            <div class="muted mt8">上一轮：{{ previous.report.summary }}</div>
          </div>
          <div class="card">
            <div class="row"><div class="big-score">{{ iv.report.overall }}</div><div class="muted">/ 4 综合得分</div></div>
            <p>{{ iv.report.summary }}</p>
          </div>
          <div class="card">
            <div class="card-title">各项目得分（0~4）</div>
            <el-table :data="projectRows" size="small">
              <el-table-column prop="project" label="项目" />
              <el-table-column v-for="d in dims" :key="d.key" :prop="d.key" :label="d.label" width="90" />
            </el-table>
          </div>
          <div class="grid3">
            <div class="card"><div class="card-title">主要风险</div><ul class="plain"><li v-for="x in iv.report.risks" :key="x">{{ x }}</li></ul></div>
            <div class="card"><div class="card-title">准备建议</div><ul class="plain"><li v-for="x in iv.report.suggestions" :key="x">{{ x }}</li></ul></div>
            <div class="card"><div class="card-title">建议复习</div><el-tag v-for="x in iv.report.review_topics" :key="x" class="tag">{{ x }}</el-tag></div>
          </div>
          <div v-if="iv.report.findings?.length" class="card mt16"><div class="card-title">证据不足的地方</div><div v-for="(finding, index) in iv.report.findings" :key="index" class="request-row"><b>{{ finding.detail }}</b><div class="muted mt8">{{ finding.question_id ? `关联题目：${finding.question_id}` : '来自面试报告' }}</div><el-button class="mt8" size="small" @click="createFindingRequest(index)">生成补充建议</el-button></div></div>
        </template>
      </el-tab-pane>
      <el-tab-pane label="工作流" name="workflow"><WorkflowTimeline :subject="`interview_id:${id}`" /></el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { showError } from '@/api/http'
import { useTask } from '@/composables/useTask'
import TaskProgress from '@/components/TaskProgress.vue'
import WorkflowTimeline from '@/components/WorkflowTimeline.vue'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const iv = ref<any>(null)
const previous = ref<any>(null)
const tab = ref('gap')
const answer = ref('')
const scroller = ref<HTMLElement | null>(null)
const prepError = ref('')
const prep = useTask()
const ans = useTask()
const fin = useTask()
const dims = [
  { key: 'correctness', label: '正确性' }, { key: 'depth', label: '深度' }, { key: 'ownership', label: '个人贡献' },
  { key: 'evidence', label: '数据细节' }, { key: 'consistency', label: '一致性' },
]
const categoryText: Record<string, string> = {
  hard_requirement: '硬性要求', star_weak: 'STAR 不完整', vague: '表述模糊', unverified_metric: '数据存疑',
  inflation_risk: '可能夸大', keyword: '关键词缺失', structure: '结构问题',
}
const gap = computed(() => iv.value?.gap_report || {})
const current = computed(() => (iv.value?.status === 'ongoing' ? iv.value?.state?.current : null))
const fitText = computed(() => ({ strong: '匹配度高', moderate: '基本匹配', weak: '差距较大' } as any)[gap.value.fit] || '未知')
const fitType = computed(() => ({ strong: 'success', moderate: 'warning', weak: 'danger' } as any)[gap.value.fit] || 'info')
const projectRows = computed(() =>
  Object.entries(iv.value?.report?.project_scores || {}).map(([project, s]: [string, any]) => ({ project, ...s })))

async function reload() {
  iv.value = await api.getInterview(id)
  if (iv.value.previous_interview_id) previous.value = await api.getInterview(iv.value.previous_interview_id)
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}

async function createFindingRequest(index: number) {
  try { await api.requestInterviewFinding(id, index); ElMessage.success('已加入资料库的待补充建议') }
  catch (error) { showError(error) }
}

onMounted(async () => {
  try {
    await reload()
    if (iv.value.status === 'preparing' && route.query.task) {
      try { await prep.waitFor(route.query.task as string) } catch (e: any) { prepError.value = e?.message }
      await reload()
    }
    for (let n = 0; iv.value.status === 'preparing' && !prepError.value && n < 60; n++) {   // 刷新页面后没有 task id：轮询状态
      await new Promise((r) => setTimeout(r, 3000))
      await reload()
    }
    if (iv.value.status === 'ongoing' || iv.value.status === 'answered_all') tab.value = iv.value.turns.length ? 'chat' : 'gap'
    if (iv.value.status === 'finished') tab.value = 'report'
  } catch (e) { showError(e) }
})

async function submit(text: string) {
  try {
    const res = await ans.run(() => api.answer(id, text))
    answer.value = ''
    if (res.next?.is_follow_up) ElMessage.info('面试官追问了一个问题')
    await reload()
  } catch (e) { showError(e); await reload() }
}
function send() {
  if (!answer.value.trim()) { ElMessage.warning('请先作答，或点击“跳过”'); return }
  submit(answer.value.trim())
}
function skip() { submit('') }

async function finish() {
  try {
    await fin.run(() => api.finishInterview(id))
    await reload()
    tab.value = 'report'
  } catch (e) { showError(e) }
}
async function startNextRound() {
  try { const result = await api.nextInterviewRound(id); router.push({ path: `/interviews/${result.interview_id}`, query: { task: result.task_id } }) }
  catch (e) { showError(e) }
}
</script>

<style scoped>
.center { max-width: 520px; margin: 60px auto; }
.issue { padding: 22px; margin-top: 16px; border: 1px solid #dbe8f8; border-radius: 18px; background: rgba(248,251,255,.75); }
.issue-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.issue-index { margin-right: 4px; color: #8aa0bf; font-size: 12px; font-weight: 700; }
.issue-qa { display: grid; grid-template-columns: 36px minmax(0,1fr); gap: 12px; align-items: start; padding: 12px 0; border-top: 1px solid #e5edf8; }
.issue-head + .issue-qa { border-top: 0; padding-top: 0; }
.label { color: var(--cc-text-3); }
.plain { padding-left: 18px; line-height: 1.8; color: var(--cc-text-2); }
.chat-layout { display: flex; gap: 16px; align-items: flex-start; }
.qlist { width: 240px; flex: none; position: sticky; top: 76px; }
.q { display: flex; gap: 8px; padding: 6px 8px; border-radius: 6px; font-size: 13px; color: var(--cc-text-2); }
.q.done { color: var(--cc-text-3); text-decoration: line-through; }
.q.now { background: var(--cc-primary-weak); color: var(--cc-primary); font-weight: 600; }
.lv { flex: none; font-size: 12px; padding: 0 6px; border-radius: 4px; background: #f2f3f5; }
.chat { display: flex; flex-direction: column; height: calc(100vh - 220px); }
.chat + .card { margin-top: 0; }
.messages { flex: 1; overflow: auto; padding-right: 6px; }
.msg { margin: 12px 0; display: flex; flex-direction: column; }
.msg.me { align-items: flex-end; }
.who { font-size: 12px; color: var(--cc-text-3); margin-bottom: 4px; }
.bubble { max-width: 80%; padding: 10px 14px; border-radius: 12px; line-height: 1.7; white-space: pre-wrap; }
.bot .bubble { background: #f2f3f5; border-top-left-radius: 2px; }
.me .bubble { background: var(--cc-primary); color: var(--cc-card); border-top-right-radius: 2px; }
.eval { margin: 4px 0 16px auto; max-width: 80%; padding: 10px 12px; border: 1px dashed var(--cc-border); border-radius: 8px; font-size: 13px; }
.dim { margin-right: 10px; color: var(--cc-text-3); }
.dim b { color: var(--cc-text-1); }
.composer { border-top: 1px solid var(--cc-border); padding-top: 12px; }
.small { font-size: 12px; margin-top: 4px; }
.big-score { font-size: 40px; font-weight: 700; color: var(--cc-primary); }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 16px; }
.grid3 .card + .card { margin-top: 0; }
.tag { margin: 0 6px 6px 0; }
.comparison { margin-bottom: 16px; background: rgba(231,242,255,.75) !important; }
.chat { height: min(760px, calc(100vh - 200px)); }
.messages { padding: 0 8px 0 0; }
.qa-pair { padding: 24px 8px; border-bottom: 1px solid #d7e5f7; }
.qa-pair:first-child { padding-top: 8px; }
.qa-row { display: grid; grid-template-columns: 42px minmax(0,1fr); gap: 14px; align-items: start; }
.qa-row + .qa-row { margin-top: 20px; }
.qa-letter { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; background: #e4efff; color: #2168e9; font-size: 18px; font-weight: 750; }
.answer-letter { background: #266bea; color: #fff; }
.qa-text { padding-top: 3px; color: var(--cc-text-1); font-size: 16px; line-height: 1.8; white-space: pre-wrap; }
.qa-row .who { color: #7690b2; font-size: 12px; margin-bottom: 4px; }
.eval { margin: 10px 0 0 56px; max-width: none; background: rgba(232,242,255,.7); border: 1px solid #d6e5fa; border-radius: 14px; }
.current-question { background: rgba(232,242,255,.55); border-radius: 18px; border: 1px solid #d7e7fb; margin-top: 18px; padding: 20px; }
@media (max-width: 800px) { .chat-layout { flex-direction: column; } .qlist { position: static; width: 100%; } .chat { width: 100%; height: 680px; } }
</style>
