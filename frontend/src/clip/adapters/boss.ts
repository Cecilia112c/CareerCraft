import { BOSS } from './boss.selectors'
import { splitJD } from '../split'

export interface ClipCard { title: string; salary: string; company: string; area: string; tags: string[]; url: string }
export interface ClipDetail extends ClipCard { skills: string[]; description: string; responsibilities: string[]; requirements: string[] }
export interface ClipResult { detail: ClipDetail | null; cards: ClipCard[]; pageType: 'search' | 'detail' | 'unknown' }

function first(root: ParentNode, selectors: string[]): Element | null {
  for (const selector of selectors) { const node = root.querySelector(selector); if (node) return node }
  return null
}
function val(root: ParentNode, selectors: string[]): string { return first(root, selectors)?.textContent?.trim() || '' }
function all(root: ParentNode, selectors: string[]): string[] {
  for (const selector of selectors) {
    const nodes = [...root.querySelectorAll(selector)]
    if (nodes.length) return nodes.map((x) => x.textContent?.trim() || '').filter(Boolean)
  }
  return []
}
function salary(value: string): string { return /[\uE000-\uF8FF]/.test(value) ? '' : value }
function jobURL(value: string | null, base: URL): string {
  if (!value) return ''
  try { const u = new URL(value, base); return u.hostname.endsWith('zhipin.com') && u.pathname.includes('/job_detail/') ? u.origin + u.pathname : '' }
  catch { return '' }
}
function lines(node: Element | null): string {
  if (!node) return ''
  const copy = node.cloneNode(true) as Element
  copy.querySelectorAll('script,style,noscript').forEach((x) => x.remove())
  copy.querySelectorAll('br').forEach((x) => x.replaceWith('\n'))
  return (copy.textContent || '').replace(/\r/g, '').replace(/[ \t]+/g, ' ').trim()
}

export function parseBoss(doc: Document, url: URL): ClipResult {
  // Saved HTML still contains BOSS's hidden anti-copy spans; the bookmarklet
  // removes them using computed styles before sending the live page.
  for (const style of doc.querySelectorAll('.job-detail-section style, .job-detail-box style')) {
    const rules = style.textContent || ''
    for (const match of rules.matchAll(/\.([A-Za-z][\w-]*)\s*\{([^}]+)\}/g)) {
      if (/(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px)?\b)/i.test(match[2])) {
        doc.querySelectorAll('.' + match[1]).forEach((node) => node.remove())
      }
    }
    style.remove()
  }
  const cards: ClipCard[] = []
  const seen = new Set<string>()
  for (const selector of BOSS.card) {
    const nodes = [...doc.querySelectorAll(selector)]
    if (!nodes.length) continue
    for (const node of nodes) {
      const anchor = first(node, BOSS.cardTitle) as HTMLAnchorElement | null
      const link = jobURL(anchor?.getAttribute('href') || node.querySelector('a[href*="/job_detail/"]')?.getAttribute('href') || null, url)
      if (!link || seen.has(link)) continue
      seen.add(link)
      cards.push({ title: val(node, BOSS.cardTitle), salary: salary(val(node, BOSS.cardSalary)),
        company: val(node, BOSS.cardCompany), area: val(node, BOSS.cardArea),
        tags: all(node, BOSS.cardTags), url: link })
    }
    break
  }
  const descNode = first(doc, BOSS.detailDesc)
  const description = lines(descNode)
  const detailLink = url.pathname.includes('/job_detail/') ? url.origin + url.pathname
    : jobURL(doc.querySelector('.job-card-wrap.active a[href*="/job_detail/"]')?.getAttribute('href') || null, url)
  let detail: ClipDetail | null = null
  if (detailLink && description.length >= 40) {
    const card = cards.find((x) => x.url === detailLink)
    const split = splitJD(description)
    detail = { title: val(doc, BOSS.detailTitle) || card?.title || '',
      salary: salary(val(doc, BOSS.detailSalary)) || card?.salary || '',
      company: card?.company || val(doc, ['.sider-company .company-info', '.job-detail-box .company-name']),
      area: card?.area || val(doc, ['.job-banner .text-city', '.job-address-desc']),
      tags: card?.tags || all(doc, ['.job-banner .text-experiece', '.job-banner .text-degree']),
      url: detailLink, skills: all(doc, BOSS.detailSkills),
      description, ...split }
  }
  return { detail, cards, pageType: cards.length ? 'search' : detail ? 'detail' : 'unknown' }
}
