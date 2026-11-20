<template>
  <div class="items">
    <div v-for="(it, i) in modelValue" :key="it.id" class="item">
      <el-input v-model="it.text" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" :placeholder="placeholder" />
      <el-button text type="danger" @click="modelValue.splice(i, 1)">删除</el-button>
    </div>
    <el-button text type="primary" size="small" @click="modelValue.push({ id: newId('b'), text: '' })">+ 添加一条</el-button>
  </div>
</template>

<script setup lang="ts">
import { newId } from '@/utils/doc'
defineProps<{ modelValue: { id: string; text: string }[]; placeholder?: string }>()
</script>

<style scoped>
.item { display: flex; gap: 6px; align-items: flex-start; margin-bottom: 6px; }
</style>
