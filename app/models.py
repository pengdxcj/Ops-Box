from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Asset(Base):
    __tablename__ = "cmdb_asset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    env: Mapped[str] = mapped_column(String(16), nullable=False, default="prod")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="IN_USE")
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    org: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False, default="cn-east-1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    cloud_server = relationship(
        "AssetCloudServer",
        back_populates="asset",
        uselist=False,
        cascade="all, delete-orphan",
    )
    database = relationship(
        "AssetDatabase",
        back_populates="asset",
        uselist=False,
        cascade="all, delete-orphan",
    )
    middleware = relationship(
        "AssetMiddleware",
        back_populates="asset",
        uselist=False,
        cascade="all, delete-orphan",
    )
    security_product = relationship(
        "AssetSecurityProduct",
        back_populates="asset",
        uselist=False,
        cascade="all, delete-orphan",
    )
    tags = relationship("AssetTag", back_populates="asset", cascade="all, delete-orphan")


class AssetCloudServer(Base):
    __tablename__ = "cmdb_asset_cloud_server"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("cmdb_asset.id"), unique=True, nullable=False)
    instance_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    vpc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cpu: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    os: Mapped[str] = mapped_column(String(64), nullable=False)
    private_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    public_ip: Mapped[str] = mapped_column(String(64), nullable=True)
    expire_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    asset = relationship("Asset", back_populates="cloud_server")


class AssetDatabase(Base):
    __tablename__ = "cmdb_asset_database"
    __table_args__ = (UniqueConstraint("endpoint", "port", name="uk_db_endpoint_port"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("cmdb_asset.id"), unique=True, nullable=False)
    db_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="primary")
    storage_gb: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    backup_policy: Mapped[str] = mapped_column(String(128), nullable=False, default="daily")

    asset = relationship("Asset", back_populates="database")


class AssetMiddleware(Base):
    __tablename__ = "cmdb_asset_middleware"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("cmdb_asset.id"), unique=True, nullable=False)
    mw_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cluster_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ha_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="single")

    asset = relationship("Asset", back_populates="middleware")


class AssetSecurityProduct(Base):
    __tablename__ = "cmdb_asset_security_product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("cmdb_asset.id"), unique=True, nullable=False)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    deploy_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    coverage_scope: Mapped[str] = mapped_column(Text, nullable=False)
    license_expire: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    asset = relationship("Asset", back_populates="security_product")


class AssetTag(Base):
    __tablename__ = "cmdb_asset_tag"
    __table_args__ = (UniqueConstraint("asset_id", "tag_key", name="uk_asset_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("cmdb_asset.id"), nullable=False, index=True)
    tag_key: Mapped[str] = mapped_column(String(64), nullable=False)
    tag_value: Mapped[str] = mapped_column(String(128), nullable=False)

    asset = relationship("Asset", back_populates="tags")


class AssetRelation(Base):
    __tablename__ = "cmdb_asset_relation"
    __table_args__ = (
        UniqueConstraint("src_asset_id", "dst_asset_id", "relation_type", name="uk_asset_relation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    src_asset_id: Mapped[int] = mapped_column(ForeignKey("cmdb_asset.id"), nullable=False, index=True)
    dst_asset_id: Mapped[int] = mapped_column(ForeignKey("cmdb_asset.id"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    direction: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AssetChangeLog(Base):
    __tablename__ = "cmdb_asset_change_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("cmdb_asset.id"), nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    before_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    after_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EsCluster(Base):
    __tablename__ = "es_cluster"
    __table_args__ = (UniqueConstraint("name", name="uk_es_cluster_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(256), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=True)
    password: Mapped[str] = mapped_column(String(128), nullable=True)
    snapshot_repo: Mapped[str] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )



class EsSnapshotTask(Base):
    __tablename__ = "es_snapshot_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("es_cluster.id"), nullable=False, index=True)
    index_name: Mapped[str] = mapped_column(String(256), nullable=False)
    snapshot_name: Mapped[str] = mapped_column(String(256), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    retry_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    last_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    cluster = relationship("EsCluster")
    logs = relationship("EsSnapshotTaskLog", back_populates="task", cascade="all, delete-orphan")


class EsSnapshotTaskLog(Base):
    __tablename__ = "es_snapshot_task_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("es_snapshot_task.id"), nullable=False, index=True)
    task_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    index_name: Mapped[str] = mapped_column(String(256), nullable=False)
    snapshot_name: Mapped[str] = mapped_column(String(256), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    task = relationship("EsSnapshotTask", back_populates="logs")
