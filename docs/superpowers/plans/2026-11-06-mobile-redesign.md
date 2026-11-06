# Mobile Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Flutter 手机端重构成「对话 / 工作台 / 空间 / 我的」四页结构，默认工作台，并用可配置的晴空蓝主题统一视觉。

**Architecture:** 新增 `AppThemeController` 管理主题色、tint、深浅模式和字号；`HomeScreen` 变成 4-tab 外壳；聊天、工作台、空间、我的各自独立成页；业务对象页复用现有屏幕，新增邮件、记忆、简报、项目、资讯等轻量页。所有数据来自现有后端 API，失败时降级为空状态。

**Tech Stack:** Flutter 3.38 / Dart 3.10、Material 3、`http`、`shared_preferences`、现有 `ApiService`。

**Spec:** `docs/superpowers/specs/2026-11-06-mobile-redesign-design.md`

## Global Constraints

- 只改 `mobile/`，不改后端业务逻辑。
- 底部 4 个 tab，顺序固定：对话 / 工作台 / 空间 / 我的。
- 默认 tab 是工作台（index 1）。
- 主题色默认晴空蓝 `#2E7CF6`；支持预设 + 自定义色相。
- 所有网络失败不得崩溃；显示空状态或上次数据。
- 文案中文；不引入新的重型依赖。
- 每个任务结束运行 `flutter analyze`，最终运行 `flutter test`。

## Review Focus

- 360×800 小屏上工作台/空间是否溢出。
- 无网络、无 token、后端字段缺失时是否仍可打开。
- 主题色切换后，深色模式和 tint 关闭时是否仍可读。
- 聊天流式输出中断/报错时是否保留已输出内容和重试入口。
- 空间 tile 跳转到已删除或未启用插件时是否给出空状态而非白屏。

---

### Task 1: 主题系统与设计 token

**Files:**
- Create: `mobile/lib/theme/app_theme.dart`
- Modify: `mobile/lib/theme.dart`
- Modify: `mobile/lib/main.dart`
- Test: `mobile/test/app_theme_test.dart`

**Interfaces:**
- Produces:
  - `class ThemePreset { final String name; final Color color; }`
  - `const kThemePresets`
  - `Color mixWithWhite(Color color, double amount)`
  - `ThemeData buildAppTheme({required Color seed, required Brightness brightness, bool tintBackground = true})`
  - `class AppThemeController extends ChangeNotifier` with `seed`, `tintBackground`, `mode`, `fontScale`, `load()`, `setSeed()`, `setTint()`, `setMode()`, `setFontScale()`, `light`, `dark`.
  - `final appTheme = AppThemeController();`

- [ ] **Step 1: Write failing theme tests**

`mobile/test/app_theme_test.dart`:
- `mixWithWhite(Color(0xFF000000), 0.5)` returns a mid grey.
- `buildAppTheme(seed: Color(0xFF2E7CF6), brightness: light, tintBackground: true).colorScheme.primary` is the seed (or close).
- `AppThemeController` defaults: seed `0xFF2E7CF6`, tint true, mode system, fontScale 1.0.
- `setSeed`, `setTint`, `setMode`, `setFontScale` notify listeners.
- `load()` reads `theme.seed`, `theme.tint`, `theme.mode`, `theme.fontScale` from SharedPreferences.

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/app_theme_test.dart`
Expected: FAIL because `theme/app_theme.dart` does not exist.

- [ ] **Step 3: Implement `app_theme.dart` and wire `main.dart`**

Build light/dark `ThemeData` from seed, with:
- `scaffoldBackgroundColor` = tint ? `mixWithWhite(seed, 0.93)` : `Color(0xFFF6F8FC)`.
- `cardTheme` white (dark `#1A1D24`), radius 16, 1px outline.
- `navigationBarTheme` 4-item friendly, selected `seed`.
- `inputDecorationTheme` rounded 12, filled.
- `textTheme` with the spec sizes.
- `MediaQuery` textScaler in `main.dart`.

- [ ] **Step 4: Run tests**

Run: `flutter test test/app_theme_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/theme/app_theme.dart mobile/lib/theme.dart mobile/lib/main.dart mobile/test/app_theme_test.dart
git commit -m "feat(mobile): add configurable bright theme system"
```

---

### Task 2: 四 tab 外壳与默认工作台

