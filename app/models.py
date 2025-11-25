from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db import Base


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    telegram_chat_id = Column(BigInteger, unique=True, index=True, nullable=False)
    title = Column(String, nullable=True)

    subscriptions = relationship("Subscription", back_populates="chat")

    def __repr__(self) -> str:
        return f"<Chat id={self.id} tg_id={self.telegram_chat_id}>"


class Repo(Base):
    __tablename__ = "repos"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False, default="github")
    owner = Column(String, nullable=True)
    name = Column(String, nullable=True)
    full_name = Column(String, unique=True, index=True, nullable=False)

    subscriptions = relationship("Subscription", back_populates="repo")

    def __repr__(self) -> str:
        return f"<Repo id={self.id} full_name={self.full_name}>"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    events = Column(String, nullable=True)
    branches = Column(String, nullable=True)

    chat = relationship("Chat", back_populates="subscriptions")
    repo = relationship("Repo", back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription chat_id={self.chat_id} repo_id={self.repo_id}>"


class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False)

    event_type = Column(String, nullable=False)
    event_subtype = Column(String, nullable=True)
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    payload_summary = Column(Text, nullable=True)

    chat = relationship("Chat")
    repo = relationship("Repo")

    def __repr__(self) -> str:
        return f"<EventLog chat_id={self.chat_id} repo_id={self.repo_id} type={self.event_type}>"
