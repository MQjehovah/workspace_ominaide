# 桌宠元宇宙架构设计

## 分层架构

```
PetView.vue
├── Engine (Three.js 渲染核心)
│   ├── SceneManager     — 场景管理（环境、光照、阴影、后期）
│   ├── AssetLoader      — GLTF/GLB 模型加载 + 纹理缓存
│   ├── AnimationSystem  — 骨骼动画（AnimationMixer + blend + layers）
│   ├── VFXSystem        — 粒子、光效、拖尾
│   └── Environment      — 3D 房间/桌面场景
├── Character
│   ├── Skeleton         — 骨骼绑定（Bone hierarchy）
│   ├── MeshGroup        — 身体各部分（可换装）
│   ├── Animator         — 动画状态混合
│   └── SkinnedMesh      — 蒙皮网格
├── FSM (有限状态机)
│   ├── States           — idle / walk / happy / sad / sleep / work / eat / chat / excited
│   ├── Transitions      — 状态切换条件 + blend duration
│   ├── LayerBlend       — 上身/下身分层动画（如走路时挥手）
│   └── Driver           — AI / 定时器 / 交互驱动
├── Interaction
│   ├── Raycaster        — 3D 拾取检测
│   ├── DragHandler      — 拖拽物体/宠物
│   ├── ContextMenu      — 右键菜单（3D 空间定位）
│   └── TriggerZones     — 触发区域（如靠近食物碗）
├── HUD
│   ├── SpeechBubble     — 对话气泡（CSS2DRenderer）
│   ├── EmotionIcon      — 心情图标
│   ├── StatusBar        — 饱腹/心情/精力条
│   └── Notifications    — 消息推送
└── AI Module
    ├── ChatClient       — LLM API 调用
    ├── MoodEngine       — 情绪变化模型
    └── BehaviorScheduler — 主动行为调度
```

## 文件拆分

为避免 `PetView.vue` 膨胀到数千行，按模块拆分到 `pet/` 目录：

```
src/renderer/src/components/pet/
├── index.ts             — 导出所有模块
├── Engine.ts            — Three.js 场景、渲染器、后期
├── AssetLoader.ts       — 模型/纹理/动画加载
├── Environment.ts       — 房间/桌面场景构建
├── Character.ts         — 角色创建（骨骼+网格+材质）
├── AnimationSystem.ts   — 动画状态机 + 混合
├── FSM.ts               — 有限状态机
├── VFX.ts               — 粒子系统
├── Interaction.ts       — 射线检测 + 交互
├── HUD.ts               — 气泡/菜单/状态条
├── AI.ts                — AI 对话 + 行为调度
└── types.ts             — 类型定义
```

## 模型/动画数据流

```
GLTF Model (外部)
  ↓ AssetLoader.parse()
Skeleton + SkinnedMesh
  ↓ AnimationMixer
AnimationClips [idle, walk, happy, ...]
  ↓ FSM.selectClip(state, layer)
Crossfade blending
  ↓ update(deltaTime)
Final pose → render
```

## 状态机设计

```
         ┌─────────────────────────────┐
         │          idle               │
         └──┬──┬──┬──┬──┬──┬──┬──┬────┘
            │  │  │  │  │  │  │  │
     walk happy sad sleep work eat chat
            │  │  │  │  │  │  │  │
         └──┴──┴──┴──┴──┴──┴──┴────┘
         ┌─────────────────────────────┐
         │       back to idle          │
         └─────────────────────────────┘

每个状态：
  - animation: 对应动画 clip 名称
  - blendIn: 入场过渡时间（秒）
  - blendOut: 出场过渡时间
  - loop: 是否循环
  - speed: 播放速度
  - onEnter/onExit: 进入/退出回调
```

## 环境场景

```
房间布局（俯视）：
┌──────────────────────────┐
│  窗                      │
│     ┌──────┐             │
│     │ 桌子 │   🖼️ 画    │
│     │ 宠物  │             │
│     │ 食物碗│             │
│     └──────┘             │
│  地毯       🪴 植物     │
│        沙发              │
└──────────────────────────┘

灯光：
  - 环境光 (柔和)
  - 平行光 (太阳，带阴影)
  - 点光源 (台灯)
  - 半球光 (天/地色彩)
后期：
  - Bloom (辉光)
  - SSAO (环境光遮蔽)
  - ToneMapping (ACES)
```

---

这个架构确认后我开始写核心代码。每个模块预计 50-200 行，总计 1500-2500 行。

**几个问题：**
1. 模型文件你手头有吗（GLTF/GLB）？还是先用程序化生成的角色占位，后续替换？
2. 环境想要室内房间还是户外场景？
3. 状态机初始要几个状态？
