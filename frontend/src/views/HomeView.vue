<template>
  <div>
    <section class="banner">
      <div class="banner-inner hero">
        <div class="grow">
          <div class="hello">CAREER DASHBOARD · 你好，{{ auth.user?.username }}</div>
          <h1>让每一份简历，都对准目标职位</h1>
          <div class="sub">完善资料 → 收藏职位 → 生成定向简历 → 模拟面试，四步完成求职准备</div>
          <div class="row mt24">
            <el-button type="primary" size="large" @click="$router.push('/jobs')">我的职位库</el-button>
            <el-button size="large" @click="$router.push('/profile')">完善资料</el-button>
          </div>
        </div>
        <div class="progress-card">
          <div class="progress-heading"><span>资料完整度</span><span class="progress-percent">{{ complete }}<small>%</small></span></div>
          <el-progress class="completeness-bar" :percentage="complete" :stroke-width="8" :show-text="false" color="#5b91e8" />
          <div class="progress-note">{{ complete === 100 ? '资料已完善，可以开始定向准备' : '继续完善资料，让简历和面试问题更准确' }}</div>
          <router-link class="progress-link" to="/profile">查看我的资料 <span aria-hidden="true">→</span></router-link>
        </div>
      </div>
    </section>

    <div class="page">
      <div class="steps">
        <div v-for="s in steps" :key="s.to" class="step" @click="$router.push(s.to)">
          <div class="step-no">0{{ s.no }}</div>
          <div class="step-title">{{ s.title }}</div>
          <div class="muted">{{ s.desc }}</div>
        </div>
      </div>

      <div class="grid mt24">
        <div class="card span2">
          <div class="card-title">
            <span>已收藏职位技能词云 <span class="muted title-sub">{{ insightMeta }}</span></span>
            <el-button text type="primary" @click="$router.push('/jobs')">查看词云 →</el-button>
          </div>
          <el-empty v-if="!insight?.terms?.length" :image-size="64" description="收藏职位后，这里会显示职位描述中的高频技能" />
          <template v-else>
            <div class="row cover-row">
              <el-progress type="circle" :percentage="Math.round(insight.coverage * 100)" :width="72" :stroke-width="7" />
              <div class="grow">
                <div class="muted">热门技能覆盖率</div>
                <div class="pills mt8">
                  <span v-for="t in insight.terms" :key="t.term" class="pill" :class="t.have ? 'blue' : 'orange'">
                    {{ t.term }} · {{ t.count }}
                  </span>
                </div>
              </div>
            </div>
            <div v-if="insight.missing_top.length" class="muted mt16">建议补充：{{ insight.missing_top.join('、') }}</div>
          </template>
        </div>

        <div class="card">
          <div class="card-title">我的待办 <el-button text type="primary" @click="todoOpen = true">+ 添加</el-button></div>
          <el-empty v-if="!todos.length" :image-size="48" description="记录笔试或面试时间，开始安排求职日程" />
          <div v-for="todo in todos" :key="todo.id" class="todo-line">
            <el-checkbox :model-value="todo.done" @change="(value: boolean) => toggleTodo(todo, value)" />
            <div class="grow" :class="{ 'todo-done': todo.done }"><b>{{ todo.title }}</b><div class="muted">{{ todo.kind === 'written_test' ? '笔试' : todo.kind === 'interview' ? '面试' : '其他' }} · {{ formatDue(todo.due_at) }}</div></div>
            <el-button text size="small" aria-label="删除待办" @click="removeTodo(todo.id)">×</el-button>
          </div>
        </div>

        <div class="card span3">
          <div class="card-title">投递漏斗</div>
          <div class="funnel-tabs">
            <button v-for="s in funnelStatuses" :key="s.value" class="funnel-tab"
                    :class="{ selected: expandedStage === s.value }"
                    :aria-expanded="expandedStage === s.value" aria-controls="funnel-jobs"
                    @click="toggleStage(s.value)">{{ s.label }} <b>{{ funnel[s.value] || 0 }}</b></button>
          </div>
          <div v-if="expandedStage" id="funnel-jobs" class="funnel-jobs" v-loading="loadingStage">
            <div class="row"><h3 class="grow">{{ funnelStatuses.find(s => s.value === expandedStage)?.label }}的职位</h3>
              <el-button text @click="expandedStage = ''">收起</el-button></div>
            <el-alert v-if="stageError" :title="stageError" type="error" :closable="false" />
            <el-empty v-else-if="!loadingStage && !stageJobs.length" description="这个阶段暂时没有职位" :image-size="48" />
            <article v-for="job in stageJobs" :key="job.id" class="funnel-job">
              <div class="row">
                <div class="grow"><router-link :to="`/jobs?id=${job.id}`" class="line-title">{{ job.title }}</router-link>
                  <div class="muted mt8">{{ job.company || '公司待补全' }} · {{ job.city || '城市待补全' }}</div></div>
                <el-select :model-value="job.status" :disabled="savingJob === job.id" style="width: 140px" aria-label="更新投递阶段"
                           @change="(status: string) => advanceJob(job, status)">
                  <el-option v-for="s in allStages" :key="s.value" :value="s.value" :label="s.label" />
                </el-select>
              </div>
              <ol class="job-progress" aria-label="岗位投递进度">
                <li v-for="(s, index) in funnelStatuses" :key="s.value"
                    :class="{ current: job.status === s.value, recorded: hasReached(job, s.value) }">
                  <span class="progress-dot">{{ index + 1 }}</span><span>{{ s.label }}</span>
                </li>
              </ol>
              <div class="muted">当前：{{ stageLabel(job.status) }}<span v-if="job.notes"> · {{ job.notes }}</span></div>
              <details v-if="job.status_history?.length" class="mt8"><summary>查看变更记录</summary>
                <div v-for="(h, index) in job.status_history" :key="index" class="muted mt8">{{ stageLabel(h.status) }} · {{ new Date(h.at).toLocaleString() }}</div>
              </details>
            </article>
          </div>
        </div>

        <div class="card">
          <div class="card-title">模拟面试 <el-button text type="primary" @click="$router.push('/interviews')">全部 →</el-button></div>
          <el-empty v-if="!interviews.length" :image-size="64" description="还没有面试记录" />
          <div v-for="i in interviews.slice(0, 5)" :key="i.id" class="line" @click="$router.push(`/interviews/${i.id}`)">
            <div class="grow ellipsis">{{ i.title }}</div>
            <span class="pill" :class="i.status === 'finished' ? 'green' : 'blue'">{{ statusText(i.status) }}</span>
          </div>
        </div>

        <div class="card span3">
          <div class="card-title">我的简历 <el-button text type="primary" @click="$router.push('/resumes')">全部 →</el-button></div>
          <el-empty v-if="!resumes.length" :image-size="64" description="还没有简历，在职位详情里点击“生成定向简历”" />
          <div class="resume-grid">
            <div v-for="r in resumes.slice(0, 4)" :key="r.id" class="resume" @click="$router.push(`/resumes/${r.id}`)">
              <div class="resume-title ellipsis">{{ r.title }}</div>
              <div class="row mt8"><span class="pill blue">v{{ r.current_version }}</span><span class="muted">{{ r.updated_at.slice(0, 10) }}</span></div>
            </div>
          </div>
        </div>
      </div>
      <div class="card mt24"><WorkflowTimeline recent /></div>
    </div>
    <el-dialog v-model="todoOpen" title="添加待办" width="420px">
      <el-form label-position="top">
        <el-form-item label="事项"><el-input v-model="todoForm.title" maxlength="120" placeholder="例如：产品经理一面" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="todoForm.kind" style="width: 100%"><el-option label="面试" value="interview" /><el-option label="笔试" value="written_test" /><el-option label="其他" value="other" /></el-select></el-form-item>
        <el-form-item label="关联职位"><el-select v-model="todoForm.job_id" clearable filterable placeholder="可选" style="width: 100%"><el-option v-for="job in jobs" :key="job.id" :label="`${job.title} · ${job.company || '公司待补全'}`" :value="job.id" /></el-select></el-form-item>
        <el-form-item label="时间"><el-date-picker v-model="todoForm.due_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="选择日期和时间" style="width: 100%" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="todoOpen = false">取消</el-button><el-button type="primary" :loading="savingTodo" @click="addTodo">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAuth } from '@/stores/auth'
