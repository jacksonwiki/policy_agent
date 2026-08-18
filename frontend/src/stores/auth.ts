import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')
  const role = ref(localStorage.getItem('role') || '')

  const isLoggedIn = computed(() => !!token.value)

  async function login(usernameInput: string, password: string) {
    const res = await api.post('/auth/login', { username: usernameInput, password })
    token.value = res.token
    username.value = res.username
    role.value = res.role
    localStorage.setItem('token', res.token)
    localStorage.setItem('username', res.username)
    localStorage.setItem('role', res.role)
  }

  async function register(usernameInput: string, password: string) {
    const res = await api.post('/auth/register', { username: usernameInput, password })
    token.value = res.token
    username.value = res.username
    role.value = res.role
    localStorage.setItem('token', res.token)
    localStorage.setItem('username', res.username)
    localStorage.setItem('role', res.role)
  }

  function logout() {
    token.value = ''
    username.value = ''
    role.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('role')
  }

  return { token, username, role, isLoggedIn, login, register, logout }
})
