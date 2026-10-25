#include "omniaide.h"
#include "config.h"
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <esp_heap_caps.h>
#include <Update.h>
#include <WiFiClient.h>

static const char* TAG = "[OA]";

static WiFiClientSecure tlsClient;

// TLS 证书校验：config.h 里填 CA 根证书则校验，留空跳过（内网/frp 场景）
static void tlsConfig() {
    if (strlen(TLS_CA_CERT)) tlsClient.setCACert(TLS_CA_CERT);
    else                     tlsClient.setInsecure();
}

void OmniAide::setEndpoint(const char* url, const char* user, const char* pass) {
    snprintf(_url, sizeof(_url), "%s", url ? url : "");
    snprintf(_user, sizeof(_user), "%s", user ? user : "");
    snprintf(_pass, sizeof(_pass), "%s", pass ? pass : "");
    _ok = false;                       // 换端点后旧 token 作废
}

bool OmniAide::configured() const {
    return strlen(_url) && strlen(_user) && strlen(_pass);
}

// 写入 PSRAM 缓冲的 Stream（writeToStream 自动兼容 Content-Length 与 chunked）
class PsramBufStream : public Stream {
public:
    PsramBufStream(uint8_t* buf, size_t cap) : _b(buf), _cap(cap), _len(0) {}
    size_t length() const { return _len; }
    virtual int available() { return 0; }
    virtual int read() { return -1; }
    virtual int peek() { return -1; }
    virtual size_t write(uint8_t c) { if (_len < _cap) { _b[_len++] = c; return 1; } return 0; }
    virtual size_t write(const uint8_t* p, size_t n) {
        if (_len + n > _cap) n = (_cap > _len) ? _cap - _len : 0;
        memcpy(_b + _len, p, n); _len += n; return n;
    }
    using Print::write;
private:
    uint8_t* _b; size_t _cap, _len;
};

// 共享 PSRAM 大响应缓冲：loopTask 内串行复用，按需扩容
// （大缓冲绝不能放 loopTask 栈：8KB 栈要留足 TLS 握手深度，溢出会砸坏相邻堆块）
static char* bigScratch(size_t need) {
    static char* s = nullptr;
    static size_t cap = 0;
    if (cap < need) {
        if (s) heap_caps_free(s);
        s = (char*)heap_caps_malloc(need, MALLOC_CAP_SPIRAM);
        cap = s ? need : 0;
    }
    return s;
}

// 通用请求。method = GET/POST/PUT；body 仅 POST/PUT 时有效；token 可空
static int httpReq(const char* url, const char* method, const char* body,
                   const char* token, char* resp, size_t respMax) {
    HTTPClient http;
    http.setTimeout(8000);
    http.setConnectTimeout(5000);
    bool ok;
    if (strncmp(url, "https", 5) == 0) {
        tlsConfig();
        tlsClient.setTimeout(8000);
        ok = http.begin(tlsClient, url);
    } else {
        ok = http.begin(url);
    }
    if (!ok) return -1;
    if (token) http.addHeader("Authorization", (String("Bearer ") + token).c_str());
    int code;
    if (strcmp(method, "GET") == 0) {
        code = http.GET();
    } else {
        http.addHeader("Content-Type", "application/json");
        code = http.sendRequest(method, (uint8_t*)body, strlen(body));   // POST/PUT 通用
    }
    if (resp && code > 0) {
        String s = http.getString();
        size_t n = min(s.length(), respMax - 1);
        memcpy(resp, s.c_str(), n);
        resp[n] = 0;
    }
    http.end();
    return code;
}

bool OmniAide::login() {
    if (!configured()) return false;
    char req[192], resp[640];
    snprintf(req, sizeof(req), "{\"username\":\"%s\",\"password\":\"%s\"}",
             _user, _pass);
    String url = String(_url) + "/api/device/auth";
    int code = httpReq(url.c_str(), "POST", req, nullptr, resp, sizeof(resp));
    if (code != 200) {
        Serial.printf("%s login HTTP %d: %.160s\n", TAG, code, resp);
        _ok = false;
        return false;
    }
    JsonDocument doc;
    if (deserializeJson(doc, resp)) return false;
    snprintf(_token, sizeof(_token), "%s", doc["access_token"] | "");
    _ok = strlen(_token) > 20;
    Serial.printf("%s login ok (90d token)\n", TAG);
    return _ok;
}

