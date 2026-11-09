import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue')
    },
    {
      path: '/',
      component: () => import('@/core/layout/CoreLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/dashboard' },
        {
          path: 'dashboard',
          name: 'Dashboard',
          meta: { title: '仪表盘' },
          component: () => import('@/views/Dashboard.vue')
        },
        {
          path: 'bots',
          name: 'BotConsole',
          meta: { title: '助手管理' },
          component: () => import('@/views/BotConsole.vue')
        },
        {
          path: 'activities',
          name: 'Activity',
          meta: { title: '活动' },
          component: () => import('@/views/Activity.vue')
        },
        {
          path: 'insights',
          name: 'Insights',
          meta: { title: '每日回顾' },
          component: () => import('@/views/Insights.vue')
        },
        {
          path: 'captures',
          name: 'Captures',
          meta: { title: '随手记' },
          component: () => import('@/views/Captures.vue')
        },
        {
          path: 'people',
          name: 'People',
          meta: { title: '人物' },
          component: () => import('@/views/People.vue')
        },
        {
          path: 'memory',
          name: 'Memory',
          meta: { title: '记忆' },
          component: () => import('@/views/Memory.vue')
        },
        {
          path: 'chat',
          name: 'Chat',
          meta: { title: '对话' },
          component: () => import('@/views/Chat.vue')
        },
        {
          path: 'notifications',
          name: 'Notifications',
          meta: { title: '通知' },
          component: () => import('@/views/Notifications.vue')
        },
        {
          path: 'files',
          name: 'Files',
          meta: { title: '文件' },
          component: () => import('@/views/Files.vue')
        },
        {
          path: 'settings',
          name: 'Settings',
          meta: { title: '设置' },
          component: () => import('@/views/Settings.vue')
        },
        {
          path: 'notes',
          name: 'Notes',
          meta: { title: '笔记' },
          component: () => import('@/views/notes/NotesPage.vue')
        },
        {
          path: 'device',
          name: 'Device',
          meta: { title: '设备' },
          component: () => import('@/views/Device.vue')
        },
        {
          path: 'projects',
          name: 'Projects',
          meta: { title: '项目' },
          component: () => import('@/views/Projects.vue')
        },
        {
          path: 'apps/:pluginName/:pathMatch(.*)*',
          name: 'PluginHost',
          meta: { title: '插件' },
          component: () => import('@/core/layout/PluginHost.vue')
        },
        {
          path: 'admin/users',
          name: 'AdminUsers',
          meta: { title: '用户管理', admin: true },
          component: () => import('@/views/AdminUsers.vue')
        },
        {
          path: 'admin/plugins',
          name: 'AdminPlugins',
          meta: { title: '插件市场', admin: true },
          component: () => import('@/views/AdminPlugins.vue')
        },
        {
          path: 'admin/runtime',
          name: 'Runtime',
          meta: { title: '运行看板', admin: true },
          component: () => import('@/views/Runtime.vue')
        },
        {
          path: 'mcp',
          name: 'McpServers',
          meta: { title: 'MCP 管理' },
          component: () => import('@/views/McpServers.vue')
        },
        {
          path: 'schedule',
          name: 'Schedule',
          meta: { title: '日程' },
          component: () => import('@/views/Schedule.vue')
        },
        {
          path: 'sources',
          name: 'Sources',
          meta: { title: '资讯' },
          component: () => import('@/views/Sources.vue')
        },
        {
          path: 'mail',
          name: 'Mail',
          meta: { title: '邮件' },
          component: () => import('@/views/Mail.vue')
        }
      ]
    }
  ]
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
