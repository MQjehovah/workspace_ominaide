/**
 * ui.cpp —— LVGL 初始化、显示/触摸对接、LVGL 任务、根布局 + 状态栏 + 时钟页
 *
 * 线程模型：LVGL 独立任务（core 1）持续 lv_timer_handler；互斥锁 s_mux 保护
 * 全部控件。ui::* 公开接口（ui.h）可在任意任务调用；uii:: 仅限本模块内部。
 */
#include "ui.h"
#include "ui_internal.h"
#include "ui_fonts.h"
#include "config.h"
#include "Arduino_GFX_Library.h"
#include <time.h>
#include <esp_heap_caps.h>

// ==================== 文件内静态（全局作用域，uii 与 ui 共用）====================
static Arduino_GFX*   s_gfx = nullptr;
static TouchDrvInterface* s_tp = nullptr;
static int  s_w = LCD_WIDTH, s_h = LCD_HEIGHT;
static SemaphoreHandle_t s_mux = nullptr;

static lv_display_t* s_disp = nullptr;
static lv_obj_t* s_root = nullptr;
static lv_obj_t* s_tv = nullptr;            // tileview：时钟/待办/对话 三页
static lv_obj_t* s_splash = nullptr;

// 状态栏控件
static lv_obj_t* s_battBar = nullptr;
static lv_obj_t* s_battLabel = nullptr;
static lv_obj_t* s_chgIcon = nullptr;
static lv_obj_t* s_oaDot = nullptr;
static lv_obj_t* s_wifiIcon = nullptr;
static lv_obj_t* s_bellIcon = nullptr;      // 通知铃铛（点击跳消息页）
static lv_obj_t* s_unreadLabel = nullptr;   // 未读角标数字

// 底部状态行
static lv_obj_t* s_stateLabel = nullptr;

// 时钟页控件
static lv_obj_t* s_timeLabel = nullptr;
static lv_obj_t* s_secLabel = nullptr;
static lv_obj_t* s_dateLabel = nullptr;
static lv_obj_t* s_newsLabel = nullptr;
static lv_obj_t* s_weatherLabel = nullptr;

// 充电脉冲动画相位
static bool s_pulseOn = false;

// LVGL 是否初始化成功（失败时所有公开接口空转，设备其余功能照常）
static bool s_ready = false;

// ---- 主题色 ----
static const uint32_t COL_BG      = 0x000000;
static const uint32_t COL_SILVER  = 0xc8ccd0;
static const uint32_t COL_GRAY    = 0x808488;
static const uint32_t COL_CYAN    = 0x00e5ff;
static const uint32_t COL_GREEN   = 0x4caf50;
static const uint32_t COL_YELLOW  = 0xffd740;
static const uint32_t COL_RED     = 0xff5252;
static const uint32_t COL_ORANGE  = 0xffab40;

// ==================== uii：锁 + 通用标签 ====================
namespace uii {

void lock()   { if (s_mux) xSemaphoreTake(s_mux, portMAX_DELAY); }
void unlock() { if (s_mux) xSemaphoreGive(s_mux); }
bool ready()  { return s_ready; }

lv_obj_t* makeLabel(lv_obj_t* parent, const char* text,
                    const lv_font_t* font, uint32_t color) {
    lv_obj_t* l = lv_label_create(parent);
    lv_label_set_text(l, text);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, lv_color_hex(color), 0);
    return l;
}

}  // namespace uii

// ---- RSS 头条轮播（全局静态：buildClockTile 与 ui::setHeadlines 共用）----
static ui::Headline s_news[8];
static int s_newsCnt = 0;
static int s_newsIdx = 0;

static void newsTimer(lv_timer_t*) {
    if (!s_newsCnt || !s_newsLabel) return;
    s_newsIdx = (s_newsIdx + 1) % s_newsCnt;
    char line[128];
    snprintf(line, sizeof(line), "· %s", s_news[s_newsIdx].title);
    lv_label_set_text(s_newsLabel, line);
}

