# 本地执行（local_shell）

Bot 默认在服务端执行所有工具。`local_shell` 让 Bot 把单条命令转发到用户自己的
桌面电脑执行，适合访问本机文件、`localhost`、局域网/VPN 资源和本机已安装的 CLI。

服务端不开放任何入站端口：桌面端主动连接 `/ws/host`，服务端通过这条 WebSocket
下发命令，桌面端执行并回传结果。

## 工具

| 工具 | 说明 |
|---|---|
| `list_local_devices` | 列出当前在线的桌面设备，返回 `device_id` 和主机名 |
| `local_shell` | 在指定桌面设备执行 shell 命令 |

`local_shell` 参数：

```json
{
  "command": "curl -s http://192.168.2.50/api",
  "cwd": "~/projects",
  "timeout_seconds": 60,
  "device_id": "可选；只有一台设备在线时可省略"
}
```

也支持用 `device` 按主机名选择，例如 `{"device": "MacBook-Pro"}`。多台设备在线
且没有指定设备时，工具会返回在线设备列表，Bot 应先调用 `list_local_devices`。

## 桌面端审批

本地命令有独立的审批策略，与服务端的 Bot 审批分开：

- **ask**（默认）：每条命令弹窗确认
- **always**：不再弹窗（可在弹窗中选择「始终允许」）
- **never**：拒绝所有本地命令

策略保存在桌面端配置 `localShellPolicy`：

```text
macOS（开发模式）
~/Library/Application Support/omniaide-desktop/omniaide-config/config.json

macOS（打包版）
~/Library/Application Support/OmniAide/omniaide-config/config.json
```

修改后重启桌面端生效。

## 安全

- 不开放入站端口，只使用桌面端主动建立的出站 WebSocket
- 命令默认逐条审批
- 输出上限：stdout 30k 字符，stderr 8k 字符
- 超时默认 600 秒，最大 3600 秒
- 桌面端继承自己的环境变量和 PATH
- 服务端工具调用会记录在活动日志中

## 限制

- 目前只支持 shell，不支持流式输出；长命令要等结束或超时后一次性返回
- 多设备只按 `device_id` / 主机名选择，没有默认设备记忆
- 桌面端必须保持运行并已登录
- 本地文件不会进入服务端备份
