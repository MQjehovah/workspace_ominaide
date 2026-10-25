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
- 中文字体用 `lv_font_conv` 从黑体生成（`device/font_cn20.c`，20px、ASCII+GB2312 一级汉字、
  2bpp 压缩，约 290KB flash）；时钟数字 `device/font_num92.c`（92px）。

## 线程模型

| 任务 | 核 | 职责 |
|------|----|------|
| `loopTask`（Arduino loop） | 1 | 状态机：录音、HTTP（语音/摘要/手势/完成待办）、电源键、NTP |
| `lvgl`（ui.cpp 内创建） | 1 | 持续 `lv_timer_handler()`，录音/上传阻塞时界面照常渲染 |

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
| 摘要轮询（60s：待办+日程） | `GET /api/device/brief` |
| 手势上报（MCP → Home Assistant） | `POST /api/device/gesture` |
| 语音问答（录音上传 → 回答+TTS WAV） | `POST /api/chat/voice` |
| 完成待办（设备端新增能力） | `PUT /api/items/{id}` |
| 设备会话对话历史（登录后拉一次） | `GET /api/chat/history?session_id=smart-assistant` |

## 息屏

电源键短按息屏 = 低功耗（WiFi 关、CPU 80MHz、模拟电断、功放关）。
LVGL 保持运行，界面状态原样保留，亮屏只恢复背光，无重绘黑闪。
