<template>
  <div v-if="running" class="task-progress">
    <div class="row">
      <span class="dot" />
      <span class="grow ellipsis">{{ stage || '处理中' }}</span>
      <span class="muted">{{ progress }}%</span>
    </div>
    <el-progress :percentage="progress" :show-text="false" :stroke-width="6" class="mt8" />
  </div>
</template>

<script setup lang="ts">
defineProps<{ running: boolean; progress: number; stage: string }>()
</script>

<style scoped>
.task-progress { padding: 12px 14px; border-radius: 8px; background: var(--cc-primary-weak); font-size: 13px; color: var(--cc-text-2); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cc-primary); animation: pulse 1s infinite alternate; }
@keyframes pulse { from { opacity: .3 } to { opacity: 1 } }
</style>
