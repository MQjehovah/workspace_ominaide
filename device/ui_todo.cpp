/**
 * ui_todo.cpp —— 待办页：OmniAide 摘要（未完成待办 + 即将开始的日程）
 * 待办圆圈可点击：标记完成态（划线+填充）并入队，主循环异步调后端完成接口。
 */
#include "ui.h"
#include "ui_internal.h"
#include "ui_fonts.h"

// ---- 主题色（与 ui.cpp 保持一致）----
static const uint32_t COL_BG     = 0x000000;
static const uint32_t COL_SILVER = 0xc8ccd0;
static const uint32_t COL_GRAY   = 0x808488;
static const uint32_t COL_CYAN   = 0x00e5ff;
static const uint32_t COL_GREEN  = 0x4caf50;
static const uint32_t COL_RED    = 0xff5252;
static const uint32_t COL_ORANGE = 0xffab40;
static const uint32_t COL_DIV    = 0x282c34;

// ---- 控件（文件内静态，uii::todoInit 与 ui::setBrief 共用）----
static lv_obj_t* s_hdrLabel = nullptr;     // "待办" / 连接状态提示
static lv_obj_t* s_hdrTime = nullptr;      // 服务器时间
static lv_obj_t* s_list = nullptr;         // 待办 + 日程 滚动列表

// ---- 待办完成请求队列（生产者=LVGL 事件回调，消费者=主循环）----
static int      s_reqQ[8];
static volatile uint8_t s_qHead = 0, s_qTail = 0;

