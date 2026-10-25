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
static lv_obj_t* s_battIcon = nullptr;      // 电池图标 + 百分比，不再用进度条
static lv_obj_t* s_battLabel = nullptr;
static lv_obj_t* s_chgIcon = nullptr;
static lv_obj_t* s_oaDot = nullptr;
static lv_obj_t* s_wifiIcon = nullptr;
static lv_obj_t* s_bellBox = nullptr;       // 铃铛容器（角标绝对定位，避免挤占 flex）
static lv_obj_t* s_bellIcon = nullptr;
static lv_obj_t* s_unreadBadge = nullptr;   // 未读角标

// 底部状态行
static lv_obj_t* s_stateLabel = nullptr;

// 时钟页控件
static lv_obj_t* s_timeLabel = nullptr;
static lv_obj_t* s_dateLabel = nullptr;
static lv_obj_t* s_newsLabel = nullptr;
static lv_obj_t* s_weatherLabel = nullptr;

// 首页快捷对话卡
static lv_obj_t* s_quickUser = nullptr;
static lv_obj_t* s_quickReply = nullptr;
static char s_lastReply[256] = "";

// 充电脉冲动画相位
static bool s_pulseOn = false;

// LVGL 是否初始化成功（失败时所有公开接口空转，设备其余功能照常）
static bool s_ready = false;

