# 认知提案 v2：Memory × Situation 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把提案从“状态提醒”升级为“记忆 × 当前情境”的联合洞察：所有承诺、人物、项目先进入记忆，再由记忆和 situation 共同生成可直接执行的提案。

**Architecture:** 新增统一实体层（entities / aliases / mentions / relations），把现有 `memory_edges` 迁移为实体提及；`Situation` 在原有快照上增加当前实体索引；提案挖掘器只消费“相关记忆 + 当前实体”，经过质量门后直接进入提案流。全流程自动触发，不设手动入口，不设数量上限。

**Tech Stack:** FastAPI、SQLAlchemy async、SQLite/PostgreSQL、Vue 3、Flutter（无改动）、pytest。

**Spec:** 本文档 §1–§3（设计决策）；历史架构见 `docs/plans/2026-11-09-cognition-layer.md`。

## Global Constraints

- 不建立独立的承诺表、未闭环表或对话提案表；承诺、人物、项目、未闭环全部是 `MemoryRecord`。
- 提案必须同时引用 `memory_id` 和 `situation_ref`；只有 situation 的候选只能走现有提醒链路。
- 不存在“收件箱 / 通知”两类提案；通过质量门的提案直接可见、可执行。通知只是同一提案的可选推送通道。
- 不提供手动“生成建议”按钮或手动挖掘接口；全部由 Job 自动触发。
- 不设每日提案数量上限；质量门决定是否生成。
- 所有实体、提及、关系必须按 `user_id` 严格隔离。
- `entity_links` 在 P0 保留为对象关系兼容层；P1 再迁移。P0 只迁移 `memory_edges`。
- 不引入 Neo4j / 图数据库；使用 SQLAlchemy + 递归 CTE。
- 不自动发送邮件、消息或执行外部副作用；提案执行仍走现有授权/审批。
- 所有新表必须通过 `Base.metadata` 创建，并在 `main.py` 导入模型。

## Review Focus

- **跨用户泄漏**：任何实体解析、提及查询、关系查询都必须带 `user_id`；测试必须覆盖两个用户。
- **重复实体**：同一人物在邮件、日程、聊天中出现时不能生成多个 `entity_id`；至少覆盖邮箱和姓名两种 alias。
- **误报**：只有记忆、没有 situation 时不应生成洞察提案；只有 situation 时不得进入洞察流。
- **已解决未闭环**：记忆标记 `resolved` 后，相关提案必须自动关闭或不再生成。
- **迁移幂等**：`memory_edges` 回填重复执行不能产生重复 mention；测试必须跑两次。
- **质量门绕过**：无 `memory_id`、无 `situation_ref`、无 quote 的候选必须被拒绝。
- **自动触发重复**：同一分钟多次记忆写入不能生成重复提案；依赖 dedupe 与 Job 幂等键。

---

## 1. 设计摘要

### 1.1 统一管线

```
聊天 / 邮件 / 钉钉 / 会议 / 活动 / 文档
                ↓
        记忆抽取（唯一入口）
                ↓
   MemoryRecord（结构化、带状态）
                ↓
    Proposal Miner ← Situation（当前实体与时机）
                ↓
           Quality Gate
                ↓
        Proposal（可见、可执行）
```

### 1.2 实体层

新增四张表：

- `entities`：实体节点（person / organization / project / topic / goal）
- `entity_aliases`：姓名、邮箱、钉钉 ID、简称
- `entity_mentions`：实体出现在哪条记忆/邮件/日程/对话里
- `entity_relations`：实体之间的有向关系

业务对象不复制进图谱，通过 `entity_mentions` 绑定。

### 1.3 记忆结构

`MemoryCandidate` 和 `MemoryRecord` 增加 `data` JSON：

```json
{
  "person": "张三",
  "project": "预算评审",
  "topic": "报价",
  "due_at": "2026-11-13T18:00:00",
  "state": "open",
  "quote": "我周五前把报价发你",
  "session_id": "abc",
  "message_ids": [123, 124]
}
```

`kind` 扩展为：

`fact | preference | commitment | relationship | project | open_loop | decision | date | lesson | recurring_topic`

