import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../pages/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: () => import('../pages/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'chat',
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('../pages/Chat.vue'),
      },
      {
        path: 'kb',
        name: 'KnowledgeBase',
        component: () => import('../pages/KnowledgeBase.vue'),
      },
      {
        path: 'inspect',
        name: 'Inspect',
        component: () => import('../pages/Inspect.vue'),
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('../pages/Users.vue'),
        meta: { requiresAdmin: true },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth !== false && !authStore.isLoggedIn) {
    next({ name: 'login' })
  } else if (to.meta.requiresAdmin && authStore.role !== 'admin') {
    next({ name: 'chat' })
  } else if (to.name === 'login' && authStore.isLoggedIn) {
    next({ name: 'chat' })
  } else {
    next()
  }
})

export default router
