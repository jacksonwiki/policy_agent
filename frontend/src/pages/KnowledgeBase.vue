<template>
  <div class="kb-page">
    <!-- 顶部统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)">
          <el-icon :size="22"><Document /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ documents.length }}</div>
          <div class="stat-label">文档总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)">
          <el-icon :size="22"><Files /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ totalChunks }}</div>
          <div class="stat-label">切片总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%)">
          <el-icon :size="22"><Coin /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ totalChars.toLocaleString() }}</div>
          <div class="stat-label">字符总量</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)">
          <el-icon :size="22"><DataAnalysis /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ avgChunkSize }}</div>
          <div class="stat-label">平均切片大小</div>
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="kb-content">
      <!-- 左侧：上传面板 -->
      <aside class="upload-panel">
        <div class="panel-header">
          <div class="panel-title">
            <el-icon :size="18"><UploadFilled /></el-icon>
            <span>上传文档</span>
          </div>
        </div>
        <div class="panel-body">
          <el-form :model="uploadForm" label-position="top" class="upload-form">
            <el-form-item label="知识库">
              <el-select v-model="uploadForm.kbId" placeholder="选择知识库" style="width: 100%">
                <el-option label="默认知识库" value="default" />
                <el-option label="车险知识库" value="auto_insurance" />
                <el-option label="健康险知识库" value="health_insurance" />
                <el-option label="寿险知识库" value="life_insurance" />
              </el-select>
            </el-form-item>

            <!-- Tab 切换：文本输入 / 文件上传 -->
            <el-tabs v-model="uploadMode" class="upload-tabs">
              <el-tab-pane label="文本输入" name="text">
                <el-form-item label="文档标题">
                  <el-input v-model="uploadForm.title" placeholder="请输入文档标题" />
                </el-form-item>
                <el-form-item label="文档内容">
                  <el-input
                    v-model="uploadForm.content"
                    type="textarea"
                    :rows="8"
                    placeholder="粘贴或输入文档内容..."
                    resize="vertical"
                  />
                  <div class="char-counter">{{ uploadForm.content.length }} 字符</div>
                </el-form-item>
              </el-tab-pane>

              <el-tab-pane label="文件上传" name="file">
                <el-form-item label="文档标题（可选）">
                  <el-input v-model="uploadForm.title" placeholder="留空则使用文件名" />
                </el-form-item>
                <el-upload
                  ref="uploadRef"
                  drag
                  :auto-upload="false"
                  :limit="1"
                  :on-change="handleFileChange"
                  :on-remove="handleFileRemove"
                  accept=".txt,.md,.csv,.json,.yaml,.yml,.pdf,.docx"
                  class="file-upload-dragger"
                >
                  <div class="upload-dragger-body">
                    <div class="upload-icon">
                      <el-icon :size="32"><UploadFilled /></el-icon>
                    </div>
                    <div class="upload-text">拖拽文件到此处，或<em>点击上传</em></div>
                    <div class="upload-hint">支持 TXT / MD / CSV / JSON / PDF / DOCX</div>
                  </div>
                </el-upload>
                <div v-if="selectedFile" class="file-info-bar">
                  <el-icon :size="14"><Document /></el-icon>
                  <span class="file-name">{{ selectedFile.name }}</span>
                  <span class="file-size">{{ formatFileSize(selectedFile.size) }}</span>
                </div>
              </el-tab-pane>
            </el-tabs>

            <el-collapse class="advanced-settings">
              <el-collapse-item title="高级设置" name="advanced">
                <el-form-item label="切片大小">
                  <el-slider v-model="uploadForm.chunkSize" :min="200" :max="2000" :step="100" show-input style="width: 100%" />
                </el-form-item>
                <el-form-item label="重叠大小">
                  <el-slider v-model="uploadForm.chunkOverlap" :min="0" :max="500" :step="50" show-input style="width: 100%" />
                </el-form-item>
              </el-collapse-item>
            </el-collapse>
            <el-button type="primary" :loading="uploading" @click="handleUpload" class="upload-btn">
              <el-icon><Upload /></el-icon>
              <span>{{ uploadMode === 'file' ? '上传文件到知识库' : '上传到知识库' }}</span>
            </el-button>
            <el-button v-if="uploadMode === 'text'" text @click="loadDemoData" class="demo-btn">
              <el-icon><MagicStick /></el-icon>
              <span>填充示例数据</span>
            </el-button>
          </el-form>
        </div>
      </aside>

      <!-- 右侧：文档列表 -->
      <main class="doc-panel">
        <div class="panel-header">
          <div class="panel-title">
            <el-icon :size="18"><FolderOpened /></el-icon>
            <span>文档列表</span>
            <el-tag size="small" round>{{ documents.length }}</el-tag>
          </div>
          <div class="panel-actions">
            <el-input
              v-model="searchQuery"
              placeholder="搜索文档..."
              :prefix-icon="Search"
              clearable
              size="small"
              style="width: 200px"
            />
            <el-button :icon="Refresh" @click="fetchDocuments" circle size="small" />
          </div>
        </div>
        <div class="panel-body">
          <div v-loading="loading" class="doc-list">
            <div
              v-for="doc in filteredDocs"
              :key="doc.doc_id"
              class="doc-card"
            >
              <div class="doc-icon">
                <el-icon :size="20"><Document /></el-icon>
              </div>
              <div class="doc-info">
                <div class="doc-title">{{ doc.title }}</div>
                <div class="doc-meta">
                  <el-tag size="small" type="info" effect="plain">{{ doc.chunk_count }} 切片</el-tag>
                  <span class="doc-id">{{ doc.doc_id }}</span>
                  <span class="doc-time">{{ formatTime(doc.created_at) }}</span>
                </div>
              </div>
              <div class="doc-actions">
                <el-tooltip content="查看内容" placement="top">
                  <el-button text size="small" @click="viewDoc(doc)">
                    <el-icon><View /></el-icon>
                  </el-button>
                </el-tooltip>
                <el-tooltip content="删除" placement="top">
                  <el-button text size="small" type="danger" @click="deleteDoc(doc.doc_id)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </el-tooltip>
              </div>
            </div>
            <el-empty v-if="!loading && filteredDocs.length === 0" description="暂无文档" :image-size="80" />
          </div>
        </div>
      </main>
    </div>

    <!-- 文档预览弹窗 -->
    <el-dialog v-model="previewVisible" title="文档预览" width="700px">
      <div v-if="previewDoc" class="preview-content">
        <h3>{{ previewDoc.title }}</h3>
        <div class="preview-meta">
          <el-tag size="small">{{ previewDoc.chunk_count }} 切片</el-tag>
          <span>创建时间: {{ formatTime(previewDoc.created_at) }}</span>
        </div>
        <el-divider />
        <div class="preview-text">{{ previewDoc.content || '无内容' }}</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import api from '../api/client'
