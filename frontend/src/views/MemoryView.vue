<template>
  <div class="page">
    <div class="page-title">
      <div>
        <h1>AI 记忆</h1>
        <div class="sub">AI 会记住你确认过的长期偏好（例如“英文技术名词保持原文”），以后每次修改简历都会遵守。你可以随时修改或删除。</div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-title">长期偏好 <span class="muted">{{ active.length }} 条生效</span></div>

        <div v-if="proposed.length" class="proposals">
          <div class="muted mb8">AI 从你的指令中总结出以下偏好，确认后才会生效：</div>
          <div v-for="m in proposed" :key="m.id" class="item proposed">
            <span class="pill orange">待确认</span>
            <span class="pill">{{ m.namespace_label }}</span>
            <span class="grow">{{ m.value }}</span>
            <el-button size="small" type="primary" @click="confirm(m)">确认</el-button>
            <el-button size="small" text type="danger" @click="forget(m)">忽略</el-button>
          </div>
        </div>

        <el-empty v-if="!active.length && !proposed.length" :image-size="64"
                  description="还没有记忆。在简历工坊里说“以后都……/记住……”，或者在下面手动添加" />
        <div v-for="m in active" :key="m.id" class="item">
          <span class="pill blue">{{ m.namespace_label }}</span>
          <template v-if="editingId === m.id">
            <el-input v-model="editText" class="grow" size="small" @keydown.enter="saveEdit(m)" />
            <el-button size="small" type="primary" @click="saveEdit(m)">保存</el-button>
            <el-button size="small" @click="editingId = 0">取消</el-button>
          </template>
          <template v-else>
            <span class="grow">{{ m.value }}</span>
            <span class="muted src">{{ sourceText(m.source) }}</span>
            <el-button size="small" text @click="startEdit(m)">编辑</el-button>
            <el-popconfirm title="删除这条记忆？" @confirm="forget(m)">
              <template #reference><el-button size="small" text type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </div>

        <div class="add row mt16">
          <el-select v-model="newNs" style="width: 120px">
            <el-option v-for="n in namespaces" :key="n.value" :value="n.value" :label="n.label" />
          </el-select>
          <el-input v-model="newValue" class="grow" placeholder="例如：项目描述不要以“负责”开头" @keydown.enter="add" />
          <el-button type="primary" :disabled="newValue.trim().length < 2" @click="add">添加</el-button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">最近的 AI 运行记录 <el-button text @click="loadRuns">刷新</el-button></div>
        <div class="muted mb8">每次调用都会记录用了哪些工具、几条记忆、耗时与 token，用于排查问题（不保存简历正文）。</div>
        <el-empty v-if="!runs.length" :image-size="48" description="暂无记录" />
        <div v-for="group in groupedRuns" :key="group.id"><div class="muted mt16">{{ group.label }}</div><div v-for="r in group.runs" :key="r.run_id" class="run">
          <div class="row">
            <span class="pill" :class="r.status === 'ok' ? 'green' : 'red'">{{ r.status === 'ok' ? '成功' : '失败' }}</span>
            <b class="grow ellipsis">{{ specText(r.spec_id) }}</b>
            <span class="muted">{{ (r.started_at || '').slice(5, 16).replace('T', ' ') }}</span>
          </div>
          <div class="muted mt8">
            模型调用 {{ r.iterations }} 次 · 工具 {{ (r.tool_calls || []).length }} 次 · 记忆 {{ r.memory?.preferences || 0 }} 条
            <span v-if="r.memory?.working_turns"> · 工作记忆 {{ r.memory.working_turns }} 轮</span>
            · 上下文约 {{ r.context_tokens || 0 }} tokens · {{ (r.duration_ms / 1000).toFixed(1) }}s
          </div>
          <div v-if="(r.tool_calls || []).length" class="pills mt8">
            <span v-for="(t, k) in r.tool_calls" :key="k" class="pill" :class="t.ok ? 'blue' : 'orange'">
              {{ t.tool }}{{ t.ok ? '' : `（${t.error_code}）` }}
            </span>
          </div>
          <div v-if="r.error" class="err mt8">{{ r.error }}</div>
        </div></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { showError } from '@/api/http'

const items = ref<any[]>([])
const namespaces = ref<any[]>([{ value: 'resume', label: '简历写作' }])
const runs = ref<any[]>([])
const groupedRuns = computed(() => { const groups = new Map<string, { id: string; label: string; runs: any[] }>(); for (const run of runs.value) { const id = run.workflow_id || 'standalone'; if (!groups.has(id)) groups.set(id, { id, label: run.workflow_id ? `${run.workflow_kind} · ${run.workflow_id.slice(0, 12)}` : '独立调用', runs: [] }); groups.get(id)!.runs.push(run) } return [...groups.values()] })
const newNs = ref('resume')
const newValue = ref('')
const editingId = ref(0)
const editText = ref('')
const active = computed(() => items.value.filter((m) => m.status === 'active'))
const proposed = computed(() => items.value.filter((m) => m.status === 'proposed'))

const SPEC_TEXT: Record<string, string> = {
  'resume.polish': '简历指令修改', 'resume.rewrite_project': '简历生成 · 项目 STAR 改写',
  'resume.headline': '简历生成 · 求职方向与简介', 'jd.normalize': '岗位解析',
  'parser.extract_section': '简历 PDF 抽取', 'interview.diagnose': '面试 · 简历诊断',
  'interview.questions': '面试 · 生成问题', 'interview.evaluate': '面试 · 评价作答', 'interview.report': '面试 · 总结报告',
}
const specText = (id: string) => SPEC_TEXT[id] || id
const sourceText = (s: string) => ({ explicit_instruction: '来自你的指令', user_manual: '手动添加',
  confirmed_proposal: '你已确认', tool: 'AI 记录' } as any)[s] || ''

async function load() {
  try {
    const res = await api.listMemory()
    items.value = res.items
    namespaces.value = res.namespaces
  } catch (e) { showError(e) }
}
async function loadRuns() { try { runs.value = await api.agentRuns(30) } catch (e) { showError(e) } }
onMounted(() => { load(); loadRuns() })

async function add() {
  if (newValue.value.trim().length < 2) return
  try { await api.addMemory(newNs.value, newValue.value.trim()); newValue.value = ''; ElMessage.success('已记住'); await load() }
  catch (e) { showError(e) }
}
async function confirm(m: any) { try { await api.confirmMemory(m.id); await load() } catch (e) { showError(e) } }
async function forget(m: any) { try { await api.forgetMemory(m.id); await load() } catch (e) { showError(e) } }
function startEdit(m: any) { editingId.value = m.id; editText.value = m.value }
async function saveEdit(m: any) {
  if (editText.value.trim().length < 2) return
  try { await api.editMemory(m.id, editText.value.trim()); editingId.value = 0; await load() } catch (e) { showError(e) }
}
</script>

<style scoped>
.grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: var(--sp-4); align-items: start; }
.grid .card + .card { margin-top: 0; }
.item { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-3) 0; border-bottom: 1px solid var(--cc-border-light); }
.proposals { padding: var(--sp-3) var(--sp-4); margin-bottom: var(--sp-3); background: #fff8ef; border-radius: var(--cc-radius-sm); }
.item.proposed { border-bottom-color: #ffe7c7; }
.src { font-size: var(--fs-xs); }
.run { padding: var(--sp-3) 0; border-bottom: 1px solid var(--cc-border-light); }
.err { color: var(--cc-danger); font-size: var(--fs-sm); word-break: break-all; }
@media (max-width: 960px) { .grid { grid-template-columns: 1fr; } }
</style>
