/**
 * ui_info.cpp —— 信息页：日程 / 消息 / 资讯 三个子标签
 *
 * 复用 ui_todo.cpp 和 ui_notif.cpp 的面板实现，避免维护两套列表。
 * 回调运行在 LVGL 任务持锁上下文，内部函数不再重复加锁。
 */
#include "ui.h"
#include "ui_internal.h"
#include "ui_fonts.h"

static const uint32_t COL_BG     = 0x000000;
static const uint32_t COL_CARD   = 0x14161c;
static const uint32_t COL_SILVER = 0xc8ccd0;
static const uint32_t COL_GRAY   = 0x808488;
static const uint32_t COL_CYAN   = 0x00e5ff;

static lv_obj_t* s_tabs[3] = {nullptr, nullptr, nullptr};
static lv_obj_t* s_panels[3] = {nullptr, nullptr, nullptr};
static lv_obj_t* s_newsList = nullptr;
static lv_obj_t* s_newsEmpty = nullptr;
static int s_current = -1;

static void styleTab(int index, bool active) {
    if (!s_tabs[index]) return;
    lv_obj_set_style_bg_color(s_tabs[index],
        lv_color_hex(active ? 0x1b2a33 : 0x11151b), 0);
    lv_obj_set_style_border_width(s_tabs[index], active ? 1 : 0, 0);
    lv_obj_set_style_border_color(s_tabs[index], lv_color_hex(0x1f6f7a), 0);
    lv_obj_t* label = lv_obj_get_child(s_tabs[index], 0);
    if (label) {
        lv_obj_set_style_text_color(label,
            lv_color_hex(active ? COL_CYAN : COL_GRAY), 0);
    }
}

static void showTabInternal(int index) {
    if (index < 0 || index > 2) index = 0;
    s_current = index;
    for (int i = 0; i < 3; i++) {
        if (!s_panels[i]) continue;
        if (i == index) lv_obj_clear_flag(s_panels[i], LV_OBJ_FLAG_HIDDEN);
        else lv_obj_add_flag(s_panels[i], LV_OBJ_FLAG_HIDDEN);
        styleTab(i, i == index);
    }
}

static lv_obj_t* makeTab(lv_obj_t* parent, const char* text, int index) {
    lv_obj_t* btn = lv_btn_create(parent);
    lv_obj_set_size(btn, 104, 32);
    lv_obj_set_style_bg_color(btn, lv_color_hex(0x11151b), 0);
    lv_obj_set_style_border_width(btn, 0, 0);
    lv_obj_set_style_radius(btn, 10, 0);
    lv_obj_set_style_pad_all(btn, 0, 0);
    lv_obj_add_event_cb(btn, [](lv_event_t* e) {
        int idx = (int)(intptr_t)lv_event_get_user_data(e);
        showTabInternal(idx);
    }, LV_EVENT_CLICKED, (void*)(intptr_t)index);
    lv_obj_t* label = uii::makeLabel(btn, text, &cn20, COL_GRAY);
    lv_obj_center(label);
    s_tabs[index] = btn;
    return btn;
}

static lv_obj_t* makePanel(lv_obj_t* parent) {
    lv_obj_t* panel = lv_obj_create(parent);
    lv_obj_set_size(panel, LV_PCT(100), LV_PCT(100));
    lv_obj_set_style_bg_color(panel, lv_color_hex(COL_BG), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(panel, 0, 0);
    lv_obj_set_style_radius(panel, 0, 0);
    lv_obj_set_style_pad_all(panel, 0, 0);
    return panel;
}

namespace uii {

void infoInit(lv_obj_t* tile) {
    lv_obj_set_style_pad_all(tile, 0, 0);
    lv_obj_set_flex_flow(tile, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(tile, 0, 0);

    lv_obj_t* header = lv_obj_create(tile);
    lv_obj_remove_style_all(header);
    lv_obj_set_size(header, contentWidth(), 42);
    lv_obj_set_flex_flow(header, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(header, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(header, 8, 0);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);
    makeTab(header, "日程", 0);
    makeTab(header, "消息", 1);
    makeTab(header, "资讯", 2);

    lv_obj_t* body = lv_obj_create(tile);
    lv_obj_remove_style_all(body);
    lv_obj_set_size(body, contentWidth(), contentHeight() - 42);
    lv_obj_set_flex_grow(body, 1);
    lv_obj_set_style_pad_all(body, 0, 0);

    s_panels[0] = makePanel(body);
    todoInit(s_panels[0]);

    s_panels[1] = makePanel(body);
    notifInit(s_panels[1]);

    s_panels[2] = makePanel(body);
    lv_obj_set_style_pad_all(s_panels[2], 14, 0);
    lv_obj_set_flex_flow(s_panels[2], LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(s_panels[2], 10, 0);
    s_newsList = lv_obj_create(s_panels[2]);
    lv_obj_remove_style_all(s_newsList);
    lv_obj_set_size(s_newsList, LV_PCT(100), LV_PCT(100));
    lv_obj_set_flex_flow(s_newsList, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(s_newsList, 10, 0);
    lv_obj_add_flag(s_newsList, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(s_newsList, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(s_newsList, LV_SCROLLBAR_MODE_AUTO);

    showTabInternal(0);
    infoClearNews();
}

void infoShowTab(int index) {
    showTabInternal(index);
}

void infoClearNews() {
    if (!s_newsList) return;
    lv_obj_clean(s_newsList);
    s_newsEmpty = uii::makeLabel(s_newsList, "暂无资讯，去 Web 端添加订阅源", &cn20, COL_GRAY);
    lv_obj_set_width(s_newsEmpty, LV_PCT(100));
    lv_label_set_long_mode(s_newsEmpty, LV_LABEL_LONG_WRAP);
}

void infoAddNews(const char* title, const char* feed) {
    if (!s_newsList || !title || !title[0]) return;
    if (s_newsEmpty) { lv_obj_del(s_newsEmpty); s_newsEmpty = nullptr; }

    lv_obj_t* card = lv_obj_create(s_newsList);
    lv_obj_set_size(card, LV_PCT(100), LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(card, lv_color_hex(COL_CARD), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, 0, 0);
    lv_obj_set_style_radius(card, 12, 0);
    lv_obj_set_style_pad_all(card, 10, 0);
    lv_obj_set_style_pad_row(card, 4, 0);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t* t = uii::makeLabel(card, title, &cn20, COL_SILVER);
    lv_obj_set_width(t, LV_PCT(100));
    lv_label_set_long_mode(t, LV_LABEL_LONG_WRAP);
    if (feed && feed[0]) {
        lv_obj_t* f = uii::makeLabel(card, feed, &cn20, COL_GRAY);
        lv_obj_set_width(f, LV_PCT(100));
        lv_label_set_long_mode(f, LV_LABEL_LONG_DOT);
    }
}

}  // namespace uii
