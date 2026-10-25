/**
 * ui_notif.cpp —— 消息页：OmniAide 通知中心（列表 / 未读点 / 点击已读 / 全部已读）
 */
#include "ui.h"
#include "ui_internal.h"
#include "ui_fonts.h"

// ---- 主题色（与 ui.cpp 保持一致）----
static const uint32_t COL_SILVER = 0xc8ccd0;
static const uint32_t COL_GRAY   = 0x808488;
static const uint32_t COL_CYAN   = 0x00e5ff;
static const uint32_t COL_YELLOW = 0xffd740;
static const uint32_t COL_GREEN  = 0x4caf50;
static const uint32_t COL_ORANGE = 0xffab40;
static const uint32_t COL_CARD   = 0x14161c;

// ---- 控件 ----
static lv_obj_t* s_list = nullptr;        // 通知滚动列表

// ---- 已读请求队列（生产者=LVGL 事件回调，消费者=主循环）----
static int      s_readQ[8];
static volatile uint8_t s_qHead = 0, s_qTail = 0;
static volatile bool    s_readAllReq = false;

namespace uii {

void notifInit(lv_obj_t* tile) {
    lv_obj_set_style_pad_all(tile, 14, 0);
    lv_obj_set_flex_flow(tile, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(tile, 8, 0);

    // 头部：标题 + 全部已读按钮（点击回调在 LVGL 任务内，只置标志）
    lv_obj_t* hdr = lv_obj_create(tile);
    lv_obj_remove_style_all(hdr);
    lv_obj_set_size(hdr, lv_pct(100), 26);
    lv_obj_set_flex_flow(hdr, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    uii::makeLabel(hdr, "消息", &cn20, COL_CYAN);
    lv_obj_t* spacer = lv_obj_create(hdr);
    lv_obj_remove_style_all(spacer);
    lv_obj_set_flex_grow(spacer, 1);
    lv_obj_t* allBtn = lv_btn_create(hdr);
    lv_obj_set_size(allBtn, 96, 24);
    lv_obj_set_style_bg_color(allBtn, lv_color_hex(0x20242c), 0);
    lv_obj_set_style_border_width(allBtn, 0, 0);
    lv_obj_set_style_radius(allBtn, 12, 0);
    lv_obj_set_style_pad_all(allBtn, 0, 0);
    lv_obj_add_event_cb(allBtn, [](lv_event_t*) { s_readAllReq = true; }, LV_EVENT_CLICKED, nullptr);
    lv_obj_t* bl = uii::makeLabel(allBtn, "全部已读", &cn20, COL_SILVER);
    lv_obj_center(bl);

    // 通知列表（滚动）
    s_list = lv_obj_create(tile);
    lv_obj_remove_style_all(s_list);
    lv_obj_set_size(s_list, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(s_list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(s_list, 12, 0);
    lv_obj_set_flex_grow(s_list, 1);
}

}  // namespace uii

namespace ui {

// 单条通知：未读点 + 标题/时间行 + 正文（点击 = 标记已读）
static void notifRow(lv_obj_t* parent, const Notif& n) {
    lv_obj_t* card = lv_obj_create(parent);
    lv_obj_set_size(card, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(card, lv_color_hex(n.unread ? COL_CARD : 0x0c0e12), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, n.unread ? 1 : 0, 0);
    lv_obj_set_style_border_color(card, lv_color_hex(0x2a3038), 0);
    lv_obj_set_style_radius(card, 10, 0);
    lv_obj_set_style_pad_all(card, 10, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);
    if (n.unread) lv_obj_add_flag(card, LV_OBJ_FLAG_CLICKABLE);

    // 标题行：未读圆点 + 标题 + 时间
    lv_obj_t* row = lv_obj_create(card);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(row, 8, 0);

    lv_obj_t* dot = lv_obj_create(row);
    lv_obj_remove_style_all(dot);
    lv_obj_set_size(dot, 10, 10);
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(dot, lv_color_hex(n.unread ? COL_YELLOW : 0x30343c), 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);

    lv_obj_t* title = uii::makeLabel(row, n.title, &cn20, n.unread ? COL_SILVER : COL_GRAY);
    lv_label_set_long_mode(title, LV_LABEL_LONG_DOT);
    lv_obj_set_flex_grow(title, 1);

    lv_obj_t* tm = uii::makeLabel(row, n.time, &cn20, COL_GRAY);

    // 正文（最多两行）
    if (n.body[0]) {
        lv_obj_t* body = uii::makeLabel(card, n.body, &cn20, n.unread ? 0xa8b0b8 : 0x606870);
        lv_label_set_long_mode(body, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(body, lv_pct(100));
    }

    // 点击已读：直接置灰并入队（LVGL 任务持锁上下文）
    if (n.unread) {
        lv_obj_set_user_data(card, (void*)(uintptr_t)n.id);
        lv_obj_add_event_cb(card, [](lv_event_t* e) {
            lv_obj_t* c = (lv_obj_t*)lv_event_get_current_target(e);
            lv_obj_set_style_bg_color(c, lv_color_hex(0x0c0e12), 0);
            lv_obj_set_style_border_width(c, 0, 0);
            uint8_t next = (uint8_t)((s_qHead + 1) % 8);
            if (next != s_qTail) {
                s_readQ[s_qHead] = (int)(uintptr_t)lv_obj_get_user_data(c);
                s_qHead = next;
            }
        }, LV_EVENT_CLICKED, nullptr);
    }
}

void setNotifs(const Notif* items, int cnt) {
    if (!uii::ready()) return;
    uii::lock();
    lv_obj_clean(s_list);

    if (cnt == 0) {
        uii::makeLabel(s_list, "暂无通知", &cn20, COL_GRAY);
    } else {
        for (int i = 0; i < cnt; i++) notifRow(s_list, items[i]);
    }
    uii::unlock();
}

bool popNotifReadReq(int& notifId) {
    if (s_qTail == s_qHead) return false;
    notifId = s_readQ[s_qTail];
    s_qTail = (uint8_t)((s_qTail + 1) % 8);
    return true;
}

bool popNotifReadAll() {
    if (!s_readAllReq) return false;
    s_readAllReq = false;
    return true;
}

}  // namespace ui
