<template>
  <div class="kb-page">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>上传文档到知识库</span>
          </template>
          <el-form :model="uploadForm" label-width="100px">
            <el-form-item label="知识库ID">
              <el-input v-model="uploadForm.kbId" placeholder="输入或选择知识库ID" />
            </el-form-item>
            <el-form-item label="文档标题">
              <el-input v-model="uploadForm.title" placeholder="文档标题" />
            </el-form-item>
            <el-form-item label="文档内容">
              <el-input
                v-model="uploadForm.content"
                type="textarea"
                :rows="8"
                placeholder="粘贴或输入文档内容..."
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="uploading" @click="handleUpload">
                上传文档
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>
            <span>知识库文档列表</span>
          </template>
          <div class="kb-list">
            <el-table :data="documents" v-loading="loading" stripe>
              <el-table-column prop="doc_id" label="文档ID" width="120" />
              <el-table-column prop="title" label="标题" />
              <el-table-column prop="chunk_count" label="切片数" width="80" />
              <el-table-column prop="created_at" label="创建时间" width="160" />
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button size="small" type="danger" @click="deleteDoc(row.doc_id)">
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <el-divider />
          <div class="kb-tips">
            <p><strong>快速测试：</strong></p>
            <el-button size="small" @click="loadDemoData">加载示例数据</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/client'

const uploadForm = ref({
  kbId: 'default',
  title: '',
  content: '',
})
const uploading = ref(false)
const loading = ref(false)
const documents = ref<any[]>([])

async function fetchDocuments() {
  loading.value = true
  try {
    const res = await api.get('/kb/documents', { params: { kb_id: uploadForm.value.kbId } })
    documents.value = res.documents || []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function handleUpload() {
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

async function deleteDoc(docId: string) {
  try {
    await ElMessageBox.confirm('确定删除该文档？', '提示')
    await api.delete(`/kb/documents/${docId}`)
    ElMessage.success('删除成功')
    fetchDocuments()
  } catch {
    // cancelled
  }
}

function loadDemoData() {
  uploadForm.value.kbId = 'default'
  uploadForm.value.title = '车险理赔流程'
  uploadForm.value.content = `车险理赔流程：
1. 事故报案：发生事故后，投保人应立即向保险公司报案，说明事故情况。
2. 现场勘查：保险公司会派专员到现场勘查，了解事故原因和损失情况。
3. 定损核价：保险公司根据勘查结果，确定损失金额。
4. 提交材料：投保人需提交相关证明材料，包括行驶证、驾驶证、事故责任书等。
5. 赔付结算：保险公司审核通过后，将赔款支付到投保人指定账户。`
  ElMessage.info('示例数据已填入，点击上传即可')
}

onMounted(fetchDocuments)
</script>

<style scoped>
.kb-page {
  max-width: 1200px;
}
.kb-list {
  min-height: 300px;
}
.kb-tips {
  color: #909399;
  font-size: 13px;
}
</style>
