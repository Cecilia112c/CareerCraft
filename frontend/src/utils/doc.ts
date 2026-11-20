// Helpers for ProfileData / ResumeDoc (same structure as agents/core/schemas.py).

const ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789'
export function newId(prefix = 'b'): string {
  let s = prefix
  for (let i = 0; i < 6; i++) s += ALPHABET[Math.floor(Math.random() * ALPHABET.length)]
  return s
}

export const emptyProject = () => ({
  id: newId('p'), name: '', subtitle: '', role: '', url: '', dates: '',
  background: [], responsibilities: [], impact: [], keywords: [],
})
export const emptyExperience = () => ({ id: newId('x'), company: '', team: '', title: '', dates: '', projects: [emptyProject()] })
export const emptyEducation = () => ({ id: newId('e'), school: '', major: '', degree: '', dates: '', bullets: [] })
export const emptyAward = () => ({ id: newId('a'), name: '', date: '' })
export const emptyProfile = () => ({
  basic: { name: '', phone: '', email: '', city: '', headline: '', summary: '', links: [] },
  education: [], experience: [], projects: [], skills: [], awards: [],
})

export function normalizeProfile(data: any): any {
  const p = Object.assign(emptyProfile(), data || {})
  p.basic = Object.assign(emptyProfile().basic, p.basic || {})
  return p
}

function* projects(doc: any): Generator<any> {
  for (const x of doc.experience || []) for (const p of x.projects || []) yield p
  for (const p of doc.projects || []) yield p
}

export function* textItems(doc: any): Generator<any> {
  for (const e of doc.education || []) yield* e.bullets || []
  for (const p of projects(doc)) {
    yield* p.background || []
    yield* p.responsibilities || []
    yield* p.impact || []
  }
}

const WHITELIST: Record<string, string[]> = {
  basic: ['name', 'phone', 'email', 'city', 'headline', 'summary'],
  education: ['school', 'major', 'degree', 'dates'],
  experience: ['company', 'team', 'title', 'dates'],
  project: ['name', 'subtitle', 'role', 'dates', 'keywords'],
  award: ['name', 'date'],
}

function* entities(doc: any): Generator<[string, any]> {
  for (const e of doc.education || []) yield ['education', e]
  for (const x of doc.experience || []) yield ['experience', x]
  for (const p of projects(doc)) yield ['project', p]
  for (const a of doc.awards || []) yield ['award', a]
}

const splitList = (t: string) => t.split(/[,，、;；|/\n]+/).map((s) => s.trim()).filter(Boolean)

/** Current text of a sentence / field key (same keys as setText). */
export function getText(doc: any, key: string): string | null {
  if (key === 'skills') return (doc.skills || []).join('、')
  for (const it of textItems(doc)) if (it.id === key) return it.text
  const dot = key.lastIndexOf('.')
  if (dot < 0) return null
  const owner = key.slice(0, dot), field = key.slice(dot + 1)
  if (owner === 'basic') return doc.basic?.[field] ?? null
  for (const [, ent] of entities(doc)) {
    if (ent.id === owner) return Array.isArray(ent[field]) ? ent[field].join(' / ') : (ent[field] ?? null)
  }
  return null
}

/** Same semantics as set_text() in Python. */
export function setText(doc: any, key: string, text: string): boolean {
  text = (text || '').trim()
  if (key === 'skills') { doc.skills = splitList(text); return true }
  for (const it of textItems(doc)) if (it.id === key) { it.text = text; return true }
  const dot = key.lastIndexOf('.')
  if (dot < 0) return false
  const owner = key.slice(0, dot), field = key.slice(dot + 1)
  if (owner === 'basic') {
    if (!WHITELIST.basic.includes(field)) return false
    doc.basic[field] = text
    return true
  }
  for (const [kind, ent] of entities(doc)) {
    if (ent.id === owner) {
      if (!WHITELIST[kind].includes(field)) return false
      ent[field] = field === 'keywords' ? splitList(text) : text
      return true
    }
  }
  return false
}

/** Outline entries for the studio: experiences, projects, education. */
export function outline(doc: any): { id: string; label: string; level: number }[] {
  const out: { id: string; label: string; level: number }[] = []
  for (const e of doc.education || []) out.push({ id: e.id, label: `教育｜${e.school || '未命名'}`, level: 0 })
  for (const x of doc.experience || []) {
    out.push({ id: x.id, label: `经历｜${x.company || '未命名'}`, level: 0 })
    for (const p of x.projects || []) out.push({ id: p.id, label: p.name || '（项目）', level: 1 })
  }
  for (const p of doc.projects || []) out.push({ id: p.id, label: `项目｜${p.name || '未命名'}`, level: 0 })
  return out
}

export function allText(doc: any): string {
  const parts: string[] = [doc.basic?.headline, doc.basic?.summary, ...(doc.skills || [])]
  for (const it of textItems(doc)) parts.push(it.text)
  for (const p of projects(doc)) parts.push(p.name, ...(p.keywords || []))
  return parts.filter(Boolean).join('\n')
}

export function completeness(p: any): number {
  if (!p) return 0
  const checks = [
    !!p.basic?.name, !!(p.basic?.phone || p.basic?.email), !!p.basic?.summary,
    (p.education || []).length > 0, (p.experience || []).length + (p.projects || []).length > 0,
    (p.skills || []).length >= 3,
    [...projects(p)].some((x) => (x.responsibilities || []).length > 0),
    [...projects(p)].some((x) => (x.impact || []).length > 0),
  ]
  return Math.round((checks.filter(Boolean).length / checks.length) * 100)
}

export function scoreClass(s: number) {
  return s >= 70 ? 'high' : s >= 45 ? 'mid' : 'low'
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
