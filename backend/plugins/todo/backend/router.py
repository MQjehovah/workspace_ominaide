from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.todo.backend.schemas import TodoCreate, TodoUpdate, TodoResponse
from plugins.todo.backend import service as todo_service

router = APIRouter(tags=["todo-plugin"])


@router.post("/items", response_model=TodoResponse, status_code=201)
async def create_todo(
    req: TodoCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    todo = await todo_service.create_todo(db, user["id"], req)
    return TodoResponse.model_validate(todo)


@router.get("/items", response_model=list[TodoResponse])
async def list_todos(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    todos, total = await todo_service.get_todos(db, user["id"], status, page, page_size)
    return [TodoResponse.model_validate(t) for t in todos]


@router.get("/items/{todo_id}", response_model=TodoResponse)
async def get_todo(
    todo_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    todo = await todo_service.get_todo(db, user["id"], todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse.model_validate(todo)


@router.put("/items/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: int,
    req: TodoUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        todo = await todo_service.update_todo(db, user["id"], todo_id, req)
        return TodoResponse.model_validate(todo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/items/{todo_id}")
async def delete_todo(
    todo_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await todo_service.delete_todo(db, user["id"], todo_id)
        return {"message": "Todo deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
