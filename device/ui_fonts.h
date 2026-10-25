/**
 * ui_fonts.h —— LVGL 自定义字体（lv_font_conv 生成，见 font_cn20.c / font_num92.c）
 */
#pragma once
#include "lvgl.h"

/* 20px 中文黑体：ASCII + GB2312 一级汉字 + 常用全角标点，2bpp 压缩 */
extern const lv_font_t cn20;

/* 92px 时钟数字：0-9 : % . - 空格，4bpp 压缩 */
extern const lv_font_t num92;
