/**
 * ui_settings.cpp —— 设置页：音量 / 亮度滑条 + 通知声音开关（NVS 持久化由主循环执行）
 *
 * 线程模型：滑条/开关回调运行在 LVGL 任务持锁上下文 → 更新待应用请求（单写单读，
 * 不取 ui 锁）；主循环 popSettingReq 取走后写硬件 + NVS。
 */
#include "ui.h"
#include "ui_internal.h"
#include "ui_fonts.h"
#include "config.h"

// ---- 主题色 ----
static const uint32_t COL_SILVER = 0xc8ccd0;
static const uint32_t COL_GRAY   = 0x808488;
static const uint32_t COL_CYAN   = 0x00e5ff;
static const uint32_t COL_GREEN  = 0x4caf50;
static const uint32_t COL_CARD   = 0x14161c;

// ---- 待应用请求（LVGL 写，主循环读；int 对齐写读原子）----
static volatile int  s_volReq = -1;
static volatile int  s_brightReq = -1;
static volatile int  s_chimeReq = -1;
static volatile int  s_otaReq = -1;
static volatile int  s_portalReq = -1;

// ---- 控件 ----
static lv_obj_t* s_volSlider = nullptr;
static lv_obj_t* s_volVal = nullptr;
static lv_obj_t* s_brightSlider = nullptr;
static lv_obj_t* s_brightVal = nullptr;
static lv_obj_t* s_chimeDot = nullptr;
static lv_obj_t* s_chimeLabel = nullptr;
static bool s_chimeOn = true;

// 连接状态卡
static lv_obj_t* s_connDot = nullptr;
static lv_obj_t* s_connLabel = nullptr;
static lv_obj_t* s_connDetail = nullptr;

