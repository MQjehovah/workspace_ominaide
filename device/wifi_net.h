/**
 * wifi_net.h —— 多网络 WiFi 凭据
 *
 * 分两层：
 *   · 纯逻辑（无 Arduino 依赖，device/test/ 下用 host g++ 直接测试）
 *     wifiPickBest / wifiListAdd / wifiListRemove / wifiListFind
 *   · NVS 持久化（仅在 Arduino 构建时编译）
 *     wifiListLoad / wifiListSave / wifiListAddPersist / wifiListRemovePersist
 *
 * 存储格式：NVS namespace "sa" 的 "wlist" 键，JSON 数组 [{"s":"ssid","p":"pass"}...]。
 * 旧版本单网络键 "wssid"/"wpass" 在首次加载时迁移进列表并删除。
 * 本文件由 .ino 与 portal.h 共用，始终处于同一个编译单元（#pragma once）。
 */
#pragma once

#include <string.h>

#define WIFI_MAX_NETS 6

struct WifiCred {
    char ssid[33];
    char pass[65];
};

static inline bool wifiSsidValid(const char* s) {
    if (!s) return false;
    size_t len = strlen(s);
    return len > 0 && len < sizeof(((WifiCred*)0)->ssid);
}

// 在已存列表里按 SSID 精确查找，找不到返回 -1
static inline int wifiListFind(const WifiCred* nets, int n, const char* ssid) {
    if (!nets || !ssid) return -1;
    for (int i = 0; i < n; ++i) {
        if (strcmp(nets[i].ssid, ssid) == 0) return i;
    }
    return -1;
}

/**
 * 从扫描结果里挑出可见的已存网络，按信号从强到弱写入 out（元素为 nets 下标）。
 * 返回挑出的数量；out 容量不足时只保留最强的若干个。
 */
static inline int wifiPickBest(const WifiCred* nets, int n,
                               const char* const* ssids, const int* rssis, int scanCount,
                               int* out, int outMax) {
    if (!nets || !out || n <= 0 || outMax <= 0) return 0;

    int cap = outMax < WIFI_MAX_NETS ? outMax : WIFI_MAX_NETS;
    int chosenRssi[WIFI_MAX_NETS];
    int count = 0;

    for (int i = 0; i < n; ++i) {
        if (!nets[i].ssid[0]) continue;

        int best = -32768;
        for (int k = 0; k < scanCount; ++k) {
            if (!ssids || !ssids[k]) continue;
            if (strcmp(ssids[k], nets[i].ssid) != 0) continue;
            if (!rssis) continue;
            if (rssis[k] > best) best = rssis[k];
        }
        if (best == -32768) continue;                        // 本次扫描看不见
        if (count == cap && best <= chosenRssi[cap - 1]) continue;  // 挤不进最强榜

        int pos = (count < cap) ? count : cap - 1;
        while (pos > 0 && chosenRssi[pos - 1] < best) {
            if (pos < cap) {
                chosenRssi[pos] = chosenRssi[pos - 1];
                out[pos] = out[pos - 1];
            }
            --pos;
        }
        chosenRssi[pos] = best;
        out[pos] = i;
        if (count < cap) ++count;
    }
    return count;
}

// 追加新网络，或按 SSID 更新密码。返回新的列表长度；非法/已满返回 -1。
static inline int wifiListAdd(WifiCred* nets, int n, const char* ssid, const char* pass) {
    if (!nets || !wifiSsidValid(ssid)) return -1;
    if (n < 0) n = 0;

    int idx = wifiListFind(nets, n, ssid);
    if (idx < 0) {
        if (n >= WIFI_MAX_NETS) return -1;
        idx = n;
        strncpy(nets[idx].ssid, ssid, sizeof(nets[idx].ssid) - 1);
        nets[idx].ssid[sizeof(nets[idx].ssid) - 1] = '\0';
        ++n;
    }
    const char* p = pass ? pass : "";
    strncpy(nets[idx].pass, p, sizeof(nets[idx].pass) - 1);
    nets[idx].pass[sizeof(nets[idx].pass) - 1] = '\0';
    return n;
}

// 删除下标 idx。返回新的列表长度；越界时原样返回。
static inline int wifiListRemove(WifiCred* nets, int n, int idx) {
    if (!nets || idx < 0 || idx >= n) return n;
    for (int i = idx; i < n - 1; ++i) nets[i] = nets[i + 1];
    memset(&nets[n - 1], 0, sizeof(WifiCred));
    return n - 1;
}

#ifdef ARDUINO

#include <Arduino.h>
#include <Preferences.h>
#include <ArduinoJson.h>

static WifiCred g_wifiNets[WIFI_MAX_NETS];
static int      g_wifiNetCount = 0;

static inline void wifiListSave(Preferences& prefs) {
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();
    for (int i = 0; i < g_wifiNetCount; ++i) {
        JsonObject o = arr.add<JsonObject>();
        o["s"] = g_wifiNets[i].ssid;
        o["p"] = g_wifiNets[i].pass;
    }
    String blob;
    serializeJson(doc, blob);
    prefs.putString("wlist", blob);
}

static inline void wifiListLoad(Preferences& prefs) {
    g_wifiNetCount = 0;

    String blob = prefs.getString("wlist", "");
    if (blob.length()) {
        JsonDocument doc;
        if (deserializeJson(doc, blob) == DeserializationError::Ok && doc.is<JsonArray>()) {
            for (JsonObject o : doc.as<JsonArray>()) {
                if (g_wifiNetCount >= WIFI_MAX_NETS) break;
                const char* s = o["s"] | "";
                g_wifiNetCount = wifiListAdd(g_wifiNets, g_wifiNetCount, s, o["p"] | "");
            }
        } else {
            Serial.println("[WiFi] wlist 解析失败，忽略");
        }
    }

    // 旧版单网络配置迁移（迁移后删掉旧键，避免删空列表后又冒出来）
    if (g_wifiNetCount == 0) {
        String ssid = prefs.getString("wssid", "");
        if (ssid.length()) {
            g_wifiNetCount = wifiListAdd(g_wifiNets, 0, ssid.c_str(), prefs.getString("wpass", "").c_str());
            if (g_wifiNetCount > 0) {
                wifiListSave(prefs);
                Serial.printf("[WiFi] 迁移旧配置 \"%s\"\n", ssid.c_str());
            }
        }
    }
    prefs.remove("wssid");
    prefs.remove("wpass");

#ifdef WIFI_SSID
    // 编译期默认网络（config.local.h）在列表为空时种进去
    if (g_wifiNetCount == 0 && strlen(WIFI_SSID)) {
        g_wifiNetCount = wifiListAdd(g_wifiNets, 0, WIFI_SSID, WIFI_PASS);
        if (g_wifiNetCount > 0) wifiListSave(prefs);
    }
#endif

    Serial.printf("[WiFi] 已保存 %d 个网络\n", g_wifiNetCount);
}

// 新增/更新一条凭据并落盘；成功返回 true
static inline bool wifiListAddPersist(Preferences& prefs, const char* ssid, const char* pass) {
    int n = wifiListAdd(g_wifiNets, g_wifiNetCount, ssid, pass);
    if (n < 0) return false;
    g_wifiNetCount = n;
    wifiListSave(prefs);
    return true;
}

// 删除一条凭据并落盘；成功返回 true
static inline bool wifiListRemovePersist(Preferences& prefs, int idx) {
    if (idx < 0 || idx >= g_wifiNetCount) return false;
    g_wifiNetCount = wifiListRemove(g_wifiNets, g_wifiNetCount, idx);
    wifiListSave(prefs);
    return true;
}

#endif  // ARDUINO