import axios from 'axios'
import { useAuthStore } from '../stores/auth'

interface KBDocument {
  doc_id: string
  title: string
  content?: string
  chunk_count: number
  created_at: string
}

const uploadMode = ref<'text' | 'file'>('text')
const uploadForm = ref({
  kbId: 'default',
  title: '',
  content: '',
  chunkSize: 800,
  chunkOverlap: 100,
})
const uploading = ref(false)
const loading = ref(false)
const documents = ref<KBDocument[]>([])
const searchQuery = ref('')
const previewVisible = ref(false)
const previewDoc = ref<KBDocument | null>(null)
const selectedFile = ref<File | null>(null)
const uploadRef = ref()

const totalChunks = computed(() => documents.value.reduce((s, d) => s + d.chunk_count, 0))
const totalChars = computed(() => documents.value.reduce((s, d) => s + (d.content?.length || 0), 0))
const avgChunkSize = computed(() => totalChunks.value > 0 ? Math.round(totalChars.value / totalChunks.value) : 0)

const filteredDocs = computed(() => {
  if (!searchQuery.value) return documents.value
  const q = searchQuery.value.toLowerCase()
  return documents.value.filter(d =>
    d.title.toLowerCase().includes(q) || d.doc_id.toLowerCase().includes(q)
  )
})

async function fetchDocuments() {
  loading.value = true
  try {
    const res = await api.get<{ documents: KBDocument[] }>('/kb/documents', { params: { kb_id: uploadForm.value.kbId } })
    documents.value = res.documents || []
  } catch {
    documents.value = []
  } finally {
    loading.value = false
  }
}

async function handleUpload() {
  if (uploadMode.value === 'file') {
    await handleFileUpload()
  } else {
    await handleTextUpload()
  }
}

