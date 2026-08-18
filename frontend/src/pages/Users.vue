<template>
  <div class="users-page">
    <el-card>
      <template #header>
        <span>用户管理</span>
      </template>
      <el-table :data="users" v-loading="loading" stripe>
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="200" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button
              size="small"
              :disabled="row.username === 'admin'"
              @click="toggleRole(row)"
            >
              {{ row.role === 'admin' ? '降为普通用户' : '升为管理员' }}
            </el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="row.username === 'admin'"
              @click="deleteUser(row.username)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/client'

const users = ref<any[]>([])
const loading = ref(false)

async function fetchUsers() {
  loading.value = true
  try {
    const res = await api.get('/users')
    users.value = res.users || []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function toggleRole(username: string) {
  try {
    const user = users.value.find((u) => u.username === username)
    const newRole = user?.role === 'admin' ? 'user' : 'admin'
    await api.put(`/users/${username}/role`, { role: newRole })
    ElMessage.success('更新成功')
    fetchUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '更新失败')
  }
}

async function deleteUser(username: string) {
  try {
    await ElMessageBox.confirm(`确定删除用户 ${username}？`, '提示')
    await api.delete(`/users/${username}`)
    ElMessage.success('删除成功')
    fetchUsers()
  } catch {
    // cancelled
  }
}

onMounted(fetchUsers)
</script>

<style scoped>
.users-page {
  max-width: 1000px;
}
</style>
