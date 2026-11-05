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
          component: () => import('@/views/Dashboard.vue')
        },
        {
          path: 'bots',
          name: '助手管理',
          component: () => import('@/views/BotConsole.vue')
        },
        {
          path: 'activities',
          name: '活动',
          component: () => import('@/views/Activity.vue')
        },
        {
          path: 'insights',
          name: '每日回顾',
          component: () => import('@/views/Insights.vue')
        },
        {
          path: 'cos',
          name: '幕僚长',
          component: () => import('@/views/ChiefOfStaff.vue')
        },
        {
          path: 'about',
          name: '关于我',
          component: () => import('@/views/About.vue')
        },
        {
          path: 'chat',
          name: '对话',
          component: () => import('@/views/Chat.vue')
        },
        {
          path: 'notifications',
          name: '通知',
          component: () => import('@/views/Notifications.vue')
        },
        {
          path: 'files',
          name: 'Files',
          component: () => import('@/views/Files.vue')
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/Settings.vue')
        },
        {
          path: 'notes',
          name: 'Notes',
          component: () => import('@/views/notes/NotesPage.vue')
        },
        {
          path: 'device',
          name: 'Device',
          component: () => import('@/views/Device.vue')
        },
        {
          path: 'projects',
          name: 'Projects',
          component: () => import('@/views/Projects.vue')
        },
        {
          path: 'apps/:pluginName/:pathMatch(.*)*',
          name: 'PluginHost',
          component: () => import('@/core/layout/PluginHost.vue')
        },
        {
          path: 'admin/users',
          name: 'AdminUsers',
          component: () => import('@/views/AdminUsers.vue')
        },
        {
          path: 'admin/plugins',
          name: 'AdminPlugins',
          component: () => import('@/views/AdminPlugins.vue')
        },
        {
          path: 'mcp',
          name: 'MCP 管理',
          component: () => import('@/views/McpServers.vue')
        },
        {
          path: 'schedule',
          name: 'Schedule',
          component: () => import('@/views/Schedule.vue')
        },
        {
          path: 'rss',
          name: 'RSS',
          component: () => import('@/views/RSS.vue')
        },
        {
          path: 'mail',
          name: '邮件',
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