**Files:**
- Create: `mobile/lib/widgets/navigation_shell.dart`
- Modify: `mobile/lib/screens/home_screen.dart`
- Test: `mobile/test/navigation_shell_test.dart`

**Interfaces:**
- Produces:
  - `class NavigationShell extends StatefulWidget { final List<Widget> pages; final int initialIndex; }`
  - `NavigationShell` exposes `currentIndex` via callback? Keep internal; tests use labels and navigation.
- Consumes: `AppThemeController` from Task 1.

- [ ] **Step 1: Write failing navigation test**

`mobile/test/navigation_shell_test.dart`:
- Pump `NavigationShell(initialIndex: 1, pages: [Text('chat'), Text('workbench'), Text('space'), Text('me')])`.
- Expect 4 destinations with labels `对话 / 工作台 / 空间 / 我的`.
- Expect `workbench` visible initially.
- Tap `空间` → expect `space`.

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/navigation_shell_test.dart`
Expected: FAIL (file missing).

- [ ] **Step 3: Implement `NavigationShell` and rewrite `HomeScreen`**

- `NavigationShell` uses `IndexedStack` + `NavigationBar`.
- `HomeScreen` composes:
  - `ChatListScreen()`
  - `WorkbenchScreen()`
  - `SpaceScreen()`
  - `ProfileScreen()`
- Keep `NotificationService` start/stop in `HomeScreen`.

- [ ] **Step 4: Run test**

Run: `flutter test test/navigation_shell_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/widgets/navigation_shell.dart mobile/lib/screens/home_screen.dart mobile/test/navigation_shell_test.dart
git commit -m "feat(mobile): four-tab shell with workbench as default"
```

---

### Task 3: 会话数据模型与会话切换

**Files:**
- Create: `mobile/lib/models/chat_session.dart`
- Modify: `mobile/lib/screens/chat_screen.dart`
- Modify: `mobile/lib/services/api_service.dart`
- Test: `mobile/test/chat_session_test.dart`

**Interfaces:**
- Produces:
  - `class ChatSession { final String id; final String title; final DateTime? updatedAt; }`
  - `ChatSession.fromJson(Map<String, dynamic>)`
  - `Future<List<ChatSession>> ApiService.listChatSessions()`
  - `String relativeTimeLabel(DateTime?)`
- Consumes: `ChatScreen` for switching sessions inside the same page.

- [ ] **Step 1: Write failing model test**

- `ChatSession.fromJson({'session_id':'s1','title':'预算评审','updated_at':'2026-11-06T10:24:00'})` maps fields.
- Missing title falls back to `新对话`.
- `relativeTimeLabel` for today returns `HH:mm`, yesterday returns `昨天`, older returns `M月d日`.

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/chat_session_test.dart`
Expected: FAIL.

- [ ] **Step 3: Implement model, API method, and session switching**

- Add `listChatSessions()` calling `/api/chat/sessions`.
- Chat tab opens latest session via `ChatScreen(autoLoadLatest: true)`.
- Tapping the title opens a bottom sheet with 新对话 + recent sessions; selecting switches in place.
- New chat generates a fresh session id and clears messages.

- [ ] **Step 4: Run test**

Run: `flutter test test/chat_session_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/models/chat_session.dart mobile/lib/screens/chat_screen.dart mobile/lib/services/api_service.dart mobile/test/chat_session_test.dart
git commit -m "feat(mobile): open latest chat and switch sessions in place"
```

---

### Task 4: 对话详情页重设计

**Files:**
- Modify: `mobile/lib/screens/chat_screen.dart`
- Create: `mobile/lib/widgets/chat_bubble.dart`
- Test: `mobile/test/chat_screen_test.dart`

**Interfaces:**
- Produces:
  - `enum ChatMode { normal, agent, web }`
  - `class ChatBubble extends StatelessWidget { final String role; final String text; final bool streaming; }`
- Consumes: `ApiService.chatStream`, `ApiService.chat`, `loadChatHistory`.

- [ ] **Step 1: Write failing widget test**