// ---- 待办行：圆圈标记 + 标题（点击圆圈 = 完成待办）----
// 点击回调运行在 LVGL 任务持锁上下文：直接改控件样式 + 入队，不取锁
static void todoRow(lv_obj_t* parent, int id, const char* title) {
    lv_obj_t* row = lv_obj_create(parent);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(row, 10, 0);

    lv_obj_t* mark = lv_obj_create(row);
    lv_obj_remove_style_all(mark);
    lv_obj_set_size(mark, 18, 18);
    lv_obj_set_style_radius(mark, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(mark, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(mark, 2, 0);
    lv_obj_set_style_border_color(mark, lv_color_hex(COL_GREEN), 0);
    lv_obj_add_flag(mark, LV_OBJ_FLAG_CLICKABLE);

    lv_obj_t* label = uii::makeLabel(row, title, &cn20, COL_SILVER);
    lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
    lv_obj_set_flex_grow(label, 1);

    // mark.user_data = 待办 id；event user_data = 标题 label
    lv_obj_set_user_data(mark, (void*)(uintptr_t)id);
    lv_obj_add_event_cb(mark, [](lv_event_t* e) {
        lv_obj_t* m = (lv_obj_t*)lv_event_get_current_target(e);
        lv_obj_t* l = (lv_obj_t*)lv_event_get_user_data(e);
        lv_obj_set_style_bg_color(m, lv_color_hex(COL_GREEN), 0);
        lv_obj_set_style_bg_opa(m, LV_OPA_COVER, 0);
        lv_obj_set_style_text_color(l, lv_color_hex(0x606870), 0);
        lv_obj_set_style_text_decor(l, LV_TEXT_DECOR_STRIKETHROUGH, 0);
        uint8_t next = (uint8_t)((s_qHead + 1) % 8);
        if (next != s_qTail) {
            s_reqQ[s_qHead] = (int)(uintptr_t)lv_obj_get_user_data(m);
            s_qHead = next;
        }
    }, LV_EVENT_CLICKED, label);
}

static void eventRow(lv_obj_t* parent, const char* text) {
    lv_obj_t* l = uii::makeLabel(parent, text, &cn20, COL_SILVER);
    lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
    lv_obj_set_width(l, lv_pct(100));
}

static void sectionHeader(lv_obj_t* parent, const char* text) {
    lv_obj_t* l = uii::makeLabel(parent, text, &cn20, COL_CYAN);
    lv_obj_set_style_pad_top(l, 6, 0);
}

// 未配置后端：给出可操作的手机配网步骤，而不是开发提示
static void setupCard(lv_obj_t* parent) {
    lv_obj_t* card = lv_obj_create(parent);
    lv_obj_set_size(card, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x14161c), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(card, lv_color_hex(0x2a3038), 0);
    lv_obj_set_style_border_width(card, 1, 0);
    lv_obj_set_style_radius(card, 12, 0);
    lv_obj_set_style_pad_all(card, 14, 0);
    lv_obj_set_style_pad_row(card, 8, 0);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    uii::makeLabel(card, "连接 OmniAide", &cn20, COL_CYAN);

    lv_obj_t* tip = uii::makeLabel(card, "设备还没有配置后端地址，请用手机完成配网：",
                                   &cn20, COL_SILVER);
    lv_obj_set_width(tip, lv_pct(100));
    lv_label_set_long_mode(tip, LV_LABEL_LONG_WRAP);

    lv_obj_t* steps = uii::makeLabel(card,
        "1. 进入设置页 → 配网模式\n"
        "2. 手机连接热点 SmartAssistant-Setup\n"
        "3. 浏览器打开 http://192.168.4.1\n"
        "4. 填写 WiFi、后端地址和账号",
        &cn20, COL_GRAY);
    lv_obj_set_width(steps, lv_pct(100));
    lv_label_set_long_mode(steps, LV_LABEL_LONG_WRAP);

    lv_obj_t* btn = lv_btn_create(card);
    lv_obj_set_size(btn, 168, 42);
    lv_obj_set_style_bg_color(btn, lv_color_hex(COL_CYAN), 0);
    lv_obj_set_style_radius(btn, 12, 0);
    lv_obj_set_style_pad_all(btn, 0, 0);
    lv_obj_add_event_cb(btn, [](lv_event_t*) { uii::requestPortal(); },
                        LV_EVENT_CLICKED, nullptr);
    lv_obj_t* bl = uii::makeLabel(btn, "进入配网模式", &cn20, 0x061014);
    lv_obj_center(bl);
}

namespace uii {

void todoInit(lv_obj_t* tile) {
    lv_obj_set_style_pad_all(tile, 14, 0);
    lv_obj_set_flex_flow(tile, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(tile, 6, 0);

    // 头部：标题 + 服务器时间
    lv_obj_t* hdr = lv_obj_create(tile);
    lv_obj_remove_style_all(hdr);
    lv_obj_set_size(hdr, lv_pct(100), 26);
    lv_obj_set_flex_flow(hdr, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    s_hdrLabel = uii::makeLabel(hdr, "今天", &cn20, COL_CYAN);
    lv_obj_t* spacer = lv_obj_create(hdr);
    lv_obj_remove_style_all(spacer);
    lv_obj_set_flex_grow(spacer, 1);
    s_hdrTime = uii::makeLabel(hdr, "", &cn20, COL_GRAY);

    // 列表（滚动）
    s_list = lv_obj_create(tile);
    lv_obj_remove_style_all(s_list);
    lv_obj_set_size(s_list, lv_pct(100), 0);
    lv_obj_set_flex_flow(s_list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(s_list, 10, 0);
    lv_obj_set_flex_grow(s_list, 1);
    lv_obj_add_flag(s_list, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(s_list, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(s_list, LV_SCROLLBAR_MODE_OFF);
}

}  // namespace uii

namespace ui {

bool popCompleteReq(int& todoId) {
    if (s_qTail == s_qHead) return false;
    todoId = s_reqQ[s_qTail];
    s_qTail = (uint8_t)((s_qTail + 1) % 8);
    return true;
}

void setBrief(const Brief& b) {
    if (!uii::ready()) return;

    // 时钟页天气：在取锁之前调用，setWeather 内部会自行加锁。
    setWeather(b.weatherTemp, b.weatherCode);
    uii::settingsSetConnection(b.configured, b.loggedIn);

    uii::lock();
    lv_label_set_text(s_hdrTime, b.serverTime);
    lv_obj_clean(s_list);

    // 首页「下一项日程」
    if (!b.configured || b.eventCnt == 0) {
        uii::homeNextEvent(nullptr);
    } else {
        char line[96];
        snprintf(line, sizeof(line), "下一项 · %s", b.events[0]);
        uii::homeNextEvent(line);
    }

    if (!b.configured) {
        lv_obj_set_style_text_color(s_hdrLabel, lv_color_hex(COL_ORANGE), 0);
        lv_label_set_text(s_hdrLabel, "今天");
        setupCard(s_list);
        uii::unlock();
        return;
    }
    lv_label_set_text(s_hdrLabel, "今天");
    lv_obj_set_style_text_color(s_hdrLabel, lv_color_hex(COL_CYAN), 0);

    if (!b.loggedIn) {
        uii::makeLabel(s_list, "正在连接后端 ...", &cn20, COL_ORANGE);
        uii::makeLabel(s_list, "若长时间无响应，请到设置页检查 WiFi 与后端地址",
                       &cn20, COL_GRAY);
        uii::unlock();
        return;
    }

    if (b.todoCnt == 0) {
        uii::makeLabel(s_list, "没有待办，享受今天 ✓", &cn20, COL_GREEN);
    } else {
        for (int i = 0; i < b.todoCnt && i < 8; i++)
            todoRow(s_list, b.todoId[i], b.todoTitle[i]);
    }

    if (b.eventCnt) {
        lv_obj_t* div = lv_obj_create(s_list);
        lv_obj_remove_style_all(div);
        lv_obj_set_size(div, lv_pct(100), 2);
        lv_obj_set_style_bg_color(div, lv_color_hex(COL_DIV), 0);
        lv_obj_set_style_bg_opa(div, LV_OPA_COVER, 0);
        sectionHeader(s_list, "日程");
        for (int i = 0; i < b.eventCnt && i < 6; i++)
            eventRow(s_list, b.events[i]);
    }

    uii::unlock();
}

}  // namespace ui
