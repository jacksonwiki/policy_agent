<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <div class="logo-icon">
          <el-icon :size="20"><Shield /></el-icon>
        </div>
        <span>保险智能助手</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="transparent"
        text-color="#ffffff99"
        active-text-color="#ffffff"
        class="side-menu"
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
          <span class="username">{{ authStore.username }}</span>
          <el-tag size="small" :type="authStore.role === 'admin' ? 'danger' : 'info'" effect="dark" round>
            {{ authStore.role === 'admin' ? '管理员' : '普通用户' }}
          </el-tag>
          <el-button size="small" round @click="handleLogout" class="logout-btn">
            <el-icon><SwitchButton /></el-icon>退出
          </el-button>
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
  background: #f0f2f8;
}

.aside {
  background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
  color: #fff;
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px 20px;
  color: #fff;
  font-size: 17px;
  font-weight: 600;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  letter-spacing: 0.5px;
}

.logo-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.side-menu {
  border-right: none;
  flex: 1;
  padding: 12px 8px;
}

.side-menu :deep(.el-menu-item) {
  border-radius: 10px;
  margin-bottom: 4px;
  height: 44px;
  line-height: 44px;
  padding-left: 14px !important;
  transition: all 0.2s;
}

.side-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.06) !important;
}

.side-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.35) 0%, rgba(118, 75, 162, 0.35) 100%) !important;
  color: #fff !important;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.side-menu :deep(.el-menu-item .el-icon) {
  margin-right: 10px;
  font-size: 16px;
}

.header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  border-bottom: 1px solid #eef0f5;
  padding: 0 24px;
  height: 60px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 14px;
}

.username {
  font-size: 14px;
  font-weight: 500;
  color: #1a1a2e;
}

.logout-btn {
  border-radius: 8px;
}

.main {
  background: #f0f2f8;
  padding: 20px;
  overflow-y: auto;
}
</style>
