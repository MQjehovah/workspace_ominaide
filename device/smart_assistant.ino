/**
 * ============================================================================
 *  SmartAssistant · 微雪 ESP32-S3-Touch-AMOLED-2.16 随身智能助手（LVGL v2.0）
 * ============================================================================
 *  核心：按住 KEY3 或说 Hi ESP → ES7210 麦克风录音(16k) → 上传后端 /api/chat/voice
 *        → 服务端 agent(记忆+MCP工具+TTS) → ES8311 扬声器播报
 *  界面：LVGL 9.2。独立 lvgl 任务持续渲染（录音/HTTP 阻塞时界面不卡），
 *        三页横滑（时钟 / 待办 / 对话），状态栏（电池/WiFi/后端连接）+ 底部状态行
 *  后端：登录(90d token) / 摘要轮询(60s，待办可点圈勾掉) / 手势上报(MCP→HA)
 *        / 语音问答 / 设备会话对话历史
 *
 *  WiFi / 后端账号在 config.h 里填；未配置时屏幕提示，不会死等。
 *  依赖：ArduinoJson + ESP_I2S + 本目录 es7210/es8311 驱动
 *        + libraries/ 内 lvgl/SensorLib/XPowersLib/GFX
 * ============================================================================
 */
#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <time.h>
#include <sys/time.h>
#include <esp_heap_caps.h>
#include <Preferences.h>
#include "portal.h"
#include "ESP_I2S.h"
#include "ESP_SR.h"
#include "Arduino_GFX_Library.h"
#include "config.h"
#include "audio_hal.h"
#include "es7210.h"
#include "es8311.h"
#include "TouchDrvCSTXXX.hpp"
#include "omniaide.h"
#include "imu.h"
#include "SensorPCF85063.hpp"
#include "ui.h"
#define XPOWERS_CHIP_AXP2101   // 必须在 XPowersLib.h 之前
#include "XPowersLib.h"

// ============================================================================
// 屏
// ============================================================================
static Arduino_DataBus* s_bus = nullptr;
static Arduino_CO5300*  s_gfx = nullptr;

bool screenInit() {
    s_bus = new Arduino_ESP32QSPI(LCD_CS, LCD_SCLK, LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3);
    s_gfx = new Arduino_CO5300(s_bus, LCD_RESET, 0, LCD_WIDTH, LCD_HEIGHT, 0, 0, 0, 0);
    if (!s_gfx->begin()) return false;
    s_gfx->setBrightness(150);
    s_bus->writeC8D8(0x36, 0xA0);
    s_gfx->fillScreen(RGB565_BLACK);
    return true;
}

// ============================================================================
// 全局
// ============================================================================
I2SClass i2s;
es8311_handle_t es8311 = nullptr;

uint8_t* recBuf = nullptr;     // PSRAM：录音 PCM（16bit 单声道）
size_t   recLen = 0;           // 字节数
int      recPeak = 0;          // 最近一次录音的采样峰值（电平诊断）
uint8_t* ttsBuf = nullptr;     // PSRAM：TTS 返回的 WAV
char*    respBuf = nullptr;    // PSRAM：HTTP 文本响应
const size_t RESP_MAX = 24 * 1024;

enum State : uint8_t { ST_BOOT, ST_NO_WIFI, ST_READY, ST_REC, ST_VOICE, ST_PLAY, ST_MUSIC, ST_ERR };
State state = ST_BOOT;
uint8_t recPin = PIN_KEY_TALK;   // 本次录音监听的按键

// ---- 外设全局（电源/时钟）----
XPowersPMU pmu;
bool pmuOk = false;
int  battPct = -1;          // -1 = 未接电池（USB 供电）
bool charging = false;
uint32_t tBatt = 0;

SensorPCF85063 rtc;
bool rtcOk = false;
bool rtcHadTime = false;

bool screenOn = true;           // 息屏状态（电源键短按切换）

// ---- OmniAide 对接 + 手势 ----
OmniAide oa;
OaBrief oaBrief;
ImuGesture imuG;
uint32_t tOaLogin = 0;
bool historyLoaded = false;         // 登录后拉一次设备会话历史

// ---- 连接配置（配网门户写入 NVS，config.h 为出厂默认）----
char cfgSsid[33] = WIFI_SSID;
char cfgWifiPass[65] = WIFI_PASS;
char cfgUrl[128] = OMNIAIDE_URL;
char cfgUser[48] = OMNIAIDE_USER;
char cfgPass[48] = OMNIAIDE_PASS;
bool portalMode = false;

// ---- 用户设置（NVS 持久化，设置页实时改）----
Preferences prefs;
bool g_audioOk = false;
int  setVolume = MIC_VOLUME;        // 0..100（es8311 播放音量）
int  setBright = 60;                // 10..100（背光百分比）
bool chimeOn = true;                // 通知到达提示音
OaChatMsg* oaHist = nullptr;        // PSRAM：历史条目缓冲
OaNotif* oaNotifs = nullptr;        // PSRAM：通知条目缓冲
int lastUnread = -1;                // 上次未读数（变了才重拉列表）

// ---- 实时事件（独立长轮询任务，避免阻塞录音/触摸）----
volatile int  evtLastId = 0;
volatile bool evtNewNotif = false;
volatile bool evtNewTimer = false;
volatile bool evtNewBriefing = false;
volatile int  evtBriefingId = 0;
volatile uint32_t evtTimerEnd = 0;          // millis() 到期时刻，0=无计时器
volatile char evtTimerLabel[48] = "计时器";

// ---- 唤醒词 / 语音打断 ----
bool srOk = false;
volatile bool wakeFlag = false;             // ESP-SR 检测到唤醒词
volatile bool voiceAbort = false;           // 播报中被按键/唤醒词打断
bool voiceDeltaShown = false;               // 本轮是否已显示“语音生成中”

// ---- 设备音乐 ----
volatile bool musicActive = false;
volatile bool musicStop = false;
volatile bool musicNext = false;
volatile int  musicCmd = 0;                 // 1=play 2=stop 3=next
volatile int  musicPlaylistId = 0;
OaTrack* musicTracks = nullptr;
bool musicPcmLogged = false;
bool musicWriteLogged = false;

// ============================================================================
// 音频
// ============================================================================
// 按《微雪例程》的完整初始化序列把 ES8311 配到目标采样率（不是只改频率寄存器）
static bool es8311ToRate(uint32_t rate) {
    if (!es8311) return false;
    es8311_clock_config_t clk = {};
    clk.mclk_inverted = false;
    clk.sclk_inverted = false;
    clk.mclk_from_mclk_pin = true;
    clk.mclk_frequency = rate * 256;
    clk.sample_frequency = rate;
    if (es8311_init(es8311, &clk, ES8311_RESOLUTION_16, ES8311_RESOLUTION_16) != ESP_OK) {
        Serial.printf("[ES8311] init @%lu FAILED\n", (unsigned long)rate);
        return false;
    }
    es8311_sample_frequency_config(es8311, rate * 256, rate);
    es8311_voice_volume_set(es8311, setVolume, NULL);
    es8311_voice_mute(es8311, false);      // 显式解静音
    return true;
}

