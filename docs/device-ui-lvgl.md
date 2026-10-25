# 设备端 LVGL UI（v2.0）

微雪 ESP32-S3-Touch-AMOLED-2.16 随身智能助手的界面层用 LVGL 9.2 重构，并完整对接 OmniAide 后端。

## 构建 / 烧录

```bash
bash scripts/build_device.sh smart_assistant compile          # 只编译
bash scripts/build_device.sh smart_assistant upload COM5      # 编译并烧录
```

- LVGL 9.2.3 随仓库内置在 `device/libraries/lvgl`（只保留 src，约 800 文件），
  构建脚本会把它和 `device/libraries/lv_conf.h` 同步到 `Documents/Arduino/libraries/`
  （arduino-cli 只搜索全局库目录）。
- 真实 WiFi / 后端账号不再写进 `config.h`：复制 `device/config.local.h.example`
  为 `device/config.local.h`（已 gitignore），或用设备「设置 → 配网」写入 NVS。
- 唤醒词使用 ESP-SR（WakeNet `Hi ESP`）。构建必须使用 `PartitionScheme=esp_sr_16`，
  并由 `device/partitions.csv` 提供 4MB app 分区 + 0xC10000 的 3.9MB 模型分区；
  构建脚本会关闭 MultiNet（只保留 WakeNet），避免 mn7 FST 崩溃。
- `device/libraries/ESP_SR` 是本地补丁版：detect/handler 任务固定到 core 0，
  让 LVGL 独占 core 1，避免界面被唤醒词检测拖慢。构建脚本会同步到 sketchbook。
- ESP-SR 占内部 RAM 较多。推荐设备使用内网 HTTP 后端
  （如 `OMNIAIDE_URL=http://192.168.2.10:8000`），这样保留 40 行 LVGL 绘制缓冲；
  远端 HTTPS 需要把 `ui.cpp` 的 draw buffer 降到约 10 行，否则 TLS 可能连接失败。
- 后端未部署 `/api/chat/voice/stream` 时，固件会自动回退到 `/api/chat/voice`。
- 中文字体用 `lv_font_conv` 从黑体生成（`device/font_cn20.c`，20px、ASCII+GB2312 一级汉字、
  2bpp 压缩，约 290KB flash）；时钟数字 `device/font_num92.c`（92px）。

## 线程模型

| 任务 | 核 | 职责 |
|------|----|------|
| `loopTask`（Arduino loop） | 1 | 状态机：录音、HTTP（语音/摘要/手势/完成待办）、电源键、NTP |
| `lvgl`（ui.cpp 内创建） | 1 | 持续 `lv_timer_handler()`，录音/上传阻塞时界面照常渲染 |
| `oa_events`（长轮询） | 0 | `GET /api/device/events` 25s 长轮询；只置事件标志，UI/提示音由 loopTask 执行 |
| `SR Feed/Detect/Handler`（ESP-SR） | 0 | 持续读 16k 麦克风；唤醒词事件只置 `wakeFlag`，录音前 `pause()`、播报时 `resume()`；补丁版固定 core 0，避免抢占 LVGL |

所有跨任务 UI 更新走 `ui.h` 公开接口，内部互斥锁保护；触摸点击回调运行在
LVGL 任务持锁上下文，只允许直接改控件 + 写请求队列（如待办完成）。

## 界面

- **状态栏**：电池条+百分比（充电呼吸动画）、后端连接点（OA）、WiFi 图标
- **三页横滑**（tileview，触摸滑动）：时钟 → 待办 → 对话
- **底部状态行**：状态机文案（按住 KEY3 说话 / 录音中 / 对话中 / 播报中 …）
- **待办页**：未完成待办（点圆圈直接勾掉 → 后端 `PUT /api/items/{id}`）+ 即将开始的日程
- **对话页**：用户问题深灰气泡 + 助手回答正文（最多保留 14 条），
  录音时底部音量条，等待 ASR/LLM/TTS 时转圈

## 后端对接（omniaide.h/cpp）

| 功能 | 接口 |
|------|------|
| 登录（90 天 token，401 自动重登） | `POST /api/device/auth` |
| 摘要轮询（60s 兜底：待办+日程） | `GET /api/device/brief` |
| 实时事件长轮询（通知/提醒/简报，25s） | `GET /api/device/events?since=&wait=` |
| 手势上报（MCP → Home Assistant） | `POST /api/device/gesture` |
| 语音问答（录音上传 → 回答+TTS WAV） | `POST /api/chat/voice` |
| 流式语音（NDJSON：识别/文本增量/base64 PCM，边生成边播报） | `POST /api/chat/voice/stream` |
| 完成待办（设备端新增能力） | `PUT /api/items/{id}` |
| 设备会话对话历史（登录后拉一次） | `GET /api/chat/history?session_id=smart-assistant` |

## 唤醒词 / 流式语音 / 打断

- 唤醒词：ESP-SR WakeNet9，当前模型为 **“Hi ESP”**。唤醒后自动进入录音。
- 自动录音：开口检测（VAD）+ 静音 850ms 自动结束，最长 10 秒。
- 流式语音：`/api/chat/voice/stream` 先做一次 ASR，随后 LLM 按句生成、TTS 按句返回
  base64 PCM；设备边收边播（24k→16k 重采样），首包音频明显早于整段合成。
- 打断：
  - 播报中说 “Hi ESP” → 立即停止播报并进入下一轮聆听；
  - 按住 KEY3 → 立即停止播报（不自动重录）。
  - 可通过 `config.h` 的 `VOICE_BARGE_IN` 关闭语音打断。

## 息屏

电源键短按息屏 = 低功耗（WiFi 关、CPU 80MHz、模拟电断、功放关）。
LVGL 保持运行，界面状态原样保留，亮屏只恢复背光，无重绘黑闪。
