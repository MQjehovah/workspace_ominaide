<template>
  <router-view />
</template>

<style>
:root {
  --sidebar-width: 240px;
  --sidebar-collapsed-width: 64px;
  --header-height: 56px;
  --color-sidebar: #1a1a2e;
  --color-sidebar-hover: #16213e;
  --color-sidebar-active: #0f3460;
  --color-sidebar-text: #a4a6b3;
  --color-sidebar-active-text: #fff;
  --color-content-bg: #f4f6f9;
  --color-card-bg: #fff;
  --color-border: #ebedf0;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: var(--color-content-bg); color: #333; }
a { text-decoration: none; color: inherit; }
.page-wrapper { padding: 20px 24px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { font-size: 20px; font-weight: 600; color: #1a1a2e; margin: 0; }
.page-card { background: var(--color-card-bg); border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.06); border: 1px solid var(--color-border); overflow: hidden; }
.page-card-body { padding: 20px; }
</style>
