"""Modèles SQLAlchemy pour Meta Analytics & Intelligence (Community Manager IA).

Tables additives uniquement. Aucune table existante n'est modifiée.
Toutes les métriques sont historisées via des snapshots ; aucune valeur
indisponible n'est jamais stockée sous forme de zéro.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class MetaAnalyticsAccount(Base):
    """Compte Meta suivi (Instagram professionnel ou Page Facebook).

    Un compte est identifié par son identifiant externe Meta (platform_account_id)
    et sa plateforme. Le jeton d'accès et la configuration Meta sont partagés avec
    le service de connexion existant (SportInstagramConnectService / ModuleConfig
    administration) : ce modèle ne duplique ni token ni secret.
    """

    __tablename__ = "meta_analytics_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # instagram | facebook
    platform_account_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    username: Mapped[str | None] = mapped_column(String(150), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # business | page | ...
    business_portfolio_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    page_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Page Facebook liée (Instagram)
    instagram_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # compte IG lié (Page FB)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    snapshots: Mapped[list["MetaAnalyticsSnapshot"]] = relationship(
        "MetaAnalyticsSnapshot", back_populates="account", cascade="all, delete-orphan"
    )
    account_metrics: Mapped[list["MetaAnalyticsAccountMetrics"]] = relationship(
        "MetaAnalyticsAccountMetrics", back_populates="account", cascade="all, delete-orphan"
    )
    audience: Mapped[list["MetaAnalyticsAudience"]] = relationship(
        "MetaAnalyticsAudience", back_populates="account", cascade="all, delete-orphan"
    )
    media: Mapped[list["MetaAnalyticsMedia"]] = relationship(
        "MetaAnalyticsMedia", back_populates="account", cascade="all, delete-orphan"
    )
    sync_runs: Mapped[list["MetaAnalyticsSyncRun"]] = relationship(
        "MetaAnalyticsSyncRun", back_populates="account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("uq_meta_analytics_account_platform", "platform", "platform_account_id", unique=True),
        Index("ix_meta_analytics_accounts_platform", "platform"),
        Index("ix_meta_analytics_accounts_active", "is_active"),
    )


class MetaAnalyticsMedia(Base):
    """Média (publication / Reel / carrousel / vidéo) collecté depuis Meta."""

    __tablename__ = "meta_analytics_media"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("meta_analytics_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    media_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # IMAGE | CAROUSEL_ALBUM | REELS | VIDEO
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    permalink: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    account: Mapped["MetaAnalyticsAccount"] = relationship("MetaAnalyticsAccount", back_populates="media")
    snapshots: Mapped[list["MetaAnalyticsSnapshot"]] = relationship(
        "MetaAnalyticsSnapshot", back_populates="media", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("uq_meta_analytics_media_account_media", "account_id", "media_id", unique=True),
        Index("ix_meta_analytics_media_account", "account_id"),
        Index("ix_meta_analytics_media_type", "media_type"),
    )


class MetaAnalyticsSnapshot(Base):
    """Valeur historisée d'une métrique à un instant donné.

    Une métrique indisponible est stockée avec metric_status='unavailable' et
    metric_value=NULL (jamais convertie en zéro).
    """

    __tablename__ = "meta_analytics_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("meta_analytics_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[int | None] = mapped_column(
        ForeignKey("meta_analytics_media.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_value: Mapped[float | None] = mapped_column(nullable=True)
    metric_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="available", index=True
    )  # available | unavailable | unsupported | error | pending
    period: Mapped[str | None] = mapped_column(String(30), nullable=True)  # day | week | month | lifetime | total
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    api_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_api: Mapped[str | None] = mapped_column(String(100), nullable=True)

    account: Mapped["MetaAnalyticsAccount"] = relationship("MetaAnalyticsAccount", back_populates="snapshots")
    media: Mapped["MetaAnalyticsMedia | None"] = relationship("MetaAnalyticsMedia", back_populates="snapshots")

    __table_args__ = (
        Index("ix_meta_analytics_snapshots_account_metric", "account_id", "metric_name", "collected_at"),
        Index("ix_meta_analytics_snapshots_media", "media_id", "metric_name"),
        Index("ix_meta_analytics_snapshots_period", "period_start", "period_end"),
    )


class MetaAnalyticsAccountMetrics(Base):
    """Dernière valeur connue (rollup) par compte et métrique, pour lecture rapide."""

    __tablename__ = "meta_analytics_account_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("meta_analytics_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_value: Mapped[float | None] = mapped_column(nullable=True)
    metric_status: Mapped[str] = mapped_column(String(30), nullable=False, default="available")
    period: Mapped[str | None] = mapped_column(String(30), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    account: Mapped["MetaAnalyticsAccount"] = relationship("MetaAnalyticsAccount", back_populates="account_metrics")

    __table_args__ = (
        Index("uq_meta_analytics_account_metrics", "account_id", "metric_name", "period", unique=True),
    )


class MetaAnalyticsAudience(Base):
    """Répartition d'audience (démographique / géographique) historisée."""

    __tablename__ = "meta_analytics_audience"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("meta_analytics_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dimension: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # gender_age | city | country | locale
    dimension_value: Mapped[str] = mapped_column(String(150), nullable=False)
    metric_value: Mapped[float | None] = mapped_column(nullable=True)  # pourcentage ou nombre
    metric_status: Mapped[str] = mapped_column(String(30), nullable=False, default="available")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    account: Mapped["MetaAnalyticsAccount"] = relationship("MetaAnalyticsAccount", back_populates="audience")

    __table_args__ = (
        Index("uq_meta_analytics_audience", "account_id", "dimension", "dimension_value", "collected_at", unique=False),
        Index("ix_meta_analytics_audience_account_dim", "account_id", "dimension"),
    )


class MetaAnalyticsSyncRun(Base):
    """Trace d'exécution d'une synchronisation (incrémentale, résistante aux erreurs)."""

    __tablename__ = "meta_analytics_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Nullable : la trace est créée au début du cycle, avant la résolution du
    # compte Meta (account_id renseigné ensuite, ou laissé nul si la résolution
    # échoue). Le verrou multi-worker repose sur status/finished_at, pas ici.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("meta_analytics_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # started | completed | failed | partial
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accounts_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metrics_collected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    account: Mapped["MetaAnalyticsAccount"] = relationship("MetaAnalyticsAccount", back_populates="sync_runs")

    __table_args__ = (
        Index("ix_meta_analytics_sync_runs_platform_status", "platform", "status", "started_at"),
    )


class MetaAnalyticsAIAnalysis(Base):
    """Analyse éditoriale produite par l'IA (via l'AI Gateway existante)."""

    __tablename__ = "meta_analytics_ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)  # performance | trends | recommendations
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    findings_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(30), nullable=True)  # low | medium | high
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recommendations: Mapped[list["MetaAnalyticsRecommendation"]] = relationship(
        "MetaAnalyticsRecommendation", back_populates="analysis", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_meta_analytics_ai_analyses_period", "period_start", "period_end"),
    )


class MetaAnalyticsRecommendation(Base):
    """Recommandation éditoriale IA avec traçabilité (données, indicateurs, confiance)."""

    __tablename__ = "meta_analytics_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("meta_analytics_ai_analyses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recommendation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # format | topic | time | hashtag | content
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    indicators_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")  # pending | accepted | refused | modified | implemented
    action: Mapped[str | None] = mapped_column(String(50), nullable=True)  # calendar | studio | ignore | improve
    linked_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("editorial_calendar_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    linked_publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("sport_publications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis: Mapped["MetaAnalyticsAIAnalysis | None"] = relationship("MetaAnalyticsAIAnalysis", back_populates="recommendations")

    __table_args__ = (
        Index("ix_meta_analytics_recommendations_status", "status"),
        Index("ix_meta_analytics_recommendations_created", "created_at"),
    )


__all__ = [
    "MetaAnalyticsAccount",
    "MetaAnalyticsMedia",
    "MetaAnalyticsSnapshot",
    "MetaAnalyticsAccountMetrics",
    "MetaAnalyticsAudience",
    "MetaAnalyticsSyncRun",
    "MetaAnalyticsAIAnalysis",
    "MetaAnalyticsRecommendation",
]
