import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
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
        { path: '', redirect: '/files' },
        {
          path: 'files',
          name: 'Files',
          component: () => import('@/views/Files.vue')
        },
        {
          path: 'workspaces',
          name: 'Workspaces',
          component: () => import('@/views/Workspaces.vue')
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/Settings.vue')
        },
        {
          path: 'apps/:pluginName/:pathMatch(.*)*',
          name: 'PluginHost',
          component: () => import('@/core/layout/PluginHost.vue')
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
