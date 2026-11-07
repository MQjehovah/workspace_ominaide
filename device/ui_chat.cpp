/**
 * ui_chat.cpp —— 对话页：历史消息气泡 + 录音音量条/处理中转圈覆盖层
 */
#include "ui.h"
#include "ui_internal.h"
#include "ui_fonts.h"

// ---- 主题色（与 ui.cpp 保持一致）----
static const uint32_t COL_CARD   = 0x1c1e24;
static const uint32_t COL_SILVER = 0xc8ccd0;
static const uint32_t COL_WHITE  = 0xf2f4f6;
static const uint32_t COL_CYAN   = 0x00e5ff;
static const uint32_t COL_GREEN  = 0x4caf50;
static const uint32_t COL_RED    = 0xff5252;

// ---- 控件（文件内静态，uii::chatInit 与 ui::* 共用）----
static lv_obj_t* s_scroll = nullptr;    // 消息滚动容器
static lv_obj_t* s_overlay = nullptr;   // 底部覆盖层
static lv_obj_t* s_spinner = nullptr;
static lv_obj_t* s_ovText = nullptr;
static lv_obj_t* s_volBar = nullptr;

// 覆盖层可见状态（供 recUpdate 跳过无效更新；读写均持锁）
static bool s_recOn = false;

// 消息上限：超出后删最旧的，防内存膨胀
static constexpr int MAX_MSGS = 14;

namespace uii {

void chatInit(lv_obj_t* tile) {
    const int cw = contentWidth();
    const int ch = contentHeight();

    // 消息滚动区（覆盖层占底部 84px）
    s_scroll = lv_obj_create(tile);
    lv_obj_remove_style_all(s_scroll);
    lv_obj_set_size(s_scroll, cw, ch - 84);
    lv_obj_set_style_pad_all(s_scroll, 14, 0);
    lv_obj_set_flex_flow(s_scroll, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(s_scroll, 14, 0);
    lv_obj_add_flag(s_scroll, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(s_scroll, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(s_scroll, LV_SCROLLBAR_MODE_OFF);

    // 底部覆盖层：转圈 + 文本 + 录音音量条
    s_overlay = lv_obj_create(tile);
    lv_obj_remove_style_all(s_overlay);
    lv_obj_set_size(s_overlay, cw, 84);
    lv_obj_set_pos(s_overlay, 0, ch - 84);
    lv_obj_add_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);

    s_spinner = lv_spinner_create(s_overlay);
    lv_obj_set_size(s_spinner, 36, 36);
    lv_obj_set_pos(s_spinner, 14, 4);
    lv_obj_set_style_arc_color(s_spinner, lv_color_hex(COL_CYAN), LV_PART_INDICATOR);

    s_ovText = uii::makeLabel(s_overlay, "", &cn20, COL_WHITE);
    lv_obj_set_pos(s_ovText, 62, 12);

    s_volBar = lv_bar_create(s_overlay);
    lv_bar_set_range(s_volBar, 0, 100);
    lv_obj_set_size(s_volBar, cw - 28, 14);
    lv_obj_set_pos(s_volBar, 14, 52);
    lv_obj_set_style_bg_color(s_volBar, lv_color_hex(0x20242a), 0);
    lv_obj_set_style_bg_opa(s_volBar, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(s_volBar, lv_color_hex(0x3a4048), 0);
    lv_obj_set_style_border_width(s_volBar, 1, 0);
    lv_obj_set_style_radius(s_volBar, 6, 0);
    lv_obj_set_style_bg_color(s_volBar, lv_color_hex(COL_GREEN), LV_PART_INDICATOR);
    lv_obj_set_style_radius(s_volBar, 4, LV_PART_INDICATOR);
    lv_bar_set_value(s_volBar, 0, LV_ANIM_OFF);
}

}  // namespace uii

namespace ui {

static void trimOld() {
    uint32_t n = lv_obj_get_child_cnt(s_scroll);
    if (n <= MAX_MSGS) return;
    lv_obj_del(lv_obj_get_child(s_scroll, 0));
}

static void scrollEnd() {
    lv_obj_update_layout(s_scroll);
    lv_obj_scroll_to_y(s_scroll, LV_COORD_MAX, LV_ANIM_OFF);
}

void chatClear() {
    if (!uii::ready()) return;
    uii::lock();
    lv_obj_clean(s_scroll);
    uii::unlock();
    uii::quickClear();
}

void chatAppend(const char* role, const char* text) {
    if (!text || !text[0]) text = "（未取到文本）";
    if (!uii::ready()) return;
    uii::lock();

    if (role && !strcmp(role, "user")) {
        // 用户问题：深灰圆角气泡，右对齐；量宽决定单行/换行
        const int maxW = uii::contentWidth() - 80;
        lv_point_t size;
        lv_text_get_size(&size, text, &cn20, 0, 0, maxW, LV_TEXT_FLAG_NONE);
        int lw = size.x < maxW ? size.x : maxW;

        lv_obj_t* row = lv_obj_create(s_scroll);
        lv_obj_remove_style_all(row);
        lv_obj_set_width(row, lv_pct(100));
        lv_obj_set_height(row, LV_SIZE_CONTENT);
        lv_obj_set_flex_align(row, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

        lv_obj_t* bubble = lv_obj_create(row);
        lv_obj_set_size(bubble, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
        lv_obj_set_style_bg_color(bubble, lv_color_hex(COL_CARD), 0);
        lv_obj_set_style_bg_opa(bubble, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(bubble, 0, 0);
        lv_obj_set_style_radius(bubble, 12, 0);
        lv_obj_set_style_pad_all(bubble, 10, 0);
        lv_obj_clear_flag(bubble, LV_OBJ_FLAG_SCROLLABLE);

        lv_obj_t* l = uii::makeLabel(bubble, text, &cn20, COL_SILVER);
        lv_label_set_long_mode(l, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(l, lw);
        trimOld();
    } else {
        // 助手回答：正文直出，自动换行
        lv_obj_t* l = uii::makeLabel(s_scroll, text, &cn20, COL_WHITE);
        lv_label_set_long_mode(l, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(l, uii::contentWidth() - 28);
        trimOld();
    }
    scrollEnd();

    uii::unlock();
    uii::quickChat(role, text);
}

void recShow(bool on) {
    if (!uii::ready()) return;
    uii::lock();
    s_recOn = on;
    if (on) {
        lv_obj_clear_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_volBar, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_spinner, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_ovText, "录音中 0s");
        lv_bar_set_value(s_volBar, 0, LV_ANIM_OFF);
    } else {
        lv_obj_add_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);
    }
    uii::unlock();
    uii::quickStatus(on ? "正在聆听 ..." : nullptr);
}

void recUpdate(int peak, uint32_t secs) {
    if (!s_recOn) return;
    uii::lock();
    int v = (int)((int64_t)peak * 100 / 24000);
    if (v < 0) v = 0;
    if (v > 100) v = 100;
    lv_bar_set_value(s_volBar, v, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(s_volBar,
        lv_color_hex(v > 80 ? COL_RED : COL_GREEN), LV_PART_INDICATOR);
    char l[24];
    snprintf(l, sizeof(l), "录音中 %lus", (unsigned long)secs);
    lv_label_set_text(s_ovText, l);
    uii::unlock();
}

void busy(const char* text) {
    if (!uii::ready()) return;
    uii::lock();
    if (!text) {
        lv_obj_add_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_clear_flag(s_overlay, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_spinner, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_volBar, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_ovText, text);
    }
    uii::unlock();
    uii::quickStatus(text);
}

}  // namespace ui
