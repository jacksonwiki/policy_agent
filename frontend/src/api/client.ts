import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '../stores/auth'

const instance: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

instance.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

instance.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

const api = {
  get: <T = any>(url: string, config?: any): Promise<T> =>
    instance.get(url, config) as unknown as Promise<T>,
  post: <T = any>(url: string, data?: any, config?: any): Promise<T> =>
    instance.post(url, data, config) as unknown as Promise<T>,
  put: <T = any>(url: string, data?: any, config?: any): Promise<T> =>
    instance.put(url, data, config) as unknown as Promise<T>,
  delete: <T = any>(url: string, config?: any): Promise<T> =>
    instance.delete(url, config) as unknown as Promise<T>,
}

export default api
