<template>
  <router-view />
</template>

<style>
:root {
  --sidebar-width: 236px;
  --sidebar-collapsed-width: 68px;
  --header-height: 60px;

  --brand-50: #eef2ff;
  --brand-100: #e0e7ff;
  --brand-400: #818cf8;
  --brand-500: #4f46e5;
  --brand-600: #4338ca;

  --color-sidebar: #0e1629;
  --color-sidebar-hover: rgba(255, 255, 255, .06);
  --color-sidebar-active: rgba(99, 102, 241, .18);
  --color-sidebar-text: #94a3b8;
  --color-sidebar-active-text: #fff;
  --color-content-bg: #f4f6fb;
  --color-card-bg: #fff;
  --color-border: #e7ebf3;
  --color-text: #1f2937;
  --color-muted: #94a3b8;
  --radius-card: 14px;

  --el-color-primary: #4f46e5;
  --el-color-primary-light-3: #7c78ec;
  --el-color-primary-light-5: #a7a3f2;
  --el-color-primary-light-7: #cbc8f7;
  --el-color-primary-light-8: #dedcf9;
  --el-color-primary-light-9: #eeedfc;
  --el-color-primary-dark-2: #3f38b7;
  --el-border-radius-base: 8px;
  --el-font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans SC', Roboto, Arial, sans-serif;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }
body {
  font-family: var(--el-font-family);
  color: var(--color-text);
  background:
    radial-gradient(1200px 600px at 100% -10%, rgba(99, 102, 241, .10), transparent 60%),
    radial-gradient(900px 500px at -10% 0%, rgba(14, 165, 233, .07), transparent 55%),
    var(--color-content-bg);
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
a { text-decoration: none; color: inherit; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: #cfd6e4; border-radius: 999px;
  border: 2px solid transparent; background-clip: content-box;
}
::-webkit-scrollbar-thumb:hover { background: #b6c0d3; background-clip: content-box; }

.page-wrapper { padding: 22px 26px 34px; max-width: 1440px; margin: 0 auto; }
.page-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 18px;
}
.page-header h2 {
  font-size: 21px; font-weight: 650; letter-spacing: -.02em; color: #111827; margin: 0;
}
.page-header .sub,
.page-header .page-sub {
  margin: 5px 0 0; font-size: 12.5px; line-height: 1.6; color: var(--color-muted);
  max-width: 760px;
}
.page-card {
  background: var(--color-card-bg);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  box-shadow: 0 1px 2px rgba(16, 24, 40, .03), 0 18px 36px -30px rgba(16, 24, 40, .42);
  overflow: hidden;
  transition: box-shadow .2s ease;
}
.page-card:hover {
  box-shadow: 0 1px 2px rgba(16, 24, 40, .04), 0 22px 44px -32px rgba(16, 24, 40, .5);
}
.page-card-body { padding: 20px; }

/* ---- Element Plus refinements ---- */
.el-button { font-weight: 500; border-radius: 8px; }
.el-button--primary:not(.is-plain):not(.is-link):not(.is-text) {
  background-image: linear-gradient(135deg, #4f46e5, #6366f1);
  border-color: transparent;
  box-shadow: 0 8px 18px -12px rgba(79, 70, 229, .9);
}
.el-button--primary:not(.is-plain):not(.is-link):not(.is-text):hover {
  background-image: linear-gradient(135deg, #4338ca, #4f46e5);
}
.el-button.is-link { font-weight: 500; }

.el-input__wrapper,
.el-select__wrapper,
.el-textarea__inner {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e2e8f0 inset;
  transition: box-shadow .15s;
}
.el-input__wrapper:hover,
.el-select__wrapper:hover,
.el-textarea__inner:hover { box-shadow: 0 0 0 1px #c7d2fe inset; }
.el-input__wrapper.is-focus,
.el-select__wrapper.is-focused,
.el-textarea__inner:focus { box-shadow: 0 0 0 1px #6366f1 inset !important; }

.el-table {
  --el-table-border-color: #eef1f7;
  --el-table-header-bg-color: #f8fafc;
  --el-table-row-hover-bg-color: #f7f9ff;
  font-size: 13px;
}
.el-table th.el-table__cell {
  background: #f8fafc !important;
  color: #64748b; font-weight: 600; font-size: 12px;
}
.el-table .el-table__cell { padding: 10px 0; }

.el-tag { border-radius: 6px; }
.el-dialog { border-radius: 14px; overflow: hidden; }
.el-message-box { border-radius: 12px; }
.el-message { border-radius: 10px; }
.el-dropdown__popper.el-popper,
.el-select__popper.el-popper,
.el-popover.el-popper { border-radius: 10px; }
.el-popper.is-light { box-shadow: 0 16px 40px -20px rgba(16, 24, 40, .35); }
.el-tabs__item { font-weight: 500; }
.el-pagination { --el-pagination-button-bg-color: transparent; }
.el-drawer { border-radius: 14px 0 0 14px; }

@media (max-width: 768px) {
  :root { --header-height: 56px; }
  .page-wrapper { padding: 14px 14px 26px; }
  .page-header { margin-bottom: 14px; }
  .page-header h2 { font-size: 18px; }
  .page-card-body { padding: 14px; }
  .el-table { max-width: 100%; }
  .el-dialog { width: calc(100vw - 24px) !important; margin-top: 8vh !important; }
  .el-drawer { width: 100% !important; }
  .notification-menu { width: calc(100vw - 24px) !important; max-width: 360px; }
  .el-message { max-width: calc(100vw - 24px); }
  .el-form-item { flex-direction: column; align-items: flex-start; }
  .el-form-item__label { width: auto !important; padding: 0 0 4px !important; text-align: left !important; }
  .el-form-item__content { width: 100%; margin-left: 0 !important; }
  .el-tabs__nav-wrap { overflow-x: auto; }
}
</style>
