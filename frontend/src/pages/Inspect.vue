<template>
  <div class="inspect-page">
    <!-- 顶部查询面板 -->
    <div class="query-panel">
      <div class="query-header">
        <div class="query-title">
          <div class="title-icon">
            <el-icon :size="18"><Search /></el-icon>
          </div>
          <span>RAG 召回检查</span>
        </div>
        <div class="query-actions">
          <el-button v-if="result" text size="small" @click="clearResult">
            <el-icon><Delete /></el-icon> 清空结果
          </el-button>
        </div>
      </div>
      <div class="query-body">
        <el-input
          v-model="inspectForm.query"
          type="textarea"
          :rows="2"
          placeholder="输入要测试的查询语句，例如：车险理赔需要哪些材料？"
          resize="none"
          @keydown.ctrl.enter="runInspect"
        />
        <div class="query-bottom">
          <div class="quick-examples">
            <span class="examples-label">快捷示例：</span>
            <el-tag
              v-for="ex in examples"
              :key="ex"
              size="small"
              effect="plain"
              class="example-tag"
              @click="inspectForm.query = ex"
            >{{ ex }}</el-tag>
          </div>
          <el-button
            type="primary"
            :loading="loading"
            @click="runInspect"
            class="run-btn"
            round
          >
            <el-icon v-if="!loading"><Promotion /></el-icon>
            <span>{{ loading ? '检查中...' : '执行检查' }}</span>
          </el-button>
        </div>
      </div>
    </div>

    <!-- 流程指示器 -->
    <div v-if="result" class="pipeline-flow">
      <div class="pipeline-step" :class="{ active: activeTab === 'vector' }" @click="activeTab = 'vector'">
        <div class="step-num">1</div>
        <div class="step-info">
          <div class="step-name">向量召回</div>
          <div class="step-count">{{ result.vector?.results?.length || 0 }} 条</div>
        </div>
      </div>
      <div class="pipeline-arrow">→</div>
      <div class="pipeline-step" :class="{ active: activeTab === 'bm25' }" @click="activeTab = 'bm25'">
        <div class="step-num">2</div>
        <div class="step-info">
          <div class="step-name">BM25召回</div>
          <div class="step-count">{{ result.bm25?.results?.length || 0 }} 条</div>
        </div>
      </div>
      <div class="pipeline-arrow">→</div>
      <div class="pipeline-step" :class="{ active: activeTab === 'rrf' }" @click="activeTab = 'rrf'">
        <div class="step-num">3</div>
        <div class="step-info">
          <div class="step-name">RRF融合</div>
          <div class="step-count">{{ result.rrf?.results?.length || 0 }} 条</div>
        </div>
      </div>
      <div class="pipeline-arrow">→</div>
      <div class="pipeline-step" :class="{ active: activeTab === 'rerank' }" @click="activeTab = 'rerank'">
        <div class="step-num">4</div>
        <div class="step-info">
          <div class="step-name">Rerank精排</div>
          <div class="step-count">{{ result.rerank?.results?.length || 0 }} 条</div>
        </div>
      </div>
      <div class="pipeline-arrow">→</div>
      <div class="pipeline-step" :class="{ active: activeTab === 'context' }" @click="activeTab = 'context'">
        <div class="step-num">5</div>
        <div class="step-info">
          <div class="step-name">最终上下文</div>
          <div class="step-count">LLM输入</div>
        </div>
      </div>
    </div>

    <!-- 结果区 -->
    <div v-if="result" class="result-panel">
      <div class="result-header">
        <h3>{{ tabTitle }}</h3>
        <el-tag v-if="activeTab !== 'context'" size="small" round>
          {{ currentResults.length }} 条结果
        </el-tag>
      </div>

      <div class="result-body">
        <!-- 向量/BM25/RRF/Rerank 结果列表 -->
        <div v-if="activeTab !== 'context'" class="results-list">
          <div
            v-for="(item, idx) in currentResults"
            :key="idx"
            class="result-card"
          >
            <div class="result-rank">#{{ idx + 1 }}</div>
            <div class="result-score-wrap">
              <div class="score-bar-wrap">
                <div class="score-label">分数</div>
                <div class="score-bar">
                  <div class="score-fill" :style="{ width: scorePercent(item.score) + '%', background: scoreGradient(item.score) }"></div>
                </div>
              </div>
              <div class="score-value" :style="{ color: scoreColor(item.score) }">
                {{ item.score?.toFixed(4) }}
              </div>
            </div>
            <div class="result-content">
              <div class="content-text">{{ item.content }}</div>
              <div class="content-meta">
                <el-tag size="small" effect="plain" type="info">ID: {{ item.id }}</el-tag>
              </div>
            </div>
          </div>
          <el-empty v-if="currentResults.length === 0" description="无结果" :image-size="60" />
        </div>

        <!-- 最终上下文 -->
        <div v-else class="context-section">
          <div class="context-block">
            <div class="block-header">
              <el-icon :size="16"><Document /></el-icon>
              <span>拼装上下文（供 LLM 使用）</span>
              <el-button text size="small" @click="copyText(result.context)">
                <el-icon><CopyDocument /></el-icon> 复制
              </el-button>
            </div>
            <pre class="context-text">{{ result.context || '无上下文' }}</pre>
          </div>
          <div class="context-block draft-block">
            <div class="block-header">
              <el-icon :size="16"><EditPen /></el-icon>
              <span>Draft 回答</span>
            </div>
            <div class="draft-answer">{{ result.draft_answer || '无草稿回答' }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <div class="empty-icon">
        <el-icon :size="48"><DataAnalysis /></el-icon>
      </div>
      <h3>RAG 全链路检查</h3>
      <p>输入查询语句，查看向量召回、BM25召回、RRF融合、Rerank精排的全过程</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/client'

interface ResultItem {
  id: string | number
  score: number
  content: string
}

interface InspectResult {
  query: string
  vector: { results: ResultItem[] }
  bm25: { results: ResultItem[] }
  rrf: { results: ResultItem[] }
  rerank: { results: ResultItem[] }
  context: string
  draft_answer: string
}

const inspectForm = ref({ kbId: 'default', query: '' })
const loading = ref(false)
const result = ref<InspectResult | null>(null)
const activeTab = ref('vector')

const examples = [
  '车险理赔流程是什么？',
  '重疾险包含哪些疾病？',
  '保险免赔额怎么计算？',
]

const tabTitles: Record<string, string> = {
  vector: '向量召回结果',
  bm25: 'BM25 召回结果',
  rrf: 'RRF 融合结果',
  rerank: 'Rerank 精排结果',
  context: '最终上下文 & Draft 回答',
}

const tabTitle = computed(() => tabTitles[activeTab.value] || '')

const currentResults = computed<ResultItem[]>(() => {
  if (!result.value) return []
  const tab = activeTab.value
  if (tab === 'vector') return result.value.vector?.results || []
  if (tab === 'bm25') return result.value.bm25?.results || []
  if (tab === 'rrf') return result.value.rrf?.results || []
  if (tab === 'rerank') return result.value.rerank?.results || []
  return []
})

async function runInspect() {
  if (!inspectForm.value.query.trim()) {
    ElMessage.warning('请输入查询内容')
    return
  }
  loading.value = true
  try {
    const res = await api.post<InspectResult>('/rag/inspect', {
      kb_id: inspectForm.value.kbId,
      query: inspectForm.value.query,
    })
    result.value = res
    activeTab.value = 'vector'
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '检查失败')
  } finally {
    loading.value = false
  }
}

