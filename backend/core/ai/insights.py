"""Insight discovery — mines activity + schedule data to build a picture of the
user's work patterns, and produces natural-language insights & proactive suggestions."""

from datetime import datetime, timedelta


async def discover_insights(user_id: int):
    """Analyse recent activity data and store structured insights + suggestions
    into the user profile's `preferences.insights`."""
    from core.config.settings import settings
    if not settings.llm_api_key:
        return
    from sqlalchemy import select, func
    from core.database.session import async_session
    from core.events.models import UserActivity
    from plugins.schedule.backend.models import Event
    from core.auth.domain.models import UserProfile
    import json as _json

    now = datetime.utcnow()
    since = now - timedelta(days=30)

    try:
        async with async_session() as db:
            # ---- Aggregate app usage ----
            r = await db.execute(
                select(UserActivity).where(
                    UserActivity.user_id == user_id,
                    UserActivity.event_type == "app.used",
                    UserActivity.created_at >= since,
                )
            )
            app_minutes: dict[str, int] = {}
            hour_minutes: dict[int, int] = {}
            weekday_minutes: dict[int, int] = {}
            sessions: list[int] = []
            for e in r.scalars().all():
                d = e.details or {}
                app = d.get("app") or "未知"
                mins = int(d.get("minutes") or 0)
                app_minutes[app] = app_minutes.get(app, 0) + mins
                if e.created_at:
                    hour_minutes[e.created_at.hour] = hour_minutes.get(e.created_at.hour, 0) + mins
                    weekday_minutes[e.created_at.weekday()] = weekday_minutes.get(e.created_at.weekday(), 0) + mins
                sessions.append(mins)

            top_apps = sorted(app_minutes.items(), key=lambda x: -x[1])[:8]
            total_minutes = sum(app_minutes.values())
            peak_hour = max(hour_minutes.items(), key=lambda x: x[1])[0] if hour_minutes else None
            avg_session = round(sum(sessions) / len(sessions)) if sessions else 0
            best_day = max(weekday_minutes.items(), key=lambda x: x[1])[0] if weekday_minutes else None
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

            # ---- Schedule recurrence ----
            sr = await db.execute(
                select(Event.title, func.count()).where(
                    Event.user_id == user_id, Event.start_time >= since
                ).group_by(Event.title).order_by(func.count().desc()).limit(5)
            )
            recurring = [{"title": t, "count": c} for t, c in sr.all() if c >= 2]

            # ---- Focus / activity volume by hour (from all events) ----
            ar = await db.execute(
                select(func.hour(UserActivity.created_at), func.count())
                .where(UserActivity.user_id == user_id, UserActivity.created_at >= since)
                .group_by(func.hour(UserActivity.created_at))
            )
            active_hours = {h: c for h, c in ar.all()}
            busiest_hour = max(active_hours.items(), key=lambda x: x[1])[0] if active_hours else None

            aggregate = {
                "total_minutes": total_minutes,
                "top_apps": [{"app": a, "minutes": m} for a, m in top_apps],
                "avg_session_min": avg_session,
                "peak_hour": peak_hour,
                "busiest_hour": busiest_hour,
                "best_day": weekday_names[best_day] if best_day is not None else None,
                "recurring_schedule": recurring,
            }

            # ---- LLM synthesis ----
            from openai import AsyncOpenAI
            import re
            client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
            summary_lines = [
                f"总使用时长: {total_minutes} 分钟",
                f"常用应用: " + ", ".join(f"{a}({m}min)" for a, m in top_apps),
                f"平均专注会话: {avg_session} 分钟",
                f"最活跃时段: {busiest_hour} 点" if busiest_hour else "",
                f"最佳工作日: {weekday_names[best_day]}" if best_day is not None else "",
                f"周期性日程: " + ", ".join(f"{x['title']}({x['count']}次)" for x in recurring) if recurring else "暂无明显周期性日程",
            ]
            prompt_text = "\n".join(s for s in summary_lines if s)

            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": (
                        "你是一个个人AI助理。下面是用户近30天的行为聚合数据。请据此生成对用户工作习惯的洞察。"
                        "只返回 JSON，格式: "
                        "{\"routine\": \"一段2-4句的中文总结，描述用户的作息与工作节奏\", "
                        "\"patterns\": [\"具体规律1\", \"具体规律2\"], "
                        "\"suggestions\": [\"可操作建议1\", \"可操作建议2\"]}。"
                        "建议要具体可操作（如创建例行日程、调整工作节奏、休息提醒等）。不要输出其他内容。"
                    )},
                    {"role": "user", "content": prompt_text},
                ],
                temperature=0.4,
            )
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", raw, re.S)
            insights = {
                "generated_at": now.isoformat(),
                "aggregate": aggregate,
                "routine": "",
                "patterns": [],
                "suggestions": [],
            }
            if m:
                try:
                    data = _json.loads(m.group(0))
                    insights["routine"] = str(data.get("routine") or "")
                    insights["patterns"] = data.get("patterns") or []
                    insights["suggestions"] = data.get("suggestions") or []
                except Exception:
                    pass

            # ---- Persist into profile.preferences.insights ----
            pr = (await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))).scalar_one_or_none()
            if pr:
                prefs = {}
                try:
                    if pr.preferences:
                        prefs = _json.loads(pr.preferences) if isinstance(pr.preferences, str) else pr.preferences
                except Exception:
                    prefs = {}
                prefs["insights"] = insights
                pr.preferences = _json.dumps(prefs, ensure_ascii=False)
                await db.commit()
                print(f"[insights] generated for user {user_id}")
    except Exception as e:
        print(f"[insights] error: {e}")
