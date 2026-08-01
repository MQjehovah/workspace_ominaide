from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from core.database.base import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<ChatMessage id={self.id} role={self.role} user_id={self.user_id}>"
