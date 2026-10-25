/**
 * imu.h —— 板载 QMI8658 六轴 + 手势识别（翻转/摇一摇/双击）
 * 手势事件 → OmniAide 后端 → Home Assistant
 */
#pragma once
#include <Arduino.h>

class ImuGesture {
public:
    bool begin();                       // QMI8658 初始化（失败返回 false）
    // 轮询（loop 每 50~100ms 调一次）。检测到手势时返回手势名，否则 nullptr
    const char* tick();
    // 最近一次加速度（诊断用）
    float ax = 0, ay = 0, az = 1;
private:
    bool _flipArmed = false;            // 已进入"屏幕朝下"状态
    uint32_t _flipSince = 0;
    uint32_t _tapLast = 0;
    uint32_t _shakeSince = 0;
    uint32_t _coolDown = 0;             // 手势全局冷却
};
