<template>
  <div class="layout">
    <header class="header">
      <div class="header-inner">
        <router-link to="/" class="logo">
          <span class="logo-mark">C</span>
          <span class="logo-text">CareerCraft</span>
          <span class="logo-sub">AI 求职助手</span>
        </router-link>
        <nav class="nav">
          <router-link v-for="n in nav" :key="n.to" :to="n.to" class="nav-item"
                       :class="{ active: isActive(n.to) }">{{ n.label }}</router-link>
        </nav>
        <div class="right">
          <button class="today" @click="$router.push({ path: '/jobs', query: { tab: 'today' } })">
            今日推荐
            <span v-if="todayCount" class="badge">{{ todayCount > 99 ? '99+' : todayCount }}</span>
          </button>
          <el-dropdown trigger="click" @command="onCommand">
            <span class="user">
              <span class="avatar">{{ initial }}</span>
              <span class="username">{{ auth.user?.username }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="pref">求职偏好</el-dropdown-item>
                <el-dropdown-item command="profile">我的资料</el-dropdown-item>
                <el-dropdown-item command="memory">AI 记忆</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </header>
    <main class="main"><router-view :key="$route.path" /></main>
    <footer v-if="!fullscreen" class="footer">CareerCraft · 研究生课程项目 · 岗位信息来自公开搜索结果与用户主动收藏</footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '@/stores/auth'
import { api } from '@/api'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const todayCount = ref(0)
const nav = [
  { to: '/', label: '首页' },
  { to: '/jobs', label: '职位' },
  { to: '/knowledge', label: '我的资料库' },
  { to: '/resumes', label: '简历工坊' },
  { to: '/interviews', label: '模拟面试' },
]
const initial = computed(() => (auth.user?.username || '?').slice(0, 1).toUpperCase())
const fullscreen = computed(() => /^\/resumes\/\d+/.test(route.path))   // 简历工坊占满一屏，不显示页脚
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))

async function refreshToday() {
  try { todayCount.value = (await api.listJobs('today')).length } catch { todayCount.value = 0 }
}
function onCommand(cmd: string) {
  if (cmd === 'logout') { auth.logout(); router.push('/login') }
  if (cmd === 'pref') router.push({ path: '/jobs', query: { pref: '1' } })
  if (cmd === 'profile') router.push('/profile')
  if (cmd === 'memory') router.push('/memory')
}
onMounted(refreshToday)
watch(() => route.fullPath, refreshToday)
</script>

<style scoped>
.layout { min-height: 100vh; display: flex; flex-direction: column; }
.main { flex: 1; }
.header {
  position: sticky; top: 0; z-index: 30; height: var(--cc-header-h);
  background: rgba(242, 248, 255, .66); backdrop-filter: saturate(180%) blur(24px);
  -webkit-backdrop-filter: saturate(180%) blur(24px);
  border-bottom: 1px solid rgba(255,255,255,.8);
  box-shadow: 0 6px 24px rgba(42,91,159,.06);
}
.header-inner {
  max-width: 1440px; height: 100%; margin: 0 auto; padding: 0 var(--sp-6);
  display: flex; align-items: center; gap: 42px;
}
.logo { display: flex; align-items: center; gap: 10px; color: var(--cc-text-1); }
.logo:hover { color: var(--cc-text-1); }
.logo-mark {
  width: 38px; height: 38px; border-radius: 13px; background: linear-gradient(145deg,#65a6ff,#2468e8); color: #fff;
  box-shadow: 0 8px 18px rgba(36,104,232,.28), inset 0 1px 0 rgba(255,255,255,.6);
  display: inline-flex; align-items: center; justify-content: center; font-size: 17px; font-weight: 700;
}
.logo-text { font-size: var(--fs-xl); font-weight: 700; letter-spacing: .3px; }
.logo-sub { padding-left: 10px; border-left: 1px solid var(--cc-border); color: var(--cc-text-3); font-size: var(--fs-sm); }

.nav { display: flex; height: 100%; gap: 6px; flex: 1; align-items: center; }
.nav-item {
  position: relative; display: flex; align-items: center; height: 40px; padding: 0 16px; border-radius: 12px;
  color: var(--cc-text-2); font-size: var(--fs-base); transition: color .2s, background .2s;
}
.nav-item:hover { color: var(--cc-primary); }
.nav-item.active { color: var(--cc-primary); font-weight: 600; background: rgba(218,235,255,.82); }
.nav-item.active::after {
  content: none;
}

.right { display: flex; align-items: center; gap: var(--sp-5); }
.today {
  position: relative; border: 0; background: none; cursor: pointer; padding: 6px 4px;
  color: var(--cc-text-2); font-size: var(--fs-base); font-family: inherit;
}
.today:hover { color: var(--cc-primary); }
.badge {
  position: absolute; top: -4px; right: -18px; min-width: 18px; height: 18px; padding: 0 5px;
  border-radius: 9px; background: var(--cc-danger); color: var(--cc-card); font-size: 11px; line-height: 18px; text-align: center;
}
.user { display: flex; align-items: center; gap: var(--sp-2); cursor: pointer; outline: none; }
.avatar {
  width: 32px; height: 32px; border-radius: 50%; background: var(--cc-primary-weak); color: var(--cc-primary);
  display: inline-flex; align-items: center; justify-content: center; font-weight: 600;
}
.username { color: var(--cc-text-2); max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.footer {
  padding: var(--sp-6); text-align: center; color: var(--cc-text-4); font-size: var(--fs-xs);
  border-top: 1px solid rgba(255,255,255,.7); background: rgba(255,255,255,.35);
}
@media (max-width: 1080px) { .logo-sub { display: none; } .nav { gap: var(--sp-5); } }
@media (max-width: 760px) {
  .header { height: auto; min-height: var(--cc-header-h); }
  .header-inner { flex-wrap: wrap; gap: 10px; padding: 12px 16px; }
  .nav { order: 3; flex: 0 0 100%; overflow-x: auto; gap: 4px; }
  .nav-item { white-space: nowrap; padding: 0 10px; }
  .right { margin-left: auto; gap: 10px; }
  .username, .today { display: none; }
}
</style>
