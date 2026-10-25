/**
 * ui_internal.h —— ui.cpp 与 ui_todo/ui_chat.cpp 之间的内部接口（非公开 API）
 */
#pragma once
#include <lvgl.h>

namespace uii {

void lock();
void unlock();
bool ready();      // LVGL 是否已成功初始化（失败时公开接口全部空转）

// 通用标签创建（ui.cpp 实现，页面模块共用）
lv_obj_t* makeLabel(lv_obj_t* parent, const char* text,
                    const lv_font_t* font, uint32_t color);

// 页面初始化（在 LVGL 任务启动前、搭建界面时调用一次）
void todoInit(lv_obj_t* tile);
void notifInit(lv_obj_t* tile);
void chatInit(lv_obj_t* tile);
void settingsInit(lv_obj_t* tile);

}  // namespace uii