// ==================== 显示驱动 ====================
static void flush_cb(lv_display_t* d, const lv_area_t* area, uint8_t* px_map) {
    int w = area->x2 - area->x1 + 1;
    int h = area->y2 - area->y1 + 1;
    lv_draw_sw_rgb565_swap(px_map, w * h);                 // LVGL 小端 → 面板大端
    s_gfx->draw16bitBeRGBBitmap(area->x1, area->y1, (uint16_t*)px_map, w, h);
    lv_display_flush_ready(d);
}

static void touch_cb(lv_indev_t*, lv_indev_data_t* data) {
    int16_t x[2] = {0}, y[2] = {0};
    uint8_t n = s_tp ? s_tp->getPoint(x, y, 1) : 0;
    if (n > 0) {
        data->point.x = x[0];
        data->point.y = y[0];
        data->state = LV_INDEV_STATE_PRESSED;
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
    }
}

// ==================== LVGL 任务 ====================
static void lvglTask(void*) {
    for (;;) {
        uii::lock();
        uint32_t next = lv_timer_handler();
        uii::unlock();
        if (next < 5) next = 5;
        if (next > 33) next = 33;
        vTaskDelay(pdMS_TO_TICKS(next));
    }
}

// 充电呼吸脉冲（LVGL 定时器，运行在 LVGL 任务持锁上下文，直接操作控件）
static void pulseTimer(lv_timer_t*) {
    if (!s_chgIcon || lv_obj_has_flag(s_chgIcon, LV_OBJ_FLAG_HIDDEN)) return;
    s_pulseOn = !s_pulseOn;
    lv_obj_set_style_text_color(s_chgIcon,
        lv_color_hex(s_pulseOn ? COL_YELLOW : 0x8a7d1a), 0);
}

static void newsTimer(lv_timer_t*);   // 前置声明：头条轮换定时器

