from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections per user + sync folder.

    Key format: "{user_id}_{folder_id}"
    Pushes file change events to connected desktop clients.
    """

    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    def _key(self, user_id: int, folder_id: int) -> str:
        return f"{user_id}_{folder_id}"

    async def connect(self, ws: WebSocket, user_id: int, folder_id: int):
        await ws.accept()
        key = self._key(user_id, folder_id)
        if key not in self.active:
            self.active[key] = []
        self.active[key].append(ws)

    def disconnect(self, ws: WebSocket, user_id: int, folder_id: int):
        key = self._key(user_id, folder_id)
        if key in self.active:
            self.active[key] = [w for w in self.active[key] if w != ws]
            if not self.active[key]:
                del self.active[key]

    async def notify_folder(self, user_id: int, folder_id: int, event: dict):
        """Broadcast event to all connections for this sync folder."""
        key = self._key(user_id, folder_id)
        if key in self.active:
            dead = []
            for ws in self.active[key]:
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(ws, user_id, folder_id)

    async def notify_user(self, user_id: int, event: dict):
        """Broadcast to all sync folders of a user (for global notifications)."""
        for key, connections in self.active.items():
            if key.startswith(f"{user_id}_"):
                for ws in connections:
                    try:
                        await ws.send_json(event)
                    except Exception:
                        pass


manager = ConnectionManager()
