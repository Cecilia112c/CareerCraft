<template>
  <section class="workflow-panel">
    <div class="workflow-title">协作时间线</div>
    <div v-if="!runs.length" class="workflow-empty">还没有工作流记录</div>
    <div v-for="run in runs" :key="run.id" class="workflow-run">
      <div class="workflow-run-head"><b>{{ kindLabel(run.kind) }}</b><span>{{ run.status }}</span></div>
      <div v-for="step in run.steps || []" :key="step.id" class="workflow-step">
        <span class="workflow-dot" :class="step.status" />
        <div class="grow"><b>{{ step.name }}</b><div class="workflow-detail">{{ step.input_summary }} → {{ step.output_summary || step.error }}</div><el-button text type="primary" @click="openStep(run.id, step.id)">查看详情</el-button><el-button v-if="canRetry(run, step)" text type="primary" @click="retry(run.id, step.id)">重试此步</el-button></div>
      </div>
    </div>
    <el-drawer v-model="detailOpen" title="工作流步骤" size="420px">
      <template v-if="detail"><h3>{{ detail.step.name }}</h3><p>输入：{{ detail.step.input_summary }}</p><p>输出：{{ detail.step.output_summary || detail.step.error || '等待执行' }}</p><p class="muted">输入产物：{{ detail.step.input_refs?.map((ref: any) => ref.id).join('、') || '无' }}</p><p class="muted">输出产物：{{ detail.step.output_refs?.map((ref: any) => ref.id).join('、') || '无' }}</p><div v-for="record in detail.agent_runs" :key="record.run_id" class="workflow-agent"><b>{{ record.spec_id }}</b><div class="muted">模型 {{ record.model || '未记录' }} · {{ record.iterations || 0 }} 次调用 · {{ record.latency_ms || 0 }} ms</div></div></template>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/api'
import { showError } from '@/api/http'
import { useTask } from '@/composables/useTask'

const props = defineProps<{ jobId?: number; subject?: string; recent?: boolean }>()
const runs = ref<any[]>([])
const detail = ref<any>(null)
const detailOpen = ref(false)
const task = useTask()
const kindLabel = (kind: string) => ({ job_import: '职位入库', resume_generate: '定向简历', evidence_match: '依据匹配', knowledge_ingest: '资料入库', interview: '模拟面试' } as Record<string, string>)[kind] || kind
const canRetry = (run: any, step: any) => run.status === 'failed'
  && (step.status === 'failed' || (step.status === 'pending' && step.error))
  && run.steps.find((item: any) => !['done', 'skipped'].includes(item.status))?.id === step.id
async function load() {
  runs.value = []
  const subject = props.subject || (props.jobId ? `job_id:${props.jobId}` : '')
  if (!subject && !props.recent) return
  try {
    const summaries = (await api.workflows(subject)).slice(0, props.recent ? 5 : 20)
    runs.value = await Promise.all(summaries.map((run: any) => api.workflow(run.id).then((detail: any) => ({ ...detail.run, steps: detail.steps }))))
  } catch { runs.value = [] }
}
watch(() => [props.jobId, props.subject, props.recent], load, { immediate: true })
async function retry(runId: string, stepId: string) { try { const response = await api.retryWorkflowStep(runId, stepId); if (response.task_id) await task.waitFor(response.task_id); await load() } catch (e) { showError(e); await load() } }
async function openStep(runId: string, stepId: string) { try { detail.value = await api.workflowStep(runId, stepId); detailOpen.value = true } catch (e) { showError(e) } }
</script>

<style scoped>
.workflow-panel { margin-top: 24px; border-top: 1px solid #dce8f7; padding-top: 20px; }
.workflow-title { font-size: 16px; font-weight: 650; margin-bottom: 14px; }
.workflow-empty, .workflow-detail { color: #7890b0; font-size: 12px; }
.workflow-run { padding: 14px 18px; margin-bottom: 12px; background: rgba(235,244,255,.65); border-radius: 16px; }
.workflow-run-head { display: flex; justify-content: space-between; color: #466789; font-size: 13px; }
.workflow-step { display: flex; gap: 12px; margin-top: 14px; }
.workflow-dot { width: 10px; height: 10px; flex: none; margin-top: 5px; border-radius: 50%; background: #9cb5d4; }
.workflow-dot.done { background: #4b8ae9; }.workflow-dot.failed { background: #d95b65; }
.workflow-agent { margin-top: 14px; padding: 12px; border-radius: 12px; background: #edf5ff; }
</style>
