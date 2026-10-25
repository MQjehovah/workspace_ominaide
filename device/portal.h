/**
 * portal.h —— 配网模式：softAP "SmartAssistant-Setup" + captive portal
 *
 * 入口：startPortal()（setup 里 portalMode 时调用，不返回；loop 里喂 handleClient）。
 * 表单保存 WiFi / 后端地址账号到 NVS（namespace "sa"）后自动重启。
 */
#pragma once
#include <WiFi.h>
#include <DNSServer.h>
#include <WebServer.h>
#include <Preferences.h>

static DNSServer s_dns;
static WebServer s_portal(80);

static const char PORTAL_HTML[] PROGMEM = R"html(<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SmartAssistant</title></head>
<body style="font-family:sans-serif;max-width:420px;margin:24px auto">
<h3>SmartAssistant &#37197;&#32593;</h3>
<form action="/save" method="post">
<p>WiFi &#21517;&#31216;<br><input name="ssid" required></p>
<p>WiFi &#23494;&#30721;<br><input name="wpass" type="password"></p>
<p>&#21518;&#31471;&#22320;&#22336;&#65288;&#21487;&#31354;&#65289;<br><input name="url" placeholder="https://mqgeek.com/ominaide"></p>
<p>&#21518;&#31471;&#36134;&#21495;<br><input name="user"></p>
<p>&#21518;&#31471;&#23494;&#30721;<br><input name="pass" type="password"></p>
<p><button style="padding:10px 24px">&#20445;&#23384;&#24182;&#37325;&#21551;</button></p>
</form></body></html>)html";

static void portalSaved() {
    s_portal.send(200, "text/html", "<meta charset='utf-8'>&#24050;&#20445;&#23384;&#65292;&#35774;&#22791;&#27491;&#22312;&#37325;&#21551;...");
    delay(1200);
    ESP.restart();
}

static void startPortal(Preferences& prefs) {
    WiFi.mode(WIFI_AP);
    WiFi.softAP("SmartAssistant-Setup");
    IPAddress ap = WiFi.softAPIP();
    s_dns.start(53, "*", ap);
    Serial.printf("[PORTAL] AP up, http://%s\n", ap.toString().c_str());

    s_portal.on("/", HTTP_GET, []() { s_portal.send(200, "text/html", PORTAL_HTML); });
    s_portal.on("/save", HTTP_POST, [&prefs]() {
        String ssid = s_portal.arg("ssid");
        if (!ssid.length()) {
            s_portal.send(400, "text/html", "<meta charset='utf-8'>WiFi &#21517;&#31216;&#19981;&#33021;&#20026;&#31354;");
            return;
        }
        prefs.putString("wssid", ssid);
        prefs.putString("wpass", s_portal.arg("wpass"));
        if (s_portal.arg("url").length()) prefs.putString("ourl", s_portal.arg("url"));
        if (s_portal.arg("user").length()) prefs.putString("ouser", s_portal.arg("user"));
        if (s_portal.arg("pass").length()) prefs.putString("opass", s_portal.arg("pass"));
        Serial.println("[PORTAL] saved, rebooting");
        portalSaved();
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
