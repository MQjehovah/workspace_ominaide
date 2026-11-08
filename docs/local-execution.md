# 本地执行（local tools）

Bot 默认在服务端执行所有工具。Local tools 让 Bot 把单次操作转发到用户自己的
桌面电脑执行，适合访问本机文件、`localhost`、局域网/VPN 资源和本机已安装的 CLI。

服务端不开放任何入站端口：桌面端主动连接 `/ws/host`，服务端通过这条 WebSocket
下发请求，桌面端执行并回传结果。

## 工具

| 工具 | 说明 |
|---|---|
| `list_local_devices` | 列出当前在线的桌面设备，返回 `device_id` 和主机名 |
| `local_shell` | 在桌面设备执行 shell 命令 |
| `local_list_dir` | 列出本地目录 |
| `local_read_file` | 读取本地文本文件 |
| `local_write_file` | 创建或覆盖本地文本文件 |
| `local_grep` | 在本地目录搜索文本 |

所有工具都支持：

```json
{
  "device_id": "可选；只有一台设备在线时可省略",
  "device": "可选；按主机名选择"
}
```

多台设备在线且没有指定设备时，工具会返回在线设备列表；Bot 应先调用
`list_local_devices`。

### 路径

- 支持 `~` 和绝对路径
- 相对路径按用户主目录解析
- `local_read_file` 默认最多读取 200KB，最大 2MB；二进制文件只返回元信息
- `local_write_file` 默认不覆盖已有文件，需要 `overwrite=true`
- `local_grep` 会跳过 `.git`、`node_modules`、`.ssh`、`.env`、私钥等敏感路径

本地文件采用**就地读写**，不会默认复制到服务端 workspace，也不会进入
OmniAide 文件库。

### shell 示例

```json
{
  "command": "curl -s http://192.168.2.50/api",
  "cwd": "~/projects",
  "timeout_seconds": 60
}
```

## 桌面端审批

先启动桌面端并登录（首次需要安装依赖）：

```bash
cd desktop
npm ci
npm run dev
```

本地工具有独立的审批策略，与服务端的 Bot 审批分开：

- **ask**（默认）：每次操作弹窗确认
- **always**：不再弹窗（可在弹窗中选择「始终允许」）
- **never**：拒绝所有本地操作

策略保存在桌面端配置 `localToolPolicy`（旧版本兼容 `localShellPolicy`）：

```text
macOS（开发模式）
~/Library/Application Support/omniaide-desktop/omniaide-config/config.json

macOS（打包版）
~/Library/Application Support/OmniAide/omniaide-config/config.json
```

修改后重启桌面端生效。

## 安全

- 不开放入站端口，只使用桌面端主动建立的出站 WebSocket
- 每次操作默认审批，写入会显示内容预览
- 敏感文件名在审批弹窗中会额外提示
- shell 输出上限：stdout 30k 字符，stderr 8k 字符
- shell 超时默认 600 秒，最大 3600 秒
- grep 最多扫描 2000 个文件、单个文件 1MB、500 条结果
- 服务端工具调用会记录在活动日志中

## 限制

- shell 和文件操作都是一次性返回，不支持流式输出
- 多设备只按 `device_id` / 主机名选择，没有默认设备记忆
- 桌面端必须保持运行并已登录
- 本地文件不会进入服务端备份
