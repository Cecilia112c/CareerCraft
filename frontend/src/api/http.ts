import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('cc_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && !location.pathname.startsWith('/login')) {
      localStorage.removeItem('cc_token')
      localStorage.removeItem('cc_user')
      location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export function errMsg(e: any): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg || JSON.stringify(d)).join('；')
  if (e?.response?.data instanceof Blob) return '请求失败'
  return e?.message || '请求失败'
}

export function showError(e: any) {
  ElMessage.error(errMsg(e))
}

export default http