- `ChatBubble(role: 'user', text: '你好')` renders text.
- `ChatBubble(role: 'assistant', text: '正在生成', streaming: true)` shows cursor/indicator.
- `ChatMode.agent.label == 'Agent'`.

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/chat_screen_test.dart`
Expected: FAIL.

- [ ] **Step 3: Implement**

- Rewrite chat page with theme tokens.
- Top bar: back (when pushed), tappable title to switch sessions, new chat.
- Context banner: static "已引用 2 份材料" (read from optional `contextLabel` constructor param).
- Message list: `ChatBubble` for user/assistant; assistant rich text preserved as plain text.
- Input: attach/reference, send. No 普通/Agent mode selector.
- Keep SSE streaming; remove the separate agent mode branch.
- On error: bubble with error text + retry button.

- [ ] **Step 4: Run tests**

Run: `flutter test test/chat_screen_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/screens/chat_screen.dart mobile/lib/widgets/chat_bubble.dart mobile/test/chat_screen_test.dart
git commit -m "feat(mobile): redesign chat detail and message bubbles"
```

---

### Task 5: 工作台

**Files:**
- Create: `mobile/lib/screens/workbench_screen.dart`
- Create: `mobile/lib/models/cos_models.dart`
- Modify: `mobile/lib/services/api_service.dart`
- Test: `mobile/test/cos_models_test.dart`

**Interfaces:**
- Produces:
  - `class DailyBrief { final String summary; final List<String> focus; final List<BriefSection> sections; }`
  - `class BriefSection { final String key; final String title; final List<BriefItem> items; }`
  - `class BriefItem { final String title; final String summary; final String source; }`
  - `Future<DailyBrief?> ApiService.getDailyBrief()`
  - `Future<Map<String, dynamic>> ApiService.getTriage()`
- Consumes: schedule/todo/notification/file APIs, `ChatScreen`, `InboxScreen`, `BriefScreen`, `LibraryScreen`.

- [ ] **Step 1: Write failing model test**

- `DailyBrief.fromJson` parses summary/focus/sections.
- Unknown section keys are kept.
- Missing fields produce empty lists, not throw.

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/cos_models_test.dart`
Expected: FAIL.

- [ ] **Step 3: Implement models + API + screen**

- `WorkbenchScreen` loads brief, triage, today's schedule, pending todos, recent files in parallel with `Future.wait` and individual try/catch.
- Header: greeting + date + search + avatar.
- Hero AI card: input, send, 3 quick chips; submit pushes `ChatScreen(initialQuery: q)`.
- Today card: first 2 events, due/overdue strip.
- Two-column: inbox summary + CoS brief.
- Files & notes row.
- Pull to refresh; skeleton/empty states.

- [ ] **Step 4: Run tests**

Run: `flutter test test/cos_models_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/screens/workbench_screen.dart mobile/lib/models/cos_models.dart mobile/lib/services/api_service.dart mobile/test/cos_models_test.dart
git commit -m "feat(mobile): add workbench with brief and triage"
```

---

### Task 6: 空间页与统一收件箱

**Files:**
- Create: `mobile/lib/screens/space_screen.dart`
- Create: `mobile/lib/screens/inbox_screen.dart`
- Create: `mobile/lib/screens/library_screen.dart`
- Create: `mobile/lib/screens/mail_screen.dart`
- Create: `mobile/lib/screens/memory_screen.dart`
- Create: `mobile/lib/screens/brief_screen.dart`
- Create: `mobile/lib/screens/projects_screen.dart`
- Create: `mobile/lib/screens/rss_screen.dart`
- Create: `mobile/lib/screens/mcp_screen.dart`
- Modify: `mobile/lib/services/api_service.dart`
- Test: `mobile/test/space_catalog_test.dart`

**Interfaces:**
- Produces:
  - `class SpaceEntry { final String key; final String label; final IconData icon; final Color color; final int? badge; final Widget Function() builder; }`
  - `List<SpaceGroup> buildSpaceCatalog({int mailCount, int dingtalkCount, int notificationCount, int todoCount, int rssCount})`
  - API methods: `listMailMessages`, `getMailMessage`, `draftReply`, `listMemoryCandidates`, `listMemoryRecords`, `approveMemory`, `rejectMemory`, `forgetMemory`, `getWeeklyReview`, `listProjects`, `listRssEntries`, `listMcpServers`.
- Consumes: existing `FilesScreen`, `NotesScreen`, `ScheduleScreen`, `TodoScreen`, `NotificationsScreen`, `MusicScreen`, `DeviceScreen`, `VibecodingScreen`.

- [ ] **Step 1: Write failing catalog test**