bool OmniAide::fetchBrief(OaBrief& out) {
    if (!configured()) return false;
    char* resp = bigScratch(4096);
    if (!resp) return false;
    String url = String(_url) + "/api/device/brief";
    int code = httpReq(url.c_str(), "GET", "", _token, resp, 4096);
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url.c_str(), "GET", "", _token, resp, sizeof(resp));
    }
    if (code != 200) {
        Serial.printf("%s brief HTTP %d\n", TAG, code);
        return false;
    }
    JsonDocument doc;
    if (deserializeJson(doc, resp)) return false;

    out.todoCnt = 0; out.eventCnt = 0;
    snprintf(out.serverTime, sizeof(out.serverTime), "%s", doc["server_time"] | "");
    out.weatherTemp = doc["weather"]["temp"] | -999;
    out.weatherCode = doc["weather"]["code"] | -1;
    for (JsonVariant t : doc["todos"].as<JsonArray>()) {
        if (out.todoCnt >= 8) break;
        out.todoId[out.todoCnt] = t["id"] | 0;
        snprintf(out.todos[out.todoCnt], 64, "%s", t["title"] | "");
        out.todoCnt++;
    }
    for (JsonVariant e : doc["events"].as<JsonArray>()) {
        if (out.eventCnt >= 3) break;
        snprintf(out.events[out.eventCnt++], 64, "%s %s",
                 e["start"] | "", e["title"] | "");
    }
    lastBriefMs = millis();
    return true;
}

bool OmniAide::sendGesture(const char* gesture, char* resultLabel, size_t labelMax) {
    if (!configured()) { snprintf(resultLabel, labelMax, "后端未配置"); return false; }
    if (!_ok && !login()) { snprintf(resultLabel, labelMax, "登录失败"); return false; }

    char req[96], resp[320];
    snprintf(req, sizeof(req), "{\"gesture\":\"%s\"}", gesture);
    String url = String(_url) + "/api/device/gesture";
    int code = httpReq(url.c_str(), "POST", req, _token, resp, sizeof(resp));
    if (code == 401) {
        if (!login()) { snprintf(resultLabel, labelMax, "登录失败"); return false; }
        code = httpReq(url.c_str(), "POST", req, _token, resp, sizeof(resp));
    }
    if (code != 200) { snprintf(resultLabel, labelMax, "HTTP %d", code); return false; }

    JsonDocument doc;
    if (deserializeJson(doc, resp)) { snprintf(resultLabel, labelMax, "解析失败"); return false; }
    bool ok = doc["ok"] | false;
    const char* label = doc["label"] | gesture;
    const char* detail = doc["detail"] | "";
    snprintf(resultLabel, labelMax, "%s %s", ok ? "已执行:" : "失败:", ok ? label : detail);
    return ok;
}

// ---------------- 语音对话 ----------------

// PCM 前写 44 字节 WAV 头（16bit 单声道）
static size_t wavHeader(uint8_t* h, uint32_t sampleRate, uint32_t dataLen) {
    uint32_t fileLen = dataLen + 36;
    memcpy(h, "RIFF", 4); memcpy(h + 4, &fileLen, 4); memcpy(h + 8, "WAVE", 4);
    memcpy(h + 12, "fmt ", 4); uint32_t f16 = 16; memcpy(h + 16, &f16, 4);
    uint16_t pcm = 1, ch = 1; memcpy(h + 20, &pcm, 2); memcpy(h + 22, &ch, 2);
    memcpy(h + 24, &sampleRate, 4);
    uint32_t byteRate = sampleRate * 2; memcpy(h + 28, &byteRate, 4);
    uint16_t align = 2; memcpy(h + 32, &align, 2); uint16_t bits = 16; memcpy(h + 34, &bits, 2);
    memcpy(h + 36, "data", 4); memcpy(h + 40, &dataLen, 4);
    return 44;
}