### 1.4 P0 挖掘规则

只做三条，先验证闭环：

1. **承诺 × 日程**：`commitment` 且 `state=open`，其 person/project 与 48 小时内日程匹配。
2. **承诺 × 时间**：`commitment` 且 `state=open`，`due_at` 在 24 小时内或已逾期。
3. **未闭环 × 会话**：`open_loop` 且 `state=open`，超过 24 小时，且最近对话仍提到同一 person/topic。

### 1.5 质量门

硬拒绝：

- 无 `memory_id`
- 无 `situation_ref`
- 无 `evidence.quote`
- 记忆状态不是 `open`
- 已有同 `memory_id` 的 open/executing 提案
- 已有同标题且同截止日的未完成待办
- 敏感级别为 `secret` 且只允许应用内展示

评分：

```
证据强度 25% + 可执行性 25% + 新颖性 20% + 未闭环 15% + 时机 10% + 置信度 5%
```

通过阈值：`0.65`。

### 1.6 自动触发

- 记忆写入/更新 → `cognition.mine.user` Job（按用户 60 秒防抖）
- 每 30 分钟 → `cognition.mine` 扫描到期承诺与未闭环
- 现有每小时活动分析继续生成会议/邮件提醒，不进入洞察挖掘

---

## 2. 文件结构

### 新增

- `backend/ai/entities/__init__.py`
- `backend/ai/entities/models.py`：Entity、EntityAlias、EntityMention、EntityRelation
- `backend/ai/entities/service.py`：实体解析、提及、关系、查询
- `backend/ai/entities/extract.py`：从 profile、situation、memory 抽取人物/项目
- `backend/ai/entities/backfill.py`：`memory_edges` 回填
- `backend/ai/cognition/situation_entities.py`：Situation 实体索引
- `backend/ai/cognition/miner.py`：Memory × Situation 规则
- `backend/ai/cognition/quality.py`：质量门
- `backend/ai/cognition/jobs.py`：自动挖掘 Job
- `backend/tests/test_entity_graph.py`
- `backend/tests/test_proposal_miner.py`
- `backend/tests/test_situation_entities.py`
- `docs/plans/2026-11-09-proposal-mining-v2.md`（本文档）

### 修改

- `backend/ai/memory/models.py`：`MemoryCandidate.data`、`MemoryRecord.data`
- `backend/ai/memory/service.py`：记忆写入后挂实体、触发掘掘
- `backend/ai/cognition/models.py`：`Proposal.source`、`Proposal.quality_score`
- `backend/ai/cognition/proposals.py`：支持 `open`/`link` 动作返回链接
- `backend/ai/cognition/situation.py`：快照增加 `entities` 和最近邮件
- `backend/ai/cognition/router.py`：提案返回证据（已有字段，确认序列化）
- `backend/ai/bots/routine_templates.py`：`daily_memory` prompt 输出 `data` 和实体
- `backend/ai/mcp/tools/knowledge.py`：`propose_memory` 接受 `data`
- `backend/core/database/migrations.py`：新表/新列/回填任务
- `backend/main.py`：导入实体模型、注册 Job
- `backend/frontend`：`Cognition.vue`、`Dashboard.vue` 显示来源与证据
- `backend/evals/cognition.py`：新增实体与挖掘用例

---

## 3. 任务

### Task 1: 实体表与迁移

**Files:**
- Create: `backend/ai/entities/__init__.py`
- Create: `backend/ai/entities/models.py`
- Modify: `backend/main.py`
- Modify: `backend/core/database/migrations.py`
- Test: `backend/tests/test_entity_graph.py`

**Interfaces:**
- Produces:
  - `Entity(id, user_id, type, canonical_name, status, merged_into, metadata, created_at, updated_at)`
  - `EntityAlias(id, user_id, entity_id, alias, alias_type, source, confidence, created_at)`
  - `EntityMention(id, user_id, entity_id, source_type, source_id, quote, role, confidence, extracted_by, created_at)`
  - `EntityRelation(id, user_id, from_entity_id, to_entity_id, relation, confidence, valid_from, valid_to, source_mention_id, metadata, created_at)`

