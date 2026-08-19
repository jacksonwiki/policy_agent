import { useAuthStore } from '../stores/auth'

export interface SSEEvent {
  event: string
  data: any
}

export interface HitlReview {
  review_id: string
  tool: string
  args: Record<string, any>
  reason: string
}

export async function connectChat(
  threadId: string,
  message: string,
  onEvent: (event: SSEEvent) => void,
  onDone: () => void,
  onError: (err: any) => void,
  signal?: AbortSignal,
): Promise<void> {
  const authStore = useAuthStore()
  const token = authStore.token

  const url = `/api/chat`

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message,
        thread_id: threadId,
      }),
      signal,
    })

    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    // Standard SSE parsing state.
    let eventName = 'message'
    let dataLines: string[] = []

    const flushEvent = () => {
      if (dataLines.length === 0) return
      const dataStr = dataLines.join('\n')
      dataLines = []
      try {
        const data = JSON.parse(dataStr)
        onEvent({ event: eventName, data })
      } catch {
        onEvent({ event: eventName, data: dataStr })
      }
      eventName = 'message'
    }

    while (true) {
      if (signal?.aborted) {
        reader.cancel()
        break
      }
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // Keep the last (possibly incomplete) line in the buffer.
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event:')) {
          // New event header: flush any previous event first.
          flushEvent()
          eventName = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart())
        } else if (line.trim() === '') {
          // Empty line terminates the current event.
          flushEvent()
        }
        // Ignore other fields (id, retry, comments, etc.).
      }
    }

    // Flush any trailing event when the stream ends.
    flushEvent()

    onDone()
  } catch (err) {
    if (signal?.aborted) {
      onDone()
    } else {
      onError(err)
    }
  }
}

export async function approveHitl(
  threadId: string,
  reviewId: string,
  action: 'approve' | 'reject' | 'modify',
  modifiedArgs?: Record<string, any>,
): Promise<any> {
  const authStore = useAuthStore()
  const token = authStore.token

  const url = `/api/chat/${threadId}/approve`
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      action,
      review_id: reviewId,
      modified_args: modifiedArgs,
    }),
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  return response.json()
}