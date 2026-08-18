<template>
  <div class="inspect-page">
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header>
            <span>RAG 召回检查</span>
          </template>
          <el-form :model="inspectForm" label-width="80px">
            <el-form-item label="知识库">
              <el-input v-model="inspectForm.kbId" />
            </el-form-item>
            <el-form-item label="查询文本">
              <el-input
                v-model="inspectForm.query"
                type="textarea"
                :rows="4"
                placeholder="输入要测试的查询..."
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading" @click="runInspect">
                执行检查
              </el-button>
              <el-button @click="clearResult" style="margin-left: 8px">
                清空
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card v-if="result">
          <template #header>
            <span>检查结果</span>
          </template>
          <el-tabs v-model="activeTab">
            <el-tab-pane label="向量召回" name="vector">
              <el-table :data="result.vector?.results || []" stripe size="small">
                <el-table-column prop="id" label="ID" width="60" />
                <el-table-column prop="score" label="分数" width="100">
                  <template #default="{ row }">
                    <span :style="{ color: scoreColor(row.score) }">{{ row.score?.toFixed(4) }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="content" label="内容">
                  <template #default="{ row }">
                    <span class="content-preview">{{ truncate(row.content, 80) }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="BM25召回" name="bm25">
              <el-table :data="result.bm25?.results || []" stripe size="small">
                <el-table-column prop="id" label="ID" width="60" />
                <el-table-column prop="score" label="分数" width="100">
                  <template #default="{ row }">
                    <span>{{ row.score?.toFixed(4) }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="content" label="内容">
                  <template #default="{ row }">
                    <span class="content-preview">{{ truncate(row.content, 80) }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="RRF融合" name="rrf">
              <el-table :data="result.rrf?.results || []" stripe size="small">
                <el-table-column prop="id" label="ID" width="60" />
                <el-table-column prop="score" label="RRF分数" width="100">
                  <template #default="{ row }">
                    <span>{{ row.score?.toFixed(4) }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="content" label="内容">
                  <template #default="{ row }">
                    <span class="content-preview">{{ truncate(row.content, 80) }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="Rerank精排" name="rerank">
              <el-table :data="result.rerank?.results || []" stripe size="small">
                <el-table-column prop="id" label="ID" width="60" />
                <el-table-column prop="score" label="相关度" width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.score > 0.7 ? 'success' : row.score > 0.3 ? 'warning' : 'danger'" size="small">
                      {{ row.score?.toFixed(4) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="content" label="内容">
                  <template #default="{ row }">
                    <span class="content-preview">{{ truncate(row.content, 100) }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="最终上下文" name="context">
              <div class="context-output">
                <h4>拼装后的上下文（供LLM使用）</h4>
                <pre class="context-text">{{ result.context || '无上下文' }}</pre>
              </div>
              <el-divider />
              <h4>Draft回答</h4>
              <div class="draft-answer">{{ result.draft_answer || '无草稿回答' }}</div>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <el-empty v-else description="执行检查后显示结果" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '../api/client'

const inspectForm = ref({ kbId: 'default', query: '' })
const loading = ref(false)
const result = ref<any>(null)
const activeTab = ref('vector')

async function runInspect() {
  if (!inspectForm.value.query) {
    return
  }
  loading.value = true
  try {
    const res = await api.post('/rag/inspect', {
      kb_id: inspectForm.value.kbId,
      query: inspectForm.value.query,
    })
    result.value = res
    activeTab.value = 'vector'
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function clearResult() {
  result.value = null
}

function truncate(text: string, n: number) {
  if (!text) return ''
  return text.length > n ? text.slice(0, n) + '...' : text
}

function scoreColor(score: number) {
  if (score > 0.8) return '#67c23a'
  if (score > 0.5) return '#e6a23c'
  return '#f56c6c'
}
</script>

<style scoped>
.inspect-page {
  max-width: 1300px;
}
.content-preview {
  font-size: 13px;
  color: #606266;
}
.context-output {
  margin-top: 12px;
}
.context-text {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  max-height: 300px;
  overflow: auto;
  font-size: 13px;
  white-space: pre-wrap;
}
.draft-answer {
  background: #ecf5ff;
  padding: 12px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
  min-height: 60px;
}
</style>
