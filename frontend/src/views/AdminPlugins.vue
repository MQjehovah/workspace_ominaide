<template>
  <div class="page-wrapper">
    <div class="page-header" style="margin-bottom:16px">
      <h2>插件市场</h2>
      <p style="color:#909399;font-size:13px;margin-top:4px">管理桌面端可安装的插件包</p>
    </div>
    <div class="page-card">
      <div class="page-card-body">
        <DesktopPluginMarket />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import DesktopPluginMarket from '@/components/DesktopPluginMarket.vue'
</script>