static bool audioInit() {
    i2s.setPins(I2S_BCK_IO, I2S_WS_IO, I2S_DO_IO, I2S_DI_IO, I2S_MCK_IO);
    if (!i2s.begin(I2S_MODE_STD, REC_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
        Serial.println("[I2S] begin FAILED");
        return false;
    }
    // ES7210 麦克风阵列：手持近讲增益（MIC1/2 27dB；3/4 远场 37.5dB）
    audio_hal_codec_config_t cfg = {
        .adc_input = AUDIO_HAL_ADC_INPUT_ALL,
        .codec_mode = AUDIO_HAL_CODEC_MODE_ENCODE,
        .i2s_iface = {
            .mode = AUDIO_HAL_MODE_SLAVE,
            .fmt = AUDIO_HAL_I2S_NORMAL,
            .samples = AUDIO_HAL_16K_SAMPLES,
            .bits = AUDIO_HAL_BIT_LENGTH_16BITS,
        },
    };
    uint32_t rv = es7210_adc_init(&Wire, &cfg);
    rv |= es7210_adc_config_i2s(cfg.codec_mode, &cfg.i2s_iface);
    rv |= es7210_adc_set_gain((es7210_input_mics_t)(ES7210_INPUT_MIC1 | ES7210_INPUT_MIC2), (es7210_gain_value_t)GAIN_27DB);
    rv |= es7210_adc_set_gain((es7210_input_mics_t)(ES7210_INPUT_MIC3 | ES7210_INPUT_MIC4), (es7210_gain_value_t)GAIN_37_5DB);
    rv |= es7210_adc_ctrl_state(cfg.codec_mode, AUDIO_HAL_CTRL_START);
    Serial.printf("[ES7210] init 0x%02x\n", (unsigned)rv);

    // ES8311 扬声器
    es8311 = es8311_create(0, ES8311_ADDRRES_0);
    if (!es8311) { Serial.println("[ES8311] create FAILED"); return false; }
    if (!es8311ToRate(REC_RATE)) return false;
    pinMode(PIN_PA, OUTPUT);
    digitalWrite(PIN_PA, HIGH);       // 功放常开（与微雪例程一致，播放后不关）
    Serial.println("[ES8311] ready");
    g_audioOk = true;
    return true;
}

// 开机自检音：500Hz 正弦 1 秒。听到"哔"= 编解码器+功放链路正常
static void beepTest() {
    digitalWrite(PIN_PA, HIGH);
    const int N = 64;
    int16_t tone_[N];
    for (int i = 0; i < N; i++)
        tone_[i] = (int16_t)(9000 * sinf(2 * PI * i * 500.0f / 16000.0f));
    int16_t st[N * 2];
    for (int i = 0; i < N; i++) { st[2 * i] = tone_[i]; st[2 * i + 1] = tone_[i]; }
    for (int r = 0; r < 250; r++) i2s.write((uint8_t*)st, sizeof(st));   // ~1s
}

// 通知到达提示音：880Hz→1320Hz 两短音
static void playChime() {
    if (!g_audioOk) return;
    const int RATE = REC_RATE;
    const int HALF = RATE * 90 / 1000;              // 每音 90ms
    static int16_t st[2 * RATE * 90 / 1000];
    for (int h = 0; h < 2; h++) {
        float f = h == 0 ? 880.0f : 1320.0f;
        for (int i = 0; i < HALF; i++) {
            int16_t v = (int16_t)(7000 * sinf(2 * PI * f * i / RATE) * (1.0f - (float)i / HALF));
            st[2 * i] = v; st[2 * i + 1] = v;
        }
        i2s.write((uint8_t*)st, HALF * 4);
    }
}

// ---- ESP-SR 唤醒词（Hi ESP）----
static void srPause() {
    if (srOk) ESP_SR.pause();
}

static volatile uint32_t gWakeMuteUntil = 0;

static void srResume() {
    if (srOk) {
        // TTS 尾音/回声可能误触发唤醒词，恢复后先静默 1.2 秒。
        gWakeMuteUntil = millis() + 1200;
        ESP_SR.setMode(SR_MODE_WAKEWORD);
        ESP_SR.resume();
    }
}

static void onSrEvent(sr_event_t event, int command_id, int phrase_id) {
    if (event == SR_EVENT_WAKEWORD || event == SR_EVENT_WAKEWORD_CHANNEL) {
        // 立体声会同时产生 WAKEWORD + WAKEWORD_CHANNEL；加去抖避免一次唤醒
        // 触发两轮对话。
        if (millis() < gWakeMuteUntil) return;
        static uint32_t lastWake = 0;
        if (millis() - lastWake < 2000) return;
        lastWake = millis();
        wakeFlag = true;
        Serial.println("[SR] WAKEWORD");
    } else if (event == SR_EVENT_TIMEOUT) {
        srResume();
    }
}

static bool srInit() {
#if WAKE_WORD_ENABLE
    ESP_SR.onEvent(onSrEvent);
    // MultiNet is compiled out; only WakeNet ("Hi ESP") is used.
    srOk = ESP_SR.begin(i2s, nullptr, 0, SR_CHANNELS_STEREO, SR_MODE_WAKEWORD, "MM");
    Serial.printf("[SR] %s\n", srOk ? "wakeword ready (Hi ESP)" : "init FAILED");
    Serial.flush();
    return srOk;
#else
    return false;
#endif
}

// 单声道 16k 录音到 PSRAM；返回是否有效
static bool recordOnce() {
    static const size_t CHUNK = 4096;                       // 立体声帧块
    static uint8_t chunk[CHUNK];
    recLen = 0;
    recPeak = 0;
    int peak = 0;                                           // 采样峰值，用于电平诊断
    uint32_t t0 = millis();
    srPause();
    ui::recShow(true);
    while (digitalRead(PIN_KEY_TALK) == LOW) {
        size_t n = i2s.readBytes((char*)chunk, CHUNK);
        if (n) {
            int16_t* s = (int16_t*)chunk;
            int chunkPeak = 0;
            for (size_t i = 0; i + 1 < n / 2; i += 2) {     // 立体声→单声道：左右混合
                if (recLen + 2 > REC_MAX_S * REC_RATE * 2) goto full;
                int32_t v = ((int32_t)s[i] + s[i + 1]) >> 1;
                int16_t m = (int16_t)constrain(v, -32768, 32767);
                int a = abs(m);
                if (a > chunkPeak) chunkPeak = a;
                memcpy(recBuf + recLen, &m, 2);
                recLen += 2;
            }
            if (chunkPeak > peak) peak = chunkPeak;
            // 音量条 + 计时（约 8Hz，够顺滑又不抢锁）
            static uint32_t tUi = 0;
            if (millis() - tUi > 120) {
                tUi = millis();
                ui::recUpdate(chunkPeak, (millis() - t0) / 1000);
            }
        }
        if (millis() - t0 > REC_MAX_S * 1000) break;
    }
full:
    ui::recShow(false);
    recPeak = peak;
    uint32_t dur = millis() - t0;
    Serial.printf("[REC] %lums %u B peak=%d/32767 (%.1fdB)\n",
                  dur, (unsigned)recLen, peak, peak ? 20 * log10f(peak / 32767.0f) : -99.0f);
    return dur >= REC_MIN_MS && recLen > REC_RATE;          // >0.5 秒音频
}

// ---- 流式 PCM 播放：24k→16k 重采样，播报中可被唤醒词/按键打断 ----
static double pcmFrac = 0.0;
static int16_t pcmPrev = 0;
static bool pcmHave = false;

static void playPcmReset() {
    pcmFrac = 0.0;
    pcmPrev = 0;
    pcmHave = false;
}

static bool bargeRequested() {
#if VOICE_BARGE_IN
    if (digitalRead(PIN_KEY_TALK) == LOW) {
        voiceAbort = true;
        return true;
    }
    if (wakeFlag) {
        voiceAbort = true;
        return true;
    }
#endif
    return false;
}

// Audio playback runs in loopTask; temporarily raise its priority above LVGL
// so I2S writes are not preempted mid-buffer (LVGL still runs when write blocks).
struct PlaybackPrioGuard {
    UBaseType_t old;
    PlaybackPrioGuard() {
        TaskHandle_t h = xTaskGetCurrentTaskHandle();
        old = uxTaskPriorityGet(h);
        vTaskPrioritySet(h, 5);
    }
    ~PlaybackPrioGuard() {
        vTaskPrioritySet(xTaskGetCurrentTaskHandle(), old);
    }
};

static bool playPcm16k(const uint8_t* data, size_t len, uint32_t rate) {
    PlaybackPrioGuard prio;
    if (!g_audioOk) return true;
    if (bargeRequested()) return false;
    if (!rate) rate = 16000;
    const int16_t* in = (const int16_t*)data;
    size_t n = len / 2;
    static int16_t st[1024];
    size_t o = 0;

    if (rate == REC_RATE) {
        for (size_t i = 0; i < n; i++) {
            st[o++] = in[i];
            st[o++] = in[i];
            if (o >= 1024) {
                i2s.write((uint8_t*)st, o * 2);
                o = 0;
                if (bargeRequested()) return false;
            }
        }
        if (o) i2s.write((uint8_t*)st, o * 2);
        return true;
    }

    // 输入 24k -> 输出 16k：每个输出样本对应 1.5 个输入样本。
    double step = (double)rate / (double)REC_RATE;
    for (size_t i = 0; i < n; i++) {
        int16_t s = in[i];
        if (!pcmHave) { pcmPrev = s; pcmHave = true; continue; }
        while (pcmFrac < 1.0) {
            int16_t v = (int16_t)((double)pcmPrev + (double)(s - pcmPrev) * pcmFrac);
            st[o++] = v;
            st[o++] = v;
            if (o >= 1024) {
                i2s.write((uint8_t*)st, o * 2);
                o = 0;
                if (bargeRequested()) return false;
            }
            pcmFrac += step;
        }
        pcmFrac -= 1.0;
        pcmPrev = s;
    }
    if (o) i2s.write((uint8_t*)st, o * 2);
    return true;
}

// 唤醒后自动录音：开口检测 + 静音自动结束
static bool recordAuto() {
    if (!recBuf) return false;
    static const size_t CHUNK = 4096;
    static uint8_t chunk[CHUNK];
    recLen = 0;
    recPeak = 0;
    int peakAll = 0;
    uint32_t t0 = millis(), tLastVoice = 0, tUi = 0;
    bool speech = false;

    srPause();
    ui::recShow(true);
    ui::busy("我在听...");

    while (millis() - t0 < (uint32_t)AUTO_RECORD_MAX_S * 1000UL) {
        size_t n = i2s.readBytes((char*)chunk, CHUNK);
        if (!n) { delay(5); continue; }
        int16_t* s = (int16_t*)chunk;
        int chunkPeak = 0;
        for (size_t i = 0; i + 1 < n / 2; i += 2) {
            if (recLen + 2 > (size_t)REC_MAX_S * REC_RATE * 2) goto done;
            int32_t v = ((int32_t)s[i] + s[i + 1]) >> 1;
            int16_t m = (int16_t)constrain(v, -32768, 32767);
            int a = abs(m);
            if (a > chunkPeak) chunkPeak = a;
            memcpy(recBuf + recLen, &m, 2);
            recLen += 2;
        }
        if (chunkPeak > peakAll) peakAll = chunkPeak;
        if (chunkPeak >= VOICE_VAD_THRESH) {
            speech = true;
            tLastVoice = millis();
        }
        if (millis() - tUi > 120) {
            tUi = millis();
            ui::recUpdate(chunkPeak, (millis() - t0) / 1000);
        }
        if (!speech && millis() - t0 > WAKE_LISTEN_MS) break;
        if (speech && millis() - tLastVoice > AUTO_RECORD_SIL_MS) break;
        if (digitalRead(PIN_KEY_TALK) == LOW) break;
    }
done:
    ui::recShow(false);
    ui::busy(nullptr);
    recPeak = peakAll;
    Serial.printf("[AUTO REC] %lums %u B peak=%d speech=%d\n",
                  millis() - t0, (unsigned)recLen, peakAll, (int)speech);
    return speech && recLen > REC_RATE / 2;
}

static void playWav(uint32_t rate, const uint8_t* data, size_t len) {
    // ES8311 完整重配到 TTS 采样率，I2S 重开
    es8311ToRate(rate);
    i2s.end();
    if (!i2s.begin(I2S_MODE_STD, rate, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
        Serial.println("[PLAY] i2s.begin FAILED");
        return;
    }

    static const size_t CHUNK = 4096;
    static int16_t stereo[CHUNK];                            // 单声道→双声道
    size_t off = 0;
    uint32_t t0 = millis();
    while (off < len) {
        size_t n = min((len - off) / 2, (size_t)(CHUNK / 2));
        const int16_t* src = (const int16_t*)(data + off);
        for (size_t i = 0; i < n; i++) { stereo[2 * i] = src[i]; stereo[2 * i + 1] = src[i]; }
        i2s.write((uint8_t*)stereo, n * 4);
        off += n * 2;
    }
    Serial.printf("[PLAY] %.1fs done\n", (millis() - t0) / 1000.0f);
    delay(80);                                                // 尾音播完
    i2s.end();
    i2s.begin(I2S_MODE_STD, REC_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);
    es8311ToRate(REC_RATE);
}

// ============================================================================
// WiFi + NTP
// ============================================================================
bool wifiOk = false;
uint32_t tWifiRetry = 0;
bool ntpRequested = false, ntpSynced = false;
uint32_t tNtpStart = 0;

void wifiTick() {
    if (!screenOn) return;                 // 息屏低功耗期间射频已关，别碰
    bool up = (WiFi.status() == WL_CONNECTED);
    if (up != wifiOk) {
        wifiOk = up;
        if (up) Serial.printf("[WiFi] connected, IP=%s RSSI=%d\n",
                              WiFi.localIP().toString().c_str(), WiFi.RSSI());
        else    Serial.println("[WiFi] lost");
        int rssi = up ? WiFi.RSSI() : -100;
        ui::setWifi(up, rssi >= -60 ? 3 : (rssi >= -70 ? 2 : 1));
    }
    if (!wifiOk && strlen(cfgSsid) && millis() - tWifiRetry > 10000) {
        tWifiRetry = millis();
        WiFi.disconnect();
        WiFi.begin(cfgSsid, cfgWifiPass);
        Serial.println("[WiFi] retry...");
    }
}

// NTP 校时（成功后写回板载 RTC，掉电也走时）
void ntpTick() {
    if (!wifiOk || ntpSynced) return;
    if (!ntpRequested) {
        configTzTime("CST-8", "ntp.aliyun.com", "ntp.tencent.com");
        ntpRequested = true;
        tNtpStart = millis();
        Serial.println("[NTP] requesting ...");
        return;
    }
    struct tm ti;
    if (getLocalTime(&ti, 0) && (ti.tm_year + 1900) >= 2024) {
        ntpSynced = true;
        Serial.printf("[NTP] synced %04d-%02d-%02d %02d:%02d:%02d\n",
                      ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday,
                      ti.tm_hour, ti.tm_min, ti.tm_sec);
        if (rtcOk) {
            rtc.setDateTime(RTC_DateTime(ti));   // 存进 PCF85063，断电续走
            Serial.println("[RTC] time saved");
        }
    } else if (millis() - tNtpStart > 30000) {
        ntpRequested = false;                    // 30 秒没同步上，重来
    }
}

// ============================================================================
// 电源 / 时钟
// ============================================================================
void batteryTick() {
    if (millis() - tBatt < 5000) return;
    tBatt = millis();
    if (!pmuOk) return;
    if (pmu.isBatteryConnect()) {
        int p = pmu.getBatteryPercent();
        battPct = (p >= 0) ? p : battPct;
        charging = pmu.isCharging();
    } else {
        battPct = -1;
        charging = pmu.isCharging();
    }
    static int lastPct = -999;
    static bool lastChg = false;
    if (battPct != lastPct || charging != lastChg) {
        Serial.printf("[BATT] pct=%d chg=%d pmu=%d\n", battPct, (int)charging, (int)pmuOk);
        lastPct = battPct;
        lastChg = charging;
    }
    ui::setBattery(battPct, charging, pmuOk);
}

void clockInit() {
    setenv("TZ", "CST-8", 1);
    tzset();
    rtcOk = rtc.begin(Wire);
    if (!rtcOk) { Serial.println("[RTC] PCF85063 NOT found"); return; }
    RTC_DateTime dt = rtc.getDateTime();
    struct tm t = dt.toUnixTime();            // 字段是私有的，走公开的 toUnixTime()
    if ((t.tm_year + 1900) >= 2024) {         // RTC 里的时间是可信的 → 先顶上
        time_t e = mktime(&t);
        if (e > 0) {
            struct timeval tv = { e, 0 };
            settimeofday(&tv, nullptr);
            rtcHadTime = true;
            Serial.printf("[RTC] restored %04d-%02d-%02d %02d:%02d\n",
                          t.tm_year + 1900, t.tm_mon + 1, t.tm_mday, t.tm_hour, t.tm_min);
        }
    } else {
        Serial.println("[RTC] time invalid, waiting for NTP");
    }
}

// 时钟页每秒刷新（LVGL 只重绘脏区，代价极低）
uint32_t tClock = 0;
void clockTick() {
    if (!screenOn) return;
    if (millis() - tClock < 1000) return;
    tClock = millis();
    time_t now = time(nullptr);
    struct tm ti;
    localtime_r(&now, &ti);
    ui::setTime(ti);
}

// ============================================================================
// 状态机 UI 辅助
// ============================================================================
char lastStateLabel[64] = "按住 KEY3 或说 Hi ESP";
uint32_t lastStateColor = 0x4caf50;   // 绿

// 用 int 而非 State 作参数：Arduino 会把函数原型插到枚举声明之前，自定义类型会编译失败
void setState(int s, const char* label, uint16_t color) {
    state = (State)s;
    snprintf(lastStateLabel, sizeof(lastStateLabel), "%s", label);
    lastStateColor = color;
    ui::setState(label, color);
}

// ============================================================================
// OmniAide 对接
// ============================================================================
// 登录成功后拉一次设备会话的历史对话（对话页冷启动就有内容）
void loadChatHistory() {
    if (!oaHist) return;
    int cnt = 0;
    if (oa.fetchChatHistory(oaHist, 8, cnt) && cnt > 0) {
        ui::chatClear();
        for (int i = 0; i < cnt; i++) ui::chatAppend(oaHist[i].role, oaHist[i].content);
    }
}

void pushBriefToUi() {
    ui::Brief ub;
    ub.configured = oa.configured();
    ub.loggedIn = oa.loggedIn();
    snprintf(ub.serverTime, sizeof(ub.serverTime), "%s", oaBrief.serverTime);
    ub.weatherTemp = oaBrief.weatherTemp;
    ub.weatherCode = oaBrief.weatherCode;
    ub.todoCnt = oaBrief.todoCnt;
    for (int i = 0; i < oaBrief.todoCnt && i < 8; i++) {
        ub.todoId[i] = oaBrief.todoId[i];
        snprintf(ub.todoTitle[i], sizeof(ub.todoTitle[i]), "%s", oaBrief.todos[i]);
    }
    ub.eventCnt = oaBrief.eventCnt;
    for (int i = 0; i < oaBrief.eventCnt && i < 6; i++)
        snprintf(ub.events[i], sizeof(ub.events[i]), "%s", oaBrief.events[i]);
    ui::setBrief(ub);
}

// 设置页变更 → 写硬件 + NVS
void settingsTick() {
    ui::SettingReq r;
    if (!ui::popSettingReq(r)) return;
    if (r.vol >= 0) {
        setVolume = r.vol;
        if (es8311) es8311_voice_volume_set(es8311, setVolume, NULL);
        prefs.putInt("vol", setVolume);
    }
    if (r.bright >= 0) {
        setBright = r.bright;
        s_gfx->setBrightness(20 + setBright * 235 / 100);
        prefs.putInt("bright", setBright);
    }
    if (r.chime >= 0) {
        chimeOn = r.chime != 0;
        prefs.putBool("chime", chimeOn);
    }
    if (r.portal > 0) {
        prefs.putBool("portal", true);
        ui::setState("进入配网模式，重启 ...", 0xffd740);
        delay(1000);
        ESP.restart();
    }
    if (r.ota > 0) otaAction();
}

// ---- 固件 OTA：第一次点 = 检查，发现新版后再点 = 升级 ----
static int otaState = 0;

static void otaProgress(int pct, void*) {
    char l[24];
    snprintf(l, sizeof(l), "更新中 %d%%", pct);
    ui::setState(l, 0xffd740);
}

static void otaAction() {
    if (otaState == 0) {                       // 检查
        ui::setState("检查更新 ...", 0x00e5ff);
        OaFirmware fw;
        if (!oa.fetchFirmwareInfo(fw) || !fw.available) {
            ui::setState("后端未发布固件", 0xff5252);
            return;
        }
        if (strcmp(fw.version, FW_VERSION) == 0) {
            ui::setState("已是最新版本", 0x4caf50);
            return;
        }
        otaState = 1;
        char l[48];
        snprintf(l, sizeof(l), "发现 v%s，再点一次开始更新", fw.version);
        ui::setState(l, 0xffd740);
        return;
    }
    otaState = 0;                              // 升级
    ui::setState("下载固件 ...", 0xffd740);
    bool ok = oa.downloadFirmware(otaProgress);
    if (ok) {
        ui::setState("更新完成，重启 ...", 0x4caf50);
        delay(1200);
        ESP.restart();
    } else {
        ui::setState("更新失败", 0xff5252);
    }
}

// 通知：拉列表刷新（未读数由调用方管理）
void refreshNotifs() {
    if (!oaNotifs) return;
    int cnt = 0;
    if (oa.fetchNotifications(oaNotifs, 8, cnt)) ui::setNotifs((const ui::Notif*)oaNotifs, cnt);
}

// 设备实时事件：在 loopTask 里短轮询（不额外占 TLS/任务栈），只置标志。
static bool evtCursorInit = false;
static uint32_t tEvtPoll = 0;

static void pollDeviceEvents() {
    if (!wifiOk || !oa.loggedIn()) return;
    if (!evtCursorInit) {
        int cursor = 0;
        if (!oa.fetchEventCursor(cursor)) return;
        evtLastId = cursor;
        evtCursorInit = true;
    }
    if (millis() - tEvtPoll < 4000) return;
    tEvtPoll = millis();
    OaEvent evs[4];
    int cnt = 0;
    bool ok = oa.pollEvents(evs, 4, cnt, evtLastId);
    if (oa.lastEventId < evtLastId) {
        // Backend restarted: its in-memory event ids reset. Re-sync from 0
        // on the next poll instead of waiting until the new id catches up.
        evtLastId = 0;
    } else if (oa.lastEventId > evtLastId) {
        evtLastId = oa.lastEventId;
    }
    if (ok) {
        for (int i = 0; i < cnt; i++) {
            if (evs[i].id > evtLastId) evtLastId = evs[i].id;
            if (!strcmp(evs[i].type, "music_play")) {
                musicPlaylistId = evs[i].value;
                musicCmd = 1;
            } else if (!strcmp(evs[i].type, "music_control")) {
                if (!strcmp(evs[i].action, "stop")) musicStop = true;
                else if (!strcmp(evs[i].action, "next")) musicNext = true;
                else if (!strcmp(evs[i].action, "play")) musicCmd = 1;
            } else if (!strcmp(evs[i].type, "timer") && evs[i].value > 0) {
                snprintf((char*)evtTimerLabel, sizeof(evtTimerLabel), "%s",
                         evs[i].title[0] ? evs[i].title : "计时器");
                evtTimerEnd = millis() + (uint32_t)evs[i].value * 1000UL;
                evtNewTimer = true;
            } else if (!strcmp(evs[i].type, "briefing")) {
                evtNewBriefing = true;
                evtBriefingId = evs[i].id;
            } else if (!strcmp(evs[i].type, "notification") ||
                       !strcmp(evs[i].type, "reminder")) {
                evtNewNotif = true;
            }
            Serial.printf("[EVT] #%d %s %s\n", evs[i].id, evs[i].type, evs[i].title);
        }
    }
}

// 消息页点击已读 / 全部已读 → 主循环异步调后端后刷新
void uiNotifTick() {
    int id;
    bool dirty = false;
    if (ui::popNotifReadReq(id)) { oa.markNotifRead(id); dirty = true; }
    if (ui::popNotifReadAll())   { oa.markAllNotifsRead(); dirty = true; }
    if (dirty) {
        refreshNotifs();
        lastUnread = oa.fetchUnreadCount();
        ui::setUnread(lastUnread);
    }
}

// 待办页点圈勾掉 → 主循环异步调后端，成功后立即刷新摘要
void uiCompleteTick() {
    int id;
    if (!ui::popCompleteReq(id)) return;
    if (!oa.loggedIn() || oa.completeTodo(id) == false) return;
    oa.lastBriefMs = 0;    // 触发 oaTick 立刻重新拉摘要
}

// OmniAide tick：登录重试 + 摘要轮询 + 手势识别上报
uint32_t tGesture = 0;
void oaTick() {
    // Music owns I2S/network while playing; don't run TLS polling on the other
    // core. KEY3 stops and BOOT skips tracks locally.
    if (musicActive) return;
#if GESTURE_ENABLE
    if (!screenOn) return;
    if (millis() - tGesture >= 100) {
        tGesture = millis();
        const char* g = imuG.tick();
        if (g) {
            Serial.printf("[GESTURE] %s\n", g);
            char result[64];
            bool ok = oa.sendGesture(g, result, sizeof(result));
            ui::setState(result, ok ? 0x4caf50 : 0xffab40);   // 绿 / 橙
        }
    }
#endif
    if (!wifiOk || !oa.configured()) return;
    if (!oa.loggedIn()) {                                      // 登录重试（10s 节流）
        if (millis() - tOaLogin > 10000) {
            tOaLogin = millis();
            if (oa.login()) {
                ui::setOa(true);
                if (!historyLoaded) { historyLoaded = true; loadChatHistory(); }
                oa.fetchBrief(oaBrief);
                oa.fetchTodaySchedule(oaBrief);                // 全天日程覆盖 brief 的 3 条
                pushBriefToUi();
                refreshNotifs();
            }
        }
        return;
    }

    // 新通知/计时器事件短轮询（8s 节流，不额外占任务栈/TLS client）
    pollDeviceEvents();

    if (millis() - oa.lastBriefMs < OA_BRIEF_PERIOD_MS) return;
    if (oa.fetchBrief(oaBrief)) {
        oa.fetchTodaySchedule(oaBrief);
        pushBriefToUi();
    }
    // 未读数每轮都拉；列表只在数字变化时重拉（省 2/3 请求）
    int unread = oa.fetchUnreadCount();
    ui::setUnread(unread);
    if (unread > lastUnread && lastUnread >= 0 && unread > 0) {
        ui::setState("有新通知", 0xffd740);            // 黄
        if (chimeOn) playChime();
    }
    if (unread >= 0 && unread != lastUnread) refreshNotifs();
    lastUnread = unread;

    // RSS 资讯头条：5 分钟一轮
    static uint32_t tRss = 0;
    if (tRss == 0 || millis() - tRss > 5UL * 60 * 1000) {
        tRss = millis();
        OaHeadline hs[8];
        int cnt = 0;
        if (oa.fetchHeadlines(hs, 8, cnt)) ui::setHeadlines((const ui::Headline*)hs, cnt);
    }
}

// ============================================================================
// 电源管理
// ============================================================================
// 电源键短按：息屏/亮屏切换（长按 4s 是 PMU 硬件默认的关机，不冲突）
// 息屏 = 低功耗：WiFi 关 + CPU 降到 80MHz + 关模拟电源(编解码器/麦偏置) + 关功放
// LVGL 保持运行（息屏后界面状态原样保留，亮屏只恢复背光，无重绘黑闪）
bool audioDown = false;         // 息屏时模拟电源被关闭，唤醒后需重新初始化音频

void setScreenOn(bool on) {
    if (screenOn == on) return;
    if (!on && musicActive) {
        musicStop = true;              // first power press stops music; press again to sleep
        return;
    }
    screenOn = on;
    Serial.printf("[PWR] %s\n", on ? "亮屏" : "息屏(低功耗)");
    if (on) {
        setCpuFrequencyMhz(240);                        // 先回高频（WiFi 需要）
        s_gfx->setBrightness(150);
        if (audioDown) {                                // 模拟电源恢复后重建音频链路
            pmu.enableALDO3();
            delay(20);
            audioInit();
            audioDown = false;
            Serial.println("[PWR] audio re-init done");
        }
        digitalWrite(PIN_PA, HIGH);                     // audioInit 已置高，冗余保护
        srResume();                                     // 恢复唤醒词监听
        if (strlen(cfgSsid) && !wifiOk) {             // 唤醒回连网络（最多 6 秒）
            ui::setState("连接网络 ...", 0xffd740);        // 黄
            WiFi.mode(WIFI_STA);
            WiFi.begin(cfgSsid, cfgWifiPass);
            uint32_t t0 = millis();
            while (WiFi.status() != WL_CONNECTED && millis() - t0 < 6000) delay(100);
            Serial.println(WiFi.status() == WL_CONNECTED ? "[WiFi] reconnected" : "[WiFi] reconnect timeout");
            wifiTick();
            ui::setState(lastStateLabel, lastStateColor);
        }
    } else {
        // ---- 低功耗息屏 ----
        s_gfx->setBrightness(0);
        digitalWrite(PIN_PA, LOW);                      // 关功放
        if (WiFi.getMode() != WIFI_MODE_NULL) {              // 关射频（最大耗电源）
            WiFi.disconnect(true, true);
            WiFi.mode(WIFI_OFF);
            wifiOk = false;
            Serial.println("[PWR] WiFi off");
        }
        srPause();                                      // 先停唤醒词，再接关闭模拟电
        pmu.disableALDO3();                             // 关模拟电：双编解码器+麦克风偏置
        audioDown = true;
        setCpuFrequencyMhz(80);                         // 降频（LVGL 仍走时，界面保留）
        Serial.println("[PWR] A3V3 off, CPU 80MHz, standby");
    }
}

uint32_t tPwr = 0;
void powerKeyTick() {
    if (!pmuOk || millis() - tPwr < 100) return;
    tPwr = millis();
    pmu.getIrqStatus();
    if (pmu.isPekeyShortPressIrq()) setScreenOn(!screenOn);
    pmu.clearIrqStatus();                  // 清掉本次事件，避免重复触发
}

// ============================================================================
// 主状态机
// ============================================================================
static bool onVoiceEvent(const char* type, const char* text,
                         const uint8_t* pcm, size_t len,
                         uint32_t rate, void*) {
    if (!strcmp(type, "audio")) {
        // 播报期间保持 SR 暂停：避免 TTS 被自己的麦克风误唤醒，也减少 CPU 占用。
        if (state != ST_PLAY) {
            setState(ST_PLAY, "播报中 ...", 0x00e5ff);
            ui::busy("播报中 ...");
        }
        return playPcm16k(pcm, len, rate);
    }
    if (!strcmp(type, "delta")) {
        if (!voiceDeltaShown) {
            voiceDeltaShown = true;
            setState(ST_VOICE, "语音生成中 ...", 0xffd740);
            ui::busy("语音生成中 ...");
        }
        return true;
    }
    if (!strcmp(type, "status") && text && text[0]) {
        setState(ST_VOICE, text, 0xffd740);
        ui::busy(text);
    }
    return true;
}

void askFlow() {
    static char transcript[512], reply[1024];

    setState(ST_VOICE, "语音生成中 ...", 0xffd740);
    ui::busy("语音生成中 ...");
    voiceAbort = false;
    srPause();

    // Stable path: full WAV from /api/chat/voice. PCM streaming playback on
    // this codec still shows repeat/reverse artifacts, so keep it off for now.
    bool ok = oa.voiceAsk(recBuf, recLen, REC_RATE, ttsBuf, TTS_MAX_BYTES,
                          transcript, sizeof(transcript), reply, sizeof(reply))
              && (transcript[0] || reply[0]);
    if (ok && oa.voiceData > 0) {
        setState(ST_PLAY, "播报中 ...", 0x00e5ff);
        ui::busy("播报中 ...");
        playWav(oa.voiceRate, ttsBuf + oa.voiceOff, oa.voiceData);
    }
    ui::busy(nullptr);

    if (transcript[0]) ui::chatAppend("user", transcript);
    if (reply[0]) ui::chatAppend("assistant", reply);

    if (!ok && !transcript[0] && !reply[0]) {
        setState(ST_ERR, "对话失败", 0xff5252);
        delay(1200);
        setState(ST_READY, "按住 KEY3 或说 Hi ESP", 0x4caf50);
        delay(500);
        srResume();
        return;
    }
    setState(ST_READY, "按住 KEY3 或说 Hi ESP", 0x4caf50);
    delay(500);
    srResume();
}

void autoAskFlow() {
    setState(ST_REC, "我在听 ...", 0xff5252);
    if (!recordAuto()) {
        setState(ST_ERR, "没听到声音", 0xff5252);
        delay(1000);
        setState(ST_READY, "按住 KEY3 或说 Hi ESP", 0x4caf50);
        delay(500);
        srResume();
        return;
    }
    askFlow();
}

// ============================================================================
// 设备音乐
// ============================================================================
static void musicPcmCb(const uint8_t* pcm, size_t len, void*) {
    if (!musicPcmLogged) {
        musicPcmLogged = true;
        Serial.printf("[MUSIC] pcm cb first len=%u\n", (unsigned)len);
    }
    const int16_t* in = (const int16_t*)pcm;
    size_t n = len / 2;
    static int16_t st[1024];
    size_t o = 0;
    for (size_t i = 0; i < n; i++) {
        int16_t s = in[i];
        st[o++] = s;
        st[o++] = s;
        if (o >= 1024) {
            size_t w = i2s.write((uint8_t*)st, o * 2);
            if (!musicWriteLogged && w != o * 2) {
                musicWriteLogged = true;
                Serial.printf("[MUSIC] i2s.write %u/%u\n", (unsigned)w, (unsigned)(o * 2));
            }
            o = 0;
            if (musicStop || musicNext) return;
        }
    }
    if (o) i2s.write((uint8_t*)st, o * 2);
}

static void playMusic() {
    musicActive = true;
    musicStop = false;
    musicNext = false;
    musicPcmLogged = false;
    musicWriteLogged = false;
    setState(ST_MUSIC, "音乐加载中 ...", 0x00e5ff);
    ui::busy("音乐加载中 ...");

    // Free ESP-SR internal RAM for HTTPS while music plays.
    ESP_SR.end();
    srOk = false;

    if (!musicTracks)
        musicTracks = (OaTrack*)heap_caps_malloc(sizeof(OaTrack) * 32, MALLOC_CAP_SPIRAM);
    int cnt = 0;
    bool ok = musicTracks && oa.fetchMusicTracks(musicPlaylistId, musicTracks, 32, cnt);
    Serial.printf("[MUSIC] fetch ok=%d cnt=%d mem=%u\n", ok, cnt, (unsigned)ESP.getFreeHeap());
    if (!ok || cnt == 0) {
        setState(ST_MUSIC, "没有音乐文件", 0xff5252);
        delay(1500);
        goto cleanup;
    }

    // Re-assert 16k on both I2S and ES8311. TTS playback may have left the
    // codec at 24k, which makes 16k music sound wrong.
    digitalWrite(PIN_PA, HIGH);
    es8311ToRate(REC_RATE);
    i2s.end();
    i2s.begin(I2S_MODE_STD, REC_RATE, I2S_DATA_BIT_WIDTH_16BIT,
              I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);

    for (int i = 0; i < cnt; i++) {
        if (musicStop || musicCmd == 2) break;
        char label[64];
        snprintf(label, sizeof(label), "♪ %s", musicTracks[i].name);
        Serial.printf("[MUSIC] track %d id=%d %s\n", i, musicTracks[i].id, musicTracks[i].name);
        setState(ST_MUSIC, label, 0x00e5ff);
        musicNext = false;
        oa.streamMusic(musicTracks[i].id, musicPcmCb, nullptr, &musicStop, &musicNext);
        if (musicStop || musicCmd == 2) break;
        musicCmd = 0;
    }

cleanup:
    musicActive = false;
    musicStop = false;
    musicNext = false;
    musicCmd = 0;
    musicPlaylistId = 0;
    oa.resetHttp();
    srInit();
    ui::busy(nullptr);
    setState(ST_READY, "按住 KEY3 或说 Hi ESP", 0x4caf50);
}

static void briefingTick() {
    if (!evtNewBriefing) return;
    if (!screenOn) setScreenOn(true);
    if (state != ST_READY || musicActive) return;

    evtNewBriefing = false;
    char title[64], body[1024];
    int notifId = 0;
    if (!oa.fetchLatestBriefing(title, sizeof(title), body, sizeof(body), notifId)) {
        Serial.println("[BRIEF] no briefing fetched");
        return;
    }

    Serial.printf("[BRIEF] %s (%u chars)\n", title, (unsigned)strlen(body));
    srPause();
    setState(ST_VOICE, "晨间简报 ...", 0xffd740);
    ui::busy("正在生成简报语音 ...");

    uint32_t rate = 24000;
    size_t off = 0, dlen = 0;
    bool ok = oa.speakText(body, ttsBuf, TTS_MAX_BYTES, rate, off, dlen);
    if (ok) {
        ui::chatAppend("assistant", body);
        setState(ST_PLAY, "播报简报 ...", 0x00e5ff);
        ui::busy("播报简报 ...");
        playWav(rate, ttsBuf + off, dlen);
    } else {
        Serial.println("[BRIEF] TTS failed");
        setState(ST_ERR, "简报语音失败", 0xff5252);
    }

    ui::busy(nullptr);
    setState(ST_READY, "按住 KEY3 或说 Hi ESP", 0x4caf50);
    delay(500);
    srResume();
}

static void musicTask(void*) {
    for (;;) {
        if (musicCmd == 1 && !musicActive) {
            musicCmd = 0;
            playMusic();
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.println("\n=== SmartAssistant · ESP32-S3-Touch-AMOLED-2.16 (LVGL) ===");

    Wire.begin(IIC_SDA, IIC_SCL);
    Wire.setClock(400000);

    // 用户设置（NVS）
    prefs.begin("sa", false);
    setVolume = prefs.getInt("vol", MIC_VOLUME);
    setBright = prefs.getInt("bright", 60);
    chimeOn = prefs.getBool("chime", true);
    strncpy(cfgSsid, prefs.getString("wssid", WIFI_SSID).c_str(), sizeof(cfgSsid) - 1);
    strncpy(cfgWifiPass, prefs.getString("wpass", WIFI_PASS).c_str(), sizeof(cfgWifiPass) - 1);
    strncpy(cfgUrl, prefs.getString("ourl", OMNIAIDE_URL).c_str(), sizeof(cfgUrl) - 1);
    strncpy(cfgUser, prefs.getString("ouser", OMNIAIDE_USER).c_str(), sizeof(cfgUser) - 1);
    strncpy(cfgPass, prefs.getString("opass", OMNIAIDE_PASS).c_str(), sizeof(cfgPass) - 1);
    portalMode = prefs.getBool("portal", false);
    prefs.putBool("portal", false);       // 读走即清（防崩溃循环）

    // 屏 + 触摸 → LVGL（开机画面立即可见）
    screenInit();
    s_gfx->setBrightness(20 + setBright * 235 / 100);
    static TouchDrvCST92xx touchObj;
    bool tpOk = false;
    touchObj.setPins(PIN_TP_RST, PIN_TP_INT);
    tpOk = touchObj.begin(Wire, CST92XX_SLAVE_ADDRESS, IIC_SDA, IIC_SCL);
    if (tpOk) {
        touchObj.setMaxCoordinates(LCD_WIDTH, LCD_HEIGHT);
        touchObj.setSwapXY(true);
        touchObj.setMirrorXY(true, false);
        Serial.printf("[TP] %s ok\n", touchObj.getModelName());
    } else {
        Serial.println("[TP] CST9220 NOT found");
    }
    ui::init(s_gfx, &touchObj, LCD_WIDTH, LCD_HEIGHT);
    ui::setSettingRefs(setVolume, setBright, chimeOn);
    pinMode(PIN_KEY_TALK, INPUT_PULLUP);

    // 配网模式：热点 + 门户页，保存后自动重启，不走正常流程
    if (portalMode) {
        ui::showPortal("SmartAssistant-Setup");
        startPortal(prefs);
        return;
    }
    oa.setEndpoint(cfgUrl, cfgUser, cfgPass);

    // 时间：先吃 RTC 里的时间（掉电走时），联网后再被 NTP 纠正
    clockInit();

    // 电源管理（冷启动偶发首读 NACK，重试）
    for (int i = 0; i < 5 && !pmuOk; i++) {
        pmuOk = pmu.begin(Wire, AXP2101_SLAVE_ADDRESS, IIC_SDA, IIC_SCL);
        if (!pmuOk) { Serial.printf("[PMU] retry %d...\n", i + 1); delay(60); }
    }
    Serial.println(pmuOk ? "[PMU] AXP2101 ok" : "[PMU] AXP2101 NOT found");
    if (pmuOk) {
        // 充电配置：500mAh 电芯按 ~0.8C 充，VBUS 输入限流放宽到 1A（充电慢的主因之一）
        pmu.setChargeTargetVoltage(XPOWERS_AXP2101_CHG_VOL_4V2);
        pmu.setChargerConstantCurr(XPOWERS_AXP2101_CHG_CUR_400MA);
        pmu.setVbusCurrentLimit(XPOWERS_AXP2101_VBUS_CUR_LIM_1000MA);
        pmu.enableIRQ(XPOWERS_AXP2101_PKEY_SHORT_IRQ);   // 电源键短按事件
        pmu.clearIrqStatus();
        Serial.printf("[PMU] 充电配置: 目标4.2V 恒流400mA VBUS限1A\n");
    }
    tBatt = 0;
    batteryTick();
    ui::setBattery(battPct, charging, pmuOk);   // PMU 缺失时也要把状态栏置成 USB/PMU! 显示

    // PSRAM 大缓冲
    recBuf = (uint8_t*)heap_caps_malloc((size_t)REC_MAX_S * REC_RATE * 2, MALLOC_CAP_SPIRAM);
    ttsBuf = (uint8_t*)heap_caps_malloc(TTS_MAX_BYTES, MALLOC_CAP_SPIRAM);   // 2MB，复用
    respBuf = (char*)heap_caps_malloc(RESP_MAX, MALLOC_CAP_SPIRAM);
    oaHist = (OaChatMsg*)heap_caps_malloc(sizeof(OaChatMsg) * 8, MALLOC_CAP_SPIRAM);
    oaNotifs = (OaNotif*)heap_caps_malloc(sizeof(OaNotif) * 8, MALLOC_CAP_SPIRAM);
    if (!recBuf || !respBuf) Serial.println("[PSRAM] alloc FAILED!");

    // 音频
    bool audioOk = audioInit();
    if (!audioOk) { Serial.println("[AUDIO] init FAILED"); setState(ST_ERR, "音频初始化失败", 0xff5252); }
    else {
        beepTest();                            // 开机自检音：听到"哔"= 扬声器链路正常
        Serial.println("[AUDIO] ok");

        srInit();                              // 唤醒词（Hi ESP）
        Serial.printf("[MEM] free=%u max=%u psram=%u\n",
                      ESP.getFreeHeap(), ESP.getMaxAllocHeap(), ESP.getFreePsram());
    }

    // WiFi
    if (strlen(cfgSsid)) {
        WiFi.mode(WIFI_STA);
        WiFi.begin(cfgSsid, cfgWifiPass);
    } else {
        Serial.println(">>> 未配置 WiFi：设置页 → 配网模式 <<<");
    }

    // 六轴手势（OmniAide → Home Assistant）
#if GESTURE_ENABLE
    if (imuG.begin()) Serial.println("[IMU] QMI8658 + gestures ok");
    else              Serial.println("[IMU] QMI8658 NOT found (gestures off)");
#endif

    setState(ST_READY, strlen(cfgSsid) ? "按住 KEY3 或说 Hi ESP" : "未配置网络", 0x4caf50);
    ui::bootDone();                            // 撤开机画面 → 时钟/待办/对话三页

    // Music player task (core 0; ESP-SR is stopped while music plays).
    xTaskCreatePinnedToCore(musicTask, "music", 10240, nullptr, 1, nullptr, 0);

    Serial.println("=== 就绪：按住 KEY3 或说 Hi ESP，松开发问 ===");
}

void loop() {
    if (portalMode) {
        portalTick();
        // 按住 KEY3 三秒 = 放弃配网，直接重启回正常模式
        static uint32_t tKey = 0;
        if (digitalRead(PIN_KEY_TALK) == LOW) {
            if (tKey == 0) tKey = millis();
            else if (millis() - tKey > 3000) { Serial.println("[PORTAL] exit"); ESP.restart(); }
        } else tKey = 0;
        delay(10);
        return;
    }
    wifiTick();
    ntpTick();
    batteryTick();
    clockTick();
    powerKeyTick();
    oaTick();
    briefingTick();

    // Music controls: KEY3 = stop, BOOT = next track.
    if (musicActive) {
        if (digitalRead(PIN_KEY_TALK) == LOW) musicStop = true;
        if (digitalRead(PIN_KEY_BOOT) == LOW) musicNext = true;
    }

    // 计时器开始 / 到期（本地倒计时，断网也能走完）
    if (evtNewTimer) {
        evtNewTimer = false;
        char l[64];
        snprintf(l, sizeof(l), "计时开始 · %s", (const char*)evtTimerLabel);
        ui::setState(l, 0x00e5ff);
    }
    if (evtTimerEnd && (int32_t)(millis() - evtTimerEnd) >= 0) {
        evtTimerEnd = 0;
        char l[64];
        snprintf(l, sizeof(l), "计时结束 · %s", (const char*)evtTimerLabel);
        ui::setState(l, 0xff5252);
        if (state == ST_READY) {
            for (int i = 0; i < 2; i++) { playChime(); delay(120); }
        }
    }

    // 实时事件到达：刷新通知、提示音；空闲时自动切到消息页
    if (evtNewNotif) {
        evtNewNotif = false;
        refreshNotifs();
        lastUnread = oa.fetchUnreadCount();
        ui::setUnread(lastUnread);
        ui::setState("有新通知", 0xffd740);
        if (chimeOn) playChime();
        if (state == ST_READY) ui::showNotifPage();
    }

    uiCompleteTick();
    uiNotifTick();
    settingsTick();
    if (!screenOn && digitalRead(PIN_KEY_TALK) == LOW) setScreenOn(true);   // 按说话键顺手亮屏

    // 唤醒词：空闲时自动进入录音 → 流式对话
    if (wakeFlag && state == ST_READY && screenOn) {
        wakeFlag = false;
        autoAskFlow();
    }

    switch (state) {
    case ST_READY:
        if (digitalRead(PIN_KEY_TALK) == LOW) {
            if (!wifiOk) { setState(ST_ERR, "未连接网络", 0xff5252); }
            else if (recBuf) {
                setState(ST_REC, "录音中 0s", 0xff5252);
                        }
        }
        break;
    case ST_REC:
        if (!recordOnce()) {
            setState(ST_READY, "按住 KEY3 或说 Hi ESP", 0x4caf50);
            srResume();
        } else if (recPeak < 150) {                        // 近乎静音：提示而不是浪费 ASR
            setState(ST_ERR, "没听到声音", 0xff5252);
            delay(1500);
            setState(ST_READY, "按住 KEY3 或说 Hi ESP", 0x4caf50);
            srResume();
        } else {
            askFlow();
        }
        break;
    default:
        break;    // ASR/LLM/TTS/PLAY 在 askFlow 内同步执行
    }
}

