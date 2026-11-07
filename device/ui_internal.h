/**
 * ui_internal.h —— ui.cpp 与 ui_*.cpp 之间的内部接口（非公开 API）
 */
#pragma once
#include <lvgl.h>

namespace uii {

void lock();
void unlock();
bool ready();          // LVGL 是否已成功初始化（失败时公开接口全部空转）
int contentWidth();    // 内容区宽度
int contentHeight();   // 内容区高度（不含状态栏、状态行和底部分页点）

// 通用标签创建（ui.cpp 实现，页面模块共用）
lv_obj_t* makeLabel(lv_obj_t* parent, const char* text,
                    const lv_font_t* font, uint32_t color);

// 页面初始化（在 LVGL 任务启动前、搭建界面时调用一次）
void infoInit(lv_obj_t* tile);
void todoInit(lv_obj_t* tile);
void notifInit(lv_obj_t* tile);
void chatInit(lv_obj_t* tile);
void settingsInit(lv_obj_t* tile);

// 信息页：0=日程，1=消息，2=资讯（调用方需已持锁）
void infoShowTab(int index);
void infoClearNews();
void infoAddNews(const char* title, const char* feed);

// 首页：下一项日程单行（调用方需已持锁）
void homeNextEvent(const char* text);

// 设置页：连接状态（内部加锁）
void settingsSetConnection(bool configured, bool loggedIn);

// 请求主循环进入配网模式 / 检查 OTA（LVGL 事件回调内调用）
void requestPortal();
void requestOta();

// 首页快捷对话卡（ui.cpp 实现，内部加锁）
void quickChat(const char* role, const char* text);
void quickStatus(const char* text);      // nullptr = 恢复最近一条回复
void quickClear();

}  // namespace uii
