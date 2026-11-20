import { ref } from 'vue'
import { api } from '@/api'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** Submit a background agent task and poll it until done. */
export function useTask() {
  const running = ref(false)
  const progress = ref(0)
  const stage = ref('')

  async function waitFor(taskId: string): Promise<any> {
    running.value = true
    progress.value = 0
    stage.value = '排队中'
    try {
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await sleep(1500)
        const t = await api.getTask(taskId)
        progress.value = t.progress
        stage.value = t.stage
        if (t.status === 'done') return t.result
        if (t.status === 'failed') throw new Error(t.error || '任务失败')
      }
    } finally {
      running.value = false
    }
  }

  async function run(start: () => Promise<{ task_id: string }>): Promise<any> {
    running.value = true
    try {
      const { task_id } = await start()
      return await waitFor(task_id)
    } finally {
      running.value = false
    }
  }

  return { running, progress, stage, run, waitFor }
}
