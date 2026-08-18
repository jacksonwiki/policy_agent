<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <el-icon :size="24"><Shield /></el-icon>
        <span>保险智能助手</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#001529"
        text-color="#ffffffb3"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能对话</span>
        </el-menu-item>
        <el-menu-item index="/kb">
          <el-icon><Folder /></el-icon>
          <span>知识库管理</span>
        </el-menu-item>
        <el-menu-item index="/inspect">
          <el-icon><DataAnalysis /></el-icon>
          <span>RAG检查</span>
        </el-menu-item>
        <el-menu-item v-if="authStore.role === 'admin'" index="/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="user-info">
          <span>{{ authStore.username }}</span>
          <el-tag size="small" :type="authStore.role === 'admin' ? 'danger' : 'info'">
            {{ authStore.role === 'admin' ? '管理员' : '普通用户' }}
          </el-tag>
          <el-button size="small" @click="handleLogout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示')
    authStore.logout()
    router.push('/login')
  } catch {
    // cancelled
  }
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
}
.aside {
  background-color: #001529;
  color: #fff;
}
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  border-bottom: 1px solid #ffffff1a;
}
.aside .el-menu {
  border-right: none;
}
.header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 20px;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
}
.main {
  background: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
}
</style>
