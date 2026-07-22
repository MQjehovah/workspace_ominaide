import json
from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPResource
from core.ai.mcp.registry import tool_registry, MCPTool
from plugins.files.backend.service import get_files, get_file as get_file_record, get_download_url
from plugins.files.backend.schemas import FileQueryParams


async def search_files(user_id: int, args: dict) -> MCPCallResponse:
    """Semantic file search using Qdrant, with fallback to filename search."""
    query = args.get("query", "")
    limit = args.get("limit", 10)
    workspace_id = args.get("workspace_id")

    results = []

    try:
        from core.ai.qdrant_index import search_similar
        semantic_results = await search_similar(
            user_id=user_id,
            query=query,
            limit=limit,
            workspace_id=workspace_id,
        )
        if semantic_results:
            results = semantic_results
    except Exception:
        pass

    if not results:
        from sqlalchemy import select, or_
        from plugins.files.backend.models import File
        from core.database.session import async_session

        async with async_session() as db:
            q = select(File).where(File.user_id == user_id, File.status == "active")
            if query:
                like = f"%{query}%"
                q = q.where(File.original_name.ilike(like))
            if workspace_id:
                q = q.where(File.workspace_id == workspace_id)
            q = q.limit(limit)
            result = await db.execute(q)
            files = list(result.scalars().all())

        results = [
            {
                "file_id": f.id,
                "filename": f.original_name,
                "file_size": f.size,
                "mime_type": f.mime_type,
                "workspace_id": f.workspace_id,
                "score": 0.0,
            }
            for f in files
        ]

    return MCPCallResponse(content=[MCPContent(text=json.dumps(results, ensure_ascii=False, default=str))])


async def list_files(user_id: int, args: dict) -> MCPCallResponse:
    """List files with filters."""
    from core.database.session import async_session
    async with async_session() as db:
        params = FileQueryParams(
            page=args.get("page", 1),
            page_size=args.get("limit", 50),
            status=args.get("status", "active"),
            workspace_id=args.get("workspace_id"),
            mime_type=args.get("mime_type"),
        )
        files, total = await get_files(db, user_id, params)

    results = [
        {
            "id": f.id,
            "name": f.original_name,
            "size": f.size,
            "mime_type": f.mime_type,
            "workspace_id": f.workspace_id,
            "is_favorite": f.is_favorite,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in files
    ]
    return MCPCallResponse(content=[MCPContent(text=json.dumps({"files": results, "total": total}, ensure_ascii=False, default=str))])


async def get_file_info(user_id: int, args: dict) -> MCPCallResponse:
    """Get detailed info about a specific file."""
    file_id = args.get("file_id")
    if not file_id:
        return MCPCallResponse(isError=True, content=[MCPContent(text="file_id is required")])

    from core.database.session import async_session
    async with async_session() as db:
        f = await get_file_record(db, user_id, file_id)
        if not f:
            return MCPCallResponse(isError=True, content=[MCPContent(text="File not found")])

        result = {
            "id": f.id,
            "name": f.original_name,
            "size": f.size,
            "mime_type": f.mime_type,
            "bucket": f.bucket,
            "object_key": f.object_key,
            "workspace_id": f.workspace_id,
            "tags": f.tags,
            "is_favorite": f.is_favorite,
            "status": f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        }
    return MCPCallResponse(content=[MCPContent(text=json.dumps(result, ensure_ascii=False, default=str))])


async def get_file_download(user_id: int, args: dict) -> MCPCallResponse:
    """Get a presigned download URL for a file."""
    file_id = args.get("file_id")
    if not file_id:
        return MCPCallResponse(isError=True, content=[MCPContent(text="file_id is required")])

    from core.database.session import async_session
    async with async_session() as db:
        f = await get_file_record(db, user_id, file_id)
        if not f:
            return MCPCallResponse(isError=True, content=[MCPContent(text="File not found")])
        url = await get_download_url(f)

    return MCPCallResponse(content=[MCPContent(text=json.dumps({
        "download_url": url,
        "filename": f.original_name,
    }, ensure_ascii=False))])
