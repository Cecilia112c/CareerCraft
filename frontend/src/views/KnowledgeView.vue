<template>
  <div class="page">
    <div class="page-title"><div><h1>我的资料库</h1><div class="sub">集中管理材料和已确认的经历依据</div></div></div>
    <el-tabs v-model="tab">
      <el-tab-pane label="结构化资料" name="profile"><ProfileView /></el-tab-pane>
      <el-tab-pane label="材料库" name="sources">
        <div class="card">
          <div class="card-title">上传材料</div>
          <input type="file" accept=".pdf,.docx,.md,.txt,.zip" multiple @change="upload" />
          <div class="muted mt8">支持 PDF、DOCX、MD、TXT 和项目 ZIP；单文件上限 20MB</div>
          <div class="row mt24"><el-input v-model="noteTitle" placeholder="备注标题" /><el-input v-model="noteText" placeholder="输入项目经历或其他补充资料" /><el-button type="primary" @click="addNote">添加备注</el-button></div>
          <div class="row mt16"><el-input v-model="githubUrl" placeholder="https://github.com/用户名/公开仓库" /><el-button :loading="githubLoading" @click="addGithub">添加 GitHub 仓库</el-button></div>
          <div class="certificate-form mt24"><b>添加证书</b><div class="row mt8"><el-input v-model="certificateName" placeholder="证书名称" /><el-input v-model="certificateIssuer" placeholder="颁发机构" /><el-input v-model="certificateDate" placeholder="获得日期" /></div><div class="row mt8"><input type="file" accept=".pdf,.png,.jpg,.jpeg" @change="selectCertificate" /><el-button :loading="certificateLoading" @click="addCertificate">保存证书</el-button></div></div>
        </div>
        <div class="card mt24"><div class="card-title">已入库材料</div><el-empty v-if="!sources.length" description="还没有材料" />
          <div v-for="source in sources" :key="source.id" class="source-row"><div class="grow"><b>{{ source.title }}</b><div class="muted">{{ source.kind }} · {{ Math.round(source.size / 1024) }} KB · {{ source.chunk_count }} 个片段 · {{ source.claim_count }} 条事实 · {{ source.status === 'pending' ? '等待解析' : source.status === 'processing' ? '正在解析与提取事实' : source.status === 'failed' ? '解析或提取失败' : '已入库' }} <span v-if="source.meta?.redacted_count">· 已屏蔽 {{ source.meta.redacted_count }} 处疑似密钥</span></div><div v-if="source.error" class="muted">{{ source.error }}</div></div><el-button text :loading="extractingId === source.id" @click="extract(source.id)">重新提取</el-button><el-button text @click="openSource(source.id)">查看</el-button><el-button text type="danger" @click="remove(source.id)">删除</el-button></div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="待确认事实" name="claims"><div class="card"><div v-if="claims.length" class="row"><span class="muted">选中 {{ selectedClaims.length }} 条</span><el-button :disabled="!selectedClaims.length" @click="batchConfirm">批量确认</el-button><el-button :disabled="!selectedClaims.length" @click="batchReject">批量拒绝</el-button></div><el-empty v-if="!claims.length" description="暂无待确认事实" /><div v-for="claim in claims" :key="claim.id" class="source-row"><el-checkbox v-model="claimSelection[claim.id]" /><div class="grow"><b>{{ claim.statement }}</b><div v-if="claim.source_quote" class="quote mt8">原文：{{ claim.source_quote }}</div></div><el-select v-model="claimProjects[claim.id]" clearable placeholder="关联项目（可选）" style="width: 180px"><el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" /></el-select><el-button type="primary" text @click="confirm(claim.id)">确认</el-button><el-button text @click="reject(claim.id)">拒绝</el-button></div></div></el-tab-pane>
      <el-tab-pane label="待补充" name="requests"><div class="card"><el-empty v-if="!requests.length" description="暂无待补充资料" /><div v-for="request in requests" :key="request.id" class="request-row"><b>{{ request.question }}</b><div class="muted mt8">{{ request.gap_type }} · {{ request.priority }} · {{ request.status === 'proposed' ? '待确认' : '可回答' }}</div><el-input v-if="request.status === 'open'" v-model="answers[request.id]" type="textarea" :rows="2" placeholder="根据真实经历回答" class="mt16" /><div class="row mt8"><el-button v-if="request.status === 'proposed'" type="primary" @click="confirmRequest(request.id)">确认建议</el-button><template v-else><el-select v-model="requestProjects[request.id]" clearable placeholder="关联项目（可选）" style="width: 180px"><el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" /></el-select><el-button type="primary" @click="answerRequest(request.id)">提交回答</el-button><el-select v-model="requestSources[request.id]" placeholder="关联已上传材料" style="width: 180px"><el-option v-for="source in sources" :key="source.id" :label="source.title" :value="source.id" /></el-select><el-button :disabled="!requestSources[request.id]" @click="attachRequest(request.id)">关联材料</el-button></template><el-button text @click="dismissRequest(request.id)">忽略</el-button></div></div></div></el-tab-pane>
    </el-tabs>
    <el-drawer v-model="drawer" title="材料内容" size="45%"><div v-if="detail"><h3>{{ detail.source.title }}</h3><div class="row mt16"><el-select v-model="linkedProjects" multiple placeholder="关联项目" style="width: 260px"><el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" /></el-select><el-button @click="saveSourceProjects">保存关联</el-button></div><div v-if="detail.source.meta?.repo_profile" class="repo-profile"><b>项目概览</b><div class="muted mt8">{{ detail.source.meta.repo_profile.file_count }} 个源码文件 · {{ Object.entries(detail.source.meta.repo_profile.languages).map(([name, count]) => `${name} ${count}`).join(' · ') }}</div><div class="pills mt8"><span v-for="name in detail.source.meta.repo_profile.frameworks" :key="name" class="pill blue">{{ name }}</span></div></div><h4 class="mt16">抽取的事实</h4><div v-for="claim in detail.claims" :key="claim.id" class="source-row"><div><b>{{ claim.statement }}</b><div class="muted">{{ claim.status === 'confirmed' ? '已确认' : claim.status === 'rejected' ? '已拒绝' : '待确认' }} · {{ claim.source_quote }}</div></div></div><h4 class="mt16">文本片段</h4><pre v-for="chunk in detail.chunks" :key="chunk.id" class="chunk">{{ chunk.text }}</pre></div></el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ProfileView from './ProfileView.vue'
