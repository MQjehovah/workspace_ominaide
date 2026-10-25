#include "imu.h"
#include <Wire.h>
#include <math.h>
#include "SensorQMI8658.hpp"

#define IIC_SDA_PIN 15
#define IIC_SCL_PIN 14

static SensorQMI8658 qmi;

bool ImuGesture::begin() {
    // QMI8658 地址 0x6B（微雪丝印 L）
    if (!qmi.begin(Wire, QMI8658_L_SLAVE_ADDRESS, IIC_SDA_PIN, IIC_SCL_PIN)) return false;
    qmi.configAccelerometer(SensorQMI8658::ACC_RANGE_8G,
                            SensorQMI8658::ACC_ODR_500Hz, SensorQMI8658::LPF_MODE_2);
    qmi.enableAccelerometer();
    return true;
}

const char* ImuGesture::tick() {
    if (!qmi.getDataReady()) return nullptr;
    float a[3];
    if (!qmi.getAccelerometer(a[0], a[1], a[2])) return nullptr;
    ax = a[0]; ay = a[1]; az = a[2];
    if (millis() < _coolDown) return nullptr;

    float mag = sqrtf(ax * ax + ay * ay + az * az);

    // ---- 双击：两次 >2.3g 尖峰，间隔 80~450ms ----
    static uint32_t lastPeak = 0;
    if (mag > 2.3f) {
        uint32_t now = millis();
        if (lastPeak && now - lastPeak > 80 && now - lastPeak < 450) {
            lastPeak = 0;
            _coolDown = now + 2500;
            return "double_tap";
        }
        lastPeak = now;
    }

    // ---- 翻转：屏幕朝下（z 由正转负）保持 800ms ----
    if (az < -0.6f) {
        if (!_flipArmed) { _flipArmed = true; _flipSince = millis(); }
        else if (millis() - _flipSince > 800) {
            _flipArmed = false;
            _coolDown = millis() + 3000;
            return "flip";
        }
    } else {
        _flipArmed = false;
    }

    // ---- 摇一摇：持续剧烈晃动 500ms（加速度模长波动 >3g）----
    static float magMax = 0, magMin = 99;
    if (mag > magMax) magMax = mag;
    if (mag < magMin) magMin = mag;
    static uint32_t shakeWin = 0;
    if (!shakeWin) shakeWin = millis();
    if (millis() - shakeWin > 500) {
        bool shook = (magMax - magMin) > 3.0f && magMax > 2.5f;
        magMax = 0; magMin = 99; shakeWin = millis();
        if (shook) {
            _coolDown = millis() + 3000;
            return "shake";
        }
    }
    return nullptr;
}
