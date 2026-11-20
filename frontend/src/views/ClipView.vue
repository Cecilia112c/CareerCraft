<template>
  <div class="clip">
    <div class="head"><span class="logo-mark">C</span><b>收藏岗位到 CareerCraft</b></div>

    <el-result v-if="!loggedIn" icon="warning" title="请先登录 CareerCraft"
               sub-title="登录后回到招聘网站，再点一次书签即可">
      <template #extra><el-button type="primary" @click="goLogin">去登录</el-button></template>
    </el-result>

    <template v-else-if="!received">
      <div class="card waiting">
        <p>正在等待招聘网站页面发送岗位内容…</p>
        <p class="muted">这个窗口需要在招聘网站的岗位详情页上点击“收藏到 CareerCraft”书签打开。超过几秒还没反应的话，回到原页面再点一次书签。</p>
      </div>
    </template>

    <template v-else-if="saved">
      <el-result icon="success" title="已保存到岗位列表" :sub-title="savedTitle">
        <template #extra>
          <el-button type="primary" @click="openInApp">在 CareerCraft 中查看</el-button>
          <el-button @click="closeWindow">关闭窗口</el-button>
        </template>
      </el-result>
    </template>

    <template v-else>
      <div class="card">
        <div class="row mb8">
          <el-tag type="success">{{ host }}</el-tag>
          <a :href="url" target="_blank" rel="noopener" class="grow ellipsis">{{ title || url }}</a>
        </div>
        <template v-if="parsed?.detail">
          <h3>当前职位</h3>
          <p>{{ parsed.detail.title }} · {{ parsed.detail.salary || '薪资待确认' }} · {{ parsed.detail.company }}</p>
          <p class="muted">{{ parsed.detail.area }} · {{ parsed.detail.skills.join(' / ') }}</p>
          <el-input v-model="parsed.detail.description" type="textarea" :rows="8" />
          <el-button type="primary" class="mt8" :loading="task.running.value" @click="saveDetail">保存到职位库</el-button>
        </template>
        <template v-if="parsed?.cards.length">
          <h3>本页职位卡片（{{ parsed.cards.length }}）</h3>
          <el-checkbox-group v-model="selectedCards">
            <div v-for="card in parsed.cards" :key="card.url"><el-checkbox :value="card.url">{{ card.title }} · {{ card.salary || '薪资待确认' }} · {{ card.company }}</el-checkbox></div>
          </el-checkbox-group>
          <el-button class="mt8" :loading="task.running.value" :disabled="!selectedCards.length" @click="saveCards">加入职位库</el-button>
        </template>
        <template v-if="!parsed?.detail && !parsed?.cards.length">
          <div class="muted mb8">未识别出结构化职位，请检查内容后手动保存。</div>
          <el-input v-model="text" type="textarea" :rows="16" />
          <div class="muted mt8">{{ text.length }} 字</div>
        </template>
        <TaskProgress class="mt8" :running="task.running.value" :progress="task.progress.value" :stage="task.stage.value" />
        <div class="row mt16">
          <span class="grow" />
          <el-button @click="closeWindow">取消</el-button>
          <el-button v-if="!parsed?.detail && !parsed?.cards.length" type="primary" :loading="task.running.value" :disabled="text.trim().length < 20" @click="save">保存岗位</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { showError } from '@/api/http'
import { useTask } from '@/composables/useTask'
import TaskProgress from '@/components/TaskProgress.vue'
import { isAllowedClipOrigin } from '@/utils/bookmarklet'
import { parseClip } from '@/clip/adapters'
import type { ClipResult } from '@/clip/adapters/boss'

const loggedIn = !!localStorage.getItem('cc_token')
const received = ref(false)
const saved = ref(false)
const savedTitle = ref('')
const savedId = ref<number | null>(null)
const url = ref('')
const title = ref('')
const host = ref('')
const text = ref('')
const parsed = ref<ClipResult | null>(null)
const selectedCards = ref<string[]>([])
const task = useTask()

function onMessage(e: MessageEvent) {
  const msg = e.data
  if (!msg || msg.source !== 'careercraft-clip') return
  if (!isAllowedClipOrigin(e.origin)) return            // 只接受招聘网站发来的内容
  try { (e.source as Window)?.postMessage('careercraft-clip-ok', e.origin) } catch { /* ignore */ }
  if (received.value && msg.url === url.value) return   // 书签会重复发送几次，忽略重复
  received.value = true
  saved.value = false
  url.value = String(msg.url || '').slice(0, 500)
  title.value = String(msg.title || '').slice(0, 200)
  host.value = new URL(e.origin).hostname
  text.value = String(msg.text || '').slice(0, 15000)
  parsed.value = null
  selectedCards.value = []
  if (msg.version === 2 && typeof msg.html === 'string') {
    try { parsed.value = parseClip(msg.html.slice(0, 1500000), url.value) } catch { /* manual fallback */ }
  }
}

async function saveDetail() {
  if (!parsed.value?.detail) return
  try {
    const res = await task.run(() => api.saveClip({ detail: parsed.value!.detail, cards: [] }))
    savedId.value = res.job_ids?.[0] ?? null
    savedTitle.value = parsed.value.detail.title
    saved.value = true
  } catch (e) { showError(e) }
}

async function saveCards() {
  if (!parsed.value) return
  try {
    const cards = parsed.value.cards.filter((c) => selectedCards.value.includes(c.url))
    const res = await task.run(() => api.saveClip({ cards }))
    ElMessage.success(`已收藏 ${res.new || 0} 个职位摘要，请打开职位详情补全 JD`)
    selectedCards.value = []
  } catch (e) { showError(e) }
}

async function save() {
  try {
    const res = await task.run(() => api.importJob(text.value, url.value))
    savedId.value = res.job_ids?.[0] ?? null
    if (savedId.value) savedTitle.value = (await api.getJob(savedId.value)).title
    saved.value = true
  } catch (e) { showError(e) }
}

function openInApp() {
  const target = `/jobs${savedId.value ? `?id=${savedId.value}` : ''}`
  if (window.opener && !window.opener.closed) {
    window.open(target, '_blank')
  } else {
    location.href = target
  }
}
function closeWindow() {
  window.close()
  setTimeout(() => ElMessage.info('可以直接关闭这个窗口了'), 300)
}
function goLogin() { location.href = '/login?redirect=/jobs' }

onMounted(() => window.addEventListener('message', onMessage))
onBeforeUnmount(() => window.removeEventListener('message', onMessage))
</script>

<style scoped>
.clip { max-width: 720px; margin: 0 auto; padding: 20px; }
.head { display: flex; align-items: center; gap: 10px; font-size: 18px; margin-bottom: 16px; }
.logo-mark { width: 28px; height: 28px; border-radius: 8px; background: var(--cc-primary); color: var(--cc-card);
  display: inline-flex; align-items: center; justify-content: center; }
.waiting { text-align: center; padding: 40px 24px; }
</style>