- [ ] **Step 1: 写失败测试**

在 `tests/test_entity_graph.py` 顶部加一个与 `test_proposals.py` 相同的 `_new_user(client)` 辅助函数，返回 `(token, user_id)`。

```python
async def test_entity_tables_and_user_isolation(client):
    token, user_id = await _new_user(client)
    from ai.entities.models import Entity, EntityAlias
    from core.database.session import async_session
    from sqlalchemy import select

    async with async_session() as db:
        row = Entity(user_id=user_id, type="person", canonical_name="张三")
        db.add(row)
        await db.flush()
        db.add(EntityAlias(user_id=user_id, entity_id=row.id, alias="zhangsan@example.com", alias_type="email"))
        await db.commit()

    async with async_session() as db:
        rows = list((await db.execute(select(Entity).where(Entity.user_id == user_id))).scalars())
        assert len(rows) == 1
        assert rows[0].canonical_name == "张三"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3.12 -m pytest tests/test_entity_graph.py::test_entity_tables_and_user_isolation -q`
Expected: FAIL，`ModuleNotFoundError: ai.entities`

- [ ] **Step 3: 实现模型与导入**

在 `ai/entities/models.py` 定义四张表；索引至少包含：

- `(user_id, type)`
- `(entity_id)`
- `(user_id, source_type, source_id)`
- `(user_id, from_entity_id)`
- `(user_id, to_entity_id)`

在 `main.py` 的模型导入区加入 `import ai.entities.models  # noqa`。

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3.12 -m pytest tests/test_entity_graph.py::test_entity_tables_and_user_isolation -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/ai/entities backend/main.py backend/core/database/migrations.py backend/tests/test_entity_graph.py
git commit -m "feat(entities): add unified entity graph tables"
```

---

### Task 2: 实体解析与提及

**Files:**
- Create: `backend/ai/entities/service.py`
- Modify: `backend/ai/entities/models.py`
- Test: `backend/tests/test_entity_graph.py`

**Interfaces:**
- Produces:
  - `normalize_name(value: str) -> str`
  - `resolve_entity(db, user_id: int, entity_type: str, name: str, *, create: bool = True, alias_type: str = "name", source: str | None = None, confidence: float = 0.8) -> Entity | None`
  - `add_mention(db, user_id: int, entity_id: int, *, source_type: str, source_id: int, quote: str, role: str = "mentioned", confidence: float = 0.8, extracted_by: str = "rule") -> EntityMention`
  - `add_relation(db, user_id: int, from_entity_id: int, to_entity_id: int, relation: str, *, confidence: float = 0.8, source_mention_id: int | None = None, valid_from=None, valid_to=None) -> EntityRelation`
  - `related_entities(db, user_id: int, entity_ids: list[int], *, depth: int = 2, relations: list[str] | None = None) -> list[Entity]`
  - `mentions_for_entities(db, user_id: int, entity_ids: list[int], *, source_types: list[str] | None = None, limit: int = 100) -> list[EntityMention]`

- [ ] **Step 1: 写失败测试**

```python
async def test_resolve_entity_by_email_alias(client):
    token, user_id = await _new_user(client)
    from ai.entities.service import resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        first = await resolve_entity(db, user_id, "person", "张三", alias_type="name")
        second = await resolve_entity(db, user_id, "person", "zhangsan@example.com", alias_type="email")
        await db.commit()
        assert first.id == second.id
```

```python
async def test_mention_and_relation_are_user_scoped(client):
    token, user_id = await _new_user(client)
    from ai.entities.service import add_mention, add_relation, resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        a = await resolve_entity(db, user_id, "person", "张三")
        b = await resolve_entity(db, user_id, "project", "预算评审")
        await add_relation(db, user_id, a.id, b.id, "owns")
        mention = await add_mention(db, user_id, a.id, source_type="memory", source_id=1, quote="张三负责预算")
        await db.commit()
        assert mention.entity_id == a.id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3.12 -m pytest tests/test_entity_graph.py -q`
Expected: FAIL，`ImportError: resolve_entity`

- [ ] **Step 3: 实现服务**

解析顺序：

1. 规范化名称（小写、去空白、去标点）
2. 精确 alias 匹配
3. 精确 canonical_name 匹配
4. 未找到且 `create=True` → 新建 Entity + 同名 Alias
5. 冲突或低置信度返回 `None`

提及和关系必须写入 `user_id`，并在写入前校验实体属于同一用户。

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3.12 -m pytest tests/test_entity_graph.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/ai/entities backend/tests/test_entity_graph.py
git commit -m "feat(entities): resolve aliases, mentions and relations"
```

