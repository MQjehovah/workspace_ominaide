from pydantic import BaseModel
from datetime import datetime


class PlaylistResponse(BaseModel):
    id: int
    name: str
    song_count: int = 0
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class PlaylistCreateRequest(BaseModel):
    name: str


class PlaylistListResponse(BaseModel):
    playlists: list[PlaylistResponse]


class PlaylistAddSongRequest(BaseModel):
    file_id: int


class PlaylistRenameRequest(BaseModel):
    name: str


class PlaylistReorderRequest(BaseModel):
    item_id: int
    direction: str  # 'up' | 'down'