namespace uii {

static lv_obj_t* rowSlider(lv_obj_t* parent, const char* name, int lo, int hi, int val,
                           lv_obj_t** slider, lv_obj_t** valLabel) {
    lv_obj_t* card = lv_obj_create(parent);
    lv_obj_set_size(card, lv_pct(100), 64);
    lv_obj_set_style_bg_color(card, lv_color_hex(COL_CARD), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, 0, 0);
    lv_obj_set_style_radius(card, 12, 0);
    lv_obj_set_style_pad_all(card, 10, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t* hdr = lv_obj_create(card);
    lv_obj_remove_style_all(hdr);
    lv_obj_set_size(hdr, lv_pct(100), 24);
    lv_obj_set_flex_flow(hdr, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    uii::makeLabel(hdr, name, &cn20, COL_SILVER);
    lv_obj_t* sp = lv_obj_create(hdr);
    lv_obj_remove_style_all(sp);
    lv_obj_set_flex_grow(sp, 1);
    *valLabel = uii::makeLabel(hdr, "", &cn20, COL_CYAN);

    *slider = lv_slider_create(card);
    lv_slider_set_range(*slider, lo, hi);
    lv_slider_set_value(*slider, val, LV_ANIM_OFF);
    lv_obj_set_size(*slider, lv_pct(100), 10);
    lv_obj_align(*slider, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(*slider, lv_color_hex(0x20242a), 0);
    lv_obj_set_style_bg_color(*slider, lv_color_hex(COL_CYAN), LV_PART_INDICATOR);
    lv_obj_set_style_pad_all(*slider, 4, LV_PART_KNOB);
    return card;
}

// 连接状态卡：一眼看出是否已连上后端，未配置时一键进配网
static void connCard(lv_obj_t* parent) {
    lv_obj_t* card = lv_obj_create(parent);
    lv_obj_set_size(card, lv_pct(100), 84);
    lv_obj_set_style_bg_color(card, lv_color_hex(COL_CARD), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, 0, 0);
    lv_obj_set_style_radius(card, 12, 0);
    lv_obj_set_style_pad_all(card, 12, 0);
    lv_obj_set_style_pad_row(card, 6, 0);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(card, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(card, [](lv_event_t*) { s_portalReq = 1; },
                        LV_EVENT_CLICKED, nullptr);

    lv_obj_t* row = lv_obj_create(card);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, lv_pct(100), 26);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(row, 8, 0);

    s_connDot = lv_obj_create(row);
    lv_obj_remove_style_all(s_connDot);
    lv_obj_set_size(s_connDot, 12, 12);
    lv_obj_set_style_radius(s_connDot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(s_connDot, lv_color_hex(COL_GRAY), 0);
    lv_obj_set_style_bg_opa(s_connDot, LV_OPA_COVER, 0);

    s_connLabel = uii::makeLabel(row, "未配置后端", &cn20, COL_SILVER);

    s_connDetail = uii::makeLabel(card, "点此进入配网模式", &cn20, COL_GRAY);
    lv_obj_set_width(s_connDetail, lv_pct(100));
    lv_label_set_long_mode(s_connDetail, LV_LABEL_LONG_DOT);
}

static void chimeRow(lv_obj_t* parent) {
    lv_obj_t* card = lv_obj_create(parent);
    lv_obj_set_size(card, lv_pct(100), 46);
    lv_obj_set_style_bg_color(card, lv_color_hex(COL_CARD), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, 0, 0);
    lv_obj_set_style_radius(card, 12, 0);
    lv_obj_set_style_pad_left(card, 12, 0);
    lv_obj_set_style_pad_right(card, 12, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(card, LV_OBJ_FLAG_CLICKABLE);

    lv_obj_t* row = lv_obj_create(card);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(row, 10, 0);

    s_chimeDot = lv_obj_create(row);
    lv_obj_remove_style_all(s_chimeDot);
    lv_obj_set_size(s_chimeDot, 16, 16);
    lv_obj_set_style_radius(s_chimeDot, LV_RADIUS_CIRCLE, 0);

    s_chimeLabel = uii::makeLabel(row, "通知声音", &cn20, COL_SILVER);

    // 点击整行切换（LVGL 任务内，直接改视觉 + 记请求）
    lv_obj_add_event_cb(card, [](lv_event_t* e) {
        lv_obj_t* c = (lv_obj_t*)lv_event_get_current_target(e);
        lv_obj_set_style_bg_color(c, lv_color_hex(0x1a1e26), 0);   // 按下反馈
        s_chimeOn = !s_chimeOn;
        s_chimeReq = s_chimeOn ? 1 : 0;
    }, LV_EVENT_CLICKED, nullptr);
}

void settingsInit(lv_obj_t* tile) {
    lv_obj_set_style_pad_all(tile, 16, 0);
    lv_obj_set_flex_flow(tile, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(tile, 12, 0);
    lv_obj_add_flag(tile, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(tile, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(tile, LV_SCROLLBAR_MODE_OFF);

    uii::makeLabel(tile, "设置", &cn20, COL_CYAN);
    connCard(tile);
    rowSlider(tile, "音量", 0, 100, 85, &s_volSlider, &s_volVal);
    rowSlider(tile, "亮度", 10, 100, 60, &s_brightSlider, &s_brightVal);
    chimeRow(tile);

    // 固件更新行（点按 = 检查/确认升级）
    lv_obj_t* otaCard = lv_obj_create(tile);
    lv_obj_set_size(otaCard, lv_pct(100), 46);
    lv_obj_set_style_bg_color(otaCard, lv_color_hex(COL_CARD), 0);
    lv_obj_set_style_bg_opa(otaCard, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(otaCard, 0, 0);
    lv_obj_set_style_radius(otaCard, 12, 0);
    lv_obj_set_style_pad_left(otaCard, 12, 0);
    lv_obj_clear_flag(otaCard, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(otaCard, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_t* otaLbl = uii::makeLabel(otaCard, "检查固件更新", &cn20, COL_SILVER);
    lv_obj_align(otaLbl, LV_ALIGN_LEFT_MID, 0, 0);
    lv_obj_add_event_cb(otaCard, [](lv_event_t* e) {
        lv_obj_set_style_bg_color((lv_obj_t*)lv_event_get_current_target(e),
                                  lv_color_hex(0x1a1e26), 0);
        s_otaReq = 1;
    }, LV_EVENT_CLICKED, nullptr);

    // 配网模式行（点按 = 重启进热点配置）
    lv_obj_t* portalCard = lv_obj_create(tile);
    lv_obj_set_size(portalCard, lv_pct(100), 46);
    lv_obj_set_style_bg_color(portalCard, lv_color_hex(COL_CARD), 0);
    lv_obj_set_style_bg_opa(portalCard, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(portalCard, 0, 0);
    lv_obj_set_style_radius(portalCard, 12, 0);
    lv_obj_set_style_pad_left(portalCard, 12, 0);
    lv_obj_clear_flag(portalCard, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(portalCard, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_t* portalLbl = uii::makeLabel(portalCard, "配网模式（热点配置）", &cn20, COL_SILVER);
    lv_obj_align(portalLbl, LV_ALIGN_LEFT_MID, 0, 0);
    lv_obj_add_event_cb(portalCard, [](lv_event_t* e) {
        lv_obj_set_style_bg_color((lv_obj_t*)lv_event_get_current_target(e),
                                  lv_color_hex(0x1a1e26), 0);
        s_portalReq = 1;
    }, LV_EVENT_CLICKED, nullptr);

    lv_obj_t* ver = uii::makeLabel(tile, "SmartAssistant " FW_VERSION " · OmniAide", &cn20, 0x3c4046);
    lv_obj_set_style_text_align(ver, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_width(ver, lv_pct(100));
}

void settingsSetConnection(bool configured, bool loggedIn) {
    if (!ready()) return;
    lock();
    if (s_connDot && s_connLabel && s_connDetail) {
        uint32_t color = 0x808488;
        const char* label = "未配置后端";
        const char* detail = "点此进入配网模式";
        if (!configured) {
            color = 0x808488;
        } else if (loggedIn) {
            color = 0x4caf50;
            label = "已连接";
            detail = "点此重新配置 WiFi / 后端";
        } else {
            color = 0xffab40;
            label = "正在连接后端 ...";
            detail = "检查 WiFi 或账号后点此重设";
        }
        lv_obj_set_style_bg_color(s_connDot, lv_color_hex(color), 0);
        lv_label_set_text(s_connLabel, label);
        lv_obj_set_style_text_color(s_connLabel, lv_color_hex(color), 0);
        lv_label_set_text(s_connDetail, detail);
    }
    unlock();
}

void requestPortal() { s_portalReq = 1; }
void requestOta()    { s_otaReq = 1; }

}  // namespace uii

namespace ui {

// 滑条值变化/开关切换 → 刷新数值标签 + 记录待应用请求（LVGL 任务上下文）
static void refreshChimeDot() {
    lv_obj_set_style_bg_color(s_chimeDot,
        lv_color_hex(s_chimeOn ? COL_GREEN : 0x30343c), 0);
    lv_obj_set_style_border_width(s_chimeDot, s_chimeOn ? 0 : 2, 0);
    lv_obj_set_style_border_color(s_chimeDot, lv_color_hex(0x30343c), 0);
}

void setSettingRefs(int vol, int bright, bool chime) {
    if (!uii::ready()) return;
    uii::lock();
    s_chimeOn = chime;
    lv_slider_set_value(s_volSlider, vol, LV_ANIM_OFF);
    lv_slider_set_value(s_brightSlider, bright, LV_ANIM_OFF);
    char b[8];
    snprintf(b, sizeof(b), "%d", vol);
    lv_label_set_text(s_volVal, b);
    snprintf(b, sizeof(b), "%d", bright);
    lv_label_set_text(s_brightVal, b);
    refreshChimeDot();

    auto track = [](lv_event_t* e) {
        lv_obj_t* s = (lv_obj_t*)lv_event_get_current_target(e);
        int v = lv_slider_get_value(s);
        if (s == s_volSlider) {
            s_volReq = v;
            char t[8]; snprintf(t, sizeof(t), "%d", v);
            lv_label_set_text(s_volVal, t);
        } else {
            s_brightReq = v;
            char t[8]; snprintf(t, sizeof(t), "%d", v);
            lv_label_set_text(s_brightVal, t);
        }
    };
    lv_obj_add_event_cb(s_volSlider, track, LV_EVENT_VALUE_CHANGED, nullptr);
    lv_obj_add_event_cb(s_brightSlider, track, LV_EVENT_VALUE_CHANGED, nullptr);
    uii::unlock();
}

bool popSettingReq(SettingReq& out) {
    out.vol = s_volReq;
    out.bright = s_brightReq;
    out.chime = s_chimeReq;
    out.ota = s_otaReq;
    out.portal = s_portalReq;
    if (out.vol < 0 && out.bright < 0 && out.chime < 0 && out.ota < 0 && out.portal < 0) return false;
    s_volReq = -1;
    s_brightReq = -1;
    s_chimeReq = -1;
    s_otaReq = -1;
    s_portalReq = -1;
    return true;
}

}  // namespace ui
