from datetime import datetime
from typing import Any, Optional, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetTagBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag_key: str
    tag_value: str


class AssetCloudServerBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instance_id: str = Field(min_length=1)
    vpc_id: str
    cpu: int
    memory_gb: int
    os: str
    private_ip: str = Field(min_length=1)
    public_ip: str = Field(min_length=1)
    expire_time: Optional[datetime] = None


class AssetDatabaseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    db_type: str
    version: str
    endpoint: str
    port: int
    role: str = "primary"
    storage_gb: int = 20
    backup_policy: str = "daily"


class AssetMiddlewareBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mw_type: str
    cluster_name: str
    version: str
    node_count: int = 1
    ha_mode: str = "single"


class AssetSecurityProductBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_type: str
    vendor: str
    version: str
    deploy_mode: str
    coverage_scope: str
    license_expire: Optional[datetime] = None


class AssetCreate(BaseModel):
    asset_code: str = Field(min_length=1)
    asset_type: str = Field(description="CLOUD_SERVER/DB/MIDDLEWARE/SECURITY_PRODUCT")
    name: str
    env: str = "prod"
    status: str = "IN_USE"
    owner: str
    org: str
    region: str = Field(default="cn-east-1", min_length=1)
    tags: List[AssetTagBase] = []
    cloud_server: Optional[AssetCloudServerBase] = None
    database: Optional[AssetDatabaseBase] = None
    middleware: Optional[AssetMiddlewareBase] = None
    security_product: Optional[AssetSecurityProductBase] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    env: Optional[str] = None
    status: Optional[str] = None
    owner: Optional[str] = None
    org: Optional[str] = None
    region: Optional[str] = None
    tags: Optional[List[AssetTagBase]] = None
    cloud_server: Optional[AssetCloudServerBase] = None
    database: Optional[AssetDatabaseBase] = None
    middleware: Optional[AssetMiddlewareBase] = None
    security_product: Optional[AssetSecurityProductBase] = None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_code: str
    asset_type: str
    name: str
    env: str
    status: str
    owner: str
    org: str
    region: str
    created_at: datetime
    updated_at: datetime
    tags: List[AssetTagBase]
    cloud_server: Optional[AssetCloudServerBase] = None
    database: Optional[AssetDatabaseBase] = None
    middleware: Optional[AssetMiddlewareBase] = None
    security_product: Optional[AssetSecurityProductBase] = None


class RelationCreate(BaseModel):
    src_asset_id: int
    dst_asset_id: int
    relation_type: str = Field(description="DEPLOY_ON/CONNECT_TO/PROTECT_BY")
    direction: int = 1


class RelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    src_asset_id: int
    dst_asset_id: int
    relation_type: str
    direction: int
    created_at: datetime


class ChangeLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    change_type: str
    before_json: str
    after_json: str
    operator: str
    changed_at: datetime


class PageResult(BaseModel):
    total: int
    page: int
    size: int
    items: List[Any]


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Optional[Any] = None


class EsClusterCreate(BaseModel):
    name: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    username: Optional[str] = None
    password: Optional[str] = None
    snapshot_repo: Optional[str] = None


class EsClusterUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    snapshot_repo: Optional[str] = None


class EsClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    username: Optional[str] = None
    snapshot_repo: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EsClusterTest(BaseModel):
    base_url: str = Field(min_length=1)
    username: Optional[str] = None
    password: Optional[str] = None


class EsSnapshotCreate(BaseModel):
    index: str = Field(min_length=1)
    snapshot: str = Field(min_length=1)



class EsSnapshotTaskCreate(BaseModel):
    cluster_id: int
    index_name: str
    scheduled_at: datetime
    snapshot_name: Optional[str] = None
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_interval_minutes: int = Field(default=2, ge=1, le=120)
    
    @field_validator('scheduled_at')
    @classmethod
    def validate_scheduled_at(cls, v: datetime) -> datetime:
        # 保持时间不变，直接使用传入的时间
        return v


class EsSnapshotTaskUpdate(BaseModel):
    index_name: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    snapshot_name: Optional[str] = None
    max_retries: Optional[int] = Field(default=None, ge=0, le=5)
    retry_interval_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    
    @field_validator('scheduled_at')
    @classmethod
    def validate_scheduled_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        # 保持时间不变，直接使用传入的时间
        return v


class EsSnapshotTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cluster_id: int
    index_name: str
    snapshot_name: Optional[str] = None
    scheduled_at: datetime
    next_run_at: Optional[datetime] = None
    status: str
    retry_count: int
    max_retries: int
    retry_interval_minutes: int
    last_run_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None
    result_json: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EsSnapshotTaskLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    task_created_at: datetime
    index_name: str
    snapshot_name: Optional[str] = None
    scheduled_at: datetime
    executed_at: datetime
    status: str
    error_message: Optional[str] = None
    result_json: Optional[str] = None
    created_at: datetime
