from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, String, create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session

from clearcv.schemas import ParseResult, StoredResume


class Base(DeclarativeBase):
    pass


class Record(Base):
    __tablename__ = "resume_records"
    id = Column(String(36), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    result = Column(JSON, nullable=False)


class Store:
    def __init__(self, url: str, retention_hours: int):
        parsed = make_url(url)
        if parsed.drivername.startswith("sqlite") and parsed.database not in {None, ":memory:"}:
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"check_same_thread": False, "timeout": 30}
            if parsed.drivername.startswith("sqlite")
            else {},
        )
        self.retention_hours = retention_hours

    def initialize(self):
        Base.metadata.create_all(self.engine)

    def ready(self):
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def purge(self):
        with Session(self.engine) as session, session.begin():
            session.execute(delete(Record).where(Record.expires_at <= datetime.now(UTC)))

    @staticmethod
    def output(record: Record) -> StoredResume:
        def utc(value: datetime) -> str:
            return (
                value.replace(tzinfo=UTC).isoformat()
                if value.tzinfo is None
                else value.astimezone(UTC).isoformat()
            )

        return StoredResume(
            id=record.id,
            created_at=utc(record.created_at),
            expires_at=utc(record.expires_at),
            result=ParseResult.model_validate(record.result),
        )

    def save(self, result: ParseResult) -> StoredResume:
        now = datetime.now(UTC)
        record = Record(
            id=str(uuid4()),
            created_at=now,
            expires_at=now + timedelta(hours=self.retention_hours),
            result=result.model_dump(mode="json"),
        )
        with Session(self.engine) as session, session.begin():
            session.add(record)
            session.flush()
            return self.output(record)

    def get(self, record_id: str) -> StoredResume | None:
        with Session(self.engine) as session:
            record = session.scalar(
                select(Record).where(Record.id == record_id, Record.expires_at > datetime.now(UTC))
            )
            return self.output(record) if record else None

    def list(self, limit: int, offset: int) -> list[dict]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(Record)
                .where(Record.expires_at > datetime.now(UTC))
                .order_by(Record.created_at.desc(), Record.id)
                .limit(limit)
                .offset(offset)
            )
            return [
                {
                    "id": item.id,
                    "created_at": self.output(item).created_at,
                    "name": item.result["fields"]["name"]["value"]
                    if item.result["fields"]["name"]
                    else None,
                    "provider": item.result["provider"],
                    "warning_count": len(item.result["warnings"]),
                }
                for item in records
            ]

    def remove(self, record_id: str) -> bool:
        with Session(self.engine) as session, session.begin():
            result = session.execute(delete(Record).where(Record.id == record_id))
            return result.rowcount > 0
