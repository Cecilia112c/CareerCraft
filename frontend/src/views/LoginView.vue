<template>
  <div class="login-page">
    <div class="hero">
      <div class="brand"><span class="logo-mark">C</span>CareerCraft</div>
      <h1>让每一份简历<br />都对准目标岗位</h1>
      <p>上传简历 · 按偏好每日推送职位 · STAR 法则润色 · AI 模拟面试</p>
    </div>
    <div class="panel">
      <el-tabs v-model="tab" stretch>
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="username" placeholder="3~32 位字母、数字或中文" size="large" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password placeholder="至少 6 位" size="large" />
        </el-form-item>
        <el-form-item v-if="tab === 'register'" label="确认密码">
          <el-input v-model="password2" type="password" show-password size="large" />
        </el-form-item>
        <el-button type="primary" size="large" native-type="submit" :loading="loading" style="width: 100%">
          {{ tab === 'login' ? '登录' : '注册并登录' }}
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuth } from '@/stores/auth'
import { showError } from '@/api/http'

const auth = useAuth()
const router = useRouter()
const route = useRoute()
const tab = ref('login')
const username = ref('')
const password = ref('')
const password2 = ref('')
const loading = ref(false)

async function submit() {
  if (username.value.trim().length < 3 || password.value.length < 6) {
    ElMessage.warning('用户名至少 3 位，密码至少 6 位')
    return
  }
  if (tab.value === 'register' && password.value !== password2.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    if (tab.value === 'login') await auth.login(username.value.trim(), password.value)
    else await auth.register(username.value.trim(), password.value)
    router.replace((route.query.redirect as string) || (tab.value === 'register' ? '/profile' : '/'))
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; gap: 96px;
  background: linear-gradient(135deg, #eef3ff 0%, #f7f9fc 55%, var(--cc-card) 100%); padding: 24px; }
.hero h1 { font-size: 40px; line-height: 1.3; margin: 24px 0 16px; }
.hero p { color: var(--cc-text-2); font-size: 16px; }
.brand { display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 700; }
.logo-mark { width: 34px; height: 34px; border-radius: 9px; background: var(--cc-primary); color: var(--cc-card);
  display: inline-flex; align-items: center; justify-content: center; }
.panel { width: 380px; padding: 28px 32px 32px; background: var(--cc-card); border-radius: 14px;
  box-shadow: 0 12px 40px rgba(31, 94, 255, .10); }
@media (max-width: 860px) { .hero { display: none; } }
</style>