// 解析 WAV data 块（智谱 TTS 的 WAV 带 ~250B AIGC 元数据块，扫描窗要深）
static bool wavParse(const uint8_t* buf, size_t bufLen, uint32_t& rate,
                     size_t& dataOff, size_t& dataLen) {
    if (bufLen < 64 || memcmp(buf, "RIFF", 4)) return false;
    rate = *(const uint32_t*)(buf + 24);
    dataOff = 0; dataLen = 0;
    for (size_t i = 12; i + 8 <= min(bufLen, (size_t)4096);) {
        uint32_t sz = *(const uint32_t*)(buf + i + 4);
        if (!memcmp(buf + i, "data", 4)) {
            dataOff = i + 8;
            dataLen = min((uint32_t)(bufLen - dataOff), sz);
            return rate >= 8000 && rate <= 96000 && dataLen > 0;
        }
        i += 8 + sz + (sz & 1);
    }
    return false;
}

// URL 解码（X-Transcript / X-Reply 头，UTF-8 percent-encoding）
static void urlDecode(const char* in, char* out, size_t outMax) {
    size_t o = 0;
    for (const char* p = in; *p && o + 4 < outMax; p++) {
        if (*p == '%' && p[1] && p[2]) {
            auto hex = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                return -1;
            };
            int h = hex(p[1]), l = hex(p[2]);
            if (h >= 0 && l >= 0) { out[o++] = (char)((h << 4) | l); p += 2; continue; }
        }
        out[o++] = (*p == '+') ? ' ' : *p;
    }
    out[o] = 0;
}

bool OmniAide::voiceAsk(const uint8_t* pcm, size_t pcmLen, uint32_t sampleRate,
                        uint8_t* wavBuf, size_t wavCap,
                        char* transcript, size_t tMax, char* reply, size_t rMax) {
    transcript[0] = reply[0] = 0;
    if (!configured()) return false;
    if (!_ok && !login()) return false;

    // PCM → WAV（临时 PSRAM）
    size_t wavLen = pcmLen + 44;
    uint8_t* wav = (uint8_t*)heap_caps_malloc(wavLen, MALLOC_CAP_SPIRAM);
    if (!wav) { Serial.printf("%s wav alloc fail\n", TAG); return false; }
    wavHeader(wav, sampleRate, pcmLen);
    memcpy(wav + 44, pcm, pcmLen);

    // multipart（file + session_id）
    const char* B = "SABoundary7f3a";
    size_t bodyCap = wavLen + 640;
    uint8_t* body = (uint8_t*)heap_caps_malloc(bodyCap, MALLOC_CAP_SPIRAM);
    if (!body) { free(wav); return false; }
    int n = snprintf((char*)body, bodyCap,
        "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"rec.wav\"\r\n"
        "Content-Type: audio/wav\r\n\r\n", B);
    memcpy(body + n, wav, wavLen);
    n += wavLen;
    n += snprintf((char*)body + n, bodyCap - n,
        "\r\n--%s\r\nContent-Disposition: form-data; name=\"session_id\"\r\n\r\nsmart-assistant\r\n"
        "--%s--\r\n", B, B);
    free(wav);

    String url = String(_url) + "/api/chat/voice";
    HTTPClient http;
    http.setTimeout(45000);          // agent+记忆+MCP+TTS 全链路，给足时间
    http.setConnectTimeout(5000);
    if (strncmp(url.c_str(), "https", 5) == 0) {
        tlsConfig();
        tlsClient.setTimeout(45000);
    }
    bool began = (strncmp(url.c_str(), "https", 5) == 0)
        ? http.begin(tlsClient, url)
        : http.begin(url);
    if (!began) { free(body); return false; }
    http.addHeader("Authorization", (String("Bearer ") + _token).c_str());
    char ctype[64];
    snprintf(ctype, sizeof(ctype), "multipart/form-data; boundary=%s", B);
    http.addHeader("Content-Type", ctype);
    // 关键：HTTPClient 默认不收集自定义响应头，必须注册后 http.header() 才取得到
    const char* respHdrs[] = { "X-Transcript", "X-Reply" };
    http.collectHeaders(respHdrs, 2);

    Serial.printf("%s voice upload %u B...\n", TAG, (unsigned)n);
    int code = http.POST(body, n);
    free(body);
    Serial.printf("%s voice HTTP %d (%lums)\n", TAG, code, millis() % 100000);
    if (code != 200) {
        String s = http.getString();
        Serial.printf("%s voice err: %.200s\n", TAG, s.c_str());
        http.end();
        if (code == 401 && login()) return voiceAsk(pcm, pcmLen, sampleRate,
                                                    wavBuf, wavCap, transcript, tMax, reply, rMax);
        return false;
    }

    // 响应头：识别文本 + 回答
    String rawT = http.header("X-Transcript");
    String rawR = http.header("X-Reply");
    Serial.printf("%s raw X-Transcript len=%d: %.120s\n", TAG, rawT.length(), rawT.c_str());
    Serial.printf("%s raw X-Reply len=%d: %.120s\n", TAG, rawR.length(), rawR.c_str());
    urlDecode(rawT.c_str(), transcript, tMax);
    urlDecode(rawR.c_str(), reply, rMax);

    // 音频体 → wavBuf
    PsramBufStream bs(wavBuf, wavCap);
    int written = http.writeToStream(&bs);
    http.end();
    Serial.printf("%s voice audio %d B, T: %s\n", TAG, written, transcript);
    if (written <= 0) return false;

    uint32_t rate; size_t off, dlen;
    if (!wavParse(wavBuf, (size_t)written, rate, off, dlen)) {
        Serial.printf("%s wav parse fail\n", TAG);
        return false;
    }
    voiceRate = rate; voiceOff = off; voiceData = dlen;
    return true;
}

