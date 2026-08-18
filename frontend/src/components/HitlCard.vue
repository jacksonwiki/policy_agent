<template>
  <div class="hitl-card">
    <el-alert type="warning" :closable="false" show-icon>
      <template #title>
        <strong>⚠️ 高风险操作待审核</strong>
      </template>
      <div class="hitl-body">
        <p><strong>工具：</strong>{{ review.tool }}</p>
        <p><strong>参数：</strong></p>
        <pre class="args">{{ formatArgs(review.args) }}</pre>
        <p v-if="review.reason"><strong>原因：</strong>{{ review.reason }}</p>
      </div>
      <div class="hitl-actions">
        <el-button type="danger" size="small" @click="handleReject" :disabled="resolving">
          拒绝
        </el-button>
        <el-button size="small" @click="handleModify" :disabled="resolving">
          修改
        </el-button>
        <el-button type="primary" size="small" @click="handleApprove" :disabled="resolving">
          通过
        </el-button>
      </div>
    </el-alert>

    <el-dialog v-model="showModify" title="修改参数" width="500px">
      <el-form :model="modifiedArgs" label-width="100px">
        <el-form-item
          v-for="(_value, key) in review.args"
          :key="key"
          :label="String(key)"
        >
          <el-input v-model="modifiedArgs[key]" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showModify = false">取消</el-button>
        <el-button type="primary" @click="confirmModify">确认修改并通过</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { approveHitl } from '../api/sse'

const props = defineProps<{
  review: {
    review_id: string
    tool: string
    args: Record<string, any>
    reason: string
  }
  threadId: string
}>()

const emit = defineEmits<{
  (e: 'resolved', data: { answer: string; intent: string }): void
}>()

const resolving = ref(false)
const showModify = ref(false)
const modifiedArgs = reactive<Record<string, any>>({})

function formatArgs(args: Record<string, any>) {
  return JSON.stringify(args, null, 2)
}

function initModifiedArgs() {
  Object.keys(props.review.args).forEach((key) => {
    modifiedArgs[key] = String(props.review.args[key])
  })
}

async function resolve(action: 'approve' | 'reject' | 'modify', args?: Record<string, any>) {
  resolving.value = true
  try {
    const result = await approveHitl(props.threadId, props.review.review_id, action, args)
    emit('resolved', { answer: result.answer || '', intent: result.intent || '' })
  } catch (e) {
    console.error('HITL resolve failed:', e)
  } finally {
    resolving.value = false
  }
}

function handleApprove() {
  resolve('approve')
}

function handleReject() {
  resolve('reject')
}

function handleModify() {
  initModifiedArgs()
  showModify.value = true
}

function confirmModify() {
  showModify.value = false
  resolve('modify', modifiedArgs)
}
</script>

<style scoped>
.hitl-card {
  margin-top: 12px;
}
.hitl-body {
  margin: 8px 0;
  font-size: 13px;
}
.hitl-body p {
  margin: 4px 0;
}
.args {
  background: #f5f7fa;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 150px;
  overflow: auto;
}
.hitl-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