import { api } from '@/api'
import { showError } from '@/api/http'
import { ElMessage } from 'element-plus'
import { completeness } from '@/utils/doc'
import WorkflowTimeline from '@/components/WorkflowTimeline.vue'

const auth = useAuth()
const complete = ref(0)
const insight = ref<any>(null)
const insightMeta = computed(() => {
  const i = insight.value
  return i?.sample_size ? `来自 ${i.sample_size} 个已收藏职位` : '按已收藏职位描述统计'
})
const todos = ref<any[]>([])
const jobs = ref<any[]>([])
const todoOpen = ref(false)
const savingTodo = ref(false)
const todoForm = ref<{ title: string; kind: string; due_at: string; job_id?: number }>({ title: '', kind: 'interview', due_at: '' })
const formatDue = (value: string) => new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
async function refreshTodos() { todos.value = await api.listTodos() }
async function addTodo() {
  if (!todoForm.value.title.trim() || !todoForm.value.due_at) { ElMessage.warning('请填写事项和时间'); return }
  savingTodo.value = true
  try { await api.createTodo({ ...todoForm.value, title: todoForm.value.title.trim() }); await refreshTodos(); todoOpen.value = false; todoForm.value = { title: '', kind: 'interview', due_at: '' } }
  catch (e) { showError(e) } finally { savingTodo.value = false }
}
async function toggleTodo(todo: any, done: boolean) { try { await api.updateTodo(todo.id, done); await refreshTodos() } catch (e) { showError(e) } }
async function removeTodo(id: number) { try { await api.deleteTodo(id); await refreshTodos() } catch (e) { showError(e) } }
const reminders = ref<any[]>([])
const funnel = ref<Record<string, number>>({})
const funnelStatuses = [{ value: 'saved', label: '已收藏' }, { value: 'applied', label: '已投递' },
  { value: 'written_test', label: '笔试' }, { value: 'interview', label: '面试' },
  { value: 'hr_interview', label: 'HR 面试' }, { value: 'offer', label: 'Offer' }]
