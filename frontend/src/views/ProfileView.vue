<template>
  <div class="page profile-page">
    <div class="page-title">
      <div>
        <h1>我的资料</h1>
        <div class="sub">资料是生成简历的唯一事实来源，AI 不会编造这里没有的内容</div>
      </div>
      <div class="row">
        <el-button @click="importOpen = true">导入简历 PDF</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存资料</el-button>
      </div>
    </div>

    <div class="layout">
      <aside class="anchors card">
        <a v-for="s in sections" :key="s.id" :href="`#${s.id}`">{{ s.label }}</a>
        <el-divider />
        <div class="muted">完整度</div>
        <el-progress :percentage="complete" />
        <div v-if="savedAt" class="muted mt8">上次保存：{{ savedAt.slice(0, 16).replace('T', ' ') }}</div>
      </aside>

      <div class="grow" v-if="p">
        <section id="basic" class="card">
          <div class="card-title">基本信息</div>
          <el-form label-position="top">
            <div class="grid3">
              <el-form-item label="姓名"><el-input v-model="p.basic.name" /></el-form-item>
              <el-form-item label="手机"><el-input v-model="p.basic.phone" /></el-form-item>
              <el-form-item label="邮箱"><el-input v-model="p.basic.email" /></el-form-item>
              <el-form-item label="所在城市"><el-input v-model="p.basic.city" /></el-form-item>
              <el-form-item label="求职方向" class="span2"><el-input v-model="p.basic.headline" placeholder="例如：后端开发实习生" /></el-form-item>
            </div>
            <el-form-item label="个人简介">
              <el-input v-model="p.basic.summary" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
            </el-form-item>
            <el-form-item label="链接（GitHub / 博客 / 作品集）">
              <div class="w100">
                <div v-for="(l, i) in p.basic.links" :key="i" class="row mb8">
                  <el-input v-model="l.label" placeholder="名称" style="width: 140px" />
                  <el-input v-model="l.url" placeholder="https://" class="grow" />
                  <el-button text type="danger" @click="p.basic.links.splice(i, 1)">删除</el-button>
                </div>
                <el-button text type="primary" size="small" @click="p.basic.links.push({ label: '', url: '' })">+ 添加链接</el-button>
              </div>
            </el-form-item>
          </el-form>
        </section>

        <section id="education" class="card">
          <div class="card-title">教育经历 <el-button text type="primary" @click="p.education.push(emptyEducation())">+ 添加</el-button></div>
          <div v-for="(e, i) in p.education" :key="e.id" class="block">
            <div class="grid4">
              <el-input v-model="e.school" placeholder="学校" />
              <el-input v-model="e.major" placeholder="专业" />
              <el-input v-model="e.degree" placeholder="学历（本科/硕士）" />
              <el-input v-model="e.dates" placeholder="2021.09-2025.06" />
            </div>
            <div class="label">补充（GPA、排名、主修课程…）</div>
            <TextItemList v-model="e.bullets" />
            <el-button text type="danger" size="small" @click="p.education.splice(i, 1)">删除这段教育经历</el-button>
          </div>
        </section>

        <section id="experience" class="card">
          <div class="card-title">实习 / 工作经历 <el-button text type="primary" @click="p.experience.push(emptyExperience())">+ 添加</el-button></div>
          <div v-for="(x, i) in p.experience" :key="x.id" class="block">
            <div class="grid4">
              <el-input v-model="x.company" placeholder="公司" />
              <el-input v-model="x.team" placeholder="部门/团队" />
              <el-input v-model="x.title" placeholder="职位" />
              <el-input v-model="x.dates" placeholder="2024.06-2024.09" />
            </div>
            <div v-for="(proj, k) in x.projects" :key="proj.id" class="mt8">
              <ProjectEditor :project="proj" />
              <el-button text type="danger" size="small" @click="x.projects.splice(k, 1)">删除该项目</el-button>
            </div>
            <div class="row mt8">
              <el-button size="small" @click="x.projects.push(emptyProject())">+ 在这段经历下添加项目</el-button>
              <el-button text type="danger" size="small" @click="p.experience.splice(i, 1)">删除这段经历</el-button>
            </div>
          </div>
        </section>

        <section id="projects" class="card">
          <div class="card-title">项目经历 <el-button text type="primary" @click="p.projects.push(emptyProject())">+ 添加</el-button></div>
          <div v-for="(proj, i) in p.projects" :key="proj.id" class="block">
            <ProjectEditor :project="proj" />
            <el-button text type="danger" size="small" @click="p.projects.splice(i, 1)">删除该项目</el-button>
          </div>
        </section>

        <section id="skills" class="card">
          <div class="card-title">专业技能</div>
          <TagInput v-model="p.skills" placeholder="输入技能后回车，例如 Python、MySQL、Docker" />
        </section>

        <section id="awards" class="card">
          <div class="card-title">获奖与证书 <el-button text type="primary" @click="p.awards.push(emptyAward())">+ 添加</el-button></div>
          <div v-for="(a, i) in p.awards" :key="a.id" class="row mb8">
            <el-input v-model="a.name" placeholder="奖项/证书名称" class="grow" />
            <el-input v-model="a.date" placeholder="2024.05" style="width: 140px" />
            <el-button text type="danger" @click="p.awards.splice(i, 1)">删除</el-button>
          </div>
        </section>
      </div>
    </div>

    <!-- 导入 PDF -->
    <el-dialog v-model="importOpen" title="导入简历 PDF" width="760px" :close-on-click-modal="false">
      <div class="row">
        <el-upload :auto-upload="false" :show-file-list="false" accept=".pdf" :on-change="onPick">
          <el-button :loading="uploading">选择 PDF 文件</el-button>
        </el-upload>
        <span class="muted grow">{{ doc ? `已上传：${doc.filename}` : '支持文字版 PDF（扫描件请手动填写）' }}</span>
      </div>
      <div v-if="doc" class="mt16">
        <div class="mb8"><b>选择识别方式</b></div>
        <el-radio-group v-model="mode">
          <el-radio-button value="rule">按标题/段落识别（秒出，不调用大模型）</el-radio-button>
          <el-radio-button value="llm">AI 智能填充（更准，需 10~30 秒）</el-radio-button>
        </el-radio-group>
        <div class="mt16"><el-button type="primary" :loading="task.running.value" @click="parse">开始识别</el-button></div>
      </div>
      <TaskProgress class="mt16" :running="task.running.value" :progress="task.progress.value" :stage="task.stage.value" />

      <div v-if="result" class="mt16">
        <el-alert v-for="w in result.warnings" :key="w" :title="w" type="warning" :closable="false" class="mb8" />
        <div class="mb8"><b>识别到的分区：</b>
          <el-tag v-for="s in result.sections" :key="s.title + s.type" class="tag" :type="s.type === 'other' ? 'info' : 'primary'">
            {{ s.title }}（{{ typeLabel[s.type] || s.type }}）</el-tag>
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="姓名">{{ r.basic.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系方式">{{ [r.basic.phone, r.basic.email].filter(Boolean).join(' / ') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="教育经历">{{ r.education.map((e: any) => e.school).join('、') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="实习/工作">{{ r.experience.map((e: any) => e.company).join('、') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="项目">{{ r.projects.map((e: any) => e.name).join('、') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="技能">{{ r.skills.slice(0, 12).join('、') || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="result.unparsed.length" class="muted mt8">未归类内容 {{ result.unparsed.length }} 段（可手动补充）</div>
        <div class="row mt16">
          <el-checkbox v-model="overwrite">覆盖已有的同类条目（不勾选则追加，基本信息只补空白字段）</el-checkbox>
        </div>
      </div>
      <template #footer>
        <el-button @click="importOpen = false">取消</el-button>
        <el-button type="primary" :disabled="!result" @click="applyResult">填入资料</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { showError } from '@/api/http'
import { useTask } from '@/composables/useTask'
import TextItemList from '@/components/TextItemList.vue'
import TagInput from '@/components/TagInput.vue'
import ProjectEditor from '@/components/ProjectEditor.vue'
import TaskProgress from '@/components/TaskProgress.vue'
import { completeness, emptyAward, emptyEducation, emptyExperience, emptyProject, normalizeProfile } from '@/utils/doc'

const p = ref<any>(null)
const saving = ref(false)
const savedAt = ref('')
const sections = [
  { id: 'basic', label: '基本信息' }, { id: 'education', label: '教育经历' },
  { id: 'experience', label: '实习/工作经历' }, { id: 'projects', label: '项目经历' },
  { id: 'skills', label: '专业技能' }, { id: 'awards', label: '获奖与证书' },
]
const typeLabel: Record<string, string> = {
  basic: '基本信息', education: '教育', experience: '经历', projects: '项目', skills: '技能',
  awards: '奖项', summary: '简介', other: '未归类',
}
const complete = computed(() => completeness(p.value))

onMounted(async () => {
  try {
    const res = await api.getProfile()
    p.value = normalizeProfile(res.data)
    savedAt.value = res.updated_at || ''
  } catch (e) { showError(e) }
})

async function save() {
  saving.value = true
  try {
    const res = await api.saveProfile(p.value)
    p.value = normalizeProfile(res.data)
    savedAt.value = res.updated_at
    ElMessage.success('资料已保存')
  } catch (e) { showError(e) } finally { saving.value = false }
}

// ------------------------------------------------ import
const importOpen = ref(false)
const uploading = ref(false)
const doc = ref<any>(null)
const mode = ref<'rule' | 'llm'>('rule')
const result = ref<any>(null)
const overwrite = ref(false)
const task = useTask()
const r = computed(() => result.value?.profile || {})

async function onPick(file: any) {
  uploading.value = true
  result.value = null
  try {
    doc.value = await api.uploadDocument(file.raw)
    if (!doc.value.has_text) ElMessage.warning('这个 PDF 里没有可提取的文字，可能是扫描件')
  } catch (e) { showError(e) } finally { uploading.value = false }
}

async function parse() {
  result.value = null
  try {
    result.value = await task.run(() => api.parseDocument(doc.value.id, mode.value))
  } catch (e) { showError(e) }
}

function applyResult() {
  const src = r.value
  const dst = p.value
  for (const k of ['name', 'phone', 'email', 'city', 'headline', 'summary']) {
    if (src.basic[k] && (overwrite.value || !dst.basic[k])) dst.basic[k] = src.basic[k]
  }
  if (src.basic.links?.length && (overwrite.value || !dst.basic.links.length)) dst.basic.links = src.basic.links
  for (const k of ['education', 'experience', 'projects', 'awards']) {
    if (!src[k]?.length) continue
    dst[k] = overwrite.value ? src[k] : [...dst[k], ...src[k]]
  }
  if (src.skills?.length) dst.skills = overwrite.value ? src.skills : Array.from(new Set([...dst.skills, ...src.skills]))
  importOpen.value = false
  ElMessage.success('已填入表单，请检查后点击“保存资料”')
}
</script>

<style scoped>
.layout { display: flex; gap: 16px; align-items: flex-start; }
.anchors { position: sticky; top: 76px; width: 200px; flex: none; display: flex; flex-direction: column; gap: 4px; }
.anchors a { padding: 6px 8px; border-radius: 6px; color: var(--cc-text-2); }
.anchors a:hover { background: var(--cc-primary-weak); color: var(--cc-primary); }
section { scroll-margin-top: 76px; }
.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0 12px; }
.grid4 { display: grid; grid-template-columns: 2fr 1.5fr 1fr 1.2fr; gap: 8px; }
.span2 { grid-column: span 2; }
.block { padding: 14px 0; border-bottom: 1px solid var(--cc-border); }
.block:last-child { border-bottom: 0; }
.label { font-size: 13px; color: var(--cc-text-2); margin: 10px 0 6px; }
.w100 { width: 100%; }
.tag { margin: 0 6px 6px 0; }
</style>
