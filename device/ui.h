/**
 * ui.h —— OmniAide 设备端 LVGL UI
 *
 * 架构：LVGL 独立 FreeRTOS 任务持续 lv_timer_handler（录音/HTTP 阻塞时界面仍流畅），
 *       .ino 主循环通过本头文件的接口更新界面，内部自带互斥锁（可在任意任务调用）。
 *       事件回调（触摸点击）运行在 LVGL 任务内，回调里不得调用 ui::* 更新类接口，
 *       只允许写请求队列（如待办完成请求）。
 */
#pragma once
#include <Arduino.h>
#include <time.h>
#include <lvgl.h>
#include "TouchDrvInterface.hpp"

class Arduino_GFX;   // 全局作用域前向声明（ui.cpp 里包含完整定义）

namespace ui {

// ---- 待办摘要（由 .ino 填充后交给 setBrief）----
struct Brief {
    int   todoId[8] = {0};
    char  todoTitle[8][64] = {};
    uint8_t todoCnt = 0;
    char  events[6][64] = {};
    uint8_t eventCnt = 0;
    char  serverTime[20] = "";
    int   weatherTemp = -999;   // ℃，-999 = 无
    int   weatherCode = -1;
    bool  configured = false;   // 后端是否已在 config.h 配置
    bool  loggedIn = false;     // 是否已登录
};

// ---- RSS 头条（时钟页轮播）----
struct Headline {
    char title[96] = "";
    char feed[24] = "";
};

// ---- 通知条目（由 .ino 填充后交给 setNotifs）----
struct Notif {
    int     id = 0;
    bool    unread = false;
    char    title[64] = "";
    char    body[384] = "";
    char    time[12] = "";
};

// 初始化：lv_init + 显示/触摸驱动 + 界面搭建（含开机画面），并启动 LVGL 任务
bool init(Arduino_GFX* gfx, TouchDrvInterface* tp, int w, int h);

// 开机完成：撤掉开机画面，显示正式四页（时钟/待办/消息/对话）
void bootDone();

// ---- 状态（线程安全）----
void setState(const char* text, uint32_t color);      // 底部状态行
void setBattery(int pct, bool charging, bool pmuOk);  // pct<0 = 无电池(USB)
void setWifi(bool ok, int bars);                      // bars 1..3
void setOa(bool loggedIn);                            // 状态栏后端连接点
void setTime(const struct tm& ti);                    // 时钟页（ti.tm_year<116 表示无效）
void setBrief(const Brief& b);                        // 待办页整页刷新
void setUnread(int n);                                // 状态栏未读角标（n<0 隐藏铃铛，0 灰色）
void setNotifs(const Notif* items, int cnt);          // 消息页整页刷新
void setHeadlines(const Headline* items, int cnt);    // 时钟页资讯轮播（cnt=0 隐藏）
void setWeather(int temp, int code);                  // 时钟页天气（temp=-999 隐藏）
void showPortal(const char* apName);                  // 配网模式全屏提示

// ---- 设置页 ----
struct SettingReq {
    int  vol = -1;        // 0..100，<0 不变
    int  bright = -1;     // 10..100，<0 不变
    int  chime = -1;      // 0/1，<0 不变
    int  ota = -1;        // 1 = 点了"检查固件更新"
    int  portal = -1;     // 1 = 点了"配网模式"
};
void setSettingRefs(int vol, int bright, bool chime);  // 开机初始值（NVS 读出）
bool popSettingReq(SettingReq& out);                   // 主循环轮询取走待应用设置

// ---- 对话页（线程安全）----
void chatClear();
void chatAppend(const char* role, const char* text);  // role: "user" / "assistant"
void showChatPage();                                  // 录音开始时切到对话页
void showNotifPage();                                 // 实时提醒到达时切到消息页

// ---- 录音/处理覆盖层（线程安全）----
void recShow(bool on);                                // 显示/隐藏录音音量条区
void recUpdate(int peak, uint32_t secs);              // peak 0..32767
void busy(const char* text);                          // 对话中/播报中：转圈+文本；text=null 隐藏

// ---- 请求队列（LVGL 任务写，主循环读）----
bool popCompleteReq(int& todoId);                     // 待办点击完成
bool popNotifReadReq(int& notifId);                   // 通知点击已读
bool popNotifReadAll();                               // 全部已读按钮

}  // namespace ui
