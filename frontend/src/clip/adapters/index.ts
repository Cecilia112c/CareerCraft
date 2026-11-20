import { parseBoss, type ClipResult } from './boss'

export function parseClip(html: string, rawURL: string): ClipResult {
  const url = new URL(rawURL)
  const doc = new DOMParser().parseFromString(html, 'text/html')
  if (url.hostname === 'zhipin.com' || url.hostname.endsWith('.zhipin.com')) return parseBoss(doc, url)
  return { detail: null, cards: [], pageType: 'unknown' }
}
