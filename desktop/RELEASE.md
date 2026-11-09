# 桌面端发布与自动更新

桌面端使用 `electron-updater` 的 generic provider，从后端静态目录检查、下载和安装更新。

## 更新地址

默认地址：

```text
https://mqgeek.com/ominaide/api/desktop/releases
```

桌面端会读取本机配置的 `serverUrl`，自动拼接：

```text
<serverUrl>/api/desktop/releases
```

后端接口：

- `GET /api/desktop/releases/latest`：发布文件列表
- `GET /api/desktop/releases/latest-mac.yml`：macOS 更新元数据
- `GET /api/desktop/releases/<filename>`：下载发布产物
- `POST /api/desktop/releases/upload`：上传发布产物（管理员）

生产文件目录：

```text
宿主机：/data/docker/omniaide/data/desktop-releases
容器内：/data/desktop-releases
```

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

3. 上传到后端，任选一种：

使用管理员 token：

```bash
cd desktop
OMNIAIDE_SERVER=https://mqgeek.com/ominaide \
OMNIAIDE_TOKEN=<admin-token> \
npm run publish:release
```

或直接拷贝：

```bash
scp release/*.dmg release/*.zip release/*.blockmap release/latest-mac.yml \
  jmq@192.168.2.10:/tmp/

ssh jmq@192.168.2.10
sudo cp /tmp/OmniAide-* /tmp/latest-mac.yml \
  /data/docker/omniaide/data/desktop-releases/
sudo chmod 644 /data/docker/omniaide/data/desktop-releases/*
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

## 注意事项

- macOS 自动更新要求新旧版本使用同一签名证书。
- 当前构建已签名，但未 notarize；分发到其他 Mac 时可能触发 Gatekeeper 提示。
- Windows 使用 `nsis` 安装包，构建时需在 Windows 或配置交叉编译环境。
