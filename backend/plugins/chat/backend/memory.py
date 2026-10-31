"""Build user context (profile + entities) for chat system prompt."""
from core.config.settings import settings


async def build_context(user_id: int, query: str = "") -> str | None:
    parts = []
    try:
        from sqlalchemy import select
        from core.auth.domain.models import UserProfile
        from core.database.session import async_session
        async with async_session() as db:
            r = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
            p = r.scalar_one_or_none()
            if p:
                info = []
                if p.name: info.append(f"姓名: {p.name}")
                if p.role: info.append(f"角色: {p.role}")
                if p.company: info.append(f"公司: {p.company}")
                if p.contacts:
                    import json
                    cs = json.loads(p.contacts) if isinstance(p.contacts, str) else p.contacts
                    if cs: info.append("联系人: " + "; ".join([f'{c.get("name","")}({c.get("relation","")})' for c in cs]))
                if p.projects:
                    import json
                    ps = json.loads(p.projects) if isinstance(p.projects, str) else p.projects
                    if ps: info.append("项目: " + "; ".join([f'{p.get("name","")}({p.get("deadline","")})' for p in ps]))
                if p.developer:
                    import json
                    dev = json.loads(p.developer) if isinstance(p.developer, str) else p.developer
                    if dev:
                        d = []
                        if dev.get("github_username"): d.append(f"GitHub: {dev['github_username']}")
                        if dev.get("github_email"): d.append(f"Git 邮箱: {dev['github_email']}")
                        if dev.get("default_org"): d.append(f"默认组织: {dev['default_org']}")
                        if dev.get("default_branch"): d.append(f"默认分支: {dev['default_branch']}")
                        if dev.get("permissions"): d.append("代码权限: " + ", ".join(dev["permissions"]))
                        if dev.get("workspace_roots"): d.append("工作区: " + ", ".join(dev["workspace_roots"]))
                        if dev.get("commit_style"): d.append(f"提交规范: {dev['commit_style']}")
                        if d: info.append("开发者档案: " + "; ".join(d))
                if info:
                    parts.append("【用户信息】\n" + "\n".join(info))
    except Exception:
        pass

    if settings.memory_layer_enabled:
        try:
            from core.ai.embeddings import generate_embedding
            from core.ai import vector_store
            vec = await generate_embedding(query)
            if vec:
                hits = await vector_store.search("entities", user_id, vec, limit=5)
                if hits:
                    related = [
                        f"{h.get('title', '')}({h.get('metadata', {}).get('type', '')})"
                        for h in hits
                    ]
                    parts.append("【相关实体】\n" + ", ".join(related))
        except Exception:
            pass

    return "\n\n".join(parts) if parts else None
