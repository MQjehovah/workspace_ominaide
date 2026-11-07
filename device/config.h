/**
 * config.h —— 智能助手（SmartAssistant）固件配置
 *
 * 安全约定：本文件不保存任何真实 WiFi / 账号 / API Key。
 * 真实配置放在 device/config.local.h（已被 .gitignore 忽略），或通过
 * 设备配网门户写入 NVS（推荐）。构建脚本会把 config.local.h 一起编译。
 */
#pragma once

// 本地私有配置（不入库）：复制 config.local.h.example -> config.local.h
#if __has_include("config.local.h")
#include "config.local.h"
#endif

// ==================== 设备 ====================
#define DEVICE_NAME     "SmartAssistant"   // 蓝牙配对时显示的名字
#define FW_VERSION      "2.5.0"            // 固件版本（设置页显示 + OTA 比对）

// TLS 证书校验：粘贴 CA 根证书（PEM）启用校验；留空跳过校验（内网/frp 场景）
#ifndef TLS_CA_CERT
#define TLS_CA_CERT     ""
#endif

// ==================== 联网与后端（出厂为空，首次用配网门户写入 NVS）====================
#ifndef WIFI_SSID
#define WIFI_SSID       ""
#endif
#ifndef WIFI_PASS
#define WIFI_PASS       ""
#endif
#ifndef OMNIAIDE_URL
#define OMNIAIDE_URL    ""
#endif
#ifndef OMNIAIDE_USER
#define OMNIAIDE_USER   ""
#endif
#ifndef OMNIAIDE_PASS
#define OMNIAIDE_PASS   ""
#endif

#define OA_BRIEF_PERIOD_MS (60UL * 1000)   // 摘要兜底轮询周期（实时事件走 /api/device/events）
#define OA_EVENT_LONGPOLL_S 25             // 设备事件长轮询等待秒数
#define GESTURE_ENABLE  1                  // 0=关闭手势识别（省电调试用）

// ==================== 语音交互 ====================
#define WAKE_WORD_ENABLE   1    // 1=启用 ESP-SR 唤醒词（"Hi ESP"）
#define VOICE_BARGE_IN     1    // 1=播报中允许唤醒词/按键打断
#define AUTO_RECORD_MAX_S  10   // 唤醒后最长录音秒数
#define AUTO_RECORD_SIL_MS 850  // 静音多久自动结束
#define WAKE_LISTEN_MS     5000 // 唤醒后等待开口的最长时间
#define VOICE_VAD_THRESH   420  // 语音起始峰值阈值
#define VOICE_SIL_THRESH   180  // 静音判定峰值阈值

// ==================== 音频 ====================
#define REC_RATE      16000    // 采样率：录音 16k（ASR 标准）
#define REC_MAX_S     15       // 单次最长录音秒数
#define REC_MIN_MS    400      // 短于此视为误触，丢弃
#define MIC_VOLUME    85       // ES8311 播放音量 0-100
#define TTS_MAX_BYTES (2UL * 1024 * 1024)   // TTS 返回 WAV 的下载上限

// ==================== 板载引脚（微雪 pin_config）====================
#define IIC_SDA        15
#define IIC_SCL        14
#define I2S_BCK_IO      9
#define I2S_WS_IO      45
#define I2S_DO_IO       8     // → ES8311（扬声器）
#define I2S_DI_IO      10     // ← ES7210（麦克风阵列）
#define I2S_MCK_IO     42
#define PIN_PA         46     // 功放使能
#define PIN_KEY_TALK   18     // KEY3：按住说话（问答模式，回答播报）
#define PIN_KEY_BOOT    0     // BOOT：按住说话（输入模式，文字打进电脑）
#define PIN_TP_INT     11     // 触摸中断
#define PIN_TP_RST     40     // 触摸复位

// ==================== 语音输入（BOOT 键）====================
#define INPUT_AUTO_COMMIT  1   // 拼音模式打完后补一个空格（触发输入法上屏）

// ==================== 屏 ====================
#define LCD_CS         12
#define LCD_SCLK       38
#define LCD_SDIO0       4
#define LCD_SDIO1       5
#define LCD_SDIO2       6
#define LCD_SDIO3       7
#define LCD_RESET      39
#define LCD_WIDTH     480
#define LCD_HEIGHT    480
