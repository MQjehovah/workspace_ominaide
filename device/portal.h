/**
 * portal.h —— 配网模式：softAP "SmartAssistant-Setup" + captive portal
 *
 * 入口：startPortal()（setup 里 portalMode 时调用，不返回；loop 里喂 handleClient）。
 * 表单保存 WiFi / 后端地址账号到 NVS（namespace "sa"）后自动重启。
 * WiFi 支持多个网络（NVS "wlist"），新填的名称追加进列表；页面可删除已保存网络。
 */
#pragma once
#include <WiFi.h>
#include <DNSServer.h>
#include <WebServer.h>
#include <Preferences.h>
#include "wifi_net.h"

static DNSServer s_dns;
static WebServer s_portal(80);

// 极简 HTML 转义（SSID 可能带 & < > "）
static String portalEscape(const char* s) {
    String out;
    for (const char* p = s; p && *p; ++p) {
        switch (*p) {
        case '&':  out += "&amp;";  break;
        case '<':  out += "&lt;";   break;
        case '>':  out += "&gt;";   break;
        case '"':  out += "&quot;"; break;
        default:   out += *p;       break;
        }
    }
    return out;
}

static String portalPage() {
    String h = "<!doctype html><html><head><meta charset='utf-8'>"
               "<meta name='viewport' content='width=device-width,initial-scale=1'>"
               "<title>SmartAssistant</title></head>"
               "<body style='font-family:sans-serif;max-width:420px;margin:24px auto'>"
               "<h3>SmartAssistant 配网</h3>"
               "<p>已保存 " + String(g_wifiNetCount) + " / " + String(WIFI_MAX_NETS) +
               " 个网络，开机自动连接当前能连上的那个。</p>";

    if (g_wifiNetCount) {
        h += "<ul style='padding-left:18px;line-height:1.9'>";
        for (int i = 0; i < g_wifiNetCount; ++i) {
            h += "<li>" + portalEscape(g_wifiNets[i].ssid) +
                 " <a href='/del?i=" + String(i) +
                 "' style='color:#c62828;font-size:12px;margin-left:6px'>删除</a></li>";
        }
        h += "</ul>";
    } else {
        h += "<p style='color:#888'>还没有保存任何网络</p>";
    }

    h += "<form action='/save' method='post'>"
         "<p>WiFi 名称（已存在则更新密码）<br><input name='ssid' required style='width:100%'></p>"
         "<p>WiFi 密码<br><input name='wpass' type='password' style='width:100%'></p>"
         "<p>后端地址（可空）<br><input name='url' placeholder='https://mqgeek.com/ominaide' style='width:100%'></p>"
         "<p>后端账号<br><input name='user' style='width:100%'></p>"
         "<p>后端密码<br><input name='pass' type='password' style='width:100%'></p>"
         "<p><button style='padding:10px 24px'>保存并重启</button></p>"
         "</form></body></html>";
    return h;
}

static void portalSaved() {
    s_portal.send(200, "text/html; charset=utf-8",
                  "<meta charset='utf-8'><body style='font-family:sans-serif'>"
                  "已保存，设备正在重启...");
    delay(1200);
    ESP.restart();
}

static void startPortal(Preferences& prefs) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP("SmartAssistant-Setup");
    IPAddress ap = WiFi.softAPIP();
    s_dns.start(53, "*", ap);
    Serial.printf("[PORTAL] AP up, http://%s\n", ap.toString().c_str());

    s_portal.on("/", HTTP_GET, []() {
        s_portal.send(200, "text/html; charset=utf-8", portalPage());
    });
    s_portal.on("/save", HTTP_POST, [&prefs]() {
        String ssid = s_portal.arg("ssid");
        if (!ssid.length()) {
            s_portal.send(400, "text/html; charset=utf-8",
                          "<meta charset='utf-8'>WiFi 名称不能为空");
            return;
        }
        if (!wifiListAddPersist(prefs, ssid.c_str(), s_portal.arg("wpass").c_str())) {
            s_portal.send(400, "text/html; charset=utf-8",
                          "<meta charset='utf-8'>保存失败：最多 " + String(WIFI_MAX_NETS) +
                          " 个网络，请先回上一页删除一个");
            return;
        }
        if (s_portal.arg("url").length()) prefs.putString("ourl", s_portal.arg("url"));
        if (s_portal.arg("user").length()) prefs.putString("ouser", s_portal.arg("user"));
        if (s_portal.arg("pass").length()) prefs.putString("opass", s_portal.arg("pass"));
        Serial.printf("[PORTAL] saved network \"%s\" (%d total), rebooting\n",
                      ssid.c_str(), g_wifiNetCount);
        portalSaved();
    });
    s_portal.on("/del", HTTP_GET, [&prefs]() {
        int i = s_portal.arg("i").toInt();
        if (!wifiListRemovePersist(prefs, i)) {
            s_portal.send(400, "text/html; charset=utf-8",
                          "<meta charset='utf-8'>删除失败：序号无效");
            return;
        }
        Serial.printf("[PORTAL] deleted network #%d (%d left)\n", i, g_wifiNetCount);
        s_portal.sendHeader("Location", "/");
        s_portal.send(302);
    });
    // 各家手机系统的 captive 探测路径 → 全部引到门户页
    s_portal.onNotFound([]() {
        s_portal.sendHeader("Location", "http://192.168.4.1/");
        s_portal.send(302);
    });
    s_portal.begin();
    Serial.println("[PORTAL] web server ready");
}

static void portalTick() {
    s_dns.processNextRequest();
    s_portal.handleClient();
}
