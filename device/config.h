/**
 * config.h —— 智能助手（SmartAssistant）固件配置
 *
 * 使用前填三样：WIFI_SSID / WIFI_PASS / ZAI_API_KEY（智谱 bigmodel 的 API Key，
 * https://open.bigmodel.cn → 右上角控制台 → API Keys）
 */
#pragma once

// ==================== 设备 ====================
#define DEVICE_NAME     "SmartAssistant"   // 蓝牙配对时显示的名字
#define FW_VERSION      "2.1.0"            // 固件版本（设置页显示 + OTA 比对）

// TLS 证书校验：粘贴 CA 根证书（PEM）启用校验；留空跳过校验（内网/frp 场景）
#define TLS_CA_CERT     ""

// ==================== 联网与大模型服务 ====================
#define WIFI_SSID       "MQjehovah"    // ← 填 WiFi 名
#define WIFI_PASS       "Jmq88326"    // ← 填 WiFi 密码
#define ZAI_API_KEY     "14cdadce664540f9b8de5c3d1f3f02d6.aBmGHWpRR2TDZZSB"    // ← 填智谱 API Key（格式 xxx.xxx）

// ==================== OmniAide 后端对接（外网 HTTPS / 内网 http 均可）====================
#define OMNIAIDE_URL    "https://mqgeek.com/ominaide"   // 外网（frp→nginx→后端）；内网备用 "http://192.168.2.10:8000"
#define OMNIAIDE_USER   "admin"                         // OmniAide 应用账号（网页端登录用的）
#define OMNIAIDE_PASS   "Jmq88326"                      // 应用密码（登录一次换 90 天 token，不做明文存储外传）
#define OA_BRIEF_PERIOD_MS (60UL * 1000)   // 摘要轮询周期
#define GESTURE_ENABLE  1                  // 0=关闭手势识别（省电调试用）

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
