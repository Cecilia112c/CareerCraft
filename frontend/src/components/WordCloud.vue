<template>
  <svg class="cloud" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="xMidYMid meet" role="img" aria-label="技能需求词云">
    <g v-for="w in placed" :key="w.term" class="word" :class="{ active: w.term === selected, dim: selected && w.term !== selected }"
       @click="emit('select', w.term === selected ? '' : w.term)">
      <title>{{ w.term }}：{{ w.count }} 份 JD 提到{{ w.have ? '（你已具备）' : '（你的资料中没有）' }}</title>
      <rect v-if="w.term === selected" :x="w.x - 4" :y="w.y - w.h + 2" :width="w.w + 8" :height="w.h + 4" rx="6" class="hl" />
      <text :x="w.x" :y="w.y" :font-size="w.size" :fill="w.color" :font-weight="w.size > 26 ? 700 : 500">{{ w.term }}</text>
    </g>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Term { term: string; count: number; have: boolean; category?: string }
const props = withDefaults(defineProps<{ terms: Term[]; selected?: string; maxFont?: number; minFont?: number }>(),
  { selected: '', maxFont: 44, minFont: 13 })
const emit = defineEmits<{ (e: 'select', term: string): void }>()

const W = 680
const H = 340
const HAVE = ['#245bdb', '#3370ff', '#5b8cff', '#7fa6ff']
const MISS = ['#d46b08', '#ff8800', '#ffa940', '#ffc069']
const SOFT = '#a8adb6'

function textWidth(text: string, size: number) {
  let w = 0
  for (const ch of text) w += /[㐀-鿿＀-￯]/.test(ch) ? size * 1.02 : size * 0.6
  return w
}
function overlaps(a: any, b: any) {
  return !(a.x + a.w + 6 < b.x || b.x + b.w + 6 < a.x || a.y + 3 < b.y - b.h || b.y + 3 < a.y - a.h)
}

const placed = computed(() => {
  const terms = [...props.terms].sort((a, b) => b.count - a.count).slice(0, 45)
  if (!terms.length) return []
  const max = terms[0].count
  const min = terms[terms.length - 1].count
  const out: any[] = []
  terms.forEach((t, i) => {
    const k = max === min ? 0.6 : Math.sqrt((t.count - min) / (max - min))
    const size = Math.round(props.minFont + (props.maxFont - props.minFont) * k)
    const w = textWidth(t.term, size)
    const h = size * 0.95
    const shade = Math.min(3, Math.floor((1 - k) * 4))
    const color = t.category === 'soft' ? SOFT : (t.have ? HAVE : MISS)[shade]
    // 阿基米德螺线：从中心向外找第一个不重叠的位置（确定性布局，刷新不跳动）
    for (let step = 0; step < 2400; step++) {
      const angle = step * 0.17 + i * 0.6
      const r = 2.2 * step * 0.17
      const x = W / 2 + r * Math.cos(angle) * 1.7 - w / 2
      const y = H / 2 + r * Math.sin(angle) + h / 2
      if (x < 6 || x + w > W - 6 || y - h < 4 || y > H - 4) continue
      const box = { x, y, w, h }
      if (out.every((p) => !overlaps(box, p))) {
        out.push({ ...box, term: t.term, count: t.count, have: t.have, size, color })
        break
      }
    }
  })
  return out
})
</script>

<style scoped>
.cloud { width: 100%; height: 100%; user-select: none; }
.word { cursor: pointer; transition: opacity .2s; }
.word text { font-family: var(--el-font-family); transition: opacity .2s; }
.word:hover text { opacity: .75; }
.word.dim { opacity: .35; }
.hl { fill: var(--cc-primary-weak); stroke: #bacefd; }
</style>
