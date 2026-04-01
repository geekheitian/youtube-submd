from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship

from api.models.status import JobStatus


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True)
    task_type = Column(String(32), nullable=False)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    video_id = Column(String(32), nullable=False, index=True)
    source_url = Column(String(512), nullable=False)
    idempotency_key = Column(String(128), nullable=False, unique=True, index=True)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    result_data = Column(Text, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_detail = Column(Text, nullable=True)

    api_key = relationship("ApiKey", back_populates="jobs")

    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True)
    key_hash = Column(String(128), nullable=False, unique=True, index=True)
    key_prefix = Column(String(16), nullable=False)
    name = Column(String(128), nullable=False)
    is_active = Column(String(1), nullable=False, default="1")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    jobs = relationship("Job", back_populates="api_key")
