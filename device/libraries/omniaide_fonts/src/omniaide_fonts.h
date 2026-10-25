#pragma once
#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 20px Chinese font: ASCII + GB2312 level-1 + punctuation, 2bpp */
extern const lv_font_t cn20;

/* 92px clock digits: 0-9 : % . - space, 4bpp */
extern const lv_font_t num92;

#ifdef __cplusplus
}
#endif
