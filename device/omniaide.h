/**
 * omniaide.h —— OmniAide 后端客户端（设备端唯一云端出口）
 *
 * 能力：登录(90天token) / 聚合摘要(含天气) / 手势上报(MCP→HA) / 语音对话
 *       / 完成待办 / 对话历史 / 全天日程 / 通知中心 / RSS 头条 / 固件 OTA
 * 端点/账号由 setEndpoint 注入（NVS 配网优先，config.h 为默认），不再依赖宏。
 */
#pragma once
#include <Arduino.h>

struct OaBrief {
    int  todoId[8] = {0};
    char todos[8][64] = {};
    uint8_t todoCnt = 0;
    char events[6][64] = {};
    uint8_t eventCnt = 0;
    char serverTime[20] = "";
    int  weatherTemp = -999;    // ℃，-999 = 无天气
    int  weatherCode = -1;      // WMO 天气码
};

// 通知条目
struct OaNotif {
    int  id = 0;
    bool unread = false;
    char title[64] = "";
    char body[384] = "";
    char time[12] = "";     // "MM-DD HH:MM"
};

// RSS 头条（时钟页轮播）
struct OaHeadline {
    char title[96] = "";
    char feed[24] = "";
};

// 对话历史条目（设备会话 session_id=smart-assistant）
struct OaChatMsg {
    char role[12];
    char content[448];
};

// 固件版本信息
struct OaFirmware {
    bool available = false;
    char version[24] = "";
};

// 实时事件（长轮询）
struct OaEvent {
    int  id = 0;
    int  value = 0;       // 计时器：秒数
    char type[24] = "";
    char title[64] = "";
    char body[224] = "";
    char action[32] = "";
};

// 音乐曲目
struct OaTrack {
    int  id = 0;
    char name[64] = "";
};

// 音乐 PCM 回调（16bit mono 24k）
typedef void (*OaMusicPcmCb)(const uint8_t* pcm, size_t len, void* ud);

// OTA 进度回调（0..100）
typedef void (*OaProgressCb)(int pct, void* ud);

// 流式语音事件：type = transcript|delta|status|audio|done
// 返回 false 表示请求中断（例如播报被唤醒词/按键打断）
typedef bool (*OaVoiceEventCb)(const char* type, const char* text,
                               const uint8_t* pcm, size_t len,
                               uint32_t rate, void* ud);

class OmniAide {
public:
    void setEndpoint(const char* url, const char* user, const char* pass);
    bool configured() const;
    bool login();
    bool fetchBrief(OaBrief& out);
    bool sendGesture(const char* gesture, char* resultLabel, size_t labelMax);
    bool completeTodo(int todoId);                                  // 勾掉一条待办
    bool fetchChatHistory(OaChatMsg* msgs, int max, int& cnt);      // 设备会话最近对话
    bool fetchTodaySchedule(OaBrief& out);                          // 全天日程覆盖 out.events
    bool fetchNotifications(OaNotif* msgs, int max, int& cnt);      // 最新通知
    int  fetchUnreadCount();                                        // 未读数，-1 失败
    bool pollEvents(OaEvent* out, int max, int& cnt, int since);    // 实时事件长轮询（25s）
    bool fetchEventCursor(int& out);                                // 开机同步游标，避免重放旧通知
    bool markNotifRead(int id);                                     // 单条已读
    bool markAllNotifsRead();                                       // 全部已读
    bool fetchHeadlines(OaHeadline* out, int max, int& cnt);        // RSS 资讯头条
    bool fetchFirmwareInfo(OaFirmware& out);                        // OTA 版本检查
    bool downloadFirmware(OaProgressCb cb, void* ud = nullptr);     // OTA 流式下载写入

    // 语音对话：pcm(16bit 单声道 PCM) + sampleRate → 播报音频写入 wavBuf(调用方提供)
    bool voiceAsk(const uint8_t* pcm, size_t pcmLen, uint32_t sampleRate,
                  uint8_t* wavBuf, size_t wavCap,
                  char* transcript, size_t tMax, char* reply, size_t rMax);

    // 流式语音：ASR 一次，边生成边播报；音频通过回调按句子推送
    bool voiceAskStream(const uint8_t* pcm, size_t pcmLen, uint32_t sampleRate,
                        char* transcript, size_t tMax, char* reply, size_t rMax,
                        OaVoiceEventCb cb, void* ud = nullptr);

    // 设备音乐：拉取曲目 / 以 24k mono PCM 流式播放
    bool fetchMusicTracks(int playlistId, OaTrack* out, int max, int& cnt);
    bool streamMusic(int fileId, OaMusicPcmCb cb, void* ud,
                     volatile bool* stop, volatile bool* next);
    void resetHttp();       // 音乐/长连接结束后强制下次 HTTP 重新建连
    bool fetchLatestBriefing(char* title, size_t titleMax,
                             char* body, size_t bodyMax, int& notifId);
    bool speakText(const char* text, uint8_t* wavBuf, size_t wavCap,
                   uint32_t& rate, size_t& off, size_t& dataLen);

    bool loggedIn() const { return _ok; }
    uint32_t lastBriefMs = 0;
    int lastEventId = 0;        // 服务端事件游标（用于检测后端重启后序号回退）

    // 最近一次语音对话的音频（voiceAsk 成功后有效）
    uint32_t voiceRate = 16000;
    size_t   voiceOff = 0, voiceData = 0;

private:
    bool _ok = false;
    char _token[512] = "";
    char _url[128] = "";
    char _user[48] = "";
    char _pass[48] = "";
};
