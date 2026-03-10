from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    expire_time: datetime | None = None


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
    license_expire: datetime | None = None


class AssetCreate(BaseModel):
    asset_code: str = Field(min_length=1)
    asset_type: str = Field(description="CLOUD_SERVER/DB/MIDDLEWARE/SECURITY_PRODUCT")
    name: str
    env: str = "prod"
    status: str = "IN_USE"
    owner: str
    org: str
    region: str = Field(default="cn-east-1", min_length=1)
    tags: list[AssetTagBase] = []
    cloud_server: AssetCloudServerBase | None = None
    database: AssetDatabaseBase | None = None
    middleware: AssetMiddlewareBase | None = None
    security_product: AssetSecurityProductBase | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    env: str | None = None
    status: str | None = None
    owner: str | None = None
    org: str | None = None
    region: str | None = None
    tags: list[AssetTagBase] | None = None
    cloud_server: AssetCloudServerBase | None = None
    database: AssetDatabaseBase | None = None
    middleware: AssetMiddlewareBase | None = None
    security_product: AssetSecurityProductBase | None = None


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
    tags: list[AssetTagBase]
    cloud_server: AssetCloudServerBase | None = None
    database: AssetDatabaseBase | None = None
    middleware: AssetMiddlewareBase | None = None
    security_product: AssetSecurityProductBase | None = None


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
    items: list[Any]


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any | None = None
