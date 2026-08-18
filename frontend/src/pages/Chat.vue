<template>
  <div class="chat-page">
    <div class="chat-layout">
      <!-- 侧边栏 -->
      <aside class="conv-sidebar">
        <div class="conv-header">
          <div class="brand">
            <div class="brand-icon">
              <el-icon :size="18"><ChatDotRound /></el-icon>
            </div>
            <span>智能对话</span>
          </div>
          <el-button type="primary" size="small" @click="newChat" class="new-chat-btn">
            <el-icon><Plus /></el-icon>新对话
          </el-button>
        </div>
        <div class="conv-list">
          <div
            v-for="conv in conversations"
            :key="conv.thread_id"
            :class="['conv-item', { active: conv.thread_id === threadId }]"
            @click="selectConversation(conv.thread_id)"
          >
            <div class="conv-icon-wrap">
              <el-icon :size="14"><ChatLineSquare /></el-icon>
            </div>
            <div class="conv-body">
              <div class="conv-title">{{ conv.title }}</div>
              <div class="conv-preview">{{ conv.last_message }}</div>
            </div>
            <div class="conv-meta">
              <span class="conv-time">{{ formatTime(conv.updated_at) }}</span>
              <el-icon
                class="conv-delete"
                @click.stop="deleteConversation(conv.thread_id)"
              ><Delete /></el-icon>
            </div>
          </div>
          <el-empty v-if="conversations.length === 0" description="暂无对话" :image-size="60" />
        </div>
      </aside>

      <!-- 聊天区 -->
      <main class="chat-container">
        <div class="chat-history" ref="historyRef">
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="['message-item', msg.role]"
          >
            <div :class="['avatar', msg.role]">
              <el-icon v-if="msg.role === 'user'" :size="18"><User /></el-icon>
              <el-icon v-else :size="18"><Robot /></el-icon>
            </div>
            <div class="bubble-wrap">
              <div v-if="msg.content" class="bubble" :class="msg.role">
                <div class="bubble-inner" v-html="formatContent(msg.content)"></div>
              </div>
              <HitlCard
                v-if="msg.hitlReview"
                :review="msg.hitlReview"
                :thread-id="threadId"
                @resolved="onHitlResolved"
              />
            </div>
          </div>
          <div v-if="streaming" class="message-item assistant">
            <div class="avatar assistant">
              <el-icon :size="18"><Robot /></el-icon>
            </div>
            <div class="bubble-wrap">
              <div class="bubble assistant typing">
                <div class="typing-dots">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="chat-footer">
          <div class="chat-input-wrap">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="2"
              placeholder="请输入您的问题..."
              :disabled="streaming"
              @keydown.enter.exact.prevent="sendMessage"
              class="chat-input"
            />
            <div class="input-actions">
              <el-button
                :type="streaming ? 'info' : 'primary'"
                :loading="streaming"
                @click="sendMessage"
                class="send-btn"
                round
              >
                <el-icon v-if="!streaming"><Promotion /></el-icon>
                <span>{{ streaming ? '思考中' : '发送' }}</span>
              </el-button>
            </div>
          </div>
          <div class="chat-actions">
            <el-button text size="small" @click="clearChat" :disabled="streaming">
              <el-icon><Delete /></el-icon> 清空对话
            </el-button>
            <span class="model-hint">Powered by DeepSeek</span>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, markRaw } from 'vue'
import { connectChat, type SSEEvent } from '../api/sse'
import HitlCard from '../components/HitlCard.vue'
import api from '../api/client'

interface ChatMessage {
  role: 'user' | 'assistant'
  content?: string
  hitlReview?: {
    review_id: string
    tool: string
    args: Record<string, any>
    reason: string
  }
}

interface Conversation {
  thread_id: string
  title: string
  last_message: string
  created_at: string
  updated_at: string
  message_count?: number
}

const STORAGE_KEY = 'policy_agent_thread_id'

const threadId = ref('')
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const streaming = ref(false)
const historyRef = ref()
const conversations = ref<Conversation[]>([])
const currentAnswer = ref('')

