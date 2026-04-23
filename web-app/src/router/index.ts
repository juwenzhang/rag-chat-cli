import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { installGuards } from './guards'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    component: () => import('@/layouts/AuthLayout'),
    children: [{ path: '', name: 'login', component: () => import('@/views/LoginView') }],
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout'),
    children: [
      { path: '', redirect: { name: 'dashboard' } },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/DashboardView'),
      },
      { path: 'token', name: 'token', component: () => import('@/views/TokenView') },
      { path: 'profile', name: 'profile', component: () => import('@/views/ProfileView') },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

installGuards(router)

export default router
