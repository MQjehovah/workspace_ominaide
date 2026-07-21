from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.music.backend.schemas import (
    PlaylistCreateRequest, PlaylistAddSongRequest,
    PlaylistResponse, PlaylistListResponse,
    PlaylistRenameRequest, PlaylistReorderRequest,
)
from plugins.music.backend import service as music_service

router = APIRouter(prefix="/api/music", tags=["music"])


def _serialize_songs(rows):
    return {"songs": [{"item_id": item.id, "file_id": f.id, "name": f.original_name, "size": f.size, "mime": f.mime_type}
                      for item, f in rows]}


@router.get("/playlists")
async def list_playlists(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await music_service.list_playlists(db, user["id"])
    playlists = [
        PlaylistResponse(id=pl.id, name=pl.name, song_count=count, created_at=pl.created_at, updated_at=pl.updated_at)
        for pl, count in rows
    ]
    return PlaylistListResponse(playlists=playlists)


@router.post("/playlists", status_code=201)
async def create_playlist(
    req: PlaylistCreateRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pl = await music_service.create_playlist(db, user["id"], req.name)
    return PlaylistResponse(id=pl.id, name=pl.name, song_count=0, created_at=pl.created_at, updated_at=pl.updated_at)


@router.delete("/playlists/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await music_service.delete_playlist(db, user["id"], playlist_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"message": "Playlist deleted"}


@router.get("/playlists/{playlist_id}/songs")
async def list_playlist_songs(
    playlist_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await music_service.list_playlist_songs(db, user["id"], playlist_id)
    return _serialize_songs(rows)


@router.post("/playlists/{playlist_id}/songs", status_code=201)
async def add_song_to_playlist(
    playlist_id: int,
    req: PlaylistAddSongRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await music_service.add_song_to_playlist(db, user["id"], playlist_id, req.file_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Playlist or file not found")
    return {"message": "Song added"}


@router.delete("/playlists/{playlist_id}/songs/{item_id}")
async def remove_song_from_playlist(
    playlist_id: int,
    item_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await music_service.remove_song_from_playlist(db, user["id"], item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Song not found in playlist")
    return {"message": "Song removed"}


@router.put("/playlists/{playlist_id}")
async def rename_playlist(
    playlist_id: int,
    req: PlaylistRenameRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await music_service.rename_playlist(db, user["id"], playlist_id, req.name)
    if not ok:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"message": "Renamed"}


@router.put("/playlists/{playlist_id}/reorder")
async def reorder_playlist_song(
    playlist_id: int,
    req: PlaylistReorderRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await music_service.reorder_playlist_song(db, user["id"], playlist_id, req.item_id, req.direction)
    if rows == []:
        raise HTTPException(status_code=404, detail="Playlist or item not found")
    return _serialize_songs(rows)
