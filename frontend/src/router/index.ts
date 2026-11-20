import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    // 一键收藏书签打开的小窗口（自己处理未登录的情况，否则跳转会丢失收到的岗位）
    { path: '/clip', component: () => import('@/views/ClipView.vue'), meta: { public: true } },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', component: () => import('@/views/HomeView.vue') },
        { path: 'profile', component: () => import('@/views/ProfileView.vue') },
        { path: 'knowledge', component: () => import('@/views/KnowledgeView.vue') },
        { path: 'jobs', component: () => import('@/views/JobsView.vue') },
        { path: 'resumes', component: () => import('@/views/ResumeListView.vue') },
        { path: 'resumes/:id', component: () => import('@/views/ResumeStudioView.vue') },
        { path: 'interviews', component: () => import('@/views/InterviewListView.vue') },
        { path: 'interviews/:id', component: () => import('@/views/InterviewRoomView.vue') },
        { path: 'memory', component: () => import('@/views/MemoryView.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  const loggedIn = !!localStorage.getItem('cc_token')
  if (!to.meta.public && !loggedIn) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.path === '/login' && loggedIn) return '/'
})

export default router
