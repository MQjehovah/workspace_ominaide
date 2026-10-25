"""手势→MCP 工具映射配置（JSON 文件存储，避免动 DB migration）。

映射值 = {"tool": MCP工具名, "args": {...}, "label": "展示名"}。
工具经 OmniAide MCP 工具中心执行（设备手势与 AI 对话共用同一链路）。

默认映射：flip=勿扰切换、shake=找手机脚本、double_tap=书桌灯。
用户可通过 PUT /api/device/gestures 修改。
"""
import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[3] / "data" / "device_gestures.json"

DEFAULT_GESTURES: dict[str, dict] = {
    "shake": {  # 摇一摇
        "tool": "ha_call_service",
        "args": {"domain": "light", "service": "toggle",
                 "entity_id": "light.philips_cn_234010960_cbulb_s_2_light"},
        "label": "摇一摇 → 台灯",
    },
    "double_tap": {  # 双击设备
        "tool": "ha_call_service",
        "args": {"domain": "light", "service": "toggle",
                 "entity_id": "light.yeelink_cn_492991530_lamp22_s_2"},
        "label": "双击 → 显示器挂灯",
    },
    "flip": {  # 屏幕朝下扣放
        "tool": "ha_call_service",
        "args": {"domain": "light", "service": "turn_off"},   # 不带 entity = 全屋关灯
        "label": "翻转 → 全屋关灯",
    },
}


def _load() -> dict:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_GESTURES)


def _save(cfg: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_gestures() -> dict:
    return _load()


def set_gestures(cfg: dict) -> dict:
    clean = {k: v for k, v in cfg.items()
             if isinstance(v, dict) and k in ("flip", "shake", "double_tap", "pickup")}
    _save(clean)
    return clean


def get_action(gesture: str) -> dict | None:
    return _load().get(gesture)
