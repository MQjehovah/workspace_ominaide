# 桌面端发布与自动更新

桌面端使用 `electron-updater` 的 generic provider，从后端静态目录检查、下载和安装更新。

## 更新地址

默认地址：

```text
https://mqgeek.com/ominaide/api/desktop/releases
```

桌面端会读取本机配置的 `serverUrl`，按平台自动拼接：

```text
macOS:   <serverUrl>/api/desktop/releases/mac
Windows: <serverUrl>/api/desktop/releases/windows
```

后端接口：

- `GET /api/desktop/releases/platforms`：各平台版本与文件
- `GET /api/desktop/releases/<platform>/latest`：平台发布详情
- `GET /api/desktop/releases/<platform>/latest-mac.yml`：macOS 更新元数据
- `GET /api/desktop/releases/<platform>/latest.yml`：Windows 更新元数据
- `GET /api/desktop/releases/<platform>/<filename>`：下载发布产物
- `POST /api/desktop/releases/upload?platform=mac|windows`：上传（管理员）
- `DELETE /api/desktop/releases/<platform>/<filename>`：删除（管理员）

生产文件目录：

```text
宿主机：/data/docker/omniaide/data/desktop-releases/{mac,windows,linux}
容器内：/data/desktop-releases/{mac,windows,linux}
```

Web 管理入口：管理 → 桌面端，包含「版本管理」和「插件管理」。

## 发布新版本

1. 更新 `desktop/package.json` 的 `version`。
2. 构建安装包：

```bash
cd desktop
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ \
ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/ \
npm run build
```

产物在 `desktop/release/`：

```text
OmniAide-<version>-arm64.dmg
OmniAide-<version>-arm64.dmg.blockmap
OmniAide-<version>-arm64-mac.zip
OmniAide-<version>-arm64-mac.zip.blockmap
latest-mac.yml
```

3. 上传到后端（Windows 使用 `--platform windows`），任选一种：

使用管理员 token：

```bash
cd desktop
OMNIAIDE_SERVER=https://mqgeek.com/ominaide \
OMNIAIDE_TOKEN=<admin-token> \
npm run publish:release -- --platform mac
```

或直接拷贝：

```bash
scp release/*.dmg release/*.zip release/*.blockmap release/latest-mac.yml \
  jmq@192.168.2.10:/tmp/

ssh jmq@192.168.2.10
sudo mkdir -p /data/docker/omniaide/data/desktop-releases/mac
sudo cp /tmp/OmniAide-* /tmp/latest-mac.yml \
  /data/docker/omniaide/data/desktop-releases/mac/
sudo chmod 644 /data/docker/omniaide/data/desktop-releases/mac/*
```

4. 验证：

```bash
curl https://mqgeek.com/ominaide/api/desktop/releases/latest-mac.yml
```

## 桌面端行为

- 启动 15 秒后自动检查更新。
- 用户菜单 →「检查更新」可手动检查。
- 发现新版本后弹窗提供「下载更新」。
- 下载完成后提供「重启并安装」。
- 开发模式下不执行更新。

## 内置插件

构建时会执行 `scripts/stage-plugins.mjs`，只把 AI 助理（`plugins/assistant`）放入
`plugin-bundle/`，electron-builder 再复制到应用资源目录 `Resources/plugins`。

- 新安装的桌面端只内置 AI 助理。
- 其余插件通过 Web「桌面端 → 插件管理」上传，桌面端从插件市场按需安装。
- 应用资源目录中的插件一律视为内置，不能卸载。
- 用户从插件市场安装的插件位于 userData，同名时会覆盖内置版本。

## 注意事项

- macOS 自动更新要求新旧版本使用同一签名证书。
- 当前构建已签名，但未 notarize；分发到其他 Mac 时可能触发 Gatekeeper 提示。
- Windows 使用 `nsis` 安装包，构建时需在 Windows 或配置交叉编译环境。
