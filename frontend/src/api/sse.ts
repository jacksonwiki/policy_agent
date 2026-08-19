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

    while (true) {
      if (signal?.aborted) {
        reader.cancel()
        break
      }
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event:')) {
          const eventType = line.slice(6).trim()
          const dataLine = lines.find((l) => l.startsWith('data:'))
          if (dataLine) {
            const dataStr = dataLine.slice(5).trim()
            try {
              const data = JSON.parse(dataStr)
              onEvent({ event: eventType, data })
            } catch {
              onEvent({ event: eventType, data: dataStr })
            }
          }
        }
      }
    }

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