<template>
  <div class="page">
    <div class="page-title">
      <div><h1>模拟面试</h1><div class="sub">选择面试官看到的材料范围，再用真实经历回答问题</div></div>
    </div>

    <div class="layout">
      <div class="card new">
        <div class="card-title">开始一场新面试</div>
        <el-form label-position="top">
          <el-form-item label="目标岗位">
            <el-select v-model="jobId" filterable placeholder="选择岗位" style="width: 100%">
              <el-option v-for="j in jobs" :key="j.id" :label="`${j.title}｜${j.company}`" :value="j.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="面试官看到的简历">
            <el-radio-group v-model="sourceType">
              <el-radio value="document">上传的原始 PDF</el-radio>
              <el-radio value="resume">简历工坊中的版本</el-radio>
              <el-radio value="profile">我的资料</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="sourceType === 'document'" label="选择 PDF">
            <el-select v-model="docId" placeholder="选择已上传的 PDF（在“我的资料 → 导入简历 PDF”上传）" style="width: 100%">
              <el-option v-for="d in documents" :key="d.id" :label="`${d.filename}（${d.created_at.slice(0, 10)}）`" :value="d.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="sourceType === 'resume'" label="选择简历（使用最新版本）">
            <el-select v-model="resumeId" placeholder="选择简历" style="width: 100%">
              <el-option v-for="r in resumes.filter((x) => x.current_version)" :key="r.id" :label="`${r.title}（v${r.current_version}）`" :value="r.id" />
            </el-select>
          </el-form-item>
          <el-form-item :label="`题目数量：${total}`">
            <el-slider v-model="total" :min="4" :max="16" :step="1" />
          </el-form-item>
          <el-form-item label="面试模式"><el-radio-group v-model="interviewMode"><el-radio value="blind">盲面：仅简历与岗位名称</el-radio><el-radio value="contrast">对照：增加岗位要求与简历原文引用</el-radio></el-radio-group></el-form-item>
          <el-button type="primary" class="w100" :loading="starting" @click="start">开始诊断并生成问题</el-button>
        </el-form>
      </div>

      <div class="grow">
        <el-empty v-if="!list.length" description="还没有面试记录" />
        <div v-for="i in list" :key="i.id" class="card item" @click="$router.push(`/interviews/${i.id}`)">
          <div class="row">
            <div class="grow ellipsis"><b>{{ i.title }}</b></div>
            <el-tag size="small" :type="i.status === 'finished' ? 'success' : i.status === 'failed' ? 'danger' : 'info'">{{ statusText(i.status) }}</el-tag>
          </div>
          <div class="row mt8">
            <span class="muted grow">{{ i.source_label }} · 已答 {{ i.answered }} 轮 · {{ i.created_at.slice(0, 16).replace('T', ' ') }}</span>
            <el-popconfirm title="删除这条面试记录？" @confirm="remove(i.id)">
              <template #reference><el-button text type="danger" size="small" @click.stop>删除</el-button></template>
            </el-popconfirm>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { showError } from '@/api/http'

const route = useRoute()
const router = useRouter()
const list = ref<any[]>([])
const jobs = ref<any[]>([])
const documents = ref<any[]>([])
const resumes = ref<any[]>([])
const jobId = ref<number | null>(Number(route.query.job_id) || null)
const sourceType = ref<'document' | 'resume' | 'profile'>('document')
const docId = ref<number | null>(null)
const resumeId = ref<number | null>(null)
const total = ref(10)
const interviewMode = ref<'blind' | 'contrast'>('blind')
const starting = ref(false)
const statusText = (s: string) =>
  ({ preparing: '准备中', ongoing: '进行中', answered_all: '待出报告', finished: '已完成', failed: '失败' } as any)[s] || s

async function load() {
  const [l, j, d, r] = await Promise.allSettled([api.listInterviews(), api.listJobs('all'), api.listDocuments(), api.listResumes()])
  if (l.status === 'fulfilled') list.value = l.value
  if (j.status === 'fulfilled') jobs.value = [...j.value.filter((x: any) => x.is_target), ...j.value.filter((x: any) => !x.is_target)]
  if (d.status === 'fulfilled') { documents.value = d.value; docId.value = docId.value || d.value[0]?.id || null }
  if (r.status === 'fulfilled') resumes.value = r.value
  if (!documents.value.length && sourceType.value === 'document') sourceType.value = resumes.value.length ? 'resume' : 'profile'
}
onMounted(load)

async function start() {
  if (!jobId.value) { ElMessage.warning('请选择目标岗位'); return }
  let source: any = { type: sourceType.value }
  if (sourceType.value === 'document') {
    if (!docId.value) { ElMessage.warning('请选择 PDF'); return }
    source.id = docId.value
  } else if (sourceType.value === 'resume') {
    if (!resumeId.value) { ElMessage.warning('请选择简历'); return }
    source.id = resumeId.value
  }
  starting.value = true
  try {
    const res = await api.createInterview(jobId.value, source, total.value, interviewMode.value)
    router.push({ path: `/interviews/${res.interview_id}`, query: { task: res.task_id } })
  } catch (e) { showError(e) } finally { starting.value = false }
}

async function remove(id: number) {
  try { await api.deleteInterview(id); await load() } catch (e) { showError(e) }
}
</script>

<style scoped>
.layout { display: flex; gap: 16px; align-items: flex-start; }
.new { width: 420px; flex: none; }
.item { cursor: pointer; }
.item:hover { border-color: var(--cc-primary); }
.grow .card + .card { margin-top: 12px; }
.w100 { width: 100%; }
</style>
