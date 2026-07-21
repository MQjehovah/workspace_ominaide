from typing import Literal
from pydantic import BaseModel, Field
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
    name: str = Field(min_length=1, max_length=100)


class PlaylistReorderRequest(BaseModel):
    item_id: int
    direction: Literal["up", "down"]