import { api } from '@/api'
import { showError } from '@/api/http'
import { useTask } from '@/composables/useTask'

const tab = ref('profile')
const sources = ref<any[]>([])
const claims = ref<any[]>([])
const requests = ref<any[]>([])
const answers = ref<Record<number, string>>({})
const claimProjects = ref<Record<number, string>>({})
const claimSelection = ref<Record<number, boolean>>({})
const selectedClaims = computed(() => claims.value.filter(claim => claimSelection.value[claim.id]).map(claim => claim.id as number))
const requestSources = ref<Record<number, number>>({})
const requestProjects = ref<Record<number, string>>({})
const linkedProjects = ref<string[]>([])
const projects = ref<any[]>([])
const noteTitle = ref('')
const noteText = ref('')
const githubUrl = ref('')
const githubLoading = ref(false)
const certificateName = ref('')
const certificateIssuer = ref('')
const certificateDate = ref('')
const certificateFile = ref<File | null>(null)
const certificateLoading = ref(false)
const detail = ref<any>(null)
const drawer = ref(false)
const extractingId = ref<number | null>(null)
const task = useTask()
async function refresh() { const [a, b, c, d] = await Promise.all([api.listKnowledgeSources(), api.listKnowledgeClaims(), api.listMaterialRequests(), api.listMaterialRequests('proposed')]); sources.value = a; claims.value = b; requests.value = [...d, ...c] }
async function upload(event: Event) { const input = event.target as HTMLInputElement; for (const file of Array.from(input.files || [])) { try { const response = await api.uploadKnowledgeSource(file); await task.run(() => Promise.resolve(response)) } catch (e) { showError(e) } } input.value = ''; await refresh() }
async function addNote() { if (!noteTitle.value.trim() || !noteText.value.trim()) { ElMessage.warning('请填写标题和内容'); return } try { const response = await api.addKnowledgeNote(noteTitle.value, noteText.value); noteTitle.value = ''; noteText.value = ''; await task.run(() => Promise.resolve(response)); await refresh() } catch (e) { showError(e) } }
async function addGithub() { if (!githubUrl.value.trim()) return; githubLoading.value = true; try { const response = await api.addGitHubSource(githubUrl.value); githubUrl.value = ''; await task.run(() => Promise.resolve(response)); await refresh() } catch (e) { showError(e) } finally { githubLoading.value = false } }
function selectCertificate(event: Event) { certificateFile.value = (event.target as HTMLInputElement).files?.[0] || null }
async function addCertificate() { if (!certificateName.value.trim() || !certificateIssuer.value.trim() || !certificateFile.value) { ElMessage.warning('请填写证书名称、颁发机构并选择文件'); return } certificateLoading.value = true; try { await api.addCertificate(certificateName.value, certificateIssuer.value, certificateDate.value, certificateFile.value); certificateName.value = ''; certificateIssuer.value = ''; certificateDate.value = ''; certificateFile.value = null; await refresh() } catch (e) { showError(e) } finally { certificateLoading.value = false } }
async function openSource(id: number) { try { detail.value = await api.knowledgeSource(id); linkedProjects.value = detail.value.source.linked_project_ids || []; drawer.value = true } catch (e) { showError(e) } }
async function saveSourceProjects() { if (!detail.value) return; try { await api.updateKnowledgeSource(detail.value.source.id, { linked_project_ids: linkedProjects.value }); ElMessage.success('已保存关联项目'); await refresh() } catch (e) { showError(e) } }
async function extract(id: number) { extractingId.value = id; try { const result = await task.run(() => api.extractKnowledgeClaims(id)); ElMessage.success(`已提取 ${result.proposed} 条待确认事实`); tab.value = 'claims'; await refresh() } catch (e) { showError(e) } finally { extractingId.value = null } }
async function remove(id: number) { try { await api.deleteKnowledgeSource(id); await refresh() } catch (e) { showError(e) } }
async function confirm(id: number) { try { await api.confirmKnowledgeClaim(id, undefined, claimProjects.value[id] || ''); await refresh() } catch (e) { showError(e) } }
async function reject(id: number) { try { await api.rejectKnowledgeClaim(id); await refresh() } catch (e) { showError(e) } }
async function batchConfirm() { try { await api.batchKnowledgeClaims(selectedClaims.value, 'confirm'); claimSelection.value = {}; await refresh() } catch (e) { showError(e) } }
async function batchReject() { try { await api.batchKnowledgeClaims(selectedClaims.value, 'reject'); claimSelection.value = {}; await refresh() } catch (e) { showError(e) } }
async function answerRequest(id: number) { if (!answers.value[id]?.trim()) { ElMessage.warning('请先填写回答'); return } try { await api.answerMaterialRequest(id, answers.value[id], requestProjects.value[id] || ''); delete answers.value[id]; await refresh() } catch (e) { showError(e) } }
async function attachRequest(id: number) { try { await api.attachMaterialRequest(id, requestSources.value[id]); ElMessage.success('已关联材料，请确认提取出的事实后用于简历'); await refresh() } catch (e) { showError(e) } }
async function confirmRequest(id: number) { try { await api.confirmMaterialRequest(id); await refresh() } catch (e) { showError(e) } }
async function dismissRequest(id: number) { try { await api.dismissMaterialRequest(id); await refresh() } catch (e) { showError(e) } }
onMounted(() => { refresh().catch(showError); api.getProfile().then((response: any) => { const data = response.data || {}; projects.value = [...(data.projects || []), ...(data.experience || []).flatMap((exp: any) => exp.projects || [])] }).catch(showError) })
</script>

<style scoped>
.source-row { display: flex; align-items: center; gap: 12px; padding: 14px 0; border-top: 1px solid #dfeafb; }
.chunk { white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; border-radius: 12px; background: #edf5ff; font: inherit; }
.request-row { padding: 16px 0; border-top: 1px solid #dfeafb; }
.repo-profile { padding: 16px; border-radius: 16px; background: #edf5ff; margin: 16px 0; }
.certificate-form { padding: 16px; border: 1px solid #dfeafb; border-radius: 16px; }
@media (max-width: 700px) { .source-row { flex-wrap: wrap; } }
</style>
