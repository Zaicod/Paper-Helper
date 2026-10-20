"""storage library implementation."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    or_,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from paper_agent.core.models import MindMapDraft, Paper, ResearchReport


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserTable(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    username_normalized: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class ProviderCredentialTable(Base):
    __tablename__ = "provider_credentials"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AgentModelSettingTable(Base):
    __tablename__ = "agent_model_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    agent_role: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class PaperTable(Base):
    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_paper_source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    published: Mapped[str | None] = mapped_column(String(64))
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AuthorTable(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)


class PaperAuthorTable(Base):
    __tablename__ = "paper_authors"

    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(
        ForeignKey("authors.id", ondelete="CASCADE"), nullable=False
    )


class PaperCategoryTable(Base):
    __tablename__ = "paper_categories"

    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[str] = mapped_column(String(128), primary_key=True)


class ResearchRunTable(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    topic: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(128))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paper_count: Mapped[int] = mapped_column(Integer, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class RunPaperTable(Base):
    __tablename__ = "research_run_papers"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class AnalysisTable(Base):
    __tablename__ = "paper_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    research_problem: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "paper_id", name="uq_analysis_run_paper"),
    )


class AnalysisFailureTable(Base):
    __tablename__ = "analysis_failures"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), primary_key=True
    )
    external_paper_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    error_type: Mapped[str] = mapped_column(String(255), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)


class CollectionTable(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CollectionPaperTable(Base):
    __tablename__ = "collection_papers"

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PaperNoteTable(Base):
    __tablename__ = "paper_notes"

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class CollectionNoteTable(Base):
    __tablename__ = "collection_notes"

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class MindMapTable(Base):
    __tablename__ = "mind_maps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(512), nullable=False)
    date_from: Mapped[str | None] = mapped_column(String(10))
    date_to: Mapped[str | None] = mapped_column(String(10))
    generator: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MindMapPaperTable(Base):
    __tablename__ = "mind_map_papers"

    mind_map_id: Mapped[int] = mapped_column(
        ForeignKey("mind_maps.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )


class CollectionResearchRunTable(Base):
    __tablename__ = "collection_research_runs"

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TagTable(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)


class PaperTagTable(Base):
    __tablename__ = "paper_tags"

    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class PaperDownloadTable(Base):
    __tablename__ = "paper_downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class PaperLibraryItem(BaseModel):
    source: str
    paper_id: str
    title: str
    abstract: str
    authors: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    published: str | None = None
    page_url: str
    pdf_url: str | None = None
    download_id: int | None = None
    analysis_count: int = 0


class CollectionView(BaseModel):
    id: int
    name: str
    description: str
    paper_count: int


class CollectionPaperView(BaseModel):
    source: str
    paper_id: str
    title: str
    abstract: str
    authors: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    published: str | None = None
    page_url: str
    pdf_url: str | None = None
    added_at: datetime
    note: str = ""


class MindMapView(BaseModel):
    id: int
    collection_id: int
    direction: str
    date_from: str | None = None
    date_to: str | None = None
    generator: str
    paper_ids: list[str] = Field(default_factory=list)
    map: MindMapDraft
    created_at: datetime


class CollectionDetailView(CollectionView):
    overall_note: str = ""
    papers: list[CollectionPaperView] = Field(default_factory=list)
    mind_maps: list[MindMapView] = Field(default_factory=list)
    research_run_ids: list[str] = Field(default_factory=list)


class PaperDownloadView(BaseModel):
    id: int
    local_path: str
    filename: str
    source_url: str
    size_bytes: int


class UserView(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime


class UserCredentials(BaseModel):
    user: UserView
    password_hash: str


class StoredProviderCredential(BaseModel):
    provider: str
    base_url: str
    encrypted_api_key: str
    api_key_hint: str
    updated_at: datetime


class AgentModelSettingView(BaseModel):
    agent_role: str
    provider: str
    model_name: str
    updated_at: datetime


class PaperLibrary:
    """Relational library; Web uses MySQL and offline tests may use SQLite."""

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            database_url,
            echo=echo,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    @classmethod
    def sqlite(cls, path: Path) -> PaperLibrary:
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{path.as_posix()}")

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def create_user(
        self, username: str, email: str, password_hash: str
    ) -> UserView:
        clean_username = username.strip()
        clean_email = email.strip()
        if not 3 <= len(clean_username) <= 64:
            raise ValueError("用户名长度必须为 3 到 64 个字符")
        if not _looks_like_email(clean_email):
            raise ValueError("邮箱格式不正确")
        self.initialize()
        try:
            with self._sessions.begin() as session:
                row = UserTable(
                    username=clean_username,
                    username_normalized=clean_username.casefold(),
                    email=clean_email,
                    email_normalized=clean_email.casefold(),
                    password_hash=password_hash,
                )
                session.add(row)
                session.flush()
                return self._to_user(row)
        except IntegrityError as exc:
            raise ValueError("用户名或邮箱已被注册") from exc

    def get_user(self, user_id: int) -> UserView | None:
        self.initialize()
        with self._sessions() as session:
            row = session.get(UserTable, user_id)
            return self._to_user(row) if row is not None else None

    def get_user_credentials(self, identifier: str) -> UserCredentials | None:
        normalized = identifier.strip().casefold()
        self.initialize()
        with self._sessions() as session:
            row = session.scalar(
                select(UserTable).where(
                    or_(
                        UserTable.username_normalized == normalized,
                        UserTable.email_normalized == normalized,
                    )
                )
            )
            if row is None:
                return None
            return UserCredentials(
                user=self._to_user(row), password_hash=row.password_hash
            )

    def list_provider_credentials(self, user_id: int) -> list[StoredProviderCredential]:
        self.initialize()
        with self._sessions() as session:
            rows = list(
                session.scalars(
                    select(ProviderCredentialTable)
                    .where(ProviderCredentialTable.user_id == user_id)
                    .order_by(ProviderCredentialTable.provider)
                )
            )
            return [
                StoredProviderCredential(
                    provider=row.provider,
                    base_url=row.base_url,
                    encrypted_api_key=row.encrypted_api_key,
                    api_key_hint=row.api_key_hint,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    def get_provider_credential(
        self, user_id: int, provider: str
    ) -> StoredProviderCredential | None:
        self.initialize()
        with self._sessions() as session:
            row = session.get(ProviderCredentialTable, (user_id, provider))
            if row is None:
                return None
            return StoredProviderCredential(
                provider=row.provider,
                base_url=row.base_url,
                encrypted_api_key=row.encrypted_api_key,
                api_key_hint=row.api_key_hint,
                updated_at=row.updated_at,
            )

    def save_provider_credential(
        self,
        user_id: int,
        provider: str,
        base_url: str,
        encrypted_api_key: str,
        api_key_hint: str,
    ) -> None:
        self.initialize()
        with self._sessions.begin() as session:
            if session.get(UserTable, user_id) is None:
                raise KeyError("user not found")
            row = session.get(ProviderCredentialTable, (user_id, provider))
            if row is None:
                session.add(
                    ProviderCredentialTable(
                        user_id=user_id,
                        provider=provider,
                        base_url=base_url,
                        encrypted_api_key=encrypted_api_key,
                        api_key_hint=api_key_hint,
                    )
                )
            else:
                row.base_url = base_url
                row.encrypted_api_key = encrypted_api_key
                row.api_key_hint = api_key_hint
                row.updated_at = _utcnow()

    def delete_provider_credential(self, user_id: int, provider: str) -> bool:
        self.initialize()
        with self._sessions.begin() as session:
            row = session.get(ProviderCredentialTable, (user_id, provider))
            if row is None:
                return False
            session.delete(row)
            return True

    def list_agent_model_settings(self, user_id: int) -> list[AgentModelSettingView]:
        self.initialize()
        with self._sessions() as session:
            rows = list(
                session.scalars(
                    select(AgentModelSettingTable)
                    .where(AgentModelSettingTable.user_id == user_id)
                    .order_by(AgentModelSettingTable.agent_role)
                )
            )
            return [
                AgentModelSettingView(
                    agent_role=row.agent_role,
                    provider=row.provider,
                    model_name=row.model_name,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    def save_agent_model_setting(
        self, user_id: int, agent_role: str, provider: str, model_name: str
    ) -> AgentModelSettingView:
        self.initialize()
        with self._sessions.begin() as session:
            if session.get(UserTable, user_id) is None:
                raise KeyError("user not found")
            row = session.get(AgentModelSettingTable, (user_id, agent_role))
            if row is None:
                row = AgentModelSettingTable(
                    user_id=user_id,
                    agent_role=agent_role,
                    provider=provider,
                    model_name=model_name,
                )
                session.add(row)
            else:
                row.provider = provider
                row.model_name = model_name
                row.updated_at = _utcnow()
            session.flush()
            return AgentModelSettingView(
                agent_role=row.agent_role,
                provider=row.provider,
                model_name=row.model_name,
                updated_at=row.updated_at,
            )

    def save_report(
        self,
        report: ResearchReport,
        run_id: str,
        category: str | None = None,
    ) -> str:
        """Upsert papers and atomically replace one research run's results."""

        self.initialize()
        with self._sessions.begin() as session:
            run = session.get(ResearchRunTable, run_id)
            if run is None:
                run = ResearchRunTable(
                    id=run_id,
                    topic=report.topic,
                    category=category,
                    generated_at=report.generated_at,
                    paper_count=len(report.papers),
                    success_count=len(report.analyses),
                    failure_count=len(report.analysis_failures),
                    report_json=report.model_dump(mode="json"),
                )
                session.add(run)
            else:
                run.topic = report.topic
                run.category = category
                run.generated_at = report.generated_at
                run.paper_count = len(report.papers)
                run.success_count = len(report.analyses)
                run.failure_count = len(report.analysis_failures)
                run.report_json = report.model_dump(mode="json")

            session.flush()
            session.execute(delete(RunPaperTable).where(RunPaperTable.run_id == run_id))
            session.execute(delete(AnalysisTable).where(AnalysisTable.run_id == run_id))
            session.execute(
                delete(AnalysisFailureTable).where(
                    AnalysisFailureTable.run_id == run_id
                )
            )

            by_external_id: dict[str, PaperTable] = {}
            for position, paper in enumerate(report.papers):
                row = self._upsert_paper(session, paper)
                by_external_id.setdefault(paper.paper_id, row)
                session.add(
                    RunPaperTable(
                        run_id=run_id,
                        paper_id=row.id,
                        position=position,
                    )
                )

            for analysis in report.analyses:
                paper_row = by_external_id.get(analysis.paper_id)
                if paper_row is None:
                    continue
                session.add(
                    AnalysisTable(
                        run_id=run_id,
                        paper_id=paper_row.id,
                        research_problem=analysis.research_problem,
                        payload=analysis.model_dump(mode="json"),
                    )
                )

            for failure in report.analysis_failures:
                session.add(
                    AnalysisFailureTable(
                        run_id=run_id,
                        external_paper_id=failure.paper_id,
                        error_type=failure.error_type,
                        retry_count=failure.retry_count,
                        stage=failure.stage,
                        message=failure.message,
                    )
                )
        return run_id

    def list_papers(
        self, query: str | None = None, limit: int = 50
    ) -> list[PaperLibraryItem]:
        self.initialize()
        limit = max(1, min(limit, 200))
        with self._sessions() as session:
            statement = select(PaperTable).order_by(PaperTable.updated_at.desc()).limit(limit)
            if query and query.strip():
                pattern = f"%{query.strip()}%"
                statement = statement.where(
                    or_(
                        PaperTable.title.ilike(pattern),
                        PaperTable.abstract.ilike(pattern),
                        PaperTable.external_id.ilike(pattern),
                    )
                )
            rows = list(session.scalars(statement))
            return [self._to_item(session, row) for row in rows]

    def get_paper(self, source: str, paper_id: str) -> PaperLibraryItem | None:
        self.initialize()
        with self._sessions() as session:
            row = session.scalar(
                select(PaperTable).where(
                    PaperTable.source == source,
                    PaperTable.external_id == paper_id,
                )
            )
            return self._to_item(session, row) if row is not None else None

    def import_downloaded_paper(
        self,
        paper: Paper,
        *,
        local_path: Path,
        source_url: str,
        size_bytes: int,
        collection_id: int | None = None,
        collection_name: str | None = None,
    ) -> PaperLibraryItem:
        """Atomically upsert one downloaded paper and assign its collection."""

        clean_name = (collection_name or "").strip()
        self.initialize()
        with self._sessions.begin() as session:
            row = self._upsert_paper(session, paper)

            collection = None
            if collection_id is not None:
                collection = session.get(CollectionTable, collection_id)
                if collection is None:
                    raise KeyError("collection not found")
            elif clean_name:
                collection = session.scalar(
                    select(CollectionTable).where(CollectionTable.name == clean_name)
                )
                if collection is None:
                    collection = CollectionTable(name=clean_name, description="")
                    session.add(collection)
                    session.flush()
            else:
                raise ValueError("collection is required")

            if session.get(CollectionPaperTable, (collection.id, row.id)) is None:
                session.add(
                    CollectionPaperTable(collection_id=collection.id, paper_id=row.id)
                )

            download = session.scalar(
                select(PaperDownloadTable).where(PaperDownloadTable.paper_id == row.id)
            )
            if download is None:
                download = PaperDownloadTable(
                    paper_id=row.id,
                    local_path=str(local_path.resolve()),
                    source_url=source_url,
                    size_bytes=size_bytes,
                )
                session.add(download)
            else:
                download.local_path = str(local_path.resolve())
                download.source_url = source_url
                download.size_bytes = size_bytes
                download.downloaded_at = _utcnow()
            session.flush()
            return self._to_item(session, row)

    def get_download(self, download_id: int) -> PaperDownloadView | None:
        self.initialize()
        with self._sessions() as session:
            row = session.get(PaperDownloadTable, download_id)
            if row is None:
                return None
            return PaperDownloadView(
                id=row.id,
                local_path=row.local_path,
                filename=Path(row.local_path).name,
                source_url=row.source_url,
                size_bytes=row.size_bytes,
            )

    def create_collection(self, name: str, description: str = "") -> CollectionView:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("collection name cannot be empty")
        self.initialize()
        with self._sessions.begin() as session:
            row = session.scalar(
                select(CollectionTable).where(CollectionTable.name == clean_name)
            )
            if row is None:
                row = CollectionTable(name=clean_name, description=description.strip())
                session.add(row)
                session.flush()
            return CollectionView(
                id=row.id,
                name=row.name,
                description=row.description,
                paper_count=self._collection_count(session, row.id),
            )

    def add_to_collection(
        self, collection_id: int, source: str, paper_id: str
    ) -> None:
        self.initialize()
        with self._sessions.begin() as session:
            collection = session.get(CollectionTable, collection_id)
            if collection is None:
                raise KeyError("collection not found")
            paper = session.scalar(
                select(PaperTable).where(
                    PaperTable.source == source,
                    PaperTable.external_id == paper_id,
                )
            )
            if paper is None:
                raise KeyError("paper not found")
            existing = session.get(CollectionPaperTable, (collection_id, paper.id))
            if existing is None:
                session.add(
                    CollectionPaperTable(
                        collection_id=collection_id,
                        paper_id=paper.id,
                    )
                )

    def add_tag(self, source: str, paper_id: str, tag: str) -> None:
        clean_tag = tag.strip()
        if not clean_tag:
            raise ValueError("tag cannot be empty")
        self.initialize()
        with self._sessions.begin() as session:
            paper = session.scalar(
                select(PaperTable).where(
                    PaperTable.source == source,
                    PaperTable.external_id == paper_id,
                )
            )
            if paper is None:
                raise KeyError("paper not found")
            tag_row = session.scalar(select(TagTable).where(TagTable.name == clean_tag))
            if tag_row is None:
                tag_row = TagTable(name=clean_tag)
                session.add(tag_row)
                session.flush()
            if session.get(PaperTagTable, (paper.id, tag_row.id)) is None:
                session.add(PaperTagTable(paper_id=paper.id, tag_id=tag_row.id))

    def list_collections(self, query: str | None = None) -> list[CollectionView]:
        self.initialize()
        with self._sessions() as session:
            statement = select(CollectionTable).order_by(CollectionTable.name)
            if query and query.strip():
                pattern = f"%{query.strip()}%"
                statement = statement.where(
                    or_(
                        CollectionTable.name.ilike(pattern),
                        CollectionTable.description.ilike(pattern),
                    )
                )
            rows = list(session.scalars(statement))
            return [
                CollectionView(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    paper_count=self._collection_count(session, row.id),
                )
                for row in rows
            ]

    def delete_collection(self, collection_id: int) -> bool:
        """Delete one collection and its scoped notes/maps, never the papers."""

        self.initialize()
        with self._sessions.begin() as session:
            collection = session.get(CollectionTable, collection_id)
            if collection is None:
                return False
            mind_map_ids = list(
                session.scalars(
                    select(MindMapTable.id).where(
                        MindMapTable.collection_id == collection_id
                    )
                )
            )
            if mind_map_ids:
                session.execute(
                    delete(MindMapPaperTable).where(
                        MindMapPaperTable.mind_map_id.in_(mind_map_ids)
                    )
                )
            session.execute(
                delete(MindMapTable).where(MindMapTable.collection_id == collection_id)
            )
            session.execute(
                delete(PaperNoteTable).where(
                    PaperNoteTable.collection_id == collection_id
                )
            )
            session.execute(
                delete(CollectionNoteTable).where(
                    CollectionNoteTable.collection_id == collection_id
                )
            )
            session.execute(
                delete(CollectionResearchRunTable).where(
                    CollectionResearchRunTable.collection_id == collection_id
                )
            )
            session.execute(
                delete(CollectionPaperTable).where(
                    CollectionPaperTable.collection_id == collection_id
                )
            )
            session.delete(collection)
            return True

    def collection_exists(self, collection_id: int) -> bool:
        self.initialize()
        with self._sessions() as session:
            return session.get(CollectionTable, collection_id) is not None

    def get_collection(self, collection_id: int) -> CollectionDetailView | None:
        """Return one complete collection workspace, including notes and maps."""

        self.initialize()
        with self._sessions() as session:
            collection = session.get(CollectionTable, collection_id)
            if collection is None:
                return None
            paper_rows = list(
                session.execute(
                    select(PaperTable, CollectionPaperTable.added_at)
                    .join(
                        CollectionPaperTable,
                        CollectionPaperTable.paper_id == PaperTable.id,
                    )
                    .where(CollectionPaperTable.collection_id == collection_id)
                    .order_by(CollectionPaperTable.added_at.desc(), PaperTable.title)
                )
            )
            papers: list[CollectionPaperView] = []
            for paper_row, added_at in paper_rows:
                item = self._to_item(session, paper_row)
                note = session.get(PaperNoteTable, (collection_id, paper_row.id))
                papers.append(
                    CollectionPaperView(
                        source=item.source,
                        paper_id=item.paper_id,
                        title=item.title,
                        abstract=item.abstract,
                        authors=item.authors,
                        categories=item.categories,
                        published=item.published,
                        page_url=item.page_url,
                        pdf_url=item.pdf_url,
                        added_at=added_at,
                        note=note.content if note else "",
                    )
                )
            collection_note = session.get(CollectionNoteTable, collection_id)
            maps = list(
                session.scalars(
                    select(MindMapTable)
                    .where(MindMapTable.collection_id == collection_id)
                    .order_by(MindMapTable.created_at.desc())
                )
            )
            run_ids = list(
                session.scalars(
                    select(CollectionResearchRunTable.run_id)
                    .where(CollectionResearchRunTable.collection_id == collection_id)
                    .order_by(CollectionResearchRunTable.created_at.desc())
                )
            )
            return CollectionDetailView(
                id=collection.id,
                name=collection.name,
                description=collection.description,
                paper_count=len(papers),
                overall_note=collection_note.content if collection_note else "",
                papers=papers,
                mind_maps=[self._to_mind_map(session, row) for row in maps],
                research_run_ids=run_ids,
            )

    def update_collection_note(self, collection_id: int, content: str) -> str:
        self.initialize()
        with self._sessions.begin() as session:
            if session.get(CollectionTable, collection_id) is None:
                raise KeyError("collection not found")
            note = session.get(CollectionNoteTable, collection_id)
            if note is None:
                note = CollectionNoteTable(collection_id=collection_id, content=content)
                session.add(note)
            else:
                note.content = content
                note.updated_at = _utcnow()
        return content

    def update_paper_note(
        self, collection_id: int, source: str, paper_id: str, content: str
    ) -> str:
        self.initialize()
        with self._sessions.begin() as session:
            paper = session.scalar(
                select(PaperTable).where(
                    PaperTable.source == source,
                    PaperTable.external_id == paper_id,
                )
            )
            if paper is None or session.get(
                CollectionPaperTable, (collection_id, paper.id)
            ) is None:
                raise KeyError("paper is not in this collection")
            note = session.get(PaperNoteTable, (collection_id, paper.id))
            if note is None:
                note = PaperNoteTable(
                    collection_id=collection_id,
                    paper_id=paper.id,
                    content=content,
                )
                session.add(note)
            else:
                note.content = content
                note.updated_at = _utcnow()
        return content

    def get_collection_papers(
        self,
        collection_id: int,
        references: list[tuple[str, str]] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[Paper]:
        """Select collection papers by explicit references and added date."""

        selected = set(references or [])
        self.initialize()
        with self._sessions() as session:
            if session.get(CollectionTable, collection_id) is None:
                raise KeyError("collection not found")
            statement = (
                select(PaperTable)
                .join(
                    CollectionPaperTable,
                    CollectionPaperTable.paper_id == PaperTable.id,
                )
                .where(CollectionPaperTable.collection_id == collection_id)
                .order_by(CollectionPaperTable.added_at, PaperTable.id)
            )
            if date_from:
                start = datetime.combine(
                    date.fromisoformat(date_from), time.min, tzinfo=timezone.utc
                )
                statement = statement.where(CollectionPaperTable.added_at >= start)
            if date_to:
                end = datetime.combine(
                    date.fromisoformat(date_to) + timedelta(days=1),
                    time.min,
                    tzinfo=timezone.utc,
                )
                statement = statement.where(CollectionPaperTable.added_at < end)
            rows = list(session.scalars(statement))
            if selected:
                rows = [
                    row
                    for row in rows
                    if (row.source, row.external_id) in selected
                ]
            return [self._to_paper(session, row) for row in rows]

    def get_collection_notes(self, collection_id: int) -> tuple[str, dict[str, str]]:
        self.initialize()
        with self._sessions() as session:
            collection_note = session.get(CollectionNoteTable, collection_id)
            notes = list(
                session.execute(
                    select(PaperTable.external_id, PaperNoteTable.content)
                    .join(PaperNoteTable, PaperNoteTable.paper_id == PaperTable.id)
                    .where(PaperNoteTable.collection_id == collection_id)
                )
            )
            return (
                collection_note.content if collection_note else "",
                {paper_id: content for paper_id, content in notes},
            )

    def save_mind_map(
        self,
        collection_id: int,
        direction: str,
        date_from: str | None,
        date_to: str | None,
        generator: str,
        draft: MindMapDraft,
        references: list[tuple[str, str]],
    ) -> MindMapView:
        self.initialize()
        with self._sessions.begin() as session:
            if session.get(CollectionTable, collection_id) is None:
                raise KeyError("collection not found")
            row = MindMapTable(
                collection_id=collection_id,
                direction=direction,
                date_from=date_from,
                date_to=date_to,
                generator=generator,
                payload=draft.model_dump(mode="json"),
            )
            session.add(row)
            session.flush()
            for source, external_id in references:
                paper = session.scalar(
                    select(PaperTable).where(
                        PaperTable.source == source,
                        PaperTable.external_id == external_id,
                    )
                )
                if paper is not None:
                    session.add(MindMapPaperTable(mind_map_id=row.id, paper_id=paper.id))
            session.flush()
            return self._to_mind_map(session, row)

    def link_research_run(self, collection_id: int, run_id: str) -> None:
        self.initialize()
        with self._sessions.begin() as session:
            if session.get(CollectionTable, collection_id) is None:
                raise KeyError("collection not found")
            if session.get(ResearchRunTable, run_id) is None:
                raise KeyError("research run not found")
            key = (collection_id, run_id)
            if session.get(CollectionResearchRunTable, key) is None:
                session.add(
                    CollectionResearchRunTable(
                        collection_id=collection_id,
                        run_id=run_id,
                    )
                )

    def close(self) -> None:
        self.engine.dispose()

    @staticmethod
    def _to_paper(session: Session, row: PaperTable) -> Paper:
        item = PaperLibrary._to_item(session, row)
        return Paper(
            paper_id=item.paper_id,
            source=item.source,
            title=item.title,
            authors=item.authors,
            abstract=item.abstract,
            published=item.published,
            categories=item.categories,
            page_url=item.page_url,
            pdf_url=item.pdf_url,
        )

    @staticmethod
    def _to_mind_map(session: Session, row: MindMapTable) -> MindMapView:
        paper_ids = list(
            session.scalars(
                select(PaperTable.external_id)
                .join(MindMapPaperTable, MindMapPaperTable.paper_id == PaperTable.id)
                .where(MindMapPaperTable.mind_map_id == row.id)
                .order_by(PaperTable.external_id)
            )
        )
        return MindMapView(
            id=row.id,
            collection_id=row.collection_id,
            direction=row.direction,
            date_from=row.date_from,
            date_to=row.date_to,
            generator=row.generator,
            paper_ids=paper_ids,
            map=MindMapDraft.model_validate(row.payload),
            created_at=row.created_at,
        )

    @staticmethod
    def _upsert_paper(session: Session, paper: Paper) -> PaperTable:
        row = session.scalar(
            select(PaperTable).where(
                PaperTable.source == paper.source,
                PaperTable.external_id == paper.paper_id,
            )
        )
        if row is None:
            row = PaperTable(
                source=paper.source,
                external_id=paper.paper_id,
                title=paper.title,
                abstract=paper.abstract,
                published=paper.published,
                page_url=paper.page_url,
                pdf_url=paper.pdf_url,
            )
            session.add(row)
            session.flush()
        else:
            row.title = paper.title
            row.abstract = paper.abstract
            row.published = paper.published
            row.page_url = paper.page_url
            row.pdf_url = paper.pdf_url
            row.updated_at = _utcnow()

        session.execute(delete(PaperAuthorTable).where(PaperAuthorTable.paper_id == row.id))
        for position, author_name in enumerate(paper.authors):
            author = session.scalar(
                select(AuthorTable).where(AuthorTable.name == author_name)
            )
            if author is None:
                author = AuthorTable(name=author_name)
                session.add(author)
                session.flush()
            session.add(
                PaperAuthorTable(
                    paper_id=row.id,
                    position=position,
                    author_id=author.id,
                )
            )

        session.execute(
            delete(PaperCategoryTable).where(PaperCategoryTable.paper_id == row.id)
        )
        for category in dict.fromkeys(paper.categories):
            session.add(PaperCategoryTable(paper_id=row.id, category=category))
        return row

    @staticmethod
    def _to_item(session: Session, row: PaperTable) -> PaperLibraryItem:
        authors = list(
            session.scalars(
                select(AuthorTable.name)
                .join(PaperAuthorTable, PaperAuthorTable.author_id == AuthorTable.id)
                .where(PaperAuthorTable.paper_id == row.id)
                .order_by(PaperAuthorTable.position)
            )
        )
        categories = list(
            session.scalars(
                select(PaperCategoryTable.category)
                .where(PaperCategoryTable.paper_id == row.id)
                .order_by(PaperCategoryTable.category)
            )
        )
        tags = list(
            session.scalars(
                select(TagTable.name)
                .join(PaperTagTable, PaperTagTable.tag_id == TagTable.id)
                .where(PaperTagTable.paper_id == row.id)
                .order_by(TagTable.name)
            )
        )
        collections = list(
            session.scalars(
                select(CollectionTable.name)
                .join(
                    CollectionPaperTable,
                    CollectionPaperTable.collection_id == CollectionTable.id,
                )
                .where(CollectionPaperTable.paper_id == row.id)
                .order_by(CollectionTable.name)
            )
        )
        download_id = session.scalar(
            select(PaperDownloadTable.id).where(PaperDownloadTable.paper_id == row.id)
        )
        analysis_count = session.scalar(
            select(func.count(AnalysisTable.id)).where(AnalysisTable.paper_id == row.id)
        )
        return PaperLibraryItem(
            source=row.source,
            paper_id=row.external_id,
            title=row.title,
            abstract=row.abstract,
            authors=authors,
            categories=categories,
            collections=collections,
            tags=tags,
            published=row.published,
            page_url=row.page_url,
            pdf_url=row.pdf_url,
            download_id=download_id,
            analysis_count=int(analysis_count or 0),
        )

    @staticmethod
    def _collection_count(session: Session, collection_id: int) -> int:
        count = session.scalar(
            select(func.count())
            .select_from(CollectionPaperTable)
            .where(CollectionPaperTable.collection_id == collection_id)
        )
        return int(count or 0)

    @staticmethod
    def _to_user(row: UserTable) -> UserView:
        return UserView(
            id=row.id,
            username=row.username,
            email=row.email,
            created_at=row.created_at,
        )


def _looks_like_email(value: str) -> bool:
    if not value or len(value) > 320 or value.count("@") != 1:
        return False
    local, domain = value.rsplit("@", 1)
    return bool(local and "." in domain and not domain.startswith("."))
