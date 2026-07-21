from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from plugins.music.backend.models import Playlist, PlaylistItem
from plugins.files.backend.models import File


async def create_playlist(db: AsyncSession, user_id: int, name: str) -> Playlist:
    pl = Playlist(user_id=user_id, name=name)
    db.add(pl)
    await db.flush()
    await db.refresh(pl)
    return pl


async def list_playlists(db: AsyncSession, user_id: int) -> list[tuple[Playlist, int]]:
    result = await db.execute(
        select(Playlist, func.count(PlaylistItem.id).label("song_count")).outerjoin(
            PlaylistItem, PlaylistItem.playlist_id == Playlist.id
        ).where(Playlist.user_id == user_id).group_by(Playlist.id).order_by(Playlist.updated_at.desc())
    )
    return result.all()


async def delete_playlist(db: AsyncSession, user_id: int, playlist_id: int) -> bool:
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user_id))
    pl = result.scalar_one_or_none()
    if not pl:
        return False
    await db.delete(pl)
    await db.flush()
    return True


async def add_song_to_playlist(db: AsyncSession, user_id: int, playlist_id: int, file_id: int) -> bool:
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user_id))
    if not result.scalar_one_or_none():
        return False
    pos_result = await db.execute(select(func.max(PlaylistItem.position)).where(PlaylistItem.playlist_id == playlist_id))
    max_pos = pos_result.scalar() or 0
    item = PlaylistItem(playlist_id=playlist_id, file_id=file_id, position=max_pos + 1)
    db.add(item)
    await db.flush()
    return True


async def list_playlist_songs(db: AsyncSession, user_id: int, playlist_id: int) -> list[tuple[PlaylistItem, File]]:
    result = await db.execute(
        select(PlaylistItem, File).join(File, File.id == PlaylistItem.file_id).where(
            PlaylistItem.playlist_id == playlist_id, File.user_id == user_id,
        ).order_by(PlaylistItem.position)
    )
    return result.all()


async def remove_song_from_playlist(db: AsyncSession, user_id: int, item_id: int) -> bool:
    result = await db.execute(
        select(PlaylistItem).join(Playlist, Playlist.id == PlaylistItem.playlist_id).where(
            PlaylistItem.id == item_id, Playlist.user_id == user_id
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return False
    await db.delete(item)
    await db.flush()
    return True


async def rename_playlist(db: AsyncSession, user_id: int, playlist_id: int, name: str) -> bool:
    result = await db.execute(select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user_id))
    pl = result.scalar_one_or_none()
    if not pl:
        return False
    pl.name = name
    await db.flush()
    return True


async def reorder_playlist_song(db: AsyncSession, user_id: int, playlist_id: int, item_id: int, direction: str) -> list[tuple[PlaylistItem, File]]:
    pl_result = await db.execute(select(Playlist).where(Playlist.id == playlist_id, Playlist.user_id == user_id))
    if not pl_result.scalar_one_or_none():
        return []
    items_result = await db.execute(
        select(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id).order_by(PlaylistItem.position)
    )
    items = list(items_result.scalars().all())
    idx = next((i for i, it in enumerate(items) if it.id == item_id), -1)
    if idx < 0:
        return []
    swap = idx - 1 if direction == 'up' else idx + 1
    if swap < 0 or swap >= len(items):
        return []
    items[idx].position, items[swap].position = items[swap].position, items[idx].position
    await db.flush()
    return await list_playlist_songs(db, user_id, playlist_id)
