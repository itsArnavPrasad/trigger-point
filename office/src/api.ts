/** The only path to the backend. The token stays in a header, never in a URL it sends. */

import { tokenFromHash } from './logic'

const KEY = 'trigger-point-office-token'

export function token(): string | null {
  const fromLink = tokenFromHash(location.hash)
  try {
    if (fromLink) {
      localStorage.setItem(KEY, fromLink)
      history.replaceState(null, '', location.pathname)
    }
    return fromLink ?? localStorage.getItem(KEY)
  } catch {
    return fromLink
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/office${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token()}`, 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

export const get = <T,>(path: string) => call<T>(path)
export const put = <T,>(path: string, body?: unknown) => call<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) })
export const post = <T,>(path: string, body?: unknown) => call<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) })

/** The server sends a heartbeat every 10 s, so silence this long means it is gone or frozen. */
export const SILENCE_MS = 25_000

function readOrGiveUp(reader: ReadableStreamDefaultReader<Uint8Array>) {
  let timer: ReturnType<typeof setTimeout>
  const silent = new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('silent')), SILENCE_MS) })
  return Promise.race([reader.read(), silent]).finally(() => clearTimeout(timer))
}

/** Follows the change stream and reconnects. A tick only says "something changed": fetch again. */
export function follow(onTick: () => void, onConnection: (up: boolean) => void): () => void {
  let stopped = false
  const controller = new AbortController()
  async function run() {
    while (!stopped) {
      try {
        const res = await fetch('/api/office/stream', { headers: { Authorization: `Bearer ${token()}` }, signal: controller.signal })
        if (!res.ok || !res.body) throw new Error('stream refused')
        onConnection(true)
        const reader = res.body.getReader()
        const text = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { done, value } = await readOrGiveUp(reader)
          if (done) break
          buffer += text.decode(value, { stream: true })
          if (buffer.includes('data:')) { buffer = ''; onTick() } else if (buffer.length > 4096) buffer = ''
        }
      } catch { /* falls through to the retry */ }
      if (stopped) return
      onConnection(false)
      await new Promise(r => setTimeout(r, 1500))
    }
  }
  void run()
  return () => { stopped = true; controller.abort() }
}