function generateThreadId() {
  return `thread-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

async function loadConversations() {
  try {
    const res = await api.get<{ conversations: Conversation[] }>('/chat/conversations')
    conversations.value = res.conversations || []
  } catch {
    conversations.value = []
  }
}

async function loadHistory(thread_id: string) {
  try {
    const res = await api.get<{ messages: ChatMessage[] }>(`/chat/history/${thread_id}`)
    if (res.messages && res.messages.length > 0) {
      messages.value = res.messages.filter((m: ChatMessage) =>
        m.role === 'user' || m.role === 'assistant'
      )
      threadId.value = thread_id
      localStorage.setItem(STORAGE_KEY, thread_id)
      await nextTick()
      scrollToBottom()
      return true
    }
  } catch {}
  return false
}

async function selectConversation(thread_id: string) {
  streaming.value = false
  await loadHistory(thread_id)
}

async function newChat() {
  streaming.value = false
  messages.value = []
  threadId.value = generateThreadId()
  localStorage.setItem(STORAGE_KEY, threadId.value)
  await nextTick()
}

async function deleteConversation(thread_id: string) {
  try {
    await api.delete(`/chat/conversations/${thread_id}`)
    conversations.value = conversations.value.filter(c => c.thread_id !== thread_id)
    if (thread_id === threadId.value) {
      messages.value = []
      threadId.value = generateThreadId()
      localStorage.setItem(STORAGE_KEY, threadId.value)
    }
  } catch {}
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return
  if (!threadId.value) {
    threadId.value = generateThreadId()
  }
  messages.value.push({ role: 'user', content: text })
  await sendMessageText(text)
  await loadConversations()
}

function onHitlResolved(data: { answer: string; intent: string }) {
  if (messages.value.length > 0) {
    const lastMsg = messages.value[messages.value.length - 1]
    lastMsg.content = data.answer || '操作已完成'
    lastMsg.hitlReview = undefined
  }
}

async function sendMessageText(text: string) {
  messages.value.push({ role: 'assistant', content: '' })
  inputText.value = ''
  streaming.value = true
  currentAnswer.value = ''

  await nextTick()
  scrollToBottom()

  try {
    await connectChat(
      threadId.value,
      text,
      (event: SSEEvent) => {
        const lastMsg = messages.value[messages.value.length - 1]
        if (event.event === 'token') {
          currentAnswer.value += event.data?.content || ''
          lastMsg.content = currentAnswer.value
          scrollToBottom()
        } else if (event.event === 'hitl_review') {
          lastMsg.hitlReview = event.data
          lastMsg.content = ''
          scrollToBottom()
        } else if (event.event === 'done') {
          lastMsg.content = event.data?.answer || currentAnswer.value
          if (event.data?.thread_id) {
            threadId.value = event.data.thread_id
            localStorage.setItem(STORAGE_KEY, threadId.value)
          }
        } else if (event.event === 'error') {
          lastMsg.content = `错误: ${event.data?.message || '未知错误'}`
        }
      },
      () => { streaming.value = false },
      () => {
        streaming.value = false
        const lastMsg = messages.value[messages.value.length - 1]
        lastMsg.content = lastMsg.content || '连接错误，请重试'
      }
    )
  } catch (e) {
    streaming.value = false
  }
}

function clearChat() {
  messages.value = []
  threadId.value = generateThreadId()
  localStorage.setItem(STORAGE_KEY, threadId.value)
}

function scrollToBottom() {
  nextTick(() => {
    if (historyRef.value) {
      historyRef.value.scrollTop = historyRef.value.scrollHeight
    }
  })
}

function formatContent(content: string) {
  if (!content) return ''
  let html = content
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>')
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\n/g, '<br>')
  return html
}

function formatTime(iso: string) {
  try {
    const d = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - d.getTime()
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ''
  }
}

onMounted(async () => {
  const savedThreadId = localStorage.getItem(STORAGE_KEY)
  let restored = false
  if (savedThreadId) {
    restored = await loadHistory(savedThreadId)
  }
  if (!restored) {
    threadId.value = generateThreadId()
    localStorage.setItem(STORAGE_KEY, threadId.value)
  }
  await loadConversations()
})
</script>

<style scoped>
.chat-page {
  height: 100%;
  background: transparent;
}

.chat-layout {
  display: flex;
  height: calc(100vh - 120px);
  gap: 16px;
}

/* === 侧边栏 === */
.conv-sidebar {
  width: 260px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.04);
}

.conv-header {
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
}

.brand-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

.new-chat-btn {
  width: 100%;
  border-radius: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  font-weight: 500;
}

.new-chat-btn:hover {
  opacity: 0.9;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conv-item {
  padding: 12px;
  border-radius: 10px;
  cursor: pointer;
  margin-bottom: 6px;
  transition: all 0.2s ease;
  display: flex;
  gap: 10px;
  border: 1px solid transparent;
}

.conv-item:hover {
  background: #f7f8fc;
  border-color: #e8e8ef;
}

.conv-item.active {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.08) 0%, rgba(118, 75, 162, 0.08) 100%);
  border-color: #667eea;
}

.conv-icon-wrap {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: #f0f0f5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
  flex-shrink: 0;
  margin-top: 2px;
}

.conv-item.active .conv-icon-wrap {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.conv-body {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-preview {
  font-size: 12px;
  color: #8c8c9a;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.conv-time {
  font-size: 11px;
  color: #b0b0bc;
}

.conv-delete {
  opacity: 0;
  transition: all 0.2s;
  cursor: pointer;
  color: #b0b0bc;
  font-size: 14px;
}

.conv-item:hover .conv-delete {
  opacity: 1;
}

.conv-delete:hover {
  color: #ff4d4f;
}

/* === 聊天容器 === */
.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.04);
}

.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: linear-gradient(180deg, #fafbff 0%, #ffffff 100%);
}

.chat-history::-webkit-scrollbar {
  width: 6px;
}
.chat-history::-webkit-scrollbar-thumb {
  background: #d0d0da;
  border-radius: 3px;
}
.chat-history::-webkit-scrollbar-thumb:hover {
  background: #b8b8c4;
}

/* === 消息气泡 === */
.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  animation: fadeInUp 0.3s ease;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-item.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.avatar.user {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.avatar.assistant {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.bubble-wrap {
  max-width: 75%;
  display: flex;
  flex-direction: column;
}

.message-item.user .bubble-wrap {
  align-items: flex-end;
}

.bubble {
  padding: 12px 16px;
  border-radius: 16px;
  line-height: 1.7;
  font-size: 14px;
  position: relative;
  transition: box-shadow 0.2s;
}

.bubble.assistant {
  background: #f5f6fa;
  color: #1a1a2e;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.bubble.user {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.bubble-inner {
  word-break: break-word;
  white-space: pre-wrap;
}

.bubble-inner :deep(strong) {
  font-weight: 600;
}

.bubble-inner :deep(.inline-code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'SF Mono', Consolas, monospace;
}

.bubble.user .bubble-inner :deep(.inline-code) {
  background: rgba(255, 255, 255, 0.25);
}

.bubble-inner :deep(.code-block) {
  background: #1e1e2e;
  color: #e0e0e8;
  padding: 12px 14px;
  border-radius: 10px;
  margin: 10px 0;
  font-size: 13px;
  font-family: 'SF Mono', Consolas, monospace;
  overflow-x: auto;
  line-height: 1.5;
}

.bubble.user .bubble-inner :deep(.code-block) {
  background: rgba(0, 0, 0, 0.3);
}

/* === 打字动画 === */
.typing {
  padding: 16px 20px;
}

.typing-dots {
  display: flex;
  gap: 5px;
}

.typing-dots span {
  width: 7px;
  height: 7px;
  background: #b0b0bc;
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out both;
}

.typing-dots span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* === 输入区 === */
.chat-footer {
  border-top: 1px solid #f0f0f5;
  padding: 16px 24px;
  background: #fafbff;
}

.chat-input-wrap {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background: #fff;
  border-radius: 14px;
  padding: 10px 12px;
  border: 2px solid #e8e8ef;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.chat-input-wrap:focus-within {
  border-color: #667eea;
  box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
}

.chat-input :deep(.el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  padding: 4px 0;
  background: transparent;
  font-size: 14px;
  line-height: 1.6;
}

.chat-input :deep(.el-textarea__inner:focus) {
  box-shadow: none !important;
}

.chat-input :deep(.el-textarea__inner)::-webkit-scrollbar {
  width: 4px;
}

.input-actions {
  flex-shrink: 0;
}

.send-btn {
  border-radius: 10px;
  padding: 8px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
  border: none !important;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.send-btn:hover {
  opacity: 0.9;
  transform: translateY(-1px);
  transition: all 0.2s;
}

.chat-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  padding: 0 4px;
}

.model-hint {
  font-size: 12px;
  color: #b0b0bc;
}
</style>