// ---------------- 完成待办 ----------------

bool OmniAide::completeTodo(int todoId) {
    if (!configured() || todoId <= 0) return false;
    if (!_ok && !login()) return false;

    char url[96], req[48], resp[256];
    snprintf(url, sizeof(url), "%s/api/items/%d", _url, todoId);
    snprintf(req, sizeof(req), "{\"status\":\"done\"}");
    int code = httpReq(url, "PUT", req, _token, resp, sizeof(resp));
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url, "PUT", req, _token, resp, sizeof(resp));
    }
    if (code != 200) {
        Serial.printf("%s completeTodo %d HTTP %d\n", TAG, todoId, code);
        return false;
    }
    Serial.printf("%s todo #%d done\n", TAG, todoId);
    return true;
}

// ---------------- 设备会话对话历史 ----------------

bool OmniAide::fetchChatHistory(OaChatMsg* msgs, int max, int& cnt) {
    cnt = 0;
    if (!configured()) return false;
    if (!_ok && !login()) return false;

    char* scratch = bigScratch(12288);
    if (!scratch) return false;

    String url = String(_url) + "/api/chat/history?session_id=smart-assistant&limit=8";
    int code = httpReq(url.c_str(), "GET", "", _token, scratch, 12288);
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url.c_str(), "GET", "", _token, scratch, 12288);
    }
    if (code != 200) {
        Serial.printf("%s history HTTP %d\n", TAG, code);
        return false;
    }

    JsonDocument doc;
    if (deserializeJson(doc, scratch)) return false;
    for (JsonVariant m : doc.as<JsonArray>()) {
        if (cnt >= max) break;
        snprintf(msgs[cnt].role, sizeof(msgs[cnt].role), "%s", m["role"] | "assistant");
        snprintf(msgs[cnt].content, sizeof(msgs[cnt].content), "%s", m["content"] | "");
        cnt++;
    }
    Serial.printf("%s history %d msgs\n", TAG, cnt);
    return true;
}

// ---------------- RSS 资讯头条 ----------------

bool OmniAide::fetchHeadlines(OaHeadline* out, int max, int& cnt) {
    cnt = 0;
    if (!configured()) return false;
    if (!_ok && !login()) return false;

    char* scratch = bigScratch(12288);
    if (!scratch) return false;

    String url = String(_url) + "/api/rss/entries?page_size=8";
    int code = httpReq(url.c_str(), "GET", "", _token, scratch, 12288);
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url.c_str(), "GET", "", _token, scratch, 12288);
    }
    if (code != 200) return false;

    JsonDocument doc;
    if (deserializeJson(doc, scratch)) return false;
    for (JsonVariant e : doc["items"].as<JsonArray>()) {
        if (cnt >= max) break;
        snprintf(out[cnt].title, sizeof(out[cnt].title), "%s", e["title"] | "");
        snprintf(out[cnt].feed, sizeof(out[cnt].feed), "%s", e["feed_title"] | "");
        if (out[cnt].title[0]) cnt++;
    }
    Serial.printf("%s headlines %d\n", TAG, cnt);
    return true;
}