const allStages = [...funnelStatuses, { value: 'rejected', label: '未通过' }, { value: 'dropped', label: '已放弃' }]
const expandedStage = ref('')
const stageJobs = ref<any[]>([])
const loadingStage = ref(false)
const stageError = ref('')
const savingJob = ref<number | null>(null)
let stageRequest = 0
const stageLabel = (status: string) => allStages.find(s => s.value === status)?.label || status
const hasReached = (job: any, status: string) => status === 'saved' || job.status === status || job.status_history?.some((h: any) => h.status === status)
async function loadStage() {
  const request = ++stageRequest
  const status = expandedStage.value
  loadingStage.value = true
  stageError.value = ''
  stageJobs.value = []
  try {
    const rows = await api.jobsByStatus(status)
    if (request === stageRequest && expandedStage.value === status) stageJobs.value = rows
  } catch (e) {
    if (request === stageRequest) stageError.value = '职位加载失败，请重新点击阶段重试'
  } finally { if (request === stageRequest) loadingStage.value = false }
}
async function toggleStage(status: string) {
  if (expandedStage.value === status) { expandedStage.value = ''; ++stageRequest; loadingStage.value = false; return }
  expandedStage.value = status
  await loadStage()
}
async function advanceJob(job: any, status: string) {
  savingJob.value = job.id
  try {
    await api.updateJob(job.id, { status })
    const data = await api.today()
    funnel.value = data.funnel
    reminders.value = data.reminders
    if (expandedStage.value) await loadStage()
  } catch (e) { showError(e) } finally { savingJob.value = null }
}
const resumes = ref<any[]>([])
const interviews = ref<any[]>([])
const steps = [
  { no: 1, title: '完善资料', desc: '上传 PDF，自动识别填充', to: '/profile' },
  { no: 2, title: '收藏职位', desc: '书签一键收藏 + 技能词云', to: '/jobs' },
  { no: 3, title: '定向简历', desc: 'STAR 法则润色，一键导出', to: '/resumes' },
  { no: 4, title: '模拟面试', desc: '简历诊断 + 项目深挖', to: '/interviews' },
]
const statusText = (s: string) =>
  ({ preparing: '准备中', ongoing: '进行中', answered_all: '待出报告', finished: '已完成', failed: '失败' } as any)[s] || s

onMounted(async () => {
  const [p, t, r, i] = await Promise.allSettled([api.getProfile(), api.today(), api.listResumes(), api.listInterviews()])
  if (p.status === 'fulfilled') complete.value = completeness(p.value.data)
  if (t.status === 'fulfilled') { insight.value = t.value.insight; reminders.value = t.value.reminders; funnel.value = t.value.funnel }
  if (r.status === 'fulfilled') resumes.value = r.value
  if (i.status === 'fulfilled') interviews.value = i.value
  const [todoResult, jobResult] = await Promise.allSettled([api.listTodos(), api.listJobs()])
  if (todoResult.status === 'fulfilled') todos.value = todoResult.value
  if (jobResult.status === 'fulfilled') jobs.value = jobResult.value
})
</script>

