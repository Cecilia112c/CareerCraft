<template>
  <div class="page">
    <div class="page-title">
      <div><h1>简历工坊</h1><div class="sub">每份简历对应一个目标岗位，所有修改都会保存为新版本，可随时回滚</div></div>
      <el-button type="primary" @click="openNew">新建定向简历</el-button>
    </div>
    <el-empty v-if="!list.length" description="还没有简历" />
    <div class="grid">
      <div v-for="r in list" :key="r.id" class="card item" @click="$router.push(`/resumes/${r.id}`)">
        <div class="row">
          <div class="grow ellipsis name">{{ r.title }}</div>
          <el-tag v-if="r.current_version" size="small">v{{ r.current_version }}</el-tag>
          <el-tag v-else size="small" type="warning">生成中/失败</el-tag>
        </div>
        <div class="muted mt8 ellipsis">目标岗位：{{ r.job_title || '通用' }}</div>
        <div class="row mt8">
          <span class="muted grow">更新于 {{ r.updated_at.slice(0, 16).replace('T', ' ') }}</span>
          <el-popconfirm title="删除这份简历及其所有版本？" @confirm="remove(r.id)">
            <template #reference><el-button text type="danger" size="small" @click.stop>删除</el-button></template>
          </el-popconfirm>
        </div>
      </div>
    </div>

    <el-dialog v-model="newOpen" title="新建定向简历" width="520px">
      <el-form label-position="top">
        <el-form-item label="目标岗位">
          <el-select v-model="jobId" placeholder="选择岗位（可在“岗位”页检索或粘贴 JD）" clearable filterable style="width: 100%">
            <el-option v-for="j in jobs" :key="j.id" :label="`${j.title}｜${j.company}`" :value="j.id" />
          </el-select>
          <div class="muted">不选则生成通用简历</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newOpen = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create">开始生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api'
import { showError } from '@/api/http'

const router = useRouter()
const list = ref<any[]>([])
const jobs = ref<any[]>([])
const newOpen = ref(false)
const jobId = ref<number | null>(null)
const creating = ref(false)

async function load() { try { list.value = await api.listResumes() } catch (e) { showError(e) } }
onMounted(load)

async function openNew() {
  newOpen.value = true
  try {
    const all = await api.listJobs('all')
    jobs.value = [...all.filter((j: any) => j.is_target), ...all.filter((j: any) => !j.is_target)]
  } catch (e) { showError(e) }
}

async function create() {
  creating.value = true
  try {
    const res = await api.createResume(jobId.value || null)
    router.push({ path: `/resumes/${res.resume_id}`, query: { task: res.task_id } })
  } catch (e) { showError(e) } finally { creating.value = false }
}

async function remove(id: number) {
  try { await api.deleteResume(id); await load() } catch (e) { showError(e) }
}
</script>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.grid .card + .card { margin-top: 0; }
.item { cursor: pointer; transition: all .15s; }
.item:hover { border-color: var(--cc-primary); box-shadow: 0 4px 14px rgba(31, 94, 255, .08); }
.name { font-weight: 600; font-size: 16px; }
</style>
