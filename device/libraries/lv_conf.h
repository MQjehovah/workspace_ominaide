/**
 * lv_conf.h —— OmniAide 设备端 LVGL 9.2 配置
 *
 * 只写与 lv_conf_template.h 默认值不同的项，其余走 LVGL 内建默认。
 * 位置要求：lvgl/src/** 通过 ../../lv_conf.h 找到本文件（libraries 根目录）。
 */
#ifndef LV_CONF_H
#define LV_CONF_H

/* ==================== 内存 ====================
 * ESP-SR 会占用大量内部 RAM。LVGL 的对象/样式/字体缓存改用内置分配器，
 * 内存池放在 PSRAM，给 HTTPS/TLS 留出内部 RAM。*/
#define LV_USE_STDLIB_MALLOC        LV_STDLIB_BUILTIN
#define LV_MEM_SIZE                 (128 * 1024U)
#define LV_MEM_ADR                  0
#define LV_MEM_POOL_INCLUDE         <esp_heap_caps.h>
#define LV_MEM_POOL_ALLOC(x)        heap_caps_malloc(x, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)

/* ==================== 字体 ====================
 * montserrat_16 仅作图标符号字体（FontAwesome 子集：WiFi/电池/充电等）；
 * 中文与正文用黑体子集 cn20（ASCII+GB2312 一级汉字，2bpp 压缩），
 * 大号时钟数字用 num92。字体本体在 device/ui/font_*.c */
#define LV_FONT_MONTSERRAT_14       0
#define LV_FONT_MONTSERRAT_16       1
#define LV_FONT_CUSTOM_DECLARE      extern const lv_font_t cn20; extern const lv_font_t num92;
#define LV_FONT_DEFAULT             &cn20
#define LV_USE_FONT_COMPRESSED      1

/* ==================== 裁剪不用的部件（省 flash） ==================== */
#define LV_USE_ANIMIMG              0
#define LV_USE_CALENDAR             0
#define LV_USE_CHART                0
#define LV_USE_CHECKBOX             0
#define LV_USE_DROPDOWN             0
#define LV_USE_IMAGEBUTTON          0
#define LV_USE_KEYBOARD             0
#define LV_USE_LED                  0
#define LV_USE_ROLLER               0
#define LV_USE_SCALE                0
#define LV_USE_SLIDER               1
#define LV_USE_SPAN                 0
#define LV_USE_SPINBOX              0   /* 依赖 TEXTAREA */
#define LV_USE_SWITCH               0
#define LV_USE_TABLE                0
#define LV_USE_TEXTAREA             0
#define LV_USE_WIN                  0

#endif  /* LV_CONF_H */
