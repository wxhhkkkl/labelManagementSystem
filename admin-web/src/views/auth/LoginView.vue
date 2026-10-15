<template>
  <main class="login-page">
    <section class="login-story">
      <div class="brand"><span class="brand-mark">L</span><div>标签管理系统<small>LABEL MANAGEMENT</small></div></div>
      <div class="login-copy"><span class="login-kicker">让每一个码都有迹可循</span><h1>统一管理标签<br>连接每一次打印</h1><p>从码导入、公司分配到工位打印，<br>在一个工作空间内完成管理与追溯。</p><div class="workflow"><span>码导入</span><span>→</span><span>码分配</span><span>→</span><span>工位打印</span></div></div>
      <p class="story-footer">标签管理 · 工位协同 · 全程追溯</p>
    </section>
    <section class="login-form-area">
      <div class="login-card">
      <span class="login-badge">管理后台</span>
      <h2>欢迎回来</h2>
      <p class="subtitle">请使用管理员账号登录</p>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="账号">
          <el-input v-model="username" autocomplete="username" placeholder="请输入账号" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" autocomplete="current-password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="error" />
        <el-button type="primary" native-type="submit" :loading="loading" class="submit">登录</el-button>
      </el-form>
      <p class="login-help">账号由总部管理员统一分配</p>
      </div>
      <p class="login-copyright">标签管理系统 · 管理后台</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../../api/auth'
import { ApiError, setToken } from '../../api/client'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  if (loading.value) return
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  try {
    const result = await login(username.value.trim(), password.value)
    setToken(result.access_token)
    const redirect = route.query.redirect
    const destination = typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//') && router.resolve(redirect).name !== 'login'
      ? redirect : '/org'
    await router.replace(destination)
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '无法连接服务，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height:100vh; display:flex; background:#fff; }
.login-story { width:52%; padding:44px 7%; background:linear-gradient(140deg,#123f9c,#2563eb); color:#fff; display:flex; flex-direction:column; }
.login-story .brand small { color:#b9d0ff; }
.login-story .brand-mark { background:#ffffff22; }
.login-copy { margin:auto 0; padding:64px 0; }
.login-kicker { display:inline-block; padding:5px 11px; border-radius:5px; color:#dbe8ff; background:#ffffff17; font-size:12px; }
h1 { font-size:clamp(28px,3.1vw,44px); line-height:1.5; letter-spacing:-1px; margin:24px 0 18px; }
.login-copy p { color:#cbddff; font-size:14px; line-height:1.9; }
.workflow { display:flex; flex-wrap:wrap; gap:16px; margin-top:36px; font-size:13px; }
.story-footer { color:#b9d0ff; font-size:11px; }
.login-form-area { flex:1; min-width:0; display:flex; flex-direction:column; padding:44px; }
.login-card { width:100%; max-width:360px; margin:auto; padding:40px 0; }
.login-badge { display:inline-block; background:var(--lms-soft); color:var(--lms-blue); padding:5px 10px; border-radius:6px; font-size:12px; }
h2 { font-size:30px; margin:20px 0 7px; }
.subtitle { color:var(--lms-muted); margin:0 0 32px; }
.error { margin-bottom:16px; }
.submit { width:100%; height:46px; margin-top:8px; }
.login-help,.login-copyright { color:var(--lms-muted); font-size:12px; text-align:center; }
.login-help { margin-top:18px; }
:deep(.el-input__wrapper) { min-height:44px; }
@media(max-width:640px) { .login-page { flex-direction:column; } .login-story { width:100%; padding:24px; } .login-copy { padding:20px 0 4px; } h1 { font-size:28px; margin:16px 0; } .workflow,.story-footer { display:none; } .login-form-area { padding:20px 24px; } .login-card { padding:20px 0; } }
</style>