// ==================== 状态栏 ====================
static void buildStatusBar(lv_obj_t* parent) {
    lv_obj_t* bar = lv_obj_create(parent);
    lv_obj_set_size(bar, s_w, 48);
    lv_obj_set_pos(bar, 0, 0);
    lv_obj_set_style_bg_color(bar, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(bar, 0, 0);
    lv_obj_set_style_radius(bar, 0, 0);
    lv_obj_set_style_pad_left(bar, 32, 0);   // 避开屏幕圆角
    lv_obj_set_style_pad_right(bar, 32, 0);
    lv_obj_set_style_pad_column(bar, 8, 0);
    lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(bar, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    // 电池条 + 百分比 + 充电图标
    s_battBar = lv_bar_create(bar);
    lv_bar_set_range(s_battBar, 0, 100);
    lv_obj_set_size(s_battBar, 44, 16);
    lv_obj_set_style_bg_color(s_battBar, lv_color_hex(0x20242a), 0);
    lv_obj_set_style_bg_opa(s_battBar, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(s_battBar, lv_color_hex(COL_GREEN), 0);
    lv_obj_set_style_border_width(s_battBar, 2, 0);
    lv_obj_set_style_radius(s_battBar, 4, 0);
    lv_obj_set_style_bg_color(s_battBar, lv_color_hex(COL_GREEN), LV_PART_INDICATOR);
    lv_bar_set_value(s_battBar, 0, LV_ANIM_OFF);

    s_battLabel = uii::makeLabel(bar, "--", &cn20, COL_GREEN);

    s_chgIcon = uii::makeLabel(bar, LV_SYMBOL_CHARGE, &lv_font_montserrat_16, COL_YELLOW);
    lv_obj_add_flag(s_chgIcon, LV_OBJ_FLAG_HIDDEN);

    // 弹性空隙
    lv_obj_t* spacer = lv_obj_create(bar);
    lv_obj_remove_style_all(spacer);
    lv_obj_set_flex_grow(spacer, 1);

    // 后端连接：OA + 圆点
    uii::makeLabel(bar, "OA", &cn20, COL_GRAY);
    s_oaDot = lv_obj_create(bar);
    lv_obj_remove_style_all(s_oaDot);
    lv_obj_set_size(s_oaDot, 12, 12);
    lv_obj_set_style_radius(s_oaDot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(s_oaDot, lv_color_hex(COL_ORANGE), 0);
    lv_obj_set_style_bg_opa(s_oaDot, LV_OPA_COVER, 0);

    // WiFi 图标
    s_wifiIcon = uii::makeLabel(bar, LV_SYMBOL_CLOSE, &lv_font_montserrat_16, COL_RED);

    // 通知铃铛 + 未读角标（点击回调在 buildRoot 末尾注册，那时 s_tv 才有效）
    s_bellIcon = uii::makeLabel(bar, LV_SYMBOL_BELL, &lv_font_montserrat_16, COL_GRAY);
    lv_obj_add_flag(s_bellIcon, LV_OBJ_FLAG_HIDDEN);      // 未登录前隐藏
    lv_obj_add_flag(s_bellIcon, LV_OBJ_FLAG_CLICKABLE);
    s_unreadLabel = uii::makeLabel(bar, "", &cn20, COL_RED);

    // 分隔线
    lv_obj_t* line = lv_obj_create(parent);
    lv_obj_remove_style_all(line);
    lv_obj_set_size(line, s_w, 2);
    lv_obj_set_y(line, 48);
    lv_obj_set_style_bg_color(line, lv_color_hex(0x30343c), 0);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
}

// ==================== 底部状态行 ====================
static void buildStateBar(lv_obj_t* parent) {
    s_stateLabel = uii::makeLabel(parent, "", &cn20, COL_GREEN);
    lv_obj_set_size(s_stateLabel, s_w, 24);
    lv_obj_set_pos(s_stateLabel, 0, s_h - 24);
    lv_obj_set_style_pad_left(s_stateLabel, 32, 0);   // 避开屏幕圆角
    lv_label_set_long_mode(s_stateLabel, LV_LABEL_LONG_DOT);
    lv_label_set_text(s_stateLabel, "启动中 ...");
}

// ==================== 时钟页 ====================
static void buildClockTile(lv_obj_t* tile) {
    // 大号 HH:MM：整屏宽度 + 文本居中（独立于秒标签，避免整体偏移）
    s_timeLabel = uii::makeLabel(tile, "--:--", &num92, 0xf2f4f6);
    lv_obj_set_width(s_timeLabel, s_w);
    lv_obj_set_style_text_align(s_timeLabel, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(s_timeLabel, 0, 64);

    // 秒：x/y 在 setTime 里按时间文本实测宽度定位（贴在大字右下）
    s_secLabel = uii::makeLabel(tile, "", &cn20, COL_CYAN);

    s_dateLabel = uii::makeLabel(tile, "", &cn20, COL_SILVER);
    lv_obj_set_width(s_dateLabel, s_w);
    lv_obj_set_y(s_dateLabel, 168);
    lv_obj_set_style_text_align(s_dateLabel, LV_TEXT_ALIGN_CENTER, 0);

    // 天气（setBrief 带出，无数据时隐藏）
    s_weatherLabel = uii::makeLabel(tile, "", &cn20, 0x8ec9e8);
    lv_obj_set_width(s_weatherLabel, s_w);
    lv_obj_set_y(s_weatherLabel, 196);
    lv_obj_set_style_text_align(s_weatherLabel, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_add_flag(s_weatherLabel, LV_OBJ_FLAG_HIDDEN);

    // RSS 资讯轮播：单行滚动，setHeadlines 填充，定时器每 8s 换条
    s_newsLabel = uii::makeLabel(tile, "", &cn20, 0x6a8a9a);
    lv_obj_set_width(s_newsLabel, s_w - 32);
    lv_obj_set_pos(s_newsLabel, 16, 236);
    lv_label_set_long_mode(s_newsLabel, LV_LABEL_LONG_SCROLL_CIRCULAR);
    lv_obj_add_flag(s_newsLabel, LV_OBJ_FLAG_HIDDEN);
    lv_timer_create(newsTimer, 8000, nullptr);
}

// ==================== 开机画面 ====================
static void buildSplash() {
    s_splash = lv_obj_create(s_root);
    lv_obj_set_size(s_splash, s_w, s_h);
    lv_obj_set_pos(s_splash, 0, 0);
    lv_obj_set_style_bg_color(s_splash, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(s_splash, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(s_splash, 0, 0);
    lv_obj_clear_flag(s_splash, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t* card = lv_obj_create(s_splash);
    lv_obj_set_size(card, 300, 180);
    lv_obj_align(card, LV_ALIGN_CENTER, 0, -10);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x101218), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, 0, 0);
    lv_obj_set_style_radius(card, 16, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t* cn = uii::makeLabel(card, "智能助手", &cn20, COL_CYAN);
    lv_obj_align(cn, LV_ALIGN_CENTER, 0, -32);

    lv_obj_t* en = uii::makeLabel(card, "SmartAssistant", &cn20, COL_GRAY);
    lv_obj_align(en, LV_ALIGN_CENTER, 0, 4);

    lv_obj_t* v = uii::makeLabel(card, "v2.0  LVGL  booting ...", &cn20, 0x3c5a6e);
    lv_obj_align(v, LV_ALIGN_CENTER, 0, 40);
}

// ==================== 根布局 ====================
static void buildRoot() {
    s_root = lv_obj_create(NULL);
    lv_obj_set_size(s_root, s_w, s_h);
    lv_obj_set_style_bg_color(s_root, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(s_root, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(s_root, 0, 0);
    lv_obj_set_style_pad_all(s_root, 0, 0);
    lv_obj_clear_flag(s_root, LV_OBJ_FLAG_SCROLLABLE);

    buildStatusBar(s_root);

    // 内容区：三页横滑 tileview（时钟 → 待办 → 对话）
    lv_obj_t* content = lv_obj_create(s_root);
    lv_obj_remove_style_all(content);
    lv_obj_set_size(content, s_w, s_h - 48 - 24);
    lv_obj_set_pos(content, 0, 50);

    s_tv = lv_tileview_create(content);
    lv_obj_set_size(s_tv, s_w, s_h - 48 - 24);
    lv_obj_set_style_bg_color(s_tv, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(s_tv, LV_OPA_COVER, 0);
    lv_obj_set_scrollbar_mode(s_tv, LV_SCROLLBAR_MODE_OFF);
    lv_obj_set_style_pad_all(s_tv, 0, 0);

    lv_obj_t* tileClock = lv_tileview_add_tile(s_tv, 0, 0, LV_DIR_HOR);
    lv_obj_t* tileTodo  = lv_tileview_add_tile(s_tv, 1, 0, LV_DIR_HOR);
    lv_obj_t* tileNotif = lv_tileview_add_tile(s_tv, 2, 0, LV_DIR_HOR);
    lv_obj_t* tileChat  = lv_tileview_add_tile(s_tv, 3, 0, LV_DIR_HOR);
    lv_obj_t* tileSet   = lv_tileview_add_tile(s_tv, 4, 0, LV_DIR_HOR);
    for (lv_obj_t* t : {tileClock, tileTodo, tileNotif, tileChat, tileSet}) {
        lv_obj_set_style_bg_color(t, lv_color_hex(COL_BG), 0);
        lv_obj_set_style_bg_opa(t, LV_OPA_COVER, 0);
    }
    buildClockTile(tileClock);
    uii::todoInit(tileTodo);
    uii::notifInit(tileNotif);
    uii::chatInit(tileChat);
    uii::settingsInit(tileSet);

    // 铃铛点击 → 消息页（s_tv 已创建；事件回调在 LVGL 任务内，直接切页不取锁）
    lv_obj_add_event_cb(s_bellIcon, [](lv_event_t* e) {
        lv_obj_t* tv = (lv_obj_t*)lv_event_get_user_data(e);
        lv_tileview_set_tile_by_index(tv, 2, 0, LV_ANIM_ON);
    }, LV_EVENT_CLICKED, s_tv);

    buildStateBar(s_root);
    buildSplash();
}

namespace ui {

// ==================== 公开 API ====================
bool init(Arduino_GFX* gfx, TouchDrvInterface* tp, int w, int h) {
    if (!gfx) return false;
    s_gfx = gfx;
    s_tp = tp;
    if (w > 0 && h > 0) { s_w = w; s_h = h; }

    lv_init();
    lv_tick_set_cb(millis);

    s_disp = lv_display_create(s_w, s_h);
    lv_display_set_flush_cb(s_disp, flush_cb);
    lv_display_set_color_format(s_disp, LV_COLOR_FORMAT_RGB565);
    // 40 行局部渲染缓冲：480*40*2 = 37.5KB，内部 RAM（DMA 可达）
    // LVGL objects live in a PSRAM pool; keep 10 lines internal for TLS headroom.
    // UI smoothness comes from pinning ESP-SR tasks to core 0 (see ESP_SR patch).
    size_t bufSize = (size_t)s_w * 40 * 2;
    uint8_t* buf = (uint8_t*)heap_caps_malloc(bufSize, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!buf) return false;
    lv_display_set_buffers(s_disp, buf, nullptr, bufSize, LV_DISPLAY_RENDER_MODE_PARTIAL);

    lv_indev_t* indev = lv_indev_create();
    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_display(indev, s_disp);
    lv_indev_set_read_cb(indev, touch_cb);

    lv_theme_default_init(s_disp, lv_color_hex(COL_CYAN), lv_color_hex(COL_GREEN), true, &cn20);

    s_mux = xSemaphoreCreateMutex();
    buildRoot();
    lv_screen_load(s_root);

    xTaskCreatePinnedToCore(lvglTask, "lvgl", 8192, nullptr, 2, nullptr, 1);
    lv_timer_create(pulseTimer, 700, nullptr);
    s_ready = true;
    return true;
}

void bootDone() {
    if (!s_ready) return;
    uii::lock();
    if (s_splash) { lv_obj_del(s_splash); s_splash = nullptr; }
    lv_label_set_text(s_stateLabel, "");
    uii::unlock();
}

void setState(const char* text, uint32_t color) {
    if (!s_ready) return;
    uii::lock();
    lv_label_set_text(s_stateLabel, text);
    lv_obj_set_style_text_color(s_stateLabel, lv_color_hex(color), 0);
    uii::unlock();
}

void setBattery(int pct, bool charging, bool pmuOk) {
    if (!s_ready) return;
    uii::lock();
    if (!pmuOk) {
        lv_obj_add_flag(s_battBar, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_battLabel, "PMU!");
        lv_obj_set_style_text_color(s_battLabel, lv_color_hex(COL_RED), 0);
    } else if (pct < 0) {
        lv_obj_add_flag(s_battBar, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_battLabel, "USB");
        lv_obj_set_style_text_color(s_battLabel, lv_color_hex(COL_GREEN), 0);
    } else {
        lv_obj_clear_flag(s_battBar, LV_OBJ_FLAG_HIDDEN);
        char b[8];
        snprintf(b, sizeof(b), "%d%%", pct);
        lv_label_set_text(s_battLabel, b);
        uint32_t c = pct > 50 ? COL_GREEN : (pct > 20 ? COL_YELLOW : COL_RED);
        lv_obj_set_style_text_color(s_battLabel, lv_color_hex(c), 0);
        lv_obj_set_style_bg_color(s_battBar, lv_color_hex(c), LV_PART_INDICATOR);
        lv_obj_set_style_border_color(s_battBar, lv_color_hex(c), 0);
        lv_bar_set_value(s_battBar, pct, LV_ANIM_OFF);
    }
    if (charging) lv_obj_clear_flag(s_chgIcon, LV_OBJ_FLAG_HIDDEN);
    else          lv_obj_add_flag(s_chgIcon, LV_OBJ_FLAG_HIDDEN);
    uii::unlock();
}

void setWifi(bool ok, int bars) {
    if (!s_ready) return;
    uii::lock();
    if (!ok) {
        lv_label_set_text(s_wifiIcon, LV_SYMBOL_CLOSE);
        lv_obj_set_style_text_color(s_wifiIcon, lv_color_hex(COL_RED), 0);
    } else {
        lv_label_set_text(s_wifiIcon, LV_SYMBOL_WIFI);
        uint32_t c = bars >= 3 ? COL_GREEN : (bars == 2 ? COL_YELLOW : COL_ORANGE);
        lv_obj_set_style_text_color(s_wifiIcon, lv_color_hex(c), 0);
    }
    uii::unlock();
}

void setOa(bool loggedIn) {
    if (!s_ready) return;
    uii::lock();
    lv_obj_set_style_bg_color(s_oaDot,
        lv_color_hex(loggedIn ? COL_CYAN : COL_ORANGE), 0);
    uii::unlock();
}

void setUnread(int n) {
    if (!s_ready) return;
    uii::lock();
    if (n < 0) {                       // 未登录：隐藏铃铛
        lv_obj_add_flag(s_bellIcon, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_unreadLabel, "");
    } else {
        lv_obj_clear_flag(s_bellIcon, LV_OBJ_FLAG_HIDDEN);
        if (n == 0) {
            lv_label_set_text(s_unreadLabel, "");
            lv_obj_set_style_text_color(s_bellIcon, lv_color_hex(COL_GRAY), 0);
        } else {
            char b[8];
            snprintf(b, sizeof(b), n > 9 ? "9+" : "%d", n);
            lv_label_set_text(s_unreadLabel, b);
            lv_obj_set_style_text_color(s_bellIcon, lv_color_hex(COL_YELLOW), 0);
        }
    }
    uii::unlock();
}

void setTime(const struct tm& ti) {
    if (!s_ready) return;
    bool valid = (ti.tm_year + 1900) >= 2024;
    char buf[40];
    if (valid) strftime(buf, sizeof(buf), "%H:%M", &ti);
    else       snprintf(buf, sizeof(buf), "--:--");

    uii::lock();
    lv_label_set_text(s_timeLabel, buf);
    lv_obj_set_style_text_color(s_timeLabel,
        lv_color_hex(valid ? 0xf2f4f6 : COL_GRAY), 0);
    if (valid) {
        // 秒贴在大字右下：x 按实测宽度算，y 对齐大字基线（line_height-base_line≈顶部偏移）
        lv_point_t sz;
        lv_text_get_size(&sz, buf, &num92, 0, 0, LV_COORD_MAX, LV_TEXT_FLAG_NONE);
        lv_obj_set_pos(s_secLabel, (s_w + sz.x) / 2 + 14,
                       64 + num92.line_height - 18);
        strftime(buf, sizeof(buf), "%S", &ti);
        lv_label_set_text(s_secLabel, buf);
        static const char* WD[] = {"日", "一", "二", "三", "四", "五", "六"};
        snprintf(buf, sizeof(buf), "%04d-%02d-%02d 星期%s",
                 ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday, WD[ti.tm_wday]);
    } else {
        lv_label_set_text(s_secLabel, "");
        snprintf(buf, sizeof(buf), "等待时间同步 ...");
    }
    lv_label_set_text(s_dateLabel, buf);
    uii::unlock();
}

void setHeadlines(const Headline* items, int cnt) {
    if (!s_ready) return;
    uii::lock();
    s_newsCnt = (cnt > 8) ? 8 : cnt;
    s_newsIdx = 0;
    if (s_newsCnt == 0) {
        lv_obj_add_flag(s_newsLabel, LV_OBJ_FLAG_HIDDEN);
    } else {
        for (int i = 0; i < s_newsCnt; i++) s_news[i] = items[i];
        char line[128];
        snprintf(line, sizeof(line), "· %s", s_news[0].title);
        lv_label_set_text(s_newsLabel, line);
        lv_obj_clear_flag(s_newsLabel, LV_OBJ_FLAG_HIDDEN);
    }
    uii::unlock();
}

// WMO 天气码 → 中文
static const char* wmoText(int code) {
    if (code == 0) return "晴";
    if (code <= 2) return "多云";
    if (code == 3) return "阴";
    if (code == 45 || code == 48) return "雾";
    if (code <= 57) return "毛雨";
    if (code <= 67) return "雨";
    if (code <= 77) return "雪";
    if (code <= 82) return "阵雨";
    if (code <= 86) return "阵雪";
    return "雷雨";
}

void setWeather(int temp, int code) {
    if (!s_ready) return;
    uii::lock();
    if (temp == -999) {
        lv_obj_add_flag(s_weatherLabel, LV_OBJ_FLAG_HIDDEN);
    } else {
        char b[24];
        snprintf(b, sizeof(b), "%d° %s", temp, wmoText(code));
        lv_label_set_text(s_weatherLabel, b);
        lv_obj_clear_flag(s_weatherLabel, LV_OBJ_FLAG_HIDDEN);
    }
    uii::unlock();
}

void showPortal(const char* apName) {
    if (!s_ready) return;
    uii::lock();
    if (s_splash) { lv_obj_del(s_splash); s_splash = nullptr; }
    lv_obj_t* ov = lv_obj_create(s_root);
    lv_obj_set_size(ov, s_w, s_h);
    lv_obj_set_pos(ov, 0, 0);
    lv_obj_set_style_bg_color(ov, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(ov, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(ov, 0, 0);
    lv_obj_clear_flag(ov, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t* card = lv_obj_create(ov);
    lv_obj_set_size(card, 420, 320);
    lv_obj_align(card, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x101218), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, 0, 0);
    lv_obj_set_style_radius(card, 16, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t* t1 = uii::makeLabel(card, "配网模式", &cn20, COL_CYAN);
    lv_obj_align(t1, LV_ALIGN_TOP_MID, 0, 24);

    char b[96];
    snprintf(b, sizeof(b), "手机连接热点\n%s", apName);
    lv_obj_t* t2 = uii::makeLabel(card, b, &cn20, COL_SILVER);
    lv_label_set_long_mode(t2, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(t2, 380);
    lv_obj_align(t2, LV_ALIGN_TOP_MID, 0, 78);

    lv_obj_t* t3 = uii::makeLabel(card, "浏览器打开\nhttp://192.168.4.1", &cn20, COL_SILVER);
    lv_label_set_long_mode(t3, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(t3, 380);
    lv_obj_align(t3, LV_ALIGN_TOP_MID, 0, 168);

    lv_obj_t* t4 = uii::makeLabel(card, "保存后设备自动重启", &cn20, COL_GRAY);
    lv_obj_align(t4, LV_ALIGN_BOTTOM_MID, 0, -24);
    uii::unlock();
}

void showChatPage() {
    if (!s_ready) return;
    uii::lock();
    lv_tileview_set_tile_by_index(s_tv, 3, 0, LV_ANIM_ON);
    uii::unlock();
}

void showNotifPage() {
    if (!s_ready) return;
    uii::lock();
    lv_tileview_set_tile_by_index(s_tv, 2, 0, LV_ANIM_ON);
    uii::unlock();
}

}  // namespace ui