function clearResult() {
  result.value = null
  inspectForm.value.query = ''
}

function scorePercent(score: number) {
  return Math.min(100, Math.max(0, score * 100))
}

function scoreColor(score: number) {
  if (score > 0.8) return '#43e97b'
  if (score > 0.5) return '#e6a23c'
  return '#f56c6c'
}

function scoreGradient(score: number) {
  if (score > 0.8) return 'linear-gradient(90deg, #43e97b, #38f9d7)'
  if (score > 0.5) return 'linear-gradient(90deg, #e6a23c, #ffd54f)'
  return 'linear-gradient(90deg, #f56c6c, #ff8a80)'
}

function copyText(text: string) {
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制到剪贴板')
  })
}
</script>

<style scoped>
.inspect-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* === 查询面板 === */
.query-panel {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.03);
  overflow: hidden;
}

.query-header {
  padding: 14px 20px;
  border-bottom: 1px solid #f0f0f5;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.query-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
}

.title-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
}

.query-body {
  padding: 16px 20px;
}

.query-body :deep(.el-textarea__inner) {
  border-radius: 10px;
  border: 2px solid #e8e8ef;
  font-size: 14px;
  line-height: 1.6;
  transition: border-color 0.2s;
}

.query-body :deep(.el-textarea__inner:focus) {
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.query-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.quick-examples {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.examples-label {
  font-size: 12px;
  color: #b0b0bc;
}

.example-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.example-tag:hover {
  background: #667eea !important;
  color: #fff !important;
  border-color: #667eea !important;
}

.run-btn {
  border-radius: 10px;
  padding: 8px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
  border: none !important;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.run-btn:hover {
  opacity: 0.9;
  transform: translateY(-1px);
  transition: all 0.2s;
}

/* === 流程指示器 === */
.pipeline-flow {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 20px;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.03);
  flex-wrap: wrap;
}

.pipeline-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.pipeline-step:hover {
  background: #f7f8fc;
}

.pipeline-step.active {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
  border-color: #667eea;
}

.step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.pipeline-step.active .step-num {
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.4);
}

.step-info {
  display: flex;
  flex-direction: column;
}

.step-name {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
}

.step-count {
  font-size: 11px;
  color: #8c8c9a;
}

.pipeline-arrow {
  color: #c0c4d0;
  font-size: 18px;
  font-weight: 300;
}

/* === 结果面板 === */
.result-panel {
  flex: 1;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.result-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f5;
  display: flex;
  align-items: center;
  gap: 12px;
}

.result-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
}

