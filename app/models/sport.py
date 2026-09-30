from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class SportAthlete(Base):
    __tablename__ = "sport_athletes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    activities: Mapped[list["SportActivity"]] = relationship("SportActivity", back_populates="athlete", cascade="all, delete-orphan")
    goals: Mapped[list["SportGoal"]] = relationship("SportGoal", back_populates="athlete", cascade="all, delete-orphan")


class SportActivity(Base):
    __tablename__ = "sport_activities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    sport_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    activity_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_loss_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_speed_m_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_pace_sec_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cadence: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="manual", index=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    athlete: Mapped[SportAthlete] = relationship("SportAthlete", back_populates="activities")
    track_points: Mapped[list["SportTrackPoint"]] = relationship("SportTrackPoint", back_populates="activity", cascade="all, delete-orphan", order_by="SportTrackPoint.sequence")

    __table_args__ = (
        Index("ix_sport_activities_athlete_started", "athlete_id", "started_at"),
        Index("uq_sport_activity_source_external", "athlete_id", "source_type", "external_id", unique=True),
    )


class SportTrackPoint(Base):
    __tablename__ = "sport_track_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("sport_activities.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_m_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    cadence: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    activity: Mapped[SportActivity] = relationship("SportActivity", back_populates="track_points")


class SportActivityAnalysis(Base):
    __tablename__ = "sport_activity_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("sport_activities.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    analysis_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="calculated")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ai_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    ai_analysis_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ai_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    activity: Mapped[SportActivity] = relationship("SportActivity")


class SportCoachConversation(Base):
    """LEGACY — conversation de l'ancien « Coach Sport » (chat supprimé).

    Conservé pour ne pas détruire les tables existantes ; plus aucune API ni
    service ne l'utilise. L'Agent Sport (``app.services.sport_agent``) passe
    par ``sport_agent_executions`` et n'écrit jamais ici.
    """

    __tablename__ = "sport_coach_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    messages: Mapped[list["SportCoachMessage"]] = relationship(
        "SportCoachMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="SportCoachMessage.created_at"
    )


class SportCoachMessage(Base):
    """LEGACY — messages de l'ancien « Coach Sport ». Voir SportCoachConversation."""

    __tablename__ = "sport_coach_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("sport_coach_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sources_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped[SportCoachConversation] = relationship("SportCoachConversation", back_populates="messages")


class SportAthleteObservation(Base):
    __tablename__ = "sport_athlete_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("sport_activities.id", ondelete="SET NULL"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="observed")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="calculated", index=True)
    sources_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SportGoal(Base):
    __tablename__ = "sport_goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    athlete: Mapped[SportAthlete] = relationship("SportAthlete", back_populates="goals")


class SportGarminConnection(Base):
    __tablename__ = "sport_garmin_connections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False, unique=True)
    garmin_email: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_tokens: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="connected", index=True)
    initial_sync_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    athlete: Mapped[SportAthlete] = relationship("SportAthlete")


class SportGarminSyncLog(Base):
    __tablename__ = "sport_garmin_sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("sport_garmin_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SportHealthDaily(Base):
    __tablename__ = "sport_health_daily"
    __table_args__ = (
        Index("uq_sport_health_daily", "athlete_id", "day", "source_type", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="garmin")
    health_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    athlete: Mapped["SportAthlete"] = relationship("SportAthlete")


class SportAnalysis(Base):
    """Analyse automatique generee par l'IA (matin, soir ou apres activite).

    ``dedupe_key`` rend la generation idempotente : une seule analyse par
    athlete et par cible (``morning:2026-09-27``, ``evening:2026-09-27``,
    ``activity:123``).
    """

    __tablename__ = "sport_analyses"
    __table_args__ = (
        Index("uq_sport_analysis_dedupe", "athlete_id", "dedupe_key", unique=True),
        Index("ix_sport_analyses_athlete_generated", "athlete_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("sport_activities.id", ondelete="CASCADE"), nullable=True, index=True)
    analysis_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    analysis_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notification_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    athlete: Mapped["SportAthlete"] = relationship("SportAthlete")
    activity: Mapped["SportActivity | None"] = relationship("SportActivity")


class SportAgentExecution(Base):
    """Trace complete d'une execution de l'Agent Sport.

    Une execution correspond a un reveil de l'agent (trigger) et conserve
    l'ordre des etapes observees : c'est la reponse technique a
    « pourquoi l'agent a-t-il decide cela ? ».
    """

    __tablename__ = "sport_agent_executions"
    __table_args__ = (
        Index("ix_sport_agent_executions_trigger", "trigger", "started_at"),
        Index("ix_sport_agent_executions_athlete_status", "athlete_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    athlete_id: Mapped[int | None] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=True, index=True)
    objective_id: Mapped[int | None] = mapped_column(ForeignKey("sport_goals.id", ondelete="SET NULL"), nullable=True, index=True)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running", index=True)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    steps_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User | None"] = relationship("User")
    athlete: Mapped["SportAthlete | None"] = relationship("SportAthlete")
    objective: Mapped["SportGoal | None"] = relationship("SportGoal")


class SportRecommendation(Base):
    """Recommandation persistee par l'Agent Sport.

    Elle porte l'objectif qui l'a fait naitre : c'est le lien concret entre
    la page Objectifs et les decisions de l'agent. Le statut permet de
    suivre les recommandations non realissees, remplacees ou expirees.
    """

    __tablename__ = "sport_recommendations"
    __table_args__ = (
        Index("ix_sport_recommendations_athlete_status", "athlete_id", "status"),
        Index("ix_sport_recommendations_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("sport_athletes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    objective_id: Mapped[int | None] = mapped_column(ForeignKey("sport_goals.id", ondelete="SET NULL"), nullable=True, index=True)
    execution_id: Mapped[int | None] = mapped_column(ForeignKey("sport_agent_executions.id", ondelete="SET NULL"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="training")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    athlete: Mapped["SportAthlete"] = relationship("SportAthlete")
    objective: Mapped["SportGoal | None"] = relationship("SportGoal")
    execution: Mapped["SportAgentExecution | None"] = relationship("SportAgentExecution")
