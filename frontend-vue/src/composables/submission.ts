/** A failed response does not prove that the server rejected the task. */
export function createSubmission(makeKey: () => string = () => crypto.randomUUID()) {
  let fingerprint: string | undefined
  let key: string | undefined
  return {
    keyFor(payload: unknown) {
      const current = JSON.stringify(payload)
      if (fingerprint !== current || !key) {
        fingerprint = current
        key = makeKey()
      }
      return key
    },
    reset() { fingerprint = undefined; key = undefined },
  }
}
