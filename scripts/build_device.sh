#!/usr/bin/env bash
# ============================================================================
# SmartAssistant 设备端固件构建脚本（OmniAide/智能助手）
# 硬件：微雪 ESP32-S3-Touch-AMOLED-2.16（双麦+扬声器+触摸AMOLED+六轴）
#
# 用法：
#   bash scripts/build_device.sh smart_assistant              # 只编译
#   bash scripts/build_device.sh smart_assistant upload COM5  # 编译并烧录
#
# 依赖：arduino-cli + esp32 core 3.x + 全局库（ArduinoJson/NimBLE/U8g2/
#       GFX_Library_for_Arduino/SensorLib/XPowersLib，已装 Documents\Arduino\libraries）
#
# 依赖（已装好）：
#   · arduino-cli  → %LOCALAPPDATA%\Programs\arduino-cli\arduino-cli.exe
#   · esp32 core 3.3.12（Arduino15 数据目录）
#   · GFX/SensorLib/XPowersLib（Documents\Arduino\libraries）
#   · LVGL 由本脚本从 device/libraries/lvgl 同步到 Documents\Arduino\libraries
#     （配置文件 lv_conf.h 一并同步，位于 sketchbook libraries 根目录）
# ============================================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # OmniAide 仓库根
SKETCH="${1:?用法: build_device.sh smart_assistant [compile|upload|monitor] [COM口]}"
ACTION="${2:-compile}"
PORT="${3:-}"

ACL="$LOCALAPPDATA/Programs/arduino-cli/arduino-cli.exe"
[ -f "$ACL" ] || { echo "找不到 arduino-cli：$ACL"; exit 1; }

SRC="$ROOT/device"                            # 设备端代码目录
[ -d "$SRC" ] || { echo "设备端目录不存在：$SRC"; exit 1; }

# LVGL 随仓库内置（device/libraries/lvgl），同步到 sketchbook（arduino-cli 只搜全局库目录）
SKETCHBOOK="$(cygpath -u "$HOME")/Documents/Arduino/libraries"
if [ -d "$SRC/libraries/lvgl" ]; then
    rm -rf "$SKETCHBOOK/lvgl"
    cp -r "$SRC/libraries/lvgl" "$SKETCHBOOK/lvgl"
    cp "$SRC/libraries/lv_conf.h" "$SKETCHBOOK/lv_conf.h"
fi
# Local ESP_SR patch: pin detect/handler to core 0 so LVGL on core 1 stays smooth.
if [ -d "$SRC/libraries/ESP_SR" ]; then
    rm -rf "$SKETCHBOOK/ESP_SR"
    cp -r "$SRC/libraries/ESP_SR" "$SKETCHBOOK/ESP_SR"
fi

FQBN="esp32:esp32:esp32s3:FlashSize=16M,PartitionScheme=esp_sr_16,PSRAM=opi,FlashMode=qio,USBMode=hwcdc,CDCOnBoot=cdc,UploadSpeed=921600"
# ESP-SR: only WakeNet is used (no MultiNet command detection). Disabling
# MultiNet avoids the mn7 FST build crash and keeps the app under 4MB.
# device/partitions.csv (copied by the core prebuild hook) gives app0/app1 4MB.
BUILD_PROPS=(--build-property upload.maximum_size=4194304
             --build-property compiler.c.extra_flags=-DCONFIG_SR_MN_EN_NONE
             --build-property compiler.cpp.extra_flags=-DCONFIG_SR_MN_EN_NONE)

# 中文路径会让 esp32 构建系统偶发出错：复制到纯 ASCII 临时目录再编译
BUILD_ROOT="$(cygpath -u "$LOCALAPPDATA")/Temp/airmouse_build"
DIRNAME="$SKETCH"
rm -rf "$BUILD_ROOT/$DIRNAME"
mkdir -p "$BUILD_ROOT"
cp -r "$SRC" "$BUILD_ROOT/$DIRNAME"

BUILD_PATH="$BUILD_ROOT/.build/$DIRNAME"

case "$ACTION" in
compile)
    "$ACL" compile --fqbn "$FQBN" "${BUILD_PROPS[@]}" \
        --build-path "$BUILD_PATH" "$BUILD_ROOT/$DIRNAME"
    ;;
publish)
    # 编译并发布到后端下发目录（设备 OTA 用）：backend/data/device_firmware/
    "$ACL" compile --fqbn "$FQBN" "${BUILD_PROPS[@]}" \
        --build-path "$BUILD_PATH" "$BUILD_ROOT/$DIRNAME"
    VER=$(grep -o '#define FW_VERSION[[:space:]]*"[^"]*"' "$SRC/config.h" | sed 's/.*"\(.*\)"/\1/')
    [ -n "$VER" ] || { echo "config.h 里没有 FW_VERSION"; exit 1; }
    DEST="$ROOT/backend/data/device_firmware"
    mkdir -p "$DEST"
    cp "$BUILD_PATH/$SKETCH.ino.bin" "$DEST/firmware.bin"
    echo -n "$VER" > "$DEST/version.txt"
    echo "已发布 v$VER → $DEST"
    ;;
upload)
    [ -n "$PORT" ] || { echo "需要串口，例如：build.sh $SKETCH upload COM5"; exit 1; }
    "$ACL" compile --fqbn "$FQBN" "${BUILD_PROPS[@]}" \
        --build-path "$BUILD_PATH" "$BUILD_ROOT/$DIRNAME"
    "$ACL" upload -p "$PORT" --fqbn "$FQBN" --input-dir "$BUILD_PATH" "$BUILD_ROOT/$DIRNAME"
    ;;
monitor)
    [ -n "$PORT" ] || { echo "需要串口，例如：build.sh $SKETCH monitor COM5"; exit 1; }
    "$ACL" monitor -p "$PORT" --config 115200
    ;;
*)
    echo "未知动作：$ACTION（compile|upload|monitor）"; exit 1
    ;;
esac
