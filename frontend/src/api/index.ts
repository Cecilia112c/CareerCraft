import http from './http'

const d = (p: Promise<any>) => p.then((r) => r.data)

export const api = {
  // auth
  register: (username: string, password: string) => d(http.post('/auth/register', { username, password })),
  login: (username: string, password: string) => d(http.post('/auth/login', { username, password })),
  me: () => d(http.get('/auth/me')),

  // profile & documents
  getProfile: () => d(http.get('/profile')),
  saveProfile: (data: any) => d(http.put('/profile', { data })),
  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return d(http.post('/documents', form))
  },
  listDocuments: () => d(http.get('/documents')),
  deleteDocument: (id: number) => d(http.delete(`/documents/${id}`)),
  parseDocument: (id: number, mode: 'rule' | 'llm') => d(http.post(`/documents/${id}/parse`, { mode })),

  // jobs & push
  bossLink: () => d(http.get('/boss-link')),
  importJob: (text: string, url: string) => d(http.post('/jobs/import', { text, url })),
  importJobs: (items: { text: string; url: string }[]) => d(http.post('/jobs/import', { items })),
  saveClip: (body: any) => d(http.post('/clip/save', body)),
  listJobs: (scope: 'all' | 'today' | 'target' = 'all') => d(http.get('/jobs', { params: { scope } })),
  getJob: (id: number) => d(http.get(`/jobs/${id}`)),
  jobsByStatus: (status: string) => d(http.get('/jobs', { params: { status } })),
  updateJob: (id: number, body: { status?: string; notes?: string }) => d(http.patch(`/jobs/${id}`, body)),
  setTarget: (id: number, value: boolean) => d(http.post(`/jobs/${id}/target`, { value })),
  deleteJob: (id: number) => d(http.delete(`/jobs/${id}`)),
  getPush: () => d(http.get('/push-setting')),
  savePush: (body: any) => d(http.put('/push-setting', body)),
  runPush: () => d(http.post('/push-setting/run-now')),
  today: () => d(http.get('/today')),
  jobBrief: (id: number) => d(http.get(`/jobs/${id}/brief`)),
  matchJobEvidence: (id: number) => d(http.post(`/jobs/${id}/evidence`)),
  jobEvidence: (id: number) => d(http.get(`/jobs/${id}/evidence`)),
  workflows: (subject = '') => d(http.get('/workflows', { params: { subject } })),
  workflow: (id: string) => d(http.get(`/workflows/${id}`)),
  workflowStep: (runId: string, stepId: string) => d(http.get(`/workflows/${runId}/steps/${stepId}`)),
  retryWorkflowStep: (runId: string, stepId: string) => d(http.post(`/workflows/${runId}/steps/${stepId}/retry`)),
  resumeWorkflow: (runId: string) => d(http.post(`/workflows/${runId}/resume`)),
  listKnowledgeSources: () => d(http.get('/knowledge/sources')),
  addKnowledgeNote: (title: string, text: string) => d(http.post('/knowledge/sources/note', { title, text })),
  addGitHubSource: (url: string) => d(http.post('/knowledge/sources/github', { url })),
  addCertificate: (name: string, issuer: string, issued_at: string, file: File) => {
    const form = new FormData(); form.append('name', name); form.append('issuer', issuer); form.append('issued_at', issued_at); form.append('file', file)
    return d(http.post('/knowledge/sources/certificate', form))
  },
  uploadKnowledgeSource: (file: File) => { const form = new FormData(); form.append('file', file); return d(http.post('/knowledge/sources', form)) },
  knowledgeSource: (id: number) => d(http.get(`/knowledge/sources/${id}`)),
  updateKnowledgeSource: (id: number, body: { title?: string; linked_project_ids?: string[] }) => d(http.patch(`/knowledge/sources/${id}`, body)),
  extractKnowledgeClaims: (id: number) => d(http.post(`/knowledge/sources/${id}/extract`)),
  deleteKnowledgeSource: (id: number) => d(http.delete(`/knowledge/sources/${id}`)),
  listKnowledgeClaims: (status = 'proposed') => d(http.get('/knowledge/claims', { params: { status } })),
  confirmKnowledgeClaim: (id: number, statement?: string, project_id = '') => d(http.post(`/knowledge/claims/${id}/confirm`, { statement, project_id })),
  rejectKnowledgeClaim: (id: number) => d(http.post(`/knowledge/claims/${id}/reject`)),
  batchKnowledgeClaims: (ids: number[], action: 'confirm' | 'reject') => d(http.post('/knowledge/claims/batch', { ids, action })),
  listMaterialRequests: (status = 'open') => d(http.get('/material-requests', { params: { status } })),
  confirmMaterialRequest: (id: number) => d(http.post(`/material-requests/${id}/confirm`)),
  answerMaterialRequest: (id: number, text: string, project_id = '') => d(http.post(`/material-requests/${id}/answer`, { text, project_id })),
  attachMaterialRequest: (id: number, source_id: number) => d(http.post(`/material-requests/${id}/attach`, { source_id })),
  dismissMaterialRequest: (id: number) => d(http.post(`/material-requests/${id}/dismiss`)),
  listTodos: () => d(http.get('/todos')),
  createTodo: (body: { title: string; kind: string; due_at: string; job_id?: number }) => d(http.post('/todos', body)),
  updateTodo: (id: number, done: boolean) => d(http.patch(`/todos/${id}`, null, { params: { done } })),
  deleteTodo: (id: number) => d(http.delete(`/todos/${id}`)),

  // resumes
  createResume: (job_id: number | null, title = '') => d(http.post('/resumes', { job_id, title })),
  listResumes: () => d(http.get('/resumes')),
  getResume: (id: number) => d(http.get(`/resumes/${id}`)),
  deleteResume: (id: number) => d(http.delete(`/resumes/${id}`)),
  getVersion: (id: number, v: number) => d(http.get(`/resumes/${id}/versions/${v}`)),
  resumeCitations: (id: number, v: number) => d(http.get(`/resumes/${id}/versions/${v}/citations`)),
  saveVersion: (id: number, base_version: number, data: any, note = '手动编辑') =>
    d(http.post(`/resumes/${id}/versions`, { base_version, data, note })),
  polish: (id: number, body: { version: number; ids: string[]; mode: string; instruction: string;
                               scope_label?: string; data?: any }) =>
    d(http.post(`/resumes/${id}/polish`, body)),
  refreshResume: (id: number) => d(http.post(`/resumes/${id}/refresh`)),
  resumePatchFeedback: (id: number, patch_id: string, reason: string) => d(http.post(`/resumes/${id}/patch-feedback`, { patch_id, reason })),
  applyPatches: (id: number, base_version: number, patches: { id: string; new: string }[]) =>
    d(http.post(`/resumes/${id}/apply-patches`, { base_version, patches })),
  rollback: (id: number, version: number) => d(http.post(`/resumes/${id}/rollback`, { version })),
  render: (data: any, interactive = true): Promise<string> =>
    d(http.post('/render', { data, interactive }, { responseType: 'text' })),
  exportResume: (id: number, v: number, format: 'html' | 'pdf') =>
    http.get(`/resumes/${id}/versions/${v}/export`, { params: { format }, responseType: 'blob', timeout: 120000 }),
  syncDiff: (id: number, version: number) => d(http.get(`/resumes/${id}/sync-diff`, { params: { version } })),
  syncProposal: (id: number, version: number) => d(http.post(`/resumes/${id}/sync-proposal`, null, { params: { version } })),
  sync: (id: number, version: number, keys: string[], proposalId = '') => d(http.post(`/resumes/${id}/sync`, { version, keys, proposal_id: proposalId })),

  // interviews
  createInterview: (job_id: number, source: any, total = 10, mode: 'blind' | 'contrast' = 'blind') => d(http.post('/interviews', { job_id, source, total, mode })),
  requestInterviewFinding: (id: number, findingId: number) => d(http.post(`/interviews/${id}/findings/${findingId}/request`)),
  listInterviews: () => d(http.get('/interviews')),
  getInterview: (id: number) => d(http.get(`/interviews/${id}`)),
  deleteInterview: (id: number) => d(http.delete(`/interviews/${id}`)),
  answer: (id: number, text: string) => d(http.post(`/interviews/${id}/answer`, { text })),
  finishInterview: (id: number) => d(http.post(`/interviews/${id}/finish`)),
  nextInterviewRound: (id: number) => d(http.post(`/interviews/${id}/next-round`)),

  // agent memory（长期偏好 / 工作记忆 / 运行记录）
  listMemory: () => d(http.get('/memory')),
  addMemory: (namespace: string, value: string) => d(http.post('/memory', { namespace, value })),
  confirmMemory: (id: number) => d(http.post(`/memory/${id}/confirm`)),
  editMemory: (id: number, value: string) => d(http.patch(`/memory/${id}`, { value })),
  forgetMemory: (id: number) => d(http.delete(`/memory/${id}`)),
  workingMemory: (agent: string, session: string) => d(http.get('/memory/working', { params: { agent, session } })),
  clearWorkingMemory: (agent: string, session: string) => d(http.delete('/memory/working', { params: { agent, session } })),
  agentRuns: (limit = 30) => d(http.get('/memory/runs', { params: { limit } })),

  // insights（技能需求词云）
  libraryInsight: (status = '') => d(http.get('/insights/library', { params: status ? { status } : {} })),
  marketInsight: () => d(http.get('/insights/market')),
  refreshMarketInsight: (titles: string[], cities: string[]) => d(http.post('/insights/market', { titles, cities })),

  // tasks
  getTask: (id: string) => d(http.get(`/tasks/${id}`)),
}
