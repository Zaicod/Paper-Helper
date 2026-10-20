/** Schedule only after completion; a generation prevents stale route results. */
export function createTaskPoller<T extends { status: string }>(
  request: (id: string) => Promise<T>,
  onResult: (task: T) => void,
  onError: (error: unknown) => void,
  delay = 1500,
) {
  let generation = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  function stop() { generation++; clearTimeout(timer); timer = undefined }
  function start(id: string) {
    stop()
    const active = generation
    async function poll() {
      try {
        const task = await request(id)
        if (active !== generation) return
        onResult(task)
        if (task.status === 'queued' || task.status === 'running') timer = setTimeout(poll, delay)
      } catch (error) {
        if (active === generation) onError(error)
      }
    }
    void poll()
  }
  return { start, stop }
}