- `buildSpaceCatalog` returns 4 groups: 沟通 / 工作 / 内容 / 更多.
- Badges use provided counts.
- `space` group order is stable.
- Unknown counts default 0.

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/space_catalog_test.dart`
Expected: FAIL.

- [ ] **Step 3: Implement space + secondary screens**

- `SpaceScreen`:
  - header "空间" + search/manage icons.
  - unified inbox card with counts and urgent count.
  - grouped tile grid, 3 columns.
  - tiles navigate to builders.
- `InboxScreen`: load `/cos/triage`, segmented 全部/邮件/钉钉/通知, list items, tap mail → `MailScreen(detailId:)`, others bottom sheet.
- `MailScreen`: list from `/plugins/mail/messages`, detail, "起草回复" → `/cos/draft-reply`, copyable dialog.
- `MemoryScreen`: pending candidates + records, approve/reject/forget.
- `BriefScreen`: daily brief + weekly review tabs.
- `ProjectsScreen`, `RssScreen`, `McpScreen`: simple lists with empty states.
- `LibraryScreen`: two cards for Files / Notes.

- [ ] **Step 4: Run tests**

Run: `flutter test test/space_catalog_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/screens/space_screen.dart mobile/lib/screens/inbox_screen.dart mobile/lib/screens/library_screen.dart mobile/lib/screens/mail_screen.dart mobile/lib/screens/memory_screen.dart mobile/lib/screens/brief_screen.dart mobile/lib/screens/projects_screen.dart mobile/lib/screens/rss_screen.dart mobile/lib/screens/mcp_screen.dart mobile/lib/services/api_service.dart mobile/test/space_catalog_test.dart
git commit -m "feat(mobile): space hub, inbox and business object screens"
```

---

### Task 7: 我的页、外观与主题同步

**Files:**
- Create: `mobile/lib/screens/profile_screen.dart`
- Create: `mobile/lib/screens/appearance_screen.dart`
- Create: `mobile/lib/screens/settings_screen.dart`
- Modify: `mobile/lib/services/api_service.dart`
- Test: `mobile/test/appearance_test.dart`

**Interfaces:**
- Produces:
  - `class AppearanceScreen extends StatelessWidget` consuming `appTheme`.
  - `Future<void> pushAppearanceSetting(String key, Object? value)` in `ApiService`.
  - `Future<Map<String, dynamic>> getAppearanceSettings()`.
- Consumes: `appTheme`, `MemoryScreen`, `NotificationsScreen`, `DeviceScreen`, `MusicScreen`, `VibecodingScreen`, `McpScreen`.

- [ ] **Step 1: Write failing appearance test**

- Tapping a preset changes `appTheme.seed` and persists.
- Toggling tint changes `tintBackground` and background color.
- Mode segmented changes `appTheme.mode`.
- Font scale slider clamps to 0.9–1.3.

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/appearance_test.dart`
Expected: FAIL.

- [ ] **Step 3: Implement profile + appearance + settings**

- Profile: header, profile card, grouped menu, logout.
- Appearance: preset swatches, custom hue slider, live preview, mode segmented, tint switch, font scale slider; each change calls controller + best-effort sync.
- Settings: server URL display, about, logout.
- Add `pushAppearanceSetting` and `getAppearanceSettings`.

- [ ] **Step 4: Run tests**

Run: `flutter test test/appearance_test.dart`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/screens/profile_screen.dart mobile/lib/screens/appearance_screen.dart mobile/lib/screens/settings_screen.dart mobile/lib/services/api_service.dart mobile/test/appearance_test.dart
git commit -m "feat(mobile): profile and configurable appearance"
```

---

### Task 8: 收尾、分析、构建

**Files:**
- Modify: `mobile/README.md`
- Modify: `docs/` if needed
- Test: all `mobile/test/*.dart`

- [ ] **Step 1: Run analyze**

Run: `flutter analyze`
Expected: no errors (warnings allowed if pre-existing).

- [ ] **Step 2: Run all tests**

Run: `flutter test`
Expected: all pass.

- [ ] **Step 3: Build web (smoke)**

Run: `flutter build web --release`
Expected: build succeeds.

- [ ] **Step 4: Update README**

Document the 4-tab structure, theme config, and where files/notes/music live.

- [ ] **Step 5: Commit**

```bash
git add mobile/README.md docs
git commit -m "docs(mobile): document redesigned navigation and theme"
```
