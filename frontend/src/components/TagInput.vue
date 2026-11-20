<template>
  <el-select :model-value="modelValue" multiple filterable allow-create default-first-option
             :reserve-keyword="false" :placeholder="placeholder" :multiple-limit="limit || 0"
             style="width: 100%" @update:model-value="(v: string[]) => emit('update:modelValue', v)">
    <el-option v-for="o in options || []" :key="o" :label="o" :value="o" />
  </el-select>
</template>

<script setup lang="ts">
defineProps<{ modelValue: string[]; placeholder?: string; options?: string[]; limit?: number }>()
const emit = defineEmits(['update:modelValue'])
</script>