// ---------------- 全天日程 ----------------

bool OmniAide::fetchTodaySchedule(OaBrief& out) {
    if (!configured()) return false;
    if (!_ok && !login()) return false;

    char day[16], nowHM[6], url[160];
    char* resp = bigScratch(4096);
    if (!resp) return false;
    time_t now = time(nullptr);
    struct tm ti;
    localtime_r(&now, &ti);
    strftime(day, sizeof(day), "%Y-%m-%d", &ti);
    strftime(nowHM, sizeof(nowHM), "%H:%M", &ti);
    snprintf(url, sizeof(url), "%s/api/schedule?start=%sT00:00:00&end=%sT23:59:59",
             _url, day, day);
    int code = httpReq(url, "GET", "", _token, resp, sizeof(resp));
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url, "GET", "", _token, resp, sizeof(resp));
    }
    if (code != 200) {
        Serial.printf("%s schedule HTTP %d\n", TAG, code);
        return false;
    }

    JsonDocument doc;
    if (deserializeJson(doc, resp)) return false;

    char hm[6][6];                       // 各条的开始时间 HH:MM
    char ev[6][64];
    int n = 0;
    for (JsonVariant e : doc.as<JsonArray>()) {
        if (n >= 6) break;
        const char* st = e["start_time"] | "";           // ISO "YYYY-MM-DDTHH:MM:SS"
        if (strlen(st) < 16) continue;
        snprintf(hm[n], sizeof(hm[n]), "%.5s", st + 11);
        snprintf(ev[n], sizeof(ev[n]), "%s %s", hm[n], e["title"] | "");
        n++;
    }

    // 正在进行的日程（最后一个已开始的）加 ▶
    int cur = -1;
    for (int i = 0; i < n; i++)
        if (strcmp(nowHM, hm[i]) >= 0) cur = i;
    if (cur >= 0) {
        char tmp[64];
        snprintf(tmp, sizeof(tmp), "▶ %s", ev[cur]);
        snprintf(ev[cur], sizeof(ev[cur]), "%s", tmp);
    }

    for (int i = 0; i < n; i++) snprintf(out.events[i], 64, "%s", ev[i]);
    out.eventCnt = n;
    Serial.printf("%s schedule %d events, cur=%d\n", TAG, n, cur);
    return true;
}

// ---------------- 通知中心 ----------------

bool OmniAide::fetchNotifications(OaNotif* msgs, int max, int& cnt) {
    cnt = 0;
    if (!configured()) return false;
    if (!_ok && !login()) return false;

    char* scratch2 = bigScratch(12288);
    if (!scratch2) return false;

    String url = String(_url) + "/api/notifications?limit=8";
    int code = httpReq(url.c_str(), "GET", "", _token, scratch2, 12288);
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url.c_str(), "GET", "", _token, scratch2, 12288);
    }
    if (code != 200) {
        Serial.printf("%s notifications HTTP %d\n", TAG, code);
        return false;
    }

    JsonDocument doc;
    if (deserializeJson(doc, scratch2)) return false;
    for (JsonVariant m : doc.as<JsonArray>()) {
        if (cnt >= max) break;
        msgs[cnt].id = m["id"] | 0;
        msgs[cnt].unread = !(m["read"] | false);
        snprintf(msgs[cnt].title, sizeof(msgs[cnt].title), "%s", m["title"] | "");
        snprintf(msgs[cnt].body, sizeof(msgs[cnt].body), "%s", m["body"] | "");
        const char* ca = m["created_at"] | "";           // ISO
        if (strlen(ca) >= 16) snprintf(msgs[cnt].time, sizeof(msgs[cnt].time), "%.11s", ca + 5);
        else msgs[cnt].time[0] = 0;
        cnt++;
    }
    Serial.printf("%s notifications %d\n", TAG, cnt);
    return true;
}