<style scoped>
.cover-row { align-items: flex-start; gap: var(--sp-5); }
.funnel-tabs { display: flex; flex-wrap: wrap; gap: 12px; }
.funnel-tab { border: 1px solid transparent; border-radius: 8px; padding: 10px 16px; background: var(--cc-primary-weak); color: var(--cc-primary); font: inherit; cursor: pointer; }
.funnel-tab:hover, .funnel-tab.selected { border-color: var(--cc-primary); background: var(--cc-primary-weak); }
.funnel-tab:focus-visible { outline: 2px solid var(--cc-primary); outline-offset: 3px; }
.funnel-jobs { margin-top: 20px; border-top: 1px solid var(--cc-border-light); padding-top: 16px; min-height: 80px; }
.funnel-job { border: 1px solid var(--cc-border-light); border-radius: 12px; padding: 20px; margin-top: 12px; }
.job-progress { display: flex; list-style: none; margin: 24px 0 16px; padding: 0; overflow-x: auto; }
.job-progress li { position: relative; display: flex; flex: 1; min-width: 90px; flex-direction: column; align-items: center; gap: 8px; color: #8c94a5; font-size: 13px; }
.job-progress li:not(:last-child)::after { position: absolute; content: ''; height: 2px; background: #e6eaf0; left: calc(50% + 18px); right: calc(-50% + 18px); top: 14px; }
.progress-dot { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: #edf0f5; }
.job-progress .recorded { color: var(--cc-primary); }
.recorded .progress-dot { background: var(--cc-primary-weak); }
.job-progress .current { color: var(--cc-primary-active); font-weight: 600; }
.current .progress-dot { background: var(--cc-primary); color: white; box-shadow: 0 0 0 4px #edf2ff; }
.funnel-job summary { cursor: pointer; color: #667085; }
.hero { display: flex; align-items: center; gap: var(--sp-10); padding-top: 56px; padding-bottom: 48px; }
.hero h1 { max-width: 800px; font-size: clamp(32px, 4vw, 52px); line-height: 1.22; }
.hello { color: var(--cc-primary); font-weight: 600; margin-bottom: var(--sp-2); }
.progress-card {
  width: 310px; flex: none; display: flex; flex-direction: column; gap: 16px;
  padding: 26px; background: rgba(255,255,255,.65); border: 1px solid rgba(255,255,255,.9);
  backdrop-filter: blur(24px) saturate(160%); border-radius: 28px; box-shadow: var(--cc-shadow-hover);
}
.progress-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; color: #526d96; font-size: 14px; font-weight: 600; }
.progress-percent { color: #245cae; font-size: 28px; line-height: 1; font-weight: 700; letter-spacing: -.04em; }
.progress-percent small { margin-left: 2px; font-size: 14px; font-weight: 600; }
.completeness-bar { width: 100%; }
.completeness-bar :deep(.el-progress-bar__outer) { background: #dceafa; }
.completeness-bar :deep(.el-progress-bar__inner) { box-shadow: 0 2px 8px rgba(70,133,222,.24); }
.progress-note { color: #7890b0; font-size: 12px; line-height: 1.6; }
.progress-link { align-self: flex-start; font-size: 13px; font-weight: 600; }

.steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--sp-4); }
.step {
  padding: var(--sp-5) var(--sp-6); background: rgba(255,255,255,.58); border: 1px solid rgba(255,255,255,.9);
  backdrop-filter: blur(22px); border-radius: var(--cc-radius); cursor: pointer; transition: box-shadow .2s, transform .2s;
  box-shadow: var(--cc-shadow);
}
.step:hover { box-shadow: var(--cc-shadow-hover); transform: translateY(-2px); }
.step-no { color: var(--cc-primary); font-size: 28px; font-weight: 700; font-family: Inter, Arial, sans-serif; }
.step-title { margin: var(--sp-1) 0; font-size: var(--fs-md); font-weight: 600; }

.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-4); }
.grid .card + .card { margin-top: 0; }
.span2 { grid-column: span 2; }
.span3 { grid-column: span 3; }
.title-sub { margin-left: var(--sp-2); font-weight: 400; }
.line { display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-3) var(--sp-2); border-radius: var(--cc-radius-sm); cursor: pointer; }
.line + .line { border-top: 1px solid var(--cc-border-light); }
.line:hover { background: var(--cc-bg-2); }
.line-title { font-size: var(--fs-md); font-weight: 500; flex: 1; min-width: 0; }
.resume-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--sp-3); }
.resume { padding: var(--sp-4); border: 1px solid #dce9fb; border-radius: var(--cc-radius-sm); cursor: pointer; background: rgba(241,247,255,.8); }
.resume:hover { border-color: var(--cc-primary-border); background: var(--cc-card); }
.resume-title { font-weight: 600; }
.todo-line { display: flex; align-items: center; gap: 10px; padding: 12px 0; border-top: 1px solid #e1ebf8; }
.todo-line b { font-size: 13px; font-weight: 600; }
.todo-done { opacity: .55; text-decoration: line-through; }
@media (max-width: 960px) {
  .hero { flex-direction: column; align-items: flex-start; } .steps, .grid, .resume-grid { grid-template-columns: 1fr; }
  .progress-card { width: 100%; }
  .span2, .span3 { grid-column: auto; }
}
</style>
