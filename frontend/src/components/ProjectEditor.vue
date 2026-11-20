<template>
  <div class="project">
    <div class="grid">
      <el-input v-model="project.name" placeholder="项目名称" />
      <el-input v-model="project.role" placeholder="你的角色（如 核心开发 / 负责人）" />
      <el-input v-model="project.dates" placeholder="时间（如 2024.06-2024.09）" />
    </div>
    <div class="star">
      <div class="col">
        <div class="label">S/T 背景与目标 <span class="muted">为什么做、要解决什么问题</span></div>
        <TextItemList v-model="project.background" placeholder="例如：订单查询接口高峰期 P99 超过 2s，影响下单转化" />
      </div>
      <div class="col">
        <div class="label">A 我的职责与行动 <span class="muted">你具体做了什么、用了什么技术</span></div>
        <TextItemList v-model="project.responsibilities" placeholder="例如：设计 Redis 二级缓存，并实现热点 key 预热" />
      </div>
      <div class="col">
        <div class="label">R 成果 <span class="muted">尽量写数字，没有就写交付物</span></div>
        <TextItemList v-model="project.impact" placeholder="例如：P99 从 2.1s 降到 350ms" />
      </div>
    </div>
    <div class="label mt8">技术关键词</div>
    <TagInput v-model="project.keywords" placeholder="输入后回车，例如 Go、Redis、Kafka" />
  </div>
</template>

<script setup lang="ts">
import TextItemList from './TextItemList.vue'
import TagInput from './TagInput.vue'
defineProps<{ project: any }>()
</script>

<style scoped>
.project { padding: 14px; border: 1px dashed var(--cc-border); border-radius: 8px; background: #fafbfc; }
.grid { display: grid; grid-template-columns: 2fr 1.5fr 1fr; gap: 8px; }
.star { display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 12px; }
.label { font-size: 13px; font-weight: 600; color: var(--cc-text-2); margin-bottom: 6px; }
.label .muted { font-weight: 400; margin-left: 6px; }
</style>