// ---- 主题色 ----
static const uint32_t COL_BG      = 0x000000;
static const uint32_t COL_SILVER  = 0xc8ccd0;
static const uint32_t COL_WHITE   = 0xf2f4f6;
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
        if (next > 33) next = 33;   // QSPI 在 60fps 下易出现撕裂/横纹，稳定 30fps
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
    lv_obj_set_style_pad_left(bar, 24, 0);   // 避开屏幕圆角
    lv_obj_set_style_pad_right(bar, 24, 0);
    lv_obj_set_style_pad_column(bar, 6, 0);
    lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(bar, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    // 电池：图标 + 百分比 + 充电符号（固定宽度，避免和右侧角标互相挤压）
    s_battIcon = uii::makeLabel(bar, LV_SYMBOL_BATTERY_FULL, &lv_font_montserrat_16, COL_GREEN);
    lv_obj_set_width(s_battIcon, 22);
    lv_obj_set_style_text_align(s_battIcon, LV_TEXT_ALIGN_CENTER, 0);

    // 用 16px 数字字体，固定 46px 足够显示 100%；cn20 太宽会被省略成 10...
    s_battLabel = uii::makeLabel(bar, "--", &lv_font_montserrat_16, COL_GREEN);
    lv_obj_set_width(s_battLabel, 46);
    lv_obj_set_style_text_align(s_battLabel, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_long_mode(s_battLabel, LV_LABEL_LONG_DOT);

    s_chgIcon = uii::makeLabel(bar, LV_SYMBOL_CHARGE, &lv_font_montserrat_16, COL_YELLOW);
    lv_obj_set_width(s_chgIcon, 16);
    lv_obj_set_style_text_align(s_chgIcon, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_add_flag(s_chgIcon, LV_OBJ_FLAG_HIDDEN);

    // 弹性空隙
    lv_obj_t* spacer = lv_obj_create(bar);
    lv_obj_remove_style_all(spacer);
    lv_obj_set_flex_grow(spacer, 1);

    // 后端连接圆点（不再放 “OA” 文字，减少拥挤）
    s_oaDot = lv_obj_create(bar);
    lv_obj_remove_style_all(s_oaDot);
    lv_obj_set_size(s_oaDot, 10, 10);
    lv_obj_set_style_radius(s_oaDot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(s_oaDot, lv_color_hex(COL_ORANGE), 0);
    lv_obj_set_style_bg_opa(s_oaDot, LV_OPA_COVER, 0);

    // WiFi 图标
    s_wifiIcon = uii::makeLabel(bar, LV_SYMBOL_CLOSE, &lv_font_montserrat_16, COL_RED);
    lv_obj_set_width(s_wifiIcon, 18);
    lv_obj_set_style_text_align(s_wifiIcon, LV_TEXT_ALIGN_CENTER, 0);

    // 铃铛容器：角标绝对定位在右上角，不再和铃铛/未读数在 flex 里互相重叠
    s_bellBox = lv_obj_create(bar);
    lv_obj_remove_style_all(s_bellBox);
    lv_obj_set_size(s_bellBox, 30, 30);
    lv_obj_clear_flag(s_bellBox, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(s_bellBox, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(s_bellBox, LV_OBJ_FLAG_HIDDEN);   // 未登录前隐藏

    s_bellIcon = uii::makeLabel(s_bellBox, LV_SYMBOL_BELL, &lv_font_montserrat_16, COL_GRAY);
    lv_obj_center(s_bellIcon);

    s_unreadBadge = uii::makeLabel(s_bellBox, "", &lv_font_montserrat_16, COL_WHITE);
    lv_obj_set_style_bg_color(s_unreadBadge, lv_color_hex(COL_RED), 0);
    lv_obj_set_style_bg_opa(s_unreadBadge, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(s_unreadBadge, 8, 0);
    lv_obj_set_style_pad_left(s_unreadBadge, 3, 0);
    lv_obj_set_style_pad_right(s_unreadBadge, 3, 0);
    lv_obj_set_style_pad_top(s_unreadBadge, 0, 0);
    lv_obj_set_style_pad_bottom(s_unreadBadge, 0, 0);
    lv_obj_align(s_unreadBadge, LV_ALIGN_TOP_RIGHT, 3, -2);
    lv_obj_add_flag(s_unreadBadge, LV_OBJ_FLAG_HIDDEN);

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
    // 大号 HH:MM：整屏宽度 + 文本居中（不再显示秒）
    s_timeLabel = uii::makeLabel(tile, "--:--", &num92, 0xf2f4f6);
    lv_obj_set_width(s_timeLabel, s_w);
    lv_obj_set_style_text_align(s_timeLabel, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_pos(s_timeLabel, 0, 54);

    s_dateLabel = uii::makeLabel(tile, "", &cn20, COL_SILVER);
    lv_obj_set_width(s_dateLabel, s_w);
    lv_obj_set_y(s_dateLabel, 160);
    lv_obj_set_style_text_align(s_dateLabel, LV_TEXT_ALIGN_CENTER, 0);

    // 天气（setBrief 带出，无数据时隐藏）
    s_weatherLabel = uii::makeLabel(tile, "", &cn20, 0x8ec9e8);
    lv_obj_set_width(s_weatherLabel, s_w);
    lv_obj_set_y(s_weatherLabel, 188);
    lv_obj_set_style_text_align(s_weatherLabel, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_add_flag(s_weatherLabel, LV_OBJ_FLAG_HIDDEN);

    // RSS 头条：静态单行省略，避免圆形滚动持续重绘拖低帧率
    s_newsLabel = uii::makeLabel(tile, "", &cn20, 0x6a8a9a);
    lv_obj_set_width(s_newsLabel, s_w - 32);
    lv_obj_set_pos(s_newsLabel, 16, 218);
    lv_label_set_long_mode(s_newsLabel, LV_LABEL_LONG_DOT);
    lv_obj_add_flag(s_newsLabel, LV_OBJ_FLAG_HIDDEN);
    lv_timer_create(newsTimer, 8000, nullptr);

    // 首页快捷对话卡：最近一轮问答直接显示在时钟页，不需要切到对话页
    lv_obj_t* card = lv_obj_create(tile);
    lv_obj_set_size(card, s_w - 32, 140);
    lv_obj_set_pos(card, 16, 252);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x12151b), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(card, lv_color_hex(0x252a32), 0);
    lv_obj_set_style_border_width(card, 1, 0);
    lv_obj_set_style_radius(card, 14, 0);
    lv_obj_set_style_pad_all(card, 12, 0);
    lv_obj_set_style_pad_row(card, 4, 0);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t* title = uii::makeLabel(card, "最近对话", &cn20, COL_GRAY);
    lv_obj_set_width(title, lv_pct(100));

    s_quickUser = uii::makeLabel(card, "说 Hi ESP 或按住 KEY3 开始对话", &cn20, COL_CYAN);
    lv_obj_set_width(s_quickUser, lv_pct(100));
    lv_label_set_long_mode(s_quickUser, LV_LABEL_LONG_DOT);

    s_quickReply = uii::makeLabel(card, "最近一轮问答会显示在这里", &cn20, COL_WHITE);
    lv_obj_set_width(s_quickReply, lv_pct(100));
    lv_label_set_long_mode(s_quickReply, LV_LABEL_LONG_DOT);

    lv_obj_t* hint = uii::makeLabel(card, "左右滑动查看待办 / 消息 / 完整对话", &cn20, 0x5a6068);
    lv_obj_set_width(hint, lv_pct(100));
    lv_label_set_long_mode(hint, LV_LABEL_LONG_DOT);
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

// 滑动/切页结束后延迟做一次整屏重绘，消除 QSPI 局刷残留的黑色横纹/缺失块
static lv_timer_t* s_refreshTimer = nullptr;

static void refreshScreenCb(lv_timer_t* t) {
    s_refreshTimer = nullptr;
    lv_obj_invalidate(lv_screen_active());
    lv_refr_now(nullptr);
    lv_timer_del(t);
}

static void refreshTileAfterScroll(lv_event_t*) {
    if (s_refreshTimer) {
        lv_timer_reset(s_refreshTimer);
    } else {
        s_refreshTimer = lv_timer_create(refreshScreenCb, 90, nullptr);
    }
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
    lv_obj_set_style_anim_duration(s_tv, 0, 0);   // 页面不再滑动动画，避免 QSPI 局刷撕裂

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

    lv_obj_add_event_cb(s_tv, refreshTileAfterScroll, LV_EVENT_SCROLL_END, nullptr);
    lv_obj_add_event_cb(s_tv, refreshTileAfterScroll, LV_EVENT_VALUE_CHANGED, nullptr);

    // 铃铛点击 → 消息页（s_tv 已创建；事件回调在 LVGL 任务内，直接切页不取锁）
    lv_obj_add_event_cb(s_bellBox, [](lv_event_t* e) {
        lv_obj_t* tv = (lv_obj_t*)lv_event_get_user_data(e);
        lv_tileview_set_tile_by_index(tv, 2, 0, LV_ANIM_OFF);
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
    // 全屏 PSRAM 渲染缓冲：QSPI 局刷在滑动后会出现跳行/黑纹，改为整屏刷新。
    // 不占内部 RAM，TLS/ESP-SR 内存不受影响。
    size_t bufSize = (size_t)s_w * s_h * 2;
    uint8_t* buf = (uint8_t*)heap_caps_malloc(bufSize, MALLOC_CAP_SPIRAM);
    if (!buf) return false;
    lv_display_set_buffers(s_disp, buf, nullptr, bufSize, LV_DISPLAY_RENDER_MODE_FULL);

    lv_indev_t* indev = lv_indev_create();
    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_display(indev, s_disp);
    lv_indev_set_read_cb(indev, touch_cb);

    lv_theme_default_init(s_disp, lv_color_hex(COL_CYAN), lv_color_hex(COL_GREEN), true, &cn20);

    s_mux = xSemaphoreCreateMutex();
    buildRoot();
    lv_screen_load(s_root);

    // ESP-SR now runs on core 0; give LVGL a higher priority on core 1 so
    // touch/scroll/clock stay responsive while HTTP runs in loopTask.
    xTaskCreatePinnedToCore(lvglTask, "lvgl", 8192, nullptr, 4, nullptr, 1);
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
    if (!text) text = "";
    static char lastText[64] = "";
    static uint32_t lastColor = 0xffffffff;
    uii::lock();
    if (!strcmp(lastText, text) && lastColor == color) {
        uii::unlock();
        return;
    }
    snprintf(lastText, sizeof(lastText), "%s", text);
    lastColor = color;
    lv_label_set_text(s_stateLabel, text);
    lv_obj_set_style_text_color(s_stateLabel, lv_color_hex(color), 0);
    uii::unlock();
}

void setBattery(int pct, bool charging, bool pmuOk) {
    if (!s_ready) return;
    static int lastPct = -999;
    static bool lastChg = false, lastPmu = true;
    uii::lock();
    if (pct == lastPct && charging == lastChg && pmuOk == lastPmu) {
        uii::unlock();
        return;
    }
    lastPct = pct;
    lastChg = charging;
    lastPmu = pmuOk;

    if (!pmuOk) {
        lv_label_set_text(s_battIcon, LV_SYMBOL_WARNING);
        lv_obj_set_style_text_color(s_battIcon, lv_color_hex(COL_RED), 0);
        lv_label_set_text(s_battLabel, "PMU!");
        lv_obj_set_style_text_color(s_battLabel, lv_color_hex(COL_RED), 0);
    } else if (pct < 0) {
        lv_label_set_text(s_battIcon, LV_SYMBOL_BATTERY_EMPTY);
        lv_obj_set_style_text_color(s_battIcon, lv_color_hex(COL_GREEN), 0);
        lv_label_set_text(s_battLabel, "USB");
        lv_obj_set_style_text_color(s_battLabel, lv_color_hex(COL_GREEN), 0);
    } else {
        const char* sym = pct >= 90 ? LV_SYMBOL_BATTERY_FULL
                        : pct >= 65 ? LV_SYMBOL_BATTERY_3
                        : pct >= 40 ? LV_SYMBOL_BATTERY_2
                        : pct >= 15 ? LV_SYMBOL_BATTERY_1
                        : LV_SYMBOL_BATTERY_EMPTY;
        lv_label_set_text(s_battIcon, sym);
        uint32_t c = pct > 50 ? COL_GREEN : (pct > 20 ? COL_YELLOW : COL_RED);
        lv_obj_set_style_text_color(s_battIcon, lv_color_hex(c), 0);
        char b[8];
        snprintf(b, sizeof(b), "%d%%", pct);
        lv_label_set_text(s_battLabel, b);
        lv_obj_set_style_text_color(s_battLabel, lv_color_hex(c), 0);
    }
    if (charging && pmuOk) lv_obj_clear_flag(s_chgIcon, LV_OBJ_FLAG_HIDDEN);
    else                 lv_obj_add_flag(s_chgIcon, LV_OBJ_FLAG_HIDDEN);
    uii::unlock();
}

void setWifi(bool ok, int bars) {
    if (!s_ready) return;
    static int last = -1;
    int key = ok ? (100 + bars) : 0;
    if (key == last) return;
    last = key;
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
    static int last = -1;
    if ((int)loggedIn == last) return;
    last = loggedIn;
    uii::lock();
    lv_obj_set_style_bg_color(s_oaDot,
        lv_color_hex(loggedIn ? COL_CYAN : COL_ORANGE), 0);
    uii::unlock();
}

void setUnread(int n) {
    if (!s_ready) return;
    static int last = -2;
    if (n == last) return;
    last = n;
    uii::lock();
    if (n < 0) {
        lv_obj_add_flag(s_bellBox, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_unreadBadge, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_unreadBadge, "");
    } else {
        lv_obj_clear_flag(s_bellBox, LV_OBJ_FLAG_HIDDEN);
        if (n == 0) {
            lv_obj_add_flag(s_unreadBadge, LV_OBJ_FLAG_HIDDEN);
            lv_label_set_text(s_unreadBadge, "");
            lv_obj_set_style_text_color(s_bellIcon, lv_color_hex(COL_GRAY), 0);
        } else {
            char b[8];
            snprintf(b, sizeof(b), n > 9 ? "9+" : "%d", n);
            lv_label_set_text(s_unreadBadge, b);
            lv_obj_clear_flag(s_unreadBadge, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_style_text_color(s_bellIcon, lv_color_hex(COL_YELLOW), 0);
        }
    }
    uii::unlock();
}

void setTime(const struct tm& ti) {
    if (!s_ready) return;
    bool valid = (ti.tm_year + 1900) >= 2024;
    char timeBuf[8];
    char dateBuf[40];
    if (valid) {
        strftime(timeBuf, sizeof(timeBuf), "%H:%M", &ti);
        static const char* WD[] = {"日", "一", "二", "三", "四", "五", "六"};
        snprintf(dateBuf, sizeof(dateBuf), "%04d-%02d-%02d 星期%s",
                 ti.tm_year + 1900, ti.tm_mon + 1, ti.tm_mday, WD[ti.tm_wday]);
    } else {
        snprintf(timeBuf, sizeof(timeBuf), "--:--");
        snprintf(dateBuf, sizeof(dateBuf), "等待时间同步 ...");
    }

    static char lastTime[8] = "";
    static char lastDate[40] = "";
    if (!strcmp(lastTime, timeBuf) && !strcmp(lastDate, dateBuf)) return;

    uii::lock();
    if (strcmp(lastTime, timeBuf)) {
        snprintf(lastTime, sizeof(lastTime), "%s", timeBuf);
        lv_label_set_text(s_timeLabel, timeBuf);
        lv_obj_set_style_text_color(s_timeLabel,
            lv_color_hex(valid ? 0xf2f4f6 : COL_GRAY), 0);
    }
    if (strcmp(lastDate, dateBuf)) {
        snprintf(lastDate, sizeof(lastDate), "%s", dateBuf);
        lv_label_set_text(s_dateLabel, dateBuf);
    }
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
    lv_tileview_set_tile_by_index(s_tv, 3, 0, LV_ANIM_OFF);
    uii::unlock();
}

void showNotifPage() {
    if (!s_ready) return;
    uii::lock();
    lv_tileview_set_tile_by_index(s_tv, 2, 0, LV_ANIM_OFF);
    uii::unlock();
}

}  // namespace ui

// ---- 首页快捷对话卡（ui_chat.cpp 通过 ui_internal.h 调用）----
namespace uii {

void quickChat(const char* role, const char* text) {
    if (!s_ready || !s_quickUser || !s_quickReply || !text) return;
    uii::lock();
    if (role && !strcmp(role, "user")) {
        s_lastReply[0] = 0;
        lv_label_set_text_fmt(s_quickUser, "你：%s", text);
        lv_label_set_text(s_quickReply, "正在思考 ...");
    } else {
        snprintf(s_lastReply, sizeof(s_lastReply), "%s", text);
        lv_label_set_text(s_quickReply, text);
    }
    uii::unlock();
}

void quickStatus(const char* text) {
    if (!s_ready || !s_quickReply) return;
    uii::lock();
    if (text) lv_label_set_text(s_quickReply, text);
    else lv_label_set_text(s_quickReply,
        s_lastReply[0] ? s_lastReply : "最近一轮问答会显示在这里");
    uii::unlock();
}

void quickClear() {
    if (!s_ready || !s_quickUser) return;
    uii::lock();
    s_lastReply[0] = 0;
    lv_label_set_text(s_quickUser, "说 Hi ESP 或按住 KEY3 开始对话");
    lv_label_set_text(s_quickReply, "最近一轮问答会显示在这里");
    uii::unlock();
}

}  // namespace uii