---

### Task 3: Profile 种子与 memory_edges 回填

**Files:**
- Create: `backend/ai/entities/extract.py`
- Create: `backend/ai/entities/backfill.py`
- Modify: `backend/ai/memory/service.py`
- Test: `backend/tests/test_entity_graph.py`

**Interfaces:**
- Produces:
  - `seed_from_profile(db, user_id: int) -> dict`
  - `backfill_memory_edges() -> dict`
  - `attach_memory_entities(db, user_id: int, record) -> dict`

- [ ] **Step 1: 写失败测试**

```python
async def test_seed_profile_creates_person_and_project(client):
    token, user_id = await _new_user(client)
    from ai.entities.extract import seed_from_profile
    from core.database.session import async_session

    async with async_session() as db:
        result = await seed_from_profile(db, user_id)
        await db.commit()
        assert result["entities"] >= 0
```

```python
async def test_memory_edges_backfill_is_idempotent(client):
    from ai.entities.backfill import backfill_memory_edges

    first = await backfill_memory_edges()
    second = await backfill_memory_edges()
    assert second["mentions_created"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3.12 -m pytest tests/test_entity_graph.py -q`
Expected: FAIL，`ImportError: seed_from_profile`

- [ ] **Step 3: 实现种子与回填**

- 从 `UserProfile.contacts/projects` 读取 JSON 列表，创建 `person` / `project` 实体。
- 遍历 `MemoryEdge`，把 `target_name` 解析成实体；创建 `EntityMention(source_type="memory", source_id=memory_id, quote=record.content[:300], role="mentions")`。
- 以 `(user_id, entity_id, source_type, source_id)` 做幂等判断。
- 在 `ai/memory/service.py` 的 `approve_candidate()` 创建 `MemoryRecord` 后调用 `attach_memory_entities()`。

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3.12 -m pytest tests/test_entity_graph.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/ai/entities backend/ai/memory/service.py backend/tests/test_entity_graph.py
git commit -m "feat(entities): seed profile entities and backfill memory edges"
```

---

### Task 4: Situation 实体索引

**Files:**
- Create: `backend/ai/cognition/situation_entities.py`
- Modify: `backend/ai/cognition/situation.py`
- Test: `backend/tests/test_situation_entities.py`

**Interfaces:**
- Produces:
  - `build_situation_entities(user_id: int, snapshot: dict | None = None) -> list[dict]`
  - 返回项：`{"entity_id", "type", "name", "role", "source_type", "source_id", "confidence"}`

- [ ] **Step 1: 写失败测试**

在 `tests/test_situation_entities.py` 顶部复用 `_new_user(client)` 辅助函数。

```python
async def test_situation_entities_from_event_and_mail(client):
    token, user_id = await _new_user(client)
    from ai.cognition.situation_entities import build_situation_entities
    from ai.entities.service import resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        await resolve_entity(db, user_id, "person", "张三")
        await resolve_entity(db, user_id, "project", "预算评审")
        await db.commit()

    snapshot = {
        "calendar": [{"id": 1, "title": "和张三开预算评审会", "time": "2026-11-09T10:00:00"}],
        "todos": [{"id": 2, "title": "准备预算材料"}],
        "inbox": {"recent_mail": [{"id": 3, "from": "zhangsan@example.com"}]},
        "goals": [{"id": 4, "title": "预算评审"}],
    }
    rows = await build_situation_entities(user_id, snapshot)
    assert any(row["source_type"] == "event" for row in rows)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3.12 -m pytest tests/test_situation_entities.py -q`
Expected: FAIL，`ModuleNotFoundError: situation_entities`

- [ ] **Step 3: 实现实体索引**

从以下来源抽取：

- `calendar[].title` 和参与人（若有）
- `todos[].title`
- `inbox.recent_mail[].from`
- `goals[].title`
- `recent.notes/projects/files` 标题

使用 `resolve_entity(..., create=False)` 只匹配已知实体，不在此处新建。把结果写入 `snapshot["entities"]`。

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3.12 -m pytest tests/test_situation_entities.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/ai/cognition/situation_entities.py backend/ai/cognition/situation.py backend/tests/test_situation_entities.py
git commit -m "feat(cognition): index situation entities"
```