int OmniAide::fetchUnreadCount() {
    if (!configured() || (!_ok && !login())) return -1;
    char resp[128];
    String url = String(_url) + "/api/notifications/unread-count";
    int code = httpReq(url.c_str(), "GET", "", _token, resp, sizeof(resp));
    if (code == 401) {
        if (!login()) return -1;
        code = httpReq(url.c_str(), "GET", "", _token, resp, sizeof(resp));
    }
    if (code != 200) return -1;
    JsonDocument doc;
    if (deserializeJson(doc, resp)) return -1;
    return doc["count"] | 0;
}

bool OmniAide::markNotifRead(int id) {
    if (!configured() || (!_ok && !login())) return false;
    char url[96], resp[128];
    snprintf(url, sizeof(url), "%s/api/notifications/%d/read", _url, id);
    int code = httpReq(url, "PUT", "{}", _token, resp, sizeof(resp));
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url, "PUT", "{}", _token, resp, sizeof(resp));
    }
    return code == 200;
}

bool OmniAide::markAllNotifsRead() {
    if (!configured() || (!_ok && !login())) return false;
    char resp[128];
    String url = String(_url) + "/api/notifications/read-all";
    int code = httpReq(url.c_str(), "PUT", "{}", _token, resp, sizeof(resp));
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url.c_str(), "PUT", "{}", _token, resp, sizeof(resp));
    }
    return code == 200;
}

// ---------------- 固件 OTA ----------------

bool OmniAide::fetchFirmwareInfo(OaFirmware& out) {
    out.available = false;
    if (!configured()) return false;
    if (!_ok && !login()) return false;
    char* resp = bigScratch(512);
    if (!resp) return false;
    String url = String(_url) + "/api/device/firmware/latest";
    int code = httpReq(url.c_str(), "GET", "", _token, resp, 512);
    if (code == 401) {
        if (!login()) return false;
        code = httpReq(url.c_str(), "GET", "", _token, resp, 512);
    }
    if (code != 200) return false;
    JsonDocument doc;
    if (deserializeJson(doc, resp)) return false;
    out.available = doc["available"] | false;
    snprintf(out.version, sizeof(out.version), "%s", doc["version"] | "");
    return true;
}

bool OmniAide::downloadFirmware(OaProgressCb cb, void* ud) {
    if (!configured()) return false;
    if (!_ok && !login()) return false;

    String url = String(_url) + "/api/device/firmware/download";
    HTTPClient http;
    http.setTimeout(120000);
    http.setConnectTimeout(8000);
    if (strncmp(url.c_str(), "https", 5) == 0) {
        tlsConfig();
        tlsClient.setTimeout(120000);
    }
    bool began = (strncmp(url.c_str(), "https", 5) == 0)
        ? http.begin(tlsClient, url)
        : http.begin(url);
    if (!began) return false;
    http.addHeader("Authorization", (String("Bearer ") + _token).c_str());
    int code = http.GET();
    if (code != 200) {
        Serial.printf("%s ota HTTP %d\n", TAG, code);
        http.end();
        return false;
    }
    int len = http.getSize();
    if (len <= 0) {
        Serial.printf("%s ota no content-length (chunked not supported)\n", TAG);
        http.end();
        return false;
    }

    if (!Update.begin(len)) {
        Serial.printf("%s ota begin fail: %s\n", TAG, Update.errorString());
        http.end();
        return false;
    }
    WiFiClient* stream = http.getStreamPtr();
    uint8_t buf[4096];
    size_t done = 0;
    while (http.connected() && done < (size_t)len) {
        size_t avail = stream->available();
        if (avail == 0) { delay(2); continue; }
        int n = stream->readBytes(buf, (avail < sizeof(buf)) ? avail : sizeof(buf));
        if (n <= 0) break;
        if (Update.write(buf, n) != (size_t)n) {
            Serial.printf("%s ota write fail: %s\n", TAG, Update.errorString());
            Update.abort();
            http.end();
            return false;
        }
        done += n;
        if (cb) cb((int)(done * 100 / len), ud);
    }
    bool ok = (done == (size_t)len) && Update.end(true);
    http.end();
    Serial.printf("%s ota %s (%u/%d bytes)\n", TAG, ok ? "OK" : "FAIL",
                  (unsigned)done, len);
    return ok;
}
