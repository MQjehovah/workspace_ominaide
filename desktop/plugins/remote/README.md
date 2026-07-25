# Remote Plugin

## TODO

- [ ] 主窗口拖拽（`-webkit-app-region: drag`）阻塞主进程，导致远程输入（键鼠）在拖拽期间卡顿。 
      主窗口在 `desktop/src/renderer/src/components/MainPanel.vue`，title bar 用的 native CSS drag。
      需要改为 JS 手动拖拽（类似 WebrtcAccept 的方案），或让 `remote:inject` 绕过主进程。
      目前 `@nut-tree-fork/nut-js` 是原生模块，无法在 preload（contextIsolation）中加载。