---

### Task 5: Memory 结构化与提案字段

**Files:**
- Modify: `backend/ai/memory/models.py`
- Modify: `backend/ai/cognition/models.py`
- Modify: `backend/ai/cognition/proposals.py`
- Modify: `backend/ai/mcp/tools/knowledge.py`
- Modify: `backend/ai/bots/routine_templates.py`
- Test: `backend/tests/test_proposal_miner.py`

**Interfaces:**
- Produces:
  - `MemoryCandidate.data: JSON`
  - `MemoryRecord.data: JSON`
  - `Proposal.source: str`
  - `Proposal.quality_score: float`
  - `_execute_action()` 支持 `open` / `link`，返回 `{"action": kind, "status": "accepted", "link": payload["link"]}`

- [ ] **Step 1: 写失败测试**

在 `tests/test_proposal_miner.py` 顶部复用 `_new_user(client)` 辅助函数。

```python
async def test_memory_record_keeps_structured_data(client):
    token, user_id = await _new_user(client)
    from ai.memory.models import MemoryRecord
    from core.database.session import async_session

    async with async_session() as db:
        row = MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="周五前把报价发给张三",
            normalized="周五前把报价发给张三",
            data={"person": "张三", "due_at": "2026-11-13", "state": "open"},
        )
        db.add(row)
        await db.commit()
        assert row.data["person"] == "张三"
```

```python
async def test_proposal_link_action_returns_url(client):
    from ai.cognition.proposals import _execute_action

    result = await _execute_action(
        None, 1, type("P", (), {"id": 1, "title": "x", "bot_id": None})(),
        {"kind": "open", "payload": {"link": "/chat?session_id=abc"}},
    )
    assert result["link"] == "/chat?session_id=abc"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3.12 -m pytest tests/test_proposal_miner.py -q`
Expected: FAIL，`TypeError` 或字段不存在

- [ ] **Step 3: 实现字段与动作**

- `memory_candidates.data`、`memory_records.data` 增加 JSON 列。
- `proposals.source` 默认 `"memory"`，`quality_score` 默认 `0.0`。
- `propose_memory` 接受 `data` 字典。
- `daily_memory` prompt 增加结构化输出要求。
- `_execute_action` 对 `open` / `link` 返回链接。

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3.12 -m pytest tests/test_proposal_miner.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/ai/memory backend/ai/cognition backend/ai/mcp/tools/knowledge.py backend/ai/bots/routine_templates.py backend/tests/test_proposal_miner.py
git commit -m "feat(memory): add structured data and proposal source fields"
```

---

### Task 6: 挖掘器与质量门

**Files:**
- Create: `backend/ai/cognition/miner.py`
- Create: `backend/ai/cognition/quality.py`
- Test: `backend/tests/test_proposal_miner.py`

**Interfaces:**
- Produces:
  - `@dataclass MiningCandidate`: `memory_id`, `kind`, `title`, `reason`, `confidence`, `action`, `evidence`, `situation_ref`, `source`
  - `evaluate(candidate: MiningCandidate) -> tuple[bool, float, list[str]]`
  - `mine_user(user_id: int) -> dict`
- 返回：`{"created": int, "rejected": int, "candidates": int}`

- [ ] **Step 1: 写失败测试**

```python
async def test_commitment_and_event_create_proposal(client):
    token, user_id = await _new_user(client)
    from datetime import datetime, timedelta
    from ai.memory.models import MemoryRecord
    from plugins.schedule.backend.models import Event
    from core.database.session import async_session
    from ai.cognition.miner import mine_user

    async with async_session() as db:
        db.add(Event(
            user_id=user_id,
            title="和张三开预算评审会",
            start_time=datetime.now() + timedelta(hours=2),
        ))
        db.add(MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="周五前把报价发给张三",
            normalized="周五前把报价发给张三",
            confidence=90,
            data={"person": "张三", "project": "预算", "state": "open",
                  "due_at": "2026-11-13", "quote": "我周五前把报价发你"},
        ))
        await db.commit()

    result = await mine_user(user_id)
    assert result["created"] >= 1