.result-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

/* === 结果卡片 === */
.results-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.result-card {
  display: flex;
  gap: 14px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid #f0f0f5;
  transition: all 0.2s;
}

.result-card:hover {
  border-color: #667eea;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.08);
}

.result-rank {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.result-score-wrap {
  width: 140px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.score-bar-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.score-label {
  font-size: 11px;
  color: #b0b0bc;
}

.score-bar {
  height: 6px;
  background: #f0f0f5;
  border-radius: 3px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.score-value {
  font-size: 16px;
  font-weight: 700;
  font-family: 'SF Mono', Consolas, monospace;
}

.result-content {
  flex: 1;
  min-width: 0;
}

.content-text {
  font-size: 13px;
  line-height: 1.7;
  color: #4a4a5e;
  white-space: pre-wrap;
  word-break: break-word;
}

.content-meta {
  margin-top: 8px;
}

/* === 上下文区 === */
.context-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.context-block {
  display: flex;
  flex-direction: column;
}

.block-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 10px;
}

.context-text {
  background: #1e1e2e;
  color: #e0e0e8;
  padding: 16px;
  border-radius: 12px;
  font-size: 13px;
  font-family: 'SF Mono', Consolas, monospace;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.draft-block .draft-answer {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
  border: 1px solid rgba(102, 126, 234, 0.15);
  padding: 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.8;
  color: #4a4a5e;
  min-height: 80px;
}

/* === 空状态 === */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.empty-icon {
  width: 80px;
  height: 80px;
  border-radius: 20px;
  background: linear-gradient(135deg, #f0f0f5 0%, #e8e8ef 100%);
  color: #b0b0bc;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}

.empty-state h3 {
  margin: 0;
  font-size: 18px;
  color: #4a4a5e;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
  color: #b0b0bc;
  max-width: 400px;
  text-align: center;
}
</style>
