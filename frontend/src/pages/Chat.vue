<template>
  <div class="chat-page">
    <div class="chat-layout">
      <div class="conv-sidebar">
        <div class="conv-header">
          <el-button type="primary" size="small" @click="newChat" style="width: 100%">
            <el-icon><Plus /></el-icon> 新对话
          </el-button>
        </div>
        <div class="conv-list">
          <div
            v-for="conv in conversations"
            :key="conv.thread_id"
            :class="['conv-item', { active: conv.thread_id === threadId }]"
            @click="selectConversation(conv.thread_id)"
          >
            <div class="conv-title">{{ conv.title }}</div>
            <div class="conv-preview">{{ conv.last_message }}</div>
            <div class="conv-meta">
              <span>{{ formatTime(conv.updated_at) }}</span>
              <el-icon
                class="conv-delete"
                @click.stop="deleteConversation(conv.thread_id)"
              ><Delete /></el-icon>
            </div>
          </div>
          <el-empty v-if="conversations.length === 0" description="暂无对话" :image-size="60" />
        </div>
      </div>

      <div class="chat-container">
        <div class="chat-history" ref="historyRef">
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="['message-item', msg.role]"
          >
            <div class="avatar">
              <el-icon v-if="msg.role === 'user'" :size="20"><User /></el-icon>
              <el-icon v-else :size="20"><Robot /></el-icon>
            </div>
            <div class="content">
              <div v-if="msg.content" class="text" v-html="formatContent(msg.content)"></div>
              <HitlCard
                v-if="msg.hitlReview"
                :review="msg.hitlReview"
                :thread-id="threadId"
                @resolved="onHitlResolved"
              />
            </div>
          </div>
          <div v-if="streaming" class="message-item assistant">
            <div class="avatar">
              <el-icon :size="20"><Robot /></el-icon>
            </div>
            <div class="content">
              <div class="text streaming">
                <span class="cursor">|</span>
              </div>
            </div>
          </div>
        </div>

        <div class="chat-input">
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="2"
            placeholder="请输入您的问题..."
            :disabled="streaming"
            @keydown.enter.exact.prevent="sendMessage"
          />
          <el-button
            type="primary"
            :loading="streaming"
            @click="sendMessage"
            style="margin-left: 12px"
          >
            发送
          </el-button>
          <el-button @click="clearChat" :disabled="streaming">清空</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
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
  } catch {
    // thread not found or empty
  }
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
  } catch { /* ignore */ }
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
  return content.replace(/\n/g, '<br>')
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
}
.chat-layout {
  display: flex;
  height: calc(100vh - 120px);
  gap: 16px;
}
.conv-sidebar {
  width: 260px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.conv-header {
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
}
.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.conv-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
  border: 1px solid transparent;
}
.conv-item:hover {
  background: #f5f7fa;
}
.conv-item.active {
  background: #ecf5ff;
  border-color: #409eff;
}
.conv-title {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-preview {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 4px;
}
.conv-delete {
  opacity: 0;
  transition: opacity 0.2s;
  cursor: pointer;
}
.conv-item:hover .conv-delete {
  opacity: 1;
}
.conv-delete:hover {
  color: #f56c6c;
}
.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  min-width: 0;
}
.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.message-item.user {
  flex-direction: row-reverse;
}
.message-item .avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.message-item.user .avatar {
  background: #67c23a;
}
.message-item .content {
  max-width: 70%;
}
.message-item .text {
  padding: 12px 16px;
  border-radius: 8px;
  background: #f4f4f5;
  line-height: 1.6;
  white-space: pre-wrap;
}
.message-item.user .text {
  background: #ecf5ff;
}
.message-item .streaming .cursor {
  animation: blink 1s infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.chat-input {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  border-top: 1px solid #ebeef5;
}
</style>