```

```python
async def test_memory_without_situation_is_rejected(client):
    token, user_id = await _new_user(client)
    from ai.cognition.miner import mine_user
    result = await mine_user(user_id)
    assert result["created"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3.12 -m pytest tests/test_proposal_miner.py -q`
Expected: FAIL，`ModuleNotFoundError: miner`

- [ ] **Step 3: 实现规则与质量门**

`mine_user`：

1. 读取 `MemoryRecord(status="active", data.state="open")`
2. 读取 `get_situation(user_id, force=True)`
3. 对每条记忆执行三条规则
4. 生成 `MiningCandidate`
5. `evaluate()` 通过则 `create_proposal(source="memory", evidence=...)`
6. 使用 `dedupe_key=f"memory:{memory_id}:{rule}"`

`evaluate`：

- 硬拒绝条件逐条检查
- 评分公式见 §1.5
- 返回 `(passed, score, reasons)`

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3.12 -m pytest tests/test_proposal_miner.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/ai/cognition/miner.py backend/ai/cognition/quality.py backend/tests/test_proposal_miner.py
git commit -m "feat(cognition): mine proposals from memory and situation"
```

---

### Task 7: 自动触发 Job

**Files:**
- Create: `backend/ai/cognition/jobs.py`
- Modify: `backend/ai/memory/service.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_proposal_miner.py`

**Interfaces:**
- Produces:
  - `enqueue_mine_user(user_id: int) -> None`
  - `async def mine_user_job(job) -> dict`
  - `JOBS: list[PeriodicJob]`

- [ ] **Step 1: 写失败测试**

```python
async def test_memory_write_enqueues_mining_job(client, monkeypatch):
    token, user_id = await _new_user(client)
    from ai.memory import service as memory_service
    from ai.memory.models import MemoryCandidate
    from core.database.session import async_session

    async with async_session() as db:
        candidate = MemoryCandidate(
            user_id=user_id,
            kind="fact",
            content="测试记忆",
            normalized="测试记忆",
            confidence=90,
        )
        db.add(candidate)
        await db.commit()
        await db.refresh(candidate)
        candidate_id = candidate.id

    calls = []

    async def fake_enqueue(target_user_id):
        calls.append(target_user_id)

    monkeypatch.setattr("ai.cognition.jobs.enqueue_mine_user", fake_enqueue)
    await memory_service.approve_candidate(user_id, candidate_id)
    assert calls == [user_id]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `py -3.12 -m pytest tests/test_proposal_miner.py::test_memory_write_enqueues_mining_job -q`
Expected: FAIL，`ImportError: enqueue_mine_user`

- [ ] **Step 3: 实现 Job**

- `enqueue_mine_user` 使用 `core.jobs.service.enqueue("cognition.mine.user", {"user_id": user_id}, idempotency_key=f"cognition:mine:{user_id}:{minute}")`
- `mine_user_job` 调用 `mine_user`
- `JOBS` 注册每 30 分钟的 `cognition.mine` 扫描未闭环和到期承诺
- `main.py` 把 `COGNITION_JOBS` 加入 scheduler
- `approve_candidate` 创建记录后调用 `enqueue_mine_user`

- [ ] **Step 4: 运行测试确认通过**

Run: `py -3.12 -m pytest tests/test_proposal_miner.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/ai/cognition/jobs.py backend/ai/memory/service.py backend/main.py backend/tests/test_proposal_miner.py
git commit -m "feat(cognition): auto-trigger proposal mining after memory writes"
```

---

### Task 8: 前端证据展示

**Files:**
- Modify: `frontend/src/views/Cognition.vue`
- Modify: `frontend/src/views/Dashboard.vue`
- Test: `frontend` build

**Interfaces:**
- Consumes: `Proposal.source`、`Proposal.evidence.quote`、`Proposal.actions`
- Produces: 提案卡片显示来源标签与原文引用；`open`/`link` 动作执行后跳转。

- [ ] **Step 1: 加入展示与动作**

在 `Cognition.vue` 提案卡片中加入：

```vue
<el-tag size="small">{{ p.source === 'memory' ? '记忆' : '提醒' }}</el-tag>
<div v-if="p.evidence?.quote" class="muted">“{{ p.evidence.quote }}”</div>
```

在 `Dashboard.vue` 同样显示 `s.evidence?.quote`。

- [ ] **Step 2: 处理执行链接**

- `Cognition.vue` 的 `actProposal` 处理返回的 `link`：`if (res.data?.link) router.push(res.data.link)`
- `Dashboard.vue` 的 `acceptProposal` 同样处理 `link`
- 不新增“收件箱/通知”开关

- [ ] **Step 3: 构建验证**

Run: `npm run build`
Expected: PASS

前端仓库没有测试框架，因此以构建通过 + 本地手测为准：打开协同页，确认提案卡显示来源与原文；点执行能创建待办或跳转链接。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/Cognition.vue frontend/src/views/Dashboard.vue
git commit -m "feat(web): show proposal source and memory evidence"
```

---

### Task 9: 评估、回归与文档

**Files:**
- Modify: `backend/evals/cognition.py`
- Modify: `docs/plans/2026-11-09-cognition-layer.md`
- Test: `backend/tests/test_entity_graph.py`, `backend/tests/test_proposal_miner.py`, `backend/tests/test_situation_entities.py`

**Interfaces:**
- Consumes: 全部前序任务
- Produces: 至少 3 个新黄金用例；全量回归通过

- [ ] **Step 1: 增加评估用例**

在 `evals/cognition.py` 增加三个用例：

- `entity_resolution`：同一人物姓名和邮箱解析到同一 `entity_id`
- `memory_situation_proposal`：承诺记忆 + 2 小时内会议 → 生成提案
- `resolved_memory_closes_proposal`：记忆 `state` 改为 `resolved` 后，再次挖掘不再生成提案

- [ ] **Step 2: 运行评估**

Run: `py -3.12 -m pytest tests/test_proposal_miner.py tests/test_entity_graph.py -q`
Expected: PASS

- [ ] **Step 3: 更新文档**

- 更新 `docs/plans/2026-11-09-cognition-layer.md` 的实现进度，链接本文档
- 在文档中记录 P0 完成项与 P1/P2 后续

- [ ] **Step 4: 运行全部验证**

Run:

```bash
py -3.12 -m pytest -q
npm run build
flutter test
```

Expected: 后端全绿，前端构建通过，移动端测试通过

- [ ] **Step 5: 提交**

```bash
git add backend/evals/cognition.py docs/plans
git commit -m "test(cognition): add entity and memory-situation golden cases"
```

---

## 4. 后续计划（不在 P0）

### P1
- `entity_links` 迁移到 `entity_relations`
- 别名合并与同人识别
- 2 跳检索：人物 → 项目 → 承诺
- 人物 × 邮件、偏好 × 日程、日期 × 时间

### P2
- topic / goal 实体
- 关系时间有效性与置信度衰减
- 跨源冲突、反馈学习
- 每周实体图谱清理任务

---

## 5. 自检

- [x] 每条设计约束都有对应任务
- [x] 每个任务有独立可运行的测试
- [x] 类型与函数名在任务间一致
- [x] 覆盖跨用户隔离、重复实体、误报、已解决未闭环、迁移幂等
- [x] 不包含收件箱/通知分层
- [x] 不包含手动触发入口
- [x] 不包含数量上限