async function handleTextUpload() {
  if (!uploadForm.value.title || !uploadForm.value.content) {
    ElMessage.warning('请填写标题和内容')
    return
  }
  uploading.value = true
  try {
    await api.post('/kb/upload', {
      kb_id: uploadForm.value.kbId,
      title: uploadForm.value.title,
      content: uploadForm.value.content,
      chunk_size: uploadForm.value.chunkSize,
      chunk_overlap: uploadForm.value.chunkOverlap,
    })
    ElMessage.success('上传成功')
    uploadForm.value.title = ''
    uploadForm.value.content = ''
    fetchDocuments()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleFileUpload() {
  if (!selectedFile.value) {
    ElMessage.warning('请选择文件')
    return
  }
  uploading.value = true
  try {
    const authStore = useAuthStore()
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('kb_id', uploadForm.value.kbId)
    formData.append('title', uploadForm.value.title)
    formData.append('chunk_size', String(uploadForm.value.chunkSize))
    formData.append('chunk_overlap', String(uploadForm.value.chunkOverlap))
    const res = await axios.post('/api/kb/upload-file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        Authorization: `Bearer ${authStore.token}`,
      },
    })
    ElMessage.success(`上传成功：${res.data.chunk_count} 个切片`)
    uploadForm.value.title = ''
    selectedFile.value = null
    uploadRef.value?.clearFiles()
    fetchDocuments()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

function handleFileChange(file: any) {
  selectedFile.value = file.raw
}

function handleFileRemove() {
  selectedFile.value = null
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function deleteDoc(docId: string) {
  try {
    await ElMessageBox.confirm('确定删除该文档？此操作不可恢复。', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await api.delete(`/kb/documents/${docId}`, { params: { kb_id: uploadForm.value.kbId } })
    ElMessage.success('删除成功')
    fetchDocuments()
  } catch {}
}

async function viewDoc(doc: KBDocument) {
  try {
    const res = await api.get<{ content: string; title: string; chunk_count: number; created_at: string }>(
      `/kb/documents/${doc.doc_id}`,
      { params: { kb_id: uploadForm.value.kbId } }
    )
    previewDoc.value = {
      doc_id: doc.doc_id,
      title: res.title || doc.title,
      content: res.content || '',
      chunk_count: res.chunk_count ?? doc.chunk_count,
      created_at: res.created_at || doc.created_at,
    }
  } catch {
    previewDoc.value = doc
  }
  previewVisible.value = true
}

function loadDemoData() {
  uploadForm.value.title = '车险理赔流程'
  uploadForm.value.content = `车险理赔流程：

1. 事故报案：发生事故后，投保人应立即向保险公司报案，说明事故发生的时间、地点、原因及损失情况。报案方式包括电话报案、线上报案等。

2. 现场勘查：保险公司会派专员到事故现场进行勘查，了解事故原因和损失情况。勘查人员会拍照取证，记录事故细节。

3. 定损核价：保险公司根据勘查结果，确定损失金额。定损过程中，保险公司会与修理厂确认维修方案和费用。

4. 提交材料：投保人需提交相关证明材料，包括行驶证、驾驶证、事故责任书、维修发票等。

5. 赔付结算：保险公司审核通过后，将赔款支付到投保人指定账户。赔付时效一般为5-15个工作日。

注意事项：
- 报案时效：事故发生后48小时内报案，逾期可能影响理赔。
- 免赔额：根据保险条款，部分情况需扣除免赔额。
- 拒赔情形：酒驾、无证驾驶、故意制造事故等属于拒赔范围。`
  ElMessage.info('示例数据已填入')
}

function formatTime(iso: string) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return iso
  }
}

onMounted(fetchDocuments)
</script>

<style scoped>
.kb-page {
  height: 100%;
}

/* === 统计卡片 === */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  background: #fff;
  border-radius: 14px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.03);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
  line-height: 1.2;
}

.stat-label {
  font-size: 13px;
  color: #8c8c9a;
  margin-top: 2px;
}

/* === 主内容区 === */
.kb-content {
  display: flex;
  gap: 16px;
  height: calc(100vh - 260px);
}

/* === 上传面板 === */
.upload-panel {
  width: 400px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f5;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.upload-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: #4a4a5e;
  font-size: 13px;
}

.char-counter {
  text-align: right;
  font-size: 12px;
  color: #b0b0bc;
  margin-top: 4px;
}

.advanced-settings {
  margin-bottom: 16px;
  border: none;
}

.advanced-settings :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: #8c8c9a;
  border-bottom: 1px solid #f0f0f5;
}

.advanced-settings :deep(.el-collapse-item__wrap) {
  border: none;
}

.upload-btn {
  width: 100%;
  border-radius: 10px;
  height: 40px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  font-weight: 500;
  margin-bottom: 8px;
}

.upload-btn:hover {
  opacity: 0.9;
}

.demo-btn {
  width: 100%;
  color: #8c8c9a;
}

/* === 文档列表面板 === */
.doc-panel {
  flex: 1;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.doc-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0;
}

.doc-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid #f0f0f5;
  transition: all 0.2s;
  cursor: default;
}

.doc-card:hover {
  border-color: #667eea;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.03) 0%, rgba(118, 75, 162, 0.03) 100%);
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.1);
}

.doc-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #f0f0f5 0%, #e8e8ef 100%);
  color: #667eea;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.doc-card:hover .doc-icon {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
  font-size: 12px;
  color: #b0b0bc;
}

.doc-id {
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 11px;
}

.doc-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

/* === 预览弹窗 === */
.preview-content h3 {
  margin: 0 0 8px;
  color: #1a1a2e;
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #8c8c9a;
}

.preview-text {
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 14px;
  color: #4a4a5e;
  max-height: 400px;
  overflow-y: auto;
  padding: 12px;
  background: #f9f9fc;
  border-radius: 10px;
}
</style>