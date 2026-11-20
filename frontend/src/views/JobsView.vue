<template>
  <div class="jobs-page">
    <!-- 顶部横幅 -->
    <section class="banner">
      <div class="banner-inner hero">
        <div class="grow">
          <h1>我的职位库</h1>
          <div class="sub">只收录你亲自看过、收藏的职位：在 BOSS 等网站上点一下书签即可收藏完整 JD，或者直接粘贴。</div>
          <div class="row mt24 actions-top">
            <el-button type="primary" size="large" @click="openImport('bookmark')">⭐ 安装收藏书签</el-button>
            <el-button size="large" @click="openImport('paste')">粘贴 JD</el-button>
            <el-button size="large" @click="openBoss">去 BOSS 搜索 ↗</el-button>
          </div>
        </div>
        <div class="pref-card" @click="prefOpen = true">
          <div class="row"><b class="grow">求职偏好</b><a class="link">编辑</a></div>
          <template v-if="pref">
            <div class="pref-line">🎯 {{ pref.titles.length ? pref.titles.join(' / ') : '未设置目标职位' }}</div>
            <div class="pref-line">📍 {{ pref.cities.length ? pref.cities.join('、') : '城市不限' }}</div>
            <div class="pref-line">💰 {{ salaryText(pref.salary_min, pref.salary_max) }}</div>
            <div class="pref-line muted">{{ pref.enabled ? `每天 ${pref.push_time} 自动刷新市场技能样本` : '每日刷新未开启' }}</div>
          </template>
        </div>
      </div>
    </section>

    <div class="content">
      <!-- 技能需求词云 -->
      <section class="card insight">
        <div class="insight-head">
          <div>
            <h2>技能需求词云</h2>
            <div class="muted">{{ insightDesc }}</div>
          </div>
          <div class="seg">
            <button :class="{ active: source === 'library' }" @click="source = 'library'">我的职位库</button>
            <button :class="{ active: source === 'market' }" @click="switchMarket">市场样本</button>
          </div>
        </div>

        <TaskProgress class="mt16" :running="mk.running.value" :progress="mk.progress.value" :stage="mk.stage.value" />

        <div v-if="!currentInsight || !currentInsight.terms.length" class="insight-empty">
          <el-empty :image-size="72" :description="emptyInsightText">
            <el-button v-if="source === 'market'" type="primary" :loading="mk.running.value" @click="refreshMarket">采集市场样本</el-button>
            <el-button v-else type="primary" @click="openImport('bookmark')">去收藏职位</el-button>
          </el-empty>
        </div>
        <div v-else class="insight-body">
          <div class="cloud-wrap">
            <WordCloud :terms="cloudTerms" :selected="selectedTerm" @select="selectTerm" />
            <div class="legend">
              <span><i class="dot have" />你已具备</span><span><i class="dot miss" />你的资料中没有</span>
              <span v-if="showSoft"><i class="dot soft" />通用素质</span>
              <el-checkbox v-model="showSoft" size="small">显示通用素质</el-checkbox>
            </div>
          </div>
          <aside class="insight-side">
            <div class="cover">
              <el-progress type="circle" :percentage="Math.round(currentInsight.coverage * 100)" :width="96" :stroke-width="9"
                           :color="coverColor" />
              <div>
                <div class="cover-title">热门技能覆盖率</div>
                <div class="muted">前 15 个硬技能里，你的资料覆盖了多少（按出现次数加权）</div>
              </div>
            </div>
            <div class="top-list">
              <div v-for="t in topTerms" :key="t.term" class="top-item" :class="{ active: selectedTerm === t.term }" @click="selectTerm(t.term)">
                <span class="term ellipsis">{{ t.term }}</span>
                <div class="bar"><div :style="{ width: Math.max(6, t.ratio * 100) + '%' }" :class="t.have ? 'have' : 'miss'" /></div>
                <span class="num">{{ t.count }}</span>
                <span class="mark" :class="t.have ? 'have' : 'miss'">{{ t.have ? '✓' : '缺' }}</span>
              </div>
            </div>
            <div v-if="currentInsight.missing_top.length" class="advice">
              <b>建议补充</b>
              <div class="muted mt8">这些技能出现频率高，但你的资料里没有。如果你确实做过，请到“我的资料”补充相关经历；没做过的不要硬写。</div>
              <div class="pills mt8"><span v-for="m in currentInsight.missing_top" :key="m" class="pill orange">{{ m }}</span></div>
            </div>
            <div v-if="source === 'market'" class="row mt16">
              <span class="muted grow">{{ marketMeta }}</span>
              <el-button size="small" :loading="mk.running.value" @click="refreshMarket">重新采集</el-button>
            </div>
          </aside>
        </div>
      </section>

      <!-- 职位库 -->
      <section class="library">
        <div class="lib-head">
          <h2>收藏的职位 <span class="muted">{{ jobs.length }}</span></h2>
          <div class="chips">
            <button v-for="s in statusTabs" :key="s.value" class="chip" :class="{ active: statusFilter === s.value }"
                    @click="statusFilter = s.value">{{ s.label }} <b>{{ statusCount(s.value) }}</b></button>
          </div>
        </div>
        <div v-if="selectedTerm && source === 'library'" class="filter-tip">
          正在查看提到 <b>{{ selectedTerm }}</b> 的职位（{{ shownJobs.length }} 个）
          <a class="link" @click="selectTerm('')">清除筛选</a>
        </div>

        <div class="body">
          <div class="list">
            <div v-if="!shownJobs.length" class="card empty">
              <el-empty :image-size="72" :description="jobs.length ? '这个筛选下没有职位' : '职位库还是空的。安装书签后，在 BOSS 职位详情页点一下就能收藏'" />
            </div>
            <div v-for="j in shownJobs" :key="j.id" class="job-card" :class="{ active: current?.id === j.id }" @click="current = j">
              <div class="row">
                <div class="grow ellipsis job-title">{{ j.title }}</div>
                <span class="salary">{{ j.salary || '薪资面议' }}</span>
              </div>
              <div class="meta">
                <span>{{ j.company || '公司待补全' }}</span>
                <span class="dot-sep">{{ j.city || '城市未知' }}</span>
                <span v-if="j.detail?.experience" class="dot-sep">{{ j.detail.experience }}</span>
              </div>
              <div class="row bottom">
                <span class="pill" :class="statusClass(j.status)">{{ statusLabel(j.status) }}</span>
                <span v-if="j.detail_level === 'summary'" class="pill orange">仅摘要</span>
                <span v-if="!j.pref_match" class="pill">不符合偏好</span>
                <span class="grow" />
                <span class="muted">{{ (j.created_at || '').slice(5, 10) }} 收藏</span>
                <span class="score" :class="scoreClass(j.score)">{{ j.score }}</span>
              </div>
            </div>
          </div>

          <!-- 详情 -->
          <div v-if="current" class="detail card">
            <div class="row">
              <h2 class="grow">{{ current.title }}</h2>
              <span class="salary big">{{ current.salary || '薪资面议' }}</span>
            </div>
            <div class="meta detail-meta">
              <span>{{ current.company || '公司待补全' }}</span>
              <span class="dot-sep">{{ current.city || '城市未知' }}</span>
              <span class="dot-sep">{{ current.detail?.experience || '经验不限' }}</span>
              <span class="dot-sep">{{ current.detail?.education || '学历不限' }}</span>
            </div>
            <div class="row actions">
              <el-button type="primary" :loading="creating" :disabled="current.detail_level === 'summary'" @click="makeResume">生成定向简历</el-button>
              <el-button :disabled="current.detail_level === 'summary'" @click="$router.push({ path: '/interviews', query: { job_id: current.id } })">模拟面试</el-button>
              <span class="grow" />
              <a v-if="current.source_url" :href="current.source_url" target="_blank" rel="noopener">查看原文 ↗</a>
              <el-popconfirm title="从职位库删除？" @confirm="remove">
                <template #reference><el-button text type="danger">删除</el-button></template>
              </el-popconfirm>
            </div>
            <el-alert v-if="current.detail_level === 'summary'" type="warning" :closable="false" class="mb16"
                      title="这个职位只有摘要：打开原文，在详情页点一下书签补全 JD 后，才能生成简历或模拟面试" />

            <div class="progress-box">
              <div class="row">
                <b>投递进度</b>
                <el-select :model-value="current.status || 'saved'" style="width: 140px" @change="changeStatus">
                  <el-option v-for="s in jobStatuses" :key="s.value" :value="s.value" :label="s.label" />
                </el-select>
              </div>
              <ol class="steps-line">
                <li v-for="(s, i) in pipeline" :key="s.value" :class="{ done: pipelineIndex(current.status) >= i, now: current.status === s.value }">
                  <span class="step-dot">{{ i + 1 }}</span>{{ s.label }}
                </li>
              </ol>
              <el-input v-model="notesDraft" type="textarea" :rows="2" placeholder="备注：面试时间、联系人、薪资沟通……（失焦自动保存）" @blur="saveNotes" />
            </div>

            <div class="match">
              <div class="row">
                <span class="match-title">匹配度</span>
                <span class="score" :class="scoreClass(current.score)">{{ current.score }}</span>
                <span class="muted">能力匹配 60 + 职位名称 20 + 期望城市 10 + 期望薪资 10</span>
              </div>
              <div v-if="(current.pref_notes || []).length" class="pills mt8">
                <span v-for="n in current.pref_notes" :key="n" class="pill"
                      :class="n.includes('不符') ? 'red' : n.includes('未知') ? '' : 'green'">{{ n }}</span>
              </div>
              <div class="pills mt8">
                <span v-for="k in current.detail?.matched || []" :key="'m' + k" class="pill blue">{{ k }}</span>
                <span v-for="k in current.detail?.missing || []" :key="'x' + k" class="pill orange">缺少 {{ k }}</span>
              </div>
            </div>

            <p v-if="current.detail?.summary" class="summary">{{ current.detail.summary }}</p>
            <h3>职位描述</h3>
            <ul v-if="(current.detail?.responsibilities || []).length">
              <li v-for="(x, i) in current.detail.responsibilities" :key="i">{{ x }}</li>
            </ul>
            <p v-else class="muted">暂无</p>
            <h3>职位要求</h3>
            <ul v-if="(current.detail?.requirements || []).length">
              <li v-for="(x, i) in current.detail.requirements" :key="i">{{ x }}</li>
            </ul>
            <p v-else class="muted">暂无</p>
            <div class="row mt16"><el-button type="primary" plain @click="matchEvidence(current.id)">匹配已确认依据</el-button><span class="muted">逐条对照岗位要求与资料库中的已确认事实</span></div>
            <el-alert v-if="evidence?.status === 'stale'" class="mt16" title="资料已更新，当前匹配结果需要重新检查" type="warning" :closable="false" />
            <div v-if="evidence?.body?.matches?.length" class="evidence-list">
              <div v-for="match in evidence.body.matches" :key="match.req_id" class="evidence-row">
                <span class="pill" :class="match.coverage === 'none' ? 'orange' : 'blue'">{{ match.coverage === 'none' ? '缺少依据' : '部分相关' }}</span>
                <div class="grow"><b>{{ match.requirement }}</b><div v-for="item in match.evidence" :key="item.evidence_id" class="muted mt8">依据：{{ item.statement }}</div></div>
              </div>
            </div>
            <WorkflowTimeline :key="timelineVersion" :job-id="current.id" />
          </div>
          <div v-else class="detail card"><el-empty description="选择左侧职位查看详情" /></div>
        </div>
      </section>
    </div>

    <!-- 求职偏好 -->
    <el-drawer v-model="prefOpen" title="求职偏好" size="460px">
      <el-form v-if="prefForm" label-position="top" class="pref-form">
        <el-form-item label="目标职位（最多 3 个）">
          <TagInput v-model="prefForm.titles" :limit="3" placeholder="输入后回车，如 后端开发、算法实习" />
        </el-form-item>
        <el-form-item label="期望工作地点（最多 5 个，不填表示不限）">
          <TagInput v-model="prefForm.cities" :limit="5" :options="cityOptions" placeholder="选择或输入城市" />
        </el-form-item>
        <el-form-item label="期望薪资（月薪，单位 K）">
          <div class="w100">
            <div class="pills">
              <button v-for="p in salaryPresets" :key="p.label" class="chip"
                      :class="{ active: prefForm.salary_min === p.min && prefForm.salary_max === p.max }"
                      @click.prevent="prefForm.salary_min = p.min; prefForm.salary_max = p.max">{{ p.label }}</button>
            </div>
            <div class="row mt8">
              <el-input-number v-model="prefForm.salary_min" :min="0" :max="200" controls-position="right" />
              <span class="muted">至</span>
              <el-input-number v-model="prefForm.salary_max" :min="0" :max="200" controls-position="right" />
              <span class="muted">K / 月</span>
            </div>
            <div class="muted mt8">用于计算职位匹配度；日薪按每月 21.75 个工作日换算。0 表示不限。</div>
          </div>
        </el-form-item>
        <el-form-item label="市场样本来源">
          <el-checkbox-group v-model="prefForm.sources">
            <el-checkbox v-for="s in leadSources" :key="s.value" :value="s.value">{{ s.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <div class="push-box">
          <div class="row">
            <div class="grow"><b>每日刷新市场技能样本</b><div class="muted">每天按目标职位重新采集一次搜索摘要，更新“市场样本”词云</div></div>
            <el-switch v-model="prefForm.enabled" />
          </div>
          <div class="row mt16">
            <span class="text-2">刷新时间</span>
            <el-time-select v-model="prefForm.push_time" start="06:00" step="00:30" end="23:30" style="width: 130px" />
          </div>
          <div class="muted mt8">上次刷新：{{ prefForm.last_push_date || '无' }}</div>
        </div>
      </el-form>
      <template #footer>
        <div class="row">
          <span class="grow" />
          <el-button @click="prefOpen = false">取消</el-button>
          <el-button type="primary" :loading="savingPref" @click="savePref(true)">保存</el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 导入职位 -->
    <el-dialog v-model="importOpen" title="收藏职位" width="720px">
      <el-tabs v-model="importTab">
        <el-tab-pane label="一键收藏书签（推荐）" name="bookmark">
          <ol class="steps">
            <li>按 <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>B</kbd> 打开浏览器书签栏。</li>
            <li>把下面这个按钮<b>拖到书签栏</b>上：
              <div class="bm-wrap"><a class="bookmarklet" :href="bookmarklet" @click.prevent="bmHint">⭐ 收藏到 CareerCraft</a></div>
            </li>
            <li>在你自己的浏览器里正常登录 BOSS 直聘，打开某个<b>职位详情页</b>（或搜索页里选中一个职位），点击书签。</li>
            <li>弹出的小窗口里检查识别结果，点“保存到职位库”。识别不准时，先用鼠标选中 JD 文字再点书签。</li>
          </ol>
          <el-alert type="info" :closable="false" show-icon
                    title="书签只读取你当前正在看的这一页，由你手动点击触发，相当于自动复制粘贴；不会批量抓取，也不会绕过登录或验证。" />
          <div class="muted mt8">点击书签没有反应时：允许招聘网站弹出窗口，并确认 CareerCraft 正在运行（{{ appOrigin }}）。换了访问地址或端口后需要重新拖一次书签。</div>
        </el-tab-pane>
        <el-tab-pane label="粘贴 JD（支持批量）" name="paste">
          <div class="muted mb8">职位之间用单独一行 <code>---</code> 隔开（最多 10 个），每段里的第一个链接会作为原文链接。</div>
          <el-input v-model="importText" type="textarea" :rows="14"
                    :placeholder="'后端开发实习生 300-400元/天 某某科技 深圳\n岗位职责：...\n任职要求：...\nhttps://www.zhipin.com/job_detail/xxx.html\n---\n第二个职位……'" />
          <div class="muted mt8">识别到 {{ pastedJobs.length }} 个职位{{ pastedJobs.length > 10 ? '（只导入前 10 个）' : '' }}</div>
          <TaskProgress class="mt8" :running="imp.running.value" :progress="imp.progress.value" :stage="imp.stage.value" />
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="importOpen = false">关闭</el-button>
        <el-button v-if="importTab === 'paste'" type="primary" :loading="imp.running.value"
                   :disabled="!pastedJobs.length" @click="doImport">解析并保存 {{ Math.min(pastedJobs.length, 10) }} 个职位</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { showError } from '@/api/http'
import { useTask } from '@/composables/useTask'
import TagInput from '@/components/TagInput.vue'
import TaskProgress from '@/components/TaskProgress.vue'
import WordCloud from '@/components/WordCloud.vue'
import WorkflowTimeline from '@/components/WorkflowTimeline.vue'
import { scoreClass } from '@/utils/doc'
import { buildBookmarklet, splitJobs } from '@/utils/bookmarklet'

const route = useRoute()
const evidence = ref<any>(null)
const timelineVersion = ref(0)
async function matchEvidence(id: number) { try { const artifact = await api.matchJobEvidence(id); evidence.value = artifact; timelineVersion.value++; ElMessage.success(`已匹配 ${artifact.body.matches.length} 条要求`) } catch (e) { showError(e) } }
const router = useRouter()
const cityOptions = ['北京', '上海', '深圳', '广州', '杭州', '成都', '南京', '武汉', '西安', '苏州', '长沙', '远程']
const leadSources = [
  { value: 'boss', label: 'BOSS 直聘' }, { value: 'tencent', label: '腾讯校招' },
  { value: 'bytedance', label: '字节校招' }, { value: 'alibaba', label: '阿里校招' },
  { value: 'huawei', label: '华为校招' }, { value: 'nowcoder', label: '牛客' }, { value: 'shixiseng', label: '实习僧' },
]
const salaryPresets = [
  { label: '不限', min: 0, max: 0 }, { label: '5K 以下', min: 0, max: 5 }, { label: '5-10K', min: 5, max: 10 },
  { label: '10-15K', min: 10, max: 15 }, { label: '15-25K', min: 15, max: 25 }, { label: '25-40K', min: 25, max: 40 },
  { label: '40K 以上', min: 40, max: 0 },
]
const jobStatuses = [
  { value: 'saved', label: '已收藏' }, { value: 'applied', label: '已投递' },
  { value: 'written_test', label: '笔试' }, { value: 'interview', label: '面试' },
  { value: 'hr_interview', label: 'HR 面' }, { value: 'offer', label: 'Offer' },
  { value: 'rejected', label: '未通过' }, { value: 'dropped', label: '已放弃' },
]
const pipeline = jobStatuses.slice(0, 6)
const statusTabs = [{ value: '', label: '全部' }, ...jobStatuses]
const statusLabel = (v: string) => jobStatuses.find((s) => s.value === v)?.label || '已收藏'
const statusClass = (v: string) => (v === 'offer' ? 'green' : v === 'rejected' || v === 'dropped' ? '' : v === 'saved' ? '' : 'blue')
const pipelineIndex = (v: string) => pipeline.findIndex((s) => s.value === v)

// 词云状态（先声明：下面的 shownJobs / watch 在初始化时就会读取它们）
const source = ref<'library' | 'market'>('library')
const library = ref<any>(null)
const market = ref<any>(null)
const selectedTerm = ref('')
const showSoft = ref(false)
const mk = useTask()

// ------------------------------------------------ 职位库
const jobs = ref<any[]>([])
const current = ref<any>(null)
watch(() => current.value?.id, async (id) => { evidence.value = id ? await api.jobEvidence(id).catch(() => null) : null })
const statusFilter = ref('')
const creating = ref(false)
const statusCount = (v: string) => (v ? jobs.value.filter((j) => (j.status || 'saved') === v).length : jobs.value.length)

const shownJobs = computed(() => {
  let list = jobs.value
  if (statusFilter.value) list = list.filter((j) => (j.status || 'saved') === statusFilter.value)
  if (selectedTerm.value && source.value === 'library') {
    const ids = new Set(library.value?.terms.find((t: any) => t.term === selectedTerm.value)?.doc_ids || [])
    list = list.filter((j) => ids.has(j.id))
  }
  return list
})
watch(shownJobs, (list) => {
  if (!current.value || !list.some((j) => j.id === current.value.id)) current.value = list[0] || null
})

async function loadJobs() {
  try {
    jobs.value = await api.listJobs('all')
    const want = Number(route.query.id)
    current.value = jobs.value.find((j) => j.id === want) || jobs.value.find((j) => j.id === current.value?.id)
      || shownJobs.value[0] || null
  } catch (e) { showError(e) }
}
watch(() => route.query.id, () => {
  const want = Number(route.query.id)
  const hit = jobs.value.find((j) => j.id === want)
  if (hit) { statusFilter.value = ''; selectTerm(''); current.value = hit }
})

async function changeStatus(status: string) {
  if (!current.value) return
  try { Object.assign(current.value, await api.updateJob(current.value.id, { status })); loadLibrary() }
  catch (e) { showError(e) }
}
const notesDraft = ref('')
watch(current, (j) => { notesDraft.value = j?.notes || '' }, { immediate: true })
async function saveNotes() {
  if (!current.value) return
  const notes = notesDraft.value
  if (notes === (current.value.notes || '')) return
  try { Object.assign(current.value, await api.updateJob(current.value.id, { notes })) } catch (e) { showError(e) }
}
async function remove() {
  try { await api.deleteJob(current.value.id); current.value = null; await Promise.all([loadJobs(), loadLibrary()]) }
  catch (e) { showError(e) }
}
async function makeResume() {
  creating.value = true
  try {
    const res = await api.createResume(current.value.id)
    router.push({ path: `/resumes/${res.resume_id}`, query: { task: res.task_id } })
  } catch (e) { showError(e) } finally { creating.value = false }
}
async function openBoss() {
  try { window.open((await api.bossLink()).url, '_blank', 'noopener') } catch (e) { showError(e) }
}

// ------------------------------------------------ 词云
const currentInsight = computed(() => (source.value === 'library' ? library.value : market.value))
const cloudTerms = computed(() => (currentInsight.value?.terms || []).filter((t: any) => showSoft.value || t.category !== 'soft'))
const topTerms = computed(() => cloudTerms.value.filter((t: any) => t.category !== 'soft').slice(0, 10))
const coverColor = computed(() => {
  const c = currentInsight.value?.coverage || 0
  return c >= 0.7 ? '#00b42a' : c >= 0.4 ? '#3370ff' : '#ff8800'
})
const insightDesc = computed(() => {
  if (source.value === 'library') return `统计你收藏的 ${library.value?.total_docs || 0} 份 JD 中各项技能被提到的次数；点击词语可以筛选下方职位`
  return market.value ? `来自搜索引擎的 ${market.value.sample_size} 份目标岗位 JD 摘要（只统计词频，不展示具体职位，岗位是否过期不影响结论）`
    : '按求职偏好里的目标职位，采集搜索引擎中的 JD 摘要做词频统计'
})
const emptyInsightText = computed(() =>
  source.value === 'library' ? '收藏几个职位后，这里会显示它们最常要求的技能' : '还没有市场样本。点击下方按钮按目标职位采集一次（约 20~40 秒，不调用大模型）')
const marketMeta = computed(() => {
  const m = market.value
  if (!m) return ''
  const q = m.query || {}
  return `${(q.titles || []).join(' / ')}${q.cities?.length ? ' · ' + q.cities.join('、') : ''} · 更新于 ${(m.created_at || '').slice(5, 16).replace('T', ' ')}`
})

async function loadLibrary() { try { library.value = await api.libraryInsight() } catch (e) { showError(e) } }
async function loadMarket() { try { market.value = await api.marketInsight() } catch (e) { showError(e) } }
function selectTerm(term: string) {
  selectedTerm.value = term
  if (term && source.value === 'library') statusFilter.value = ''
}
function switchMarket() { source.value = 'market'; selectTerm('') }
watch(source, () => selectTerm(''))

async function refreshMarket() {
  if (!pref.value?.titles?.length) { ElMessage.warning('请先在“求职偏好”里填写目标职位'); prefOpen.value = true; return }
  try {
    const res = await mk.run(() => api.refreshMarketInsight(pref.value.titles, pref.value.cities))
    res.warnings?.forEach((w: string) => ElMessage.warning(w))
    market.value = res
    ElMessage.success(`已采集 ${res.sample_size} 份 JD 样本`)
  } catch (e) { showError(e) }
}

// ------------------------------------------------ 求职偏好
const pref = ref<any>(null)
const prefForm = ref<any>(null)
const prefOpen = ref(!!route.query.pref)
const savingPref = ref(false)
function salaryText(min: number, max: number) {
  if (!min && !max) return '薪资不限'
  if (min && max) return `${min}-${max}K/月`
  return min ? `${min}K 以上/月` : `${max}K 以下/月`
}
async function loadPref() {
  try { pref.value = await api.getPush(); prefForm.value = JSON.parse(JSON.stringify(pref.value)) } catch (e) { showError(e) }
}
watch(prefOpen, (open) => {
  if (open && pref.value) prefForm.value = JSON.parse(JSON.stringify(pref.value))
  if (!open && route.query.pref) router.replace({ query: { ...route.query, pref: undefined } })
})
watch(() => route.query.pref, (v) => { if (v) prefOpen.value = true })
async function savePref(close = false) {
  const f = prefForm.value
  if (!f) return
  if (f.salary_min && f.salary_max && f.salary_min > f.salary_max) { ElMessage.warning('薪资下限不能高于上限'); return }
  if (f.enabled && !f.titles.length) { ElMessage.warning('开启每日刷新前请填写目标职位'); return }
  savingPref.value = true
  try {
    pref.value = await api.savePush({
      enabled: f.enabled, titles: f.titles, cities: f.cities, sources: f.sources || [], salary_min: f.salary_min || 0,
      salary_max: f.salary_max || 0, top_n: f.top_n || 10, push_time: f.push_time,
    })
    ElMessage.success('求职偏好已保存')
    if (close) prefOpen.value = false
  } catch (e) { showError(e) } finally { savingPref.value = false }
}

// ------------------------------------------------ 导入
const importOpen = ref(false)
const importTab = ref<'paste' | 'bookmark'>('bookmark')
const importText = ref('')
const pastedJobs = computed(() => splitJobs(importText.value))
const appOrigin = location.origin
const bookmarklet = buildBookmarklet(appOrigin)
const imp = useTask()
function openImport(t: 'paste' | 'bookmark') { importTab.value = t; importOpen.value = true }
function bmHint() { ElMessage.info('请把这个按钮拖到浏览器书签栏，而不是直接点击') }
async function doImport() {
  const items = pastedJobs.value.slice(0, 10)
  if (!items.length) { ElMessage.warning('JD 内容太短'); return }
  try {
    const res = await imp.run(() => api.importJobs(items))
    importOpen.value = false
    importText.value = ''
    statusFilter.value = ''
    await Promise.all([loadJobs(), loadLibrary()])
    current.value = jobs.value.find((j) => j.id === res.job_ids[0]) || current.value
    ElMessage.success(`已保存 ${res.job_ids.length} 个职位`)
    res.failed?.forEach((f: string) => ElMessage({ message: f, type: 'warning', duration: 6000 }))
  } catch (e) { showError(e) }
}

// 从书签小窗口保存后回到本页时刷新
function onFocus() { loadJobs(); loadLibrary() }
onMounted(async () => {
  window.addEventListener('focus', onFocus)
  await Promise.all([loadJobs(), loadLibrary(), loadMarket(), loadPref()])
  if (route.query.source === 'market') source.value = 'market'
})
onBeforeUnmount(() => window.removeEventListener('focus', onFocus))
</script>

<style scoped>
.hero { display: flex; align-items: center; gap: var(--sp-8); padding-top: 36px; padding-bottom: 32px; }
.actions-top { flex-wrap: wrap; }
.pref-card {
  width: 280px; flex: none; padding: var(--sp-5); background: var(--cc-card); border-radius: var(--cc-radius);
  box-shadow: var(--cc-shadow-hover); cursor: pointer; transition: transform .2s;
}
.pref-card:hover { transform: translateY(-2px); }
.pref-line { margin-top: var(--sp-2); color: var(--cc-text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.link { color: var(--cc-primary); cursor: pointer; }

.content { max-width: var(--cc-content-w); margin: 0 auto; padding: var(--sp-6) var(--sp-6) 64px; }

/* 词云 */
.insight h2, .library h2 { margin: 0; font-size: var(--fs-xl); font-weight: 600; }
.insight-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--sp-4); }
.insight-head .muted { margin-top: 4px; max-width: 640px; }
.seg { display: inline-flex; flex: none; padding: 3px; background: #eceef1; border-radius: 8px; }
.seg button { border: 0; background: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; color: var(--cc-text-2);
  font-size: var(--fs-base); font-family: inherit; }
.seg button.active { background: var(--cc-card); color: var(--cc-text-1); font-weight: 600; box-shadow: 0 1px 3px rgba(0, 0, 0, .08); }
.insight-empty { padding: var(--sp-6) 0; }
.insight-body { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: var(--sp-6); margin-top: var(--sp-4); }
.cloud-wrap { min-height: 320px; display: flex; flex-direction: column; background: linear-gradient(180deg, #fafcff, var(--cc-card));
  border: 1px solid var(--cc-border-light); border-radius: var(--cc-radius); padding: var(--sp-3); }
.cloud-wrap svg { flex: 1; min-height: 280px; }
.legend { display: flex; align-items: center; gap: var(--sp-4); padding: 0 var(--sp-2); color: var(--cc-text-3); font-size: var(--fs-sm); }
.legend .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }
.dot.have { background: var(--cc-primary); } .dot.miss { background: #ff8800; } .dot.soft { background: #a8adb6; }
.cover { display: flex; align-items: center; gap: var(--sp-4); }
.cover-title { font-weight: 600; font-size: var(--fs-md); margin-bottom: 4px; }
.top-list { margin-top: var(--sp-4); }
.top-item { display: grid; grid-template-columns: 96px 1fr 28px 22px; align-items: center; gap: var(--sp-2);
  padding: 5px 6px; border-radius: 6px; cursor: pointer; }
.top-item:hover, .top-item.active { background: var(--cc-primary-weak); }
.term { font-size: var(--fs-sm); }
.bar { height: 8px; background: #f2f3f5; border-radius: 4px; overflow: hidden; }
.bar div { height: 100%; border-radius: 4px; }
.bar .have { background: var(--cc-primary); } .bar .miss { background: #ff8800; }
.num { text-align: right; color: var(--cc-text-3); font-size: var(--fs-sm); }
.mark { text-align: center; font-size: var(--fs-xs); font-weight: 600; }
.mark.have { color: #00a828; } .mark.miss { color: #e07000; }
.advice { margin-top: var(--sp-4); padding: var(--sp-3) var(--sp-4); background: #fff8ef; border-radius: var(--cc-radius-sm); }

/* 职位库 */
.library { margin-top: var(--sp-8); }
.lib-head { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-4); flex-wrap: wrap; }
.chips { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
.chip { border: 1px solid var(--cc-border); background: var(--cc-card); color: var(--cc-text-2); border-radius: 16px; padding: 4px 12px;
  cursor: pointer; font-size: var(--fs-sm); font-family: inherit; }
.chip b { margin-left: 2px; font-weight: 600; }
.chip:hover { color: var(--cc-primary); border-color: var(--cc-primary-border); }
.chip.active { color: var(--cc-primary); border-color: var(--cc-primary); background: var(--cc-primary-weak); }
.filter-tip { margin-top: var(--sp-3); padding: var(--sp-2) var(--sp-4); background: var(--cc-primary-weak); border-radius: var(--cc-radius-sm); color: var(--cc-text-2); }
.filter-tip .link { margin-left: var(--sp-3); }

.body { display: flex; gap: var(--sp-5); margin-top: var(--sp-4); align-items: flex-start; }
.list { width: 440px; flex: none; }
.job-card { background: var(--cc-card); border: 1px solid var(--cc-border-light); border-radius: var(--cc-radius);
  padding: var(--sp-5) var(--sp-5) var(--sp-4); margin-bottom: var(--sp-3); cursor: pointer;
  transition: box-shadow .2s, border-color .2s, transform .2s; }
.job-card { background: rgba(255,255,255,.66); border-color: rgba(255,255,255,.9);
  backdrop-filter: blur(20px) saturate(150%); box-shadow: var(--cc-shadow); padding: 24px; }
.job-card:hover { box-shadow: var(--cc-shadow-hover); transform: translateY(-1px); }
.job-card.active { border-color: #8bb7ff; box-shadow: 0 0 0 1px #8bb7ff inset, var(--cc-shadow-hover); }
.evidence-list { margin-top: 16px; border-top: 1px solid #dce8f7; }
.evidence-row { display: flex; align-items: flex-start; gap: 12px; padding: 14px 0; border-bottom: 1px solid #e6effa; }
.evidence-row b { color: var(--cc-text-1); font-weight: 600; }
.job-title { font-size: var(--fs-lg); font-weight: 600; }
.job-card:hover .job-title { color: var(--cc-primary); }
.meta { margin-top: 6px; color: var(--cc-text-2); font-size: var(--fs-sm); }
.bottom { margin-top: var(--sp-4); padding-top: var(--sp-4); border-top: 1px solid #e2ecfa; gap: var(--sp-2); }

.detail { flex: 1; min-width: 0; position: sticky; top: calc(var(--cc-header-h) + 16px);
  max-height: calc(100vh - var(--cc-header-h) - 32px); overflow: auto; padding: var(--sp-8); }
.detail { border-radius: 26px; }
.detail h2 { margin: 0; font-size: 24px; font-weight: 600; }
.salary.big { font-size: var(--fs-xl); }
.detail-meta { margin-top: var(--sp-2); font-size: var(--fs-base); }
.actions { margin: var(--sp-5) 0; padding-bottom: var(--sp-5); border-bottom: 1px solid var(--cc-border-light); }
.progress-box { padding: var(--sp-4); border: 1px solid var(--cc-border-light); border-radius: var(--cc-radius-sm); margin-bottom: var(--sp-4); }
.steps-line { display: flex; gap: 0; padding: 0; margin: var(--sp-4) 0; list-style: none; }
.steps-line li { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; font-size: var(--fs-xs);
  color: var(--cc-text-3); position: relative; }
.steps-line li + li::before { content: ""; position: absolute; top: 11px; right: 50%; width: 100%; height: 2px; background: var(--cc-border); z-index: 0; }
.steps-line li.done + li.done::before, .steps-line li.done + li.now::before { background: var(--cc-primary); }
.step-dot { width: 24px; height: 24px; border-radius: 50%; background: #f2f3f5; display: flex; align-items: center;
  justify-content: center; font-weight: 600; position: relative; z-index: 1; }
.steps-line li.done { color: var(--cc-text-1); }
.steps-line li.done .step-dot { background: var(--cc-primary); color: var(--cc-card); }
.steps-line li.now .step-dot { box-shadow: 0 0 0 4px #d6e2ff; }
.match { padding: var(--sp-4); background: var(--cc-bg-2); border-radius: var(--cc-radius-sm); }
.match-title { font-weight: 600; }
.summary { margin: var(--sp-5) 0 0; padding: var(--sp-3) var(--sp-4); background: var(--cc-primary-weak); border-radius: var(--cc-radius-sm); color: var(--cc-text-2); }
.detail h3 { margin: var(--sp-6) 0 var(--sp-3); font-size: var(--fs-md); font-weight: 600; }
.detail ul { margin: 0; padding-left: 20px; color: var(--cc-text-2); line-height: 1.9; }

.pref-form :deep(.el-form-item) { margin-bottom: var(--sp-6); }
.w100 { width: 100%; }
.push-box { padding: var(--sp-4); border-radius: var(--cc-radius-sm); background: var(--cc-bg-2); border: 1px solid var(--cc-border-light); }
.steps { padding-left: 20px; line-height: 2; color: var(--cc-text-2); }
.bm-wrap { margin: var(--sp-2) 0 var(--sp-1); }
.bookmarklet { display: inline-block; padding: 8px 18px; border-radius: 8px; background: var(--cc-primary); color: var(--cc-card); font-weight: 600; cursor: grab; }
.bookmarklet:hover { color: var(--cc-card); }
kbd { padding: 1px 6px; border: 1px solid var(--cc-border); border-bottom-width: 2px; border-radius: 4px; background: var(--cc-card); font-size: 12px; }

@media (max-width: 1000px) {
  .hero { flex-direction: column; align-items: flex-start; } .pref-card { width: 100%; }
  .insight-body { grid-template-columns: 1fr; }
  .body { flex-direction: column; } .list { width: 100%; } .detail { position: static; max-height: none; width: 100%; }
}
</style>
