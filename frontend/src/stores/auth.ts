import { defineStore } from 'pinia'
import { api } from '@/api'

export const useAuth = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('cc_token') || '',
    user: JSON.parse(localStorage.getItem('cc_user') || 'null') as { id: number; username: string } | null,
  }),
  getters: { loggedIn: (s) => !!s.token },
  actions: {
    _save(res: any) {
      this.token = res.token
      this.user = res.user
      localStorage.setItem('cc_token', res.token)
      localStorage.setItem('cc_user', JSON.stringify(res.user))
    },
    async login(username: string, password: string) { this._save(await api.login(username, password)) },
    async register(username: string, password: string) { this._save(await api.register(username, password)) },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('cc_token')
      localStorage.removeItem('cc_user')
    },
  },
})
