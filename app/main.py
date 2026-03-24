import csv
import io
import json
import threading
import time
import requests
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Optional, List, Union

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import Base, engine, get_db, SessionLocal
from app.models import (
    Asset,
    AssetChangeLog,
    AssetCloudServer,
    AssetDatabase,
    AssetMiddleware,
    AssetRelation,
    AssetSecurityProduct,
    AssetTag,
    EsCluster,
    EsSnapshotTask,
    EsSnapshotTaskLog,
)
from app.schemas import (
    ApiResponse,
    AssetCreate,
    AssetOut,
    AssetUpdate,
    ChangeLogOut,
    PageResult,
    RelationCreate,
    RelationOut,
    EsClusterCreate,
    EsClusterOut,
    EsClusterUpdate,
    EsClusterTest,
    EsSnapshotCreate,
    EsSnapshotTaskCreate,
    EsSnapshotTaskOut,
    EsSnapshotTaskUpdate,
    EsSnapshotTaskLogOut,
)

app = FastAPI(title=settings.app_name, version=settings.app_version)
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# 创建脚本存储文件夹
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SCRIPTS_DIR.mkdir(exist_ok=True)

# 挂载脚本文件夹作为静态文件
app.mount("/scripts", StaticFiles(directory=SCRIPTS_DIR), name="scripts")

EXPORT_FIELDS = [
    "asset_code",
    "asset_type",
    "name",
    "env",
    "status",
    "owner",
    "org",
    "region",
    "tags",
    "instance_id",
    "vpc_id",
    "cpu",
    "memory_gb",
    "os",
    "private_ip",
    "public_ip",
    "expire_time",
    "db_type",
    "db_version",
    "db_endpoint",
    "db_port",
    "db_role",
    "db_storage_gb",
    "db_backup_policy",
    "mw_type",
    "mw_cluster_name",
    "mw_version",
    "mw_node_count",
    "mw_ha_mode",
    "sec_product_type",
    "sec_vendor",
    "sec_version",
    "sec_deploy_mode",
    "sec_coverage_scope",
    "sec_license_expire",
]


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    start_snapshot_scheduler()


@app.on_event("shutdown")
def shutdown():
    stop_snapshot_scheduler()


@app.get("/", include_in_schema=False)
def frontend_index():
    return FileResponse(frontend_dir / "index.html")


def _snapshot_asset(asset: Asset) -> dict:
    def _model_to_dict(model):
        if model is None:
            return None
        return {key: value for key, value in vars(model).items() if not key.startswith("_")}

    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "asset_type": asset.asset_type,
        "name": asset.name,
        "env": asset.env,
        "status": asset.status,
        "owner": asset.owner,
        "org": asset.org,
        "region": asset.region,
        "tags": [{"tag_key": tag.tag_key, "tag_value": tag.tag_value} for tag in asset.tags],
        "cloud_server": _model_to_dict(asset.cloud_server),
        "database": _model_to_dict(asset.database),
        "middleware": _model_to_dict(asset.middleware),
        "security_product": _model_to_dict(asset.security_product),
    }


def _create_or_replace_extension(asset: Asset, payload: Optional[dict], creator: Callable[[], object]):
    if payload is None:
        return
    extension = creator()
    for key, value in payload.items():
        setattr(extension, key, value)
    setattr(asset, extension.__class__.__name__.replace("Asset", "").lower(), extension)


def _sync_tags(asset: Asset, tags: List[dict]):
    asset.tags.clear()
    for tag in tags:
        asset.tags.append(AssetTag(tag_key=tag["tag_key"], tag_value=tag["tag_value"]))


def _apply_extensions(asset: Asset, payload: Union[AssetCreate, AssetUpdate]):
    if payload.cloud_server is not None:
        asset.cloud_server = AssetCloudServer(**payload.cloud_server.model_dump())
    if payload.database is not None:
        asset.database = AssetDatabase(**payload.database.model_dump())
    if payload.middleware is not None:
        asset.middleware = AssetMiddleware(**payload.middleware.model_dump())
    if payload.security_product is not None:
        asset.security_product = AssetSecurityProduct(**payload.security_product.model_dump())


def _record_change(
    db: Session, *, asset_id: int, change_type: str, before_data: dict, after_data: dict, operator: str
):
    db.add(
        AssetChangeLog(
            asset_id=asset_id,
            change_type=change_type,
            before_json=json.dumps(before_data, default=str, ensure_ascii=False),
            after_json=json.dumps(after_data, default=str, ensure_ascii=False),
            operator=operator,
        )
    )


def _validate_extension(asset_type: str, payload: AssetCreate):
    mapping = {
        "CLOUD_SERVER": payload.cloud_server,
        "DB": payload.database,
        "MIDDLEWARE": payload.middleware,
        "SECURITY_PRODUCT": payload.security_product,
    }
    expected = mapping.get(asset_type)
    if expected is None:
        raise HTTPException(status_code=400, detail=f"asset_type={asset_type} requires matching extension payload")


def _asset_filters(asset_type: Optional[str], env: Optional[str], status: Optional[str], owner: Optional[str]):
    filters = []
    if asset_type:
        filters.append(Asset.asset_type == asset_type)
    if env:
        filters.append(Asset.env == env)
    if status:
        filters.append(Asset.status == status)
    if owner:
        filters.append(Asset.owner == owner)
    return and_(*filters) if filters else True


def _serialize_tags(tags: List[AssetTag]) -> str:
    return ";".join(f"{tag.tag_key}={tag.tag_value}" for tag in tags)


def _parse_tags(text: str) -> List[dict]:
    if not text:
        return []
    tags = []
    for raw in text.split(";"):
        if not raw.strip():
            continue
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            tags.append({"tag_key": key, "tag_value": value})
    return tags


def _dedupe_tags(tags: List[dict]) -> List[dict]:
    seen: dict[str, str] = {}
    for tag in tags:
        seen[tag["tag_key"]] = tag["tag_value"]
    return [{"tag_key": key, "tag_value": value} for key, value in seen.items()]


def _require_row_value(row: dict, key: str, row_index: int) -> str:
    value = (row.get(key) or "").strip()
    if not value:
        raise ValueError(f"row {row_index}: {key} is required")
    return value


def _optional_row_value(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _optional_int(row: dict, key: str) -> Optional[int]:
    value = _optional_row_value(row, key)
    if not value:
        return None
    return int(value)


def _parse_datetime(value: str, row_index: int, key: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"row {row_index}: {key} is not a valid ISO datetime") from exc


def _asset_to_export_row(asset: Asset) -> dict:
    row = {field: "" for field in EXPORT_FIELDS}
    row.update(
        {
            "asset_code": asset.asset_code,
            "asset_type": asset.asset_type,
            "name": asset.name,
            "env": asset.env,
            "status": asset.status,
            "owner": asset.owner,
            "org": asset.org,
            "region": asset.region,
            "tags": _serialize_tags(asset.tags),
        }
    )
    if asset.cloud_server:
        row.update(
            {
                "instance_id": asset.cloud_server.instance_id,
                "vpc_id": asset.cloud_server.vpc_id,
                "cpu": asset.cloud_server.cpu,
                "memory_gb": asset.cloud_server.memory_gb,
                "os": asset.cloud_server.os,
                "private_ip": asset.cloud_server.private_ip,
                "public_ip": asset.cloud_server.public_ip,
                "expire_time": asset.cloud_server.expire_time.isoformat()
                if asset.cloud_server.expire_time
                else "",
            }
        )
    if asset.database:
        row.update(
            {
                "db_type": asset.database.db_type,
                "db_version": asset.database.version,
                "db_endpoint": asset.database.endpoint,
                "db_port": asset.database.port,
                "db_role": asset.database.role,
                "db_storage_gb": asset.database.storage_gb,
                "db_backup_policy": asset.database.backup_policy,
            }
        )
    if asset.middleware:
        row.update(
            {
                "mw_type": asset.middleware.mw_type,
                "mw_cluster_name": asset.middleware.cluster_name,
                "mw_version": asset.middleware.version,
                "mw_node_count": asset.middleware.node_count,
                "mw_ha_mode": asset.middleware.ha_mode,
            }
        )
    if asset.security_product:
        row.update(
            {
                "sec_product_type": asset.security_product.product_type,
                "sec_vendor": asset.security_product.vendor,
                "sec_version": asset.security_product.version,
                "sec_deploy_mode": asset.security_product.deploy_mode,
                "sec_coverage_scope": asset.security_product.coverage_scope,
                "sec_license_expire": asset.security_product.license_expire.isoformat()
                if asset.security_product.license_expire
                else "",
            }
        )
    return row


def _fetch_asset_or_404(db: Session, asset_id: int) -> Asset:
    stmt = (
        select(Asset)
        .where(Asset.id == asset_id)
        .options(
            joinedload(Asset.tags),
            joinedload(Asset.cloud_server),
            joinedload(Asset.database),
            joinedload(Asset.middleware),
            joinedload(Asset.security_product),
        )
    )
    asset = db.execute(stmt).scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset


@app.get("/healthz", response_model=ApiResponse)
def healthz():
    return ApiResponse(data={"status": "up"})


@app.post("/api/v1/assets", response_model=ApiResponse)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db)):
    exists = db.execute(select(Asset).where(Asset.asset_code == payload.asset_code)).scalars().first()
    if exists:
        raise HTTPException(status_code=409, detail="asset_code already exists")
    _validate_extension(payload.asset_type, payload)

    asset = Asset(
        asset_code=payload.asset_code,
        asset_type=payload.asset_type,
        name=payload.name,
        env=payload.env,
        status=payload.status,
        owner=payload.owner,
        org=payload.org,
        region=payload.region,
    )
    if payload.tags:
        _sync_tags(asset, [tag.model_dump() for tag in payload.tags])
    _apply_extensions(asset, payload)

    db.add(asset)
    db.flush()
    _record_change(db, asset_id=asset.id, change_type="CREATE", before_data={}, after_data=_snapshot_asset(asset), operator="api")
    db.commit()
    db.refresh(asset)
    return ApiResponse(data=AssetOut.model_validate(asset).model_dump())


@app.get("/api/v1/assets", response_model=ApiResponse)
def list_assets(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    asset_type: Optional[str] = None,
    env: Optional[str] = None,
    status: Optional[str] = None,
    owner: Optional[str] = None,
    db: Session = Depends(get_db),
):
    where_clause = _asset_filters(asset_type, env, status, owner)
    total = db.execute(select(func.count()).select_from(Asset).where(where_clause)).scalar_one()
    stmt = (
        select(Asset)
        .where(where_clause)
        .options(
            joinedload(Asset.tags),
            joinedload(Asset.cloud_server),
            joinedload(Asset.database),
            joinedload(Asset.middleware),
            joinedload(Asset.security_product),
        )
        .order_by(Asset.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    assets = db.execute(stmt).scalars().unique().all()
    data = PageResult(
        total=total,
        page=page,
        size=size,
        items=[AssetOut.model_validate(asset).model_dump() for asset in assets],
    )
    return ApiResponse(data=data.model_dump())


@app.get("/api/v1/assets/export")
def export_assets(
    asset_type: Optional[str] = None,
    env: Optional[str] = None,
    status: Optional[str] = None,
    owner: Optional[str] = None,
    db: Session = Depends(get_db),
):
    where_clause = _asset_filters(asset_type, env, status, owner)
    stmt = (
        select(Asset)
        .where(where_clause)
        .options(
            joinedload(Asset.tags),
            joinedload(Asset.cloud_server),
            joinedload(Asset.database),
            joinedload(Asset.middleware),
            joinedload(Asset.security_product),
        )
        .order_by(Asset.id.asc())
    )
    assets = db.execute(stmt).scalars().unique().all()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for asset in assets:
        writer.writerow(_asset_to_export_row(asset))
    buffer.seek(0)

    filename = f"cmdb_assets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers=headers)


@app.post("/api/v1/assets/import", response_model=ApiResponse)
def import_assets(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    reader = csv.DictReader(io.TextIOWrapper(file.file, encoding="utf-8-sig"))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="csv header is required")

    success = 0
    errors: list[dict] = []
    total = 0

    for row_index, row in enumerate(reader, start=2):
        total += 1
        try:
            asset_code = _require_row_value(row, "asset_code", row_index)
            region = _require_row_value(row, "region", row_index)
            asset_type = (_optional_row_value(row, "asset_type") or "CLOUD_SERVER").upper()

            exists = db.execute(select(Asset.id).where(Asset.asset_code == asset_code)).scalar_one_or_none()
            if exists:
                raise ValueError(f"row {row_index}: asset_code already exists")

            asset = Asset(
                asset_code=asset_code,
                asset_type=asset_type,
                name=_optional_row_value(row, "name") or asset_code,
                env=_optional_row_value(row, "env") or "prod",
                status=_optional_row_value(row, "status") or "IN_USE",
                owner=_optional_row_value(row, "owner") or "import",
                org=_optional_row_value(row, "org") or "import",
                region=region,
            )

            tags = _dedupe_tags(_parse_tags(_optional_row_value(row, "tags")))
            if tags:
                _sync_tags(asset, tags)

            if asset_type == "CLOUD_SERVER":
                asset.cloud_server = AssetCloudServer(
                    instance_id=_require_row_value(row, "instance_id", row_index),
                    vpc_id=_require_row_value(row, "vpc_id", row_index),
                    cpu=int(_require_row_value(row, "cpu", row_index)),
                    memory_gb=int(_require_row_value(row, "memory_gb", row_index)),
                    os=_require_row_value(row, "os", row_index),
                    private_ip=_require_row_value(row, "private_ip", row_index),
                    public_ip=_require_row_value(row, "public_ip", row_index),
                    expire_time=_parse_datetime(_optional_row_value(row, "expire_time"), row_index, "expire_time"),
                )
            elif asset_type == "DB":
                asset.database = AssetDatabase(
                    db_type=_require_row_value(row, "db_type", row_index),
                    version=_require_row_value(row, "db_version", row_index),
                    endpoint=_require_row_value(row, "db_endpoint", row_index),
                    port=int(_require_row_value(row, "db_port", row_index)),
                    role=_optional_row_value(row, "db_role") or "primary",
                    storage_gb=_optional_int(row, "db_storage_gb") or 20,
                    backup_policy=_optional_row_value(row, "db_backup_policy") or "daily",
                )
            elif asset_type == "MIDDLEWARE":
                asset.middleware = AssetMiddleware(
                    mw_type=_require_row_value(row, "mw_type", row_index),
                    cluster_name=_require_row_value(row, "mw_cluster_name", row_index),
                    version=_require_row_value(row, "mw_version", row_index),
                    node_count=_optional_int(row, "mw_node_count") or 1,
                    ha_mode=_optional_row_value(row, "mw_ha_mode") or "single",
                )
            elif asset_type == "SECURITY_PRODUCT":
                asset.security_product = AssetSecurityProduct(
                    product_type=_require_row_value(row, "sec_product_type", row_index),
                    vendor=_require_row_value(row, "sec_vendor", row_index),
                    version=_require_row_value(row, "sec_version", row_index),
                    deploy_mode=_require_row_value(row, "sec_deploy_mode", row_index),
                    coverage_scope=_require_row_value(row, "sec_coverage_scope", row_index),
                    license_expire=_parse_datetime(
                        _optional_row_value(row, "sec_license_expire"), row_index, "sec_license_expire"
                    ),
                )
            else:
                raise ValueError(f"row {row_index}: asset_type {asset_type} is not supported")

            db.add(asset)
            db.flush()
            _record_change(
                db,
                asset_id=asset.id,
                change_type="CREATE",
                before_data={},
                after_data=_snapshot_asset(asset),
                operator="import",
            )
            db.commit()
            success += 1
        except (ValueError, IntegrityError) as exc:
            db.rollback()
            errors.append({"row": row_index, "reason": str(exc)})

    return ApiResponse(
        data={
            "total": total,
            "success": success,
            "failed": total - success,
            "errors": errors,
        }
    )


@app.get("/api/v1/assets/{asset_id}", response_model=ApiResponse)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = _fetch_asset_or_404(db, asset_id)
    return ApiResponse(data=AssetOut.model_validate(asset).model_dump())


@app.delete("/api/v1/assets/{asset_id}", response_model=ApiResponse)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = _fetch_asset_or_404(db, asset_id)

    db.query(AssetRelation).filter(
        (AssetRelation.src_asset_id == asset_id) | (AssetRelation.dst_asset_id == asset_id)
    ).delete(synchronize_session=False)
    db.query(AssetChangeLog).filter(AssetChangeLog.asset_id == asset_id).delete(synchronize_session=False)

    db.delete(asset)
    db.commit()
    return ApiResponse(data={"deleted": asset_id})


@app.put("/api/v1/assets/{asset_id}", response_model=ApiResponse)
def update_asset(asset_id: int, payload: AssetUpdate, db: Session = Depends(get_db)):
    asset = _fetch_asset_or_404(db, asset_id)
    before_data = _snapshot_asset(asset)

    update_data = payload.model_dump(exclude_unset=True)
    for field in ["name", "env", "status", "owner", "org", "region"]:
        if field in update_data:
            setattr(asset, field, update_data[field])

    if "tags" in update_data and payload.tags is not None:
        _sync_tags(asset, [tag.model_dump() for tag in payload.tags])

    if payload.cloud_server is not None:
        if asset.cloud_server is None:
            asset.cloud_server = AssetCloudServer(**payload.cloud_server.model_dump())
        else:
            for key, value in payload.cloud_server.model_dump().items():
                setattr(asset.cloud_server, key, value)
    if payload.database is not None:
        if asset.database is None:
            asset.database = AssetDatabase(**payload.database.model_dump())
        else:
            for key, value in payload.database.model_dump().items():
                setattr(asset.database, key, value)
    if payload.middleware is not None:
        if asset.middleware is None:
            asset.middleware = AssetMiddleware(**payload.middleware.model_dump())
        else:
            for key, value in payload.middleware.model_dump().items():
                setattr(asset.middleware, key, value)
    if payload.security_product is not None:
        if asset.security_product is None:
            asset.security_product = AssetSecurityProduct(**payload.security_product.model_dump())
        else:
            for key, value in payload.security_product.model_dump().items():
                setattr(asset.security_product, key, value)

    db.flush()
    _record_change(
        db,
        asset_id=asset.id,
        change_type="UPDATE",
        before_data=before_data,
        after_data=_snapshot_asset(asset),
        operator="api",
    )
    db.commit()
    db.refresh(asset)
    return ApiResponse(data=AssetOut.model_validate(asset).model_dump())


@app.post("/api/v1/relations", response_model=ApiResponse)
def create_relation(payload: RelationCreate, db: Session = Depends(get_db)):
    src = db.execute(select(Asset.id).where(Asset.id == payload.src_asset_id)).first()
    dst = db.execute(select(Asset.id).where(Asset.id == payload.dst_asset_id)).first()
    if not src or not dst:
        raise HTTPException(status_code=400, detail="src_asset_id or dst_asset_id does not exist")

    relation = AssetRelation(**payload.model_dump())
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return ApiResponse(data=RelationOut.model_validate(relation).model_dump())


@app.get("/api/v1/relations/topology", response_model=ApiResponse)
def get_topology(asset_id: int = Query(..., ge=1), db: Session = Depends(get_db)):
    root = db.execute(select(Asset).where(Asset.id == asset_id)).scalars().first()
    if not root:
        raise HTTPException(status_code=404, detail="asset not found")

    edges = db.execute(
        select(AssetRelation).where(
            (AssetRelation.src_asset_id == asset_id) | (AssetRelation.dst_asset_id == asset_id)
        )
    ).scalars().all()
    node_ids = {asset_id}
    for edge in edges:
        node_ids.add(edge.src_asset_id)
        node_ids.add(edge.dst_asset_id)

    nodes = db.execute(select(Asset).where(Asset.id.in_(node_ids))).scalars().all()
    data = {
        "root_asset_id": asset_id,
        "nodes": [{"id": n.id, "name": n.name, "asset_type": n.asset_type, "status": n.status} for n in nodes],
        "edges": [RelationOut.model_validate(e).model_dump() for e in edges],
    }
    return ApiResponse(data=data)


@app.post("/api/v1/discovery/sync", response_model=ApiResponse)
def trigger_discovery_sync(db: Session = Depends(get_db)):
    count_assets = db.execute(select(func.count()).select_from(Asset)).scalar_one()
    return ApiResponse(
        data={
            "task_id": "sync-manual",
            "summary": {
                "checked_total": count_assets,
                "new_assets": 0,
                "updated_assets": 0,
                "deactivated_assets": 0,
            },
            "message": "This is a demo sync endpoint. Integrate real cloud/provider API in scheduler jobs.",
        }
    )


@app.get("/api/v1/security/coverage", response_model=ApiResponse)
def security_coverage(db: Session = Depends(get_db)):
    protected_relations = db.execute(
        select(AssetRelation).where(AssetRelation.relation_type == "PROTECT_BY")
    ).scalars().all()
    protected_ids = {r.src_asset_id for r in protected_relations} | {r.dst_asset_id for r in protected_relations}

    all_assets = db.execute(
        select(Asset).where(Asset.asset_type != "SECURITY_PRODUCT", Asset.status == "IN_USE")
    ).scalars().all()
    total = len(all_assets)
    protected = len([a for a in all_assets if a.id in protected_ids])
    ratio = round((protected / total) * 100, 2) if total else 0.0

    by_type: dict[str, dict[str, int | float]] = {}
    for asset in all_assets:
        if asset.asset_type not in by_type:
            by_type[asset.asset_type] = {"total": 0, "protected": 0, "ratio": 0.0}
        by_type[asset.asset_type]["total"] += 1
        if asset.id in protected_ids:
            by_type[asset.asset_type]["protected"] += 1
    for asset_type in by_type:
        t = by_type[asset_type]["total"] or 0
        p = by_type[asset_type]["protected"] or 0
        by_type[asset_type]["ratio"] = round((p / t) * 100, 2) if t else 0.0

    return ApiResponse(data={"total": total, "protected": protected, "ratio": ratio, "by_type": by_type})


@app.get("/api/v1/security/uncovered", response_model=ApiResponse)
def security_uncovered(db: Session = Depends(get_db)):
    protected_relations = db.execute(
        select(AssetRelation).where(AssetRelation.relation_type == "PROTECT_BY")
    ).scalars().all()
    protected_ids = {r.src_asset_id for r in protected_relations} | {r.dst_asset_id for r in protected_relations}

    uncovered = db.execute(
        select(Asset).where(Asset.asset_type != "SECURITY_PRODUCT", Asset.status == "IN_USE")
    ).scalars().all()
    data = [
        {"id": a.id, "asset_code": a.asset_code, "name": a.name, "asset_type": a.asset_type, "env": a.env}
        for a in uncovered
        if a.id not in protected_ids
    ]
    return ApiResponse(data={"total": len(data), "items": data})


@app.get("/api/v1/audit/changes", response_model=ApiResponse)
def list_changes(
    asset_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    filters = []
    if asset_id:
        filters.append(AssetChangeLog.asset_id == asset_id)
    where_clause = and_(*filters) if filters else True
    total = db.execute(select(func.count()).select_from(AssetChangeLog).where(where_clause)).scalar_one()
    logs = db.execute(
        select(AssetChangeLog)
        .where(where_clause)
        .order_by(AssetChangeLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).scalars().all()

    data = PageResult(
        total=total,
        page=page,
        size=size,
        items=[ChangeLogOut.model_validate(log).model_dump() for log in logs],
    )
    return ApiResponse(data=data.model_dump())


def _normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def _fetch_es_cluster_or_404(db: Session, cluster_id: int) -> EsCluster:
    cluster = db.execute(select(EsCluster).where(EsCluster.id == cluster_id)).scalars().first()
    if not cluster:
        raise HTTPException(status_code=404, detail="es cluster not found")
    return cluster


def _es_auth(cluster: EsCluster):
    if cluster.username:
        return (cluster.username, cluster.password or "")
    return None


def _es_request(
    cluster: EsCluster,
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    timeout: int = 8,
):
    url = f"{cluster.base_url}{path}"
    try:
        res = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            auth=_es_auth(cluster),
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"ES????: {exc}") from exc

    payload = None
    if res.headers.get("content-type", "").startswith("application/json"):
        payload = res.json()

    if not res.ok:
        detail = None
        if isinstance(payload, dict):
            detail = payload.get("error") or payload.get("message")
        if not detail:
            detail = res.text[:500]
        raise HTTPException(status_code=502, detail=f"ES????: {res.status_code} {detail}")

    return payload if payload is not None else {}


def _require_snapshot_repo(cluster: EsCluster) -> str:
    repo = (cluster.snapshot_repo or "").strip()
    if not repo:
        raise HTTPException(status_code=400, detail="snapshot_repo is required")
    return repo


@app.get("/api/v1/es/clusters", response_model=ApiResponse)
def list_es_clusters(db: Session = Depends(get_db)):
    clusters = db.execute(select(EsCluster).order_by(EsCluster.id.desc())).scalars().all()
    return ApiResponse(data=[EsClusterOut.model_validate(c).model_dump() for c in clusters])


@app.post("/api/v1/es/clusters", response_model=ApiResponse)
def create_es_cluster(payload: EsClusterCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    base_url = payload.base_url.strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")

    cluster = EsCluster(
        name=name,
        base_url=_normalize_base_url(base_url),
        username=(payload.username or "").strip() or None,
        password=payload.password or None,
        snapshot_repo=(payload.snapshot_repo or "").strip() or None,
    )
    try:
        db.add(cluster)
        db.commit()
        db.refresh(cluster)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="cluster name already exists") from exc

    return ApiResponse(data=EsClusterOut.model_validate(cluster).model_dump())



@app.put("/api/v1/es/clusters/{cluster_id}", response_model=ApiResponse)
def update_es_cluster(cluster_id: int, payload: EsClusterUpdate, db: Session = Depends(get_db)):
    cluster = _fetch_es_cluster_or_404(db, cluster_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data:
        name = (update_data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        cluster.name = name
    if "base_url" in update_data:
        base_url = (update_data.get("base_url") or "").strip()
        if not base_url:
            raise HTTPException(status_code=400, detail="base_url is required")
        cluster.base_url = _normalize_base_url(base_url)
    if "username" in update_data:
        cluster.username = (update_data.get("username") or "").strip() or None
    if "password" in update_data:
        cluster.password = update_data.get("password") or None
    if "snapshot_repo" in update_data:
        cluster.snapshot_repo = (update_data.get("snapshot_repo") or "").strip() or None

    try:
        db.add(cluster)
        db.commit()
        db.refresh(cluster)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="cluster name already exists") from exc

    return ApiResponse(data=EsClusterOut.model_validate(cluster).model_dump())


@app.delete("/api/v1/es/clusters/{cluster_id}", response_model=ApiResponse)
def delete_es_cluster(cluster_id: int, db: Session = Depends(get_db)):
    cluster = _fetch_es_cluster_or_404(db, cluster_id)
    db.delete(cluster)
    db.commit()
    return ApiResponse(data={"deleted": cluster_id})


@app.post("/api/v1/es/clusters/test", response_model=ApiResponse)
def test_es_cluster_by_payload(payload: EsClusterTest):
    temp_cluster = EsCluster(
        name="temp",
        base_url=_normalize_base_url(payload.base_url.strip()),
        username=(payload.username or "").strip() or None,
        password=payload.password or None,
    )
    data = _es_request(temp_cluster, "GET", "/_cluster/health")
    return ApiResponse(data={"cluster_name": data.get("cluster_name"), "status": data.get("status")})



@app.get("/api/v1/es/clusters/{cluster_id}/repositories", response_model=ApiResponse)
def list_es_repositories(cluster_id: int, db: Session = Depends(get_db)):
    cluster = _fetch_es_cluster_or_404(db, cluster_id)
    payload = _es_request(cluster, "GET", "/_snapshot")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="ES repository response invalid")
    repos = sorted(payload.keys())
    return ApiResponse(data={"items": repos})


@app.post("/api/v1/es/clusters/{cluster_id}/test", response_model=ApiResponse)
def test_es_cluster(cluster_id: int, db: Session = Depends(get_db)):
    cluster = _fetch_es_cluster_or_404(db, cluster_id)
    data = _es_request(cluster, "GET", "/_cluster/health")
    return ApiResponse(data={"cluster_name": data.get("cluster_name"), "status": data.get("status")})


@app.get("/api/v1/es/clusters/{cluster_id}/summary", response_model=ApiResponse)
def es_cluster_summary(cluster_id: int, db: Session = Depends(get_db)):
    cluster = _fetch_es_cluster_or_404(db, cluster_id)
    state = _es_request(cluster, "GET", "/_cluster/state")
    health = _es_request(cluster, "GET", "/_cluster/health")
    stats = _es_request(cluster, "GET", "/_cluster/stats")

    nodes = (stats.get("nodes") or {}).get("count") or {}
    indices = stats.get("indices") or {}

    data = {
        "cluster": {
            "name": state.get("cluster_name"),
            "uuid": state.get("cluster_uuid"),
            "status": health.get("status"),
        },
        "nodes": {
            "total": nodes.get("total"),
            "master": nodes.get("master"),
            "data": nodes.get("data"),
        },
        "shards": {
            "total": health.get("active_shards"),
            "primary": health.get("active_primary_shards"),
            "replica": health.get("active_shards") - health.get("active_primary_shards") if health.get("active_shards") and health.get("active_primary_shards") else 0,
        },
        "indices": {
            "count": indices.get("count"),
            "docs": (indices.get("docs") or {}).get("count"),
            "store_bytes": (indices.get("store") or {}).get("size_in_bytes"),
        },
    }
    return ApiResponse(data=data)


@app.get("/api/v1/es/clusters/{cluster_id}/unbacked", response_model=ApiResponse)
def es_unbacked_indices(
    cluster_id: int,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
):
    cluster = _fetch_es_cluster_or_404(db, cluster_id)
    repo = _require_snapshot_repo(cluster)
    pattern = "*"
    if keyword:
        pattern = keyword.strip()
        if not pattern.endswith("*"):
            pattern = f"{pattern}*"

    indices_payload = _es_request(
        cluster,
        "GET",
        "/_cat/indices",
        params={"format": "json", "index": pattern},
    )
    if not isinstance(indices_payload, list):
        raise HTTPException(status_code=502, detail="ES indices response invalid")
    indices = sorted({item.get("index") for item in indices_payload if item.get("index")})

    snapshots_payload = _es_request(cluster, "GET", f"/_snapshot/{repo}/_all")
    snapshots = (snapshots_payload or {}).get("snapshots") or []
    backed = {idx for snap in snapshots for idx in snap.get("indices", [])}

    unbacked = [name for name in indices if name not in backed]
    return ApiResponse(data={"total": len(unbacked), "items": unbacked, "repo": repo})


@app.post("/api/v1/es/clusters/{cluster_id}/snapshots", response_model=ApiResponse)
def es_create_snapshot(cluster_id: int, payload: EsSnapshotCreate, db: Session = Depends(get_db)):
    cluster = _fetch_es_cluster_or_404(db, cluster_id)
    repo = _require_snapshot_repo(cluster)

    body = {"indices": payload.index, "include_global_state": False}
    result = _es_request(
        cluster,
        "PUT",
        f"/_snapshot/{repo}/{payload.snapshot}",
        params={"wait_for_completion": "true"},
        json_body=body,
    )
    return ApiResponse(data=result)








SNAPSHOT_TASK_STATUS_PENDING = "PENDING"
SNAPSHOT_TASK_STATUS_RUNNING = "RUNNING"
SNAPSHOT_TASK_STATUS_SUCCESS = "SUCCESS"
SNAPSHOT_TASK_STATUS_FAILED = "FAILED"
SNAPSHOT_TASK_STATUS_RETRYING = "RETRYING"
SNAPSHOT_TASK_STATUS_CANCELED = "CANCELED"

snapshot_scheduler_stop = threading.Event()
snapshot_scheduler_thread: Optional[threading.Thread] = None


def _normalize_schedule_time(value: datetime) -> datetime:
    # 确保返回不带时区的本地时间
    # 前端已经处理了时区，传递的是正确的本地时间
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.replace(second=0, microsecond=0)


def _build_snapshot_name(index_name: str, scheduled_at: datetime) -> str:
    safe_index = index_name.replace(" ", "_").replace("/", "_")
    return f"auto_{safe_index}_{scheduled_at.strftime('%Y%m%d_%H%M')}"


def _record_snapshot_task_log(
    db: Session,
    task: EsSnapshotTask,
    status: str,
    executed_at: datetime,
    error_message: Optional[str],
    result: Optional[dict],
):
    db.add(
        EsSnapshotTaskLog(
            task_id=task.id,
            task_created_at=task.created_at,
            index_name=task.index_name,
            snapshot_name=task.snapshot_name,
            scheduled_at=task.scheduled_at,
            executed_at=executed_at,
            status=status,
            error_message=error_message,
            result_json=json.dumps(result, ensure_ascii=False) if result is not None else None,
        )
    )


def _execute_snapshot_task(db: Session, task: EsSnapshotTask):
    if task.status not in (SNAPSHOT_TASK_STATUS_PENDING, SNAPSHOT_TASK_STATUS_RETRYING):
        return

    now = datetime.now()
    task.status = SNAPSHOT_TASK_STATUS_RUNNING
    task.last_run_at = now
    db.add(task)
    db.commit()
    db.refresh(task)

    attempt_status = SNAPSHOT_TASK_STATUS_FAILED
    error_message = None
    result = None

    try:
        cluster = _fetch_es_cluster_or_404(db, task.cluster_id)
        repo = _require_snapshot_repo(cluster)
        snapshot_name = task.snapshot_name or _build_snapshot_name(task.index_name, task.scheduled_at)
        task.snapshot_name = snapshot_name

        body = {"indices": task.index_name, "include_global_state": False}
        # 发起快照请求，不等待完成
        _es_request(
            cluster,
            "PUT",
            f"/_snapshot/{repo}/{snapshot_name}",
            params={"wait_for_completion": "false"},
            json_body=body,
            timeout=30,
        )
        
        # 开始轮询快照状态
        import time
        max_timeout = 2600  # 最大超时时间，单位：秒
        poll_interval = 30  # 轮询间隔，单位：秒
        start_time = time.time()
        
        while time.time() - start_time < max_timeout:
            # 检查任务是否被终止
            db.refresh(task)
            if task.status == SNAPSHOT_TASK_STATUS_CANCELED:
                error_message = "任务被手动终止"
                attempt_status = SNAPSHOT_TASK_STATUS_CANCELED
                break
                
            time.sleep(poll_interval)
            # 查询快照状态
            try:
                status_result = _es_request(
                    cluster,
                    "GET",
                    f"/_snapshot/{repo}/{snapshot_name}",
                    timeout=30,
                )
                
                snapshot_status = status_result.get('snapshots', [{}])[0].get('state')
                if snapshot_status == 'SUCCESS':
                    attempt_status = SNAPSHOT_TASK_STATUS_SUCCESS
                    task.status = SNAPSHOT_TASK_STATUS_SUCCESS
                    task.last_success_at = datetime.now()
                    task.last_error = None
                    task.result_json = json.dumps(status_result, ensure_ascii=False)
                    task.next_run_at = None
                    break
                elif snapshot_status == 'FAILED':
                    error_message = f"快照创建失败: {status_result.get('snapshots', [{}])[0].get('failures', [{}])[0].get('reason', 'Unknown error')}"
                    attempt_status = SNAPSHOT_TASK_STATUS_FAILED
                    break
                # IN_PROGRESS 状态，继续轮询
            except Exception as exc:
                # 记录错误但继续轮询，避免网络临时问题导致任务失败
                pass
        
        # 超时处理
        if time.time() - start_time >= max_timeout:
            error_message = f"快照创建超时，超过最大等待时间 {max_timeout} 秒"
            attempt_status = SNAPSHOT_TASK_STATUS_FAILED
    except HTTPException as exc:
        error_message = str(exc.detail)
    except Exception as exc:
        error_message = str(exc)

    if attempt_status == SNAPSHOT_TASK_STATUS_CANCELED:
        # 任务被手动终止，不进行重试
        task.status = SNAPSHOT_TASK_STATUS_CANCELED
        task.next_run_at = None
        task.last_error = error_message
    elif attempt_status != SNAPSHOT_TASK_STATUS_SUCCESS:
        task.retry_count += 1
        task.last_error = error_message
        if task.retry_count <= task.max_retries:
            task.status = SNAPSHOT_TASK_STATUS_RETRYING
            task.next_run_at = datetime.now() + timedelta(minutes=task.retry_interval_minutes)
        else:
            task.status = SNAPSHOT_TASK_STATUS_FAILED
            task.next_run_at = None

    _record_snapshot_task_log(db, task, attempt_status, datetime.now(), error_message, result)
    db.add(task)
    db.commit()


def _snapshot_scheduler_loop():
    while not snapshot_scheduler_stop.is_set():
        now = datetime.now()
        db = SessionLocal()
        try:
            tasks = (
                db.execute(
                    select(EsSnapshotTask)
                    .where(
                        EsSnapshotTask.status.in_(
                            [SNAPSHOT_TASK_STATUS_PENDING, SNAPSHOT_TASK_STATUS_RETRYING]
                        ),
                        EsSnapshotTask.next_run_at <= now,
                    )
                    .order_by(EsSnapshotTask.next_run_at.asc())
                    .limit(5)
                )
                .scalars()
                .all()
            )
            for task in tasks:
                _execute_snapshot_task(db, task)
        except Exception:
            db.rollback()
        finally:
            db.close()
        snapshot_scheduler_stop.wait(5)


def start_snapshot_scheduler():
    global snapshot_scheduler_thread
    if snapshot_scheduler_thread and snapshot_scheduler_thread.is_alive():
        return
    snapshot_scheduler_stop.clear()
    snapshot_scheduler_thread = threading.Thread(target=_snapshot_scheduler_loop, daemon=True)
    snapshot_scheduler_thread.start()


def stop_snapshot_scheduler():
    snapshot_scheduler_stop.set()
    if snapshot_scheduler_thread and snapshot_scheduler_thread.is_alive():
        snapshot_scheduler_thread.join(timeout=2)


@app.post("/api/v1/es/snapshots/tasks", response_model=ApiResponse)
def create_snapshot_task(payload: EsSnapshotTaskCreate, db: Session = Depends(get_db)):
    cluster = _fetch_es_cluster_or_404(db, payload.cluster_id)
    _require_snapshot_repo(cluster)

    scheduled_at = _normalize_schedule_time(payload.scheduled_at)
    now = datetime.now()  # 使用本地时间
    # 确保scheduled_at也不带时区，与本地时间保持一致
    if scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.replace(tzinfo=None)
    next_run_at = scheduled_at if scheduled_at >= now else now

    task = EsSnapshotTask(
        cluster_id=payload.cluster_id,
        index_name=payload.index_name.strip(),
        snapshot_name=(payload.snapshot_name or "").strip() or None,
        scheduled_at=scheduled_at,
        next_run_at=next_run_at,
        status=SNAPSHOT_TASK_STATUS_PENDING,
        retry_count=0,
        max_retries=payload.max_retries,
        retry_interval_minutes=payload.retry_interval_minutes,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return ApiResponse(data=EsSnapshotTaskOut.model_validate(task).model_dump())


@app.get("/api/v1/es/snapshots/tasks", response_model=ApiResponse)
def list_snapshot_tasks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    cluster_id: Optional[int] = None,
    status: Optional[str] = None,
    index_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    filters = []
    if cluster_id is not None:
        filters.append(EsSnapshotTask.cluster_id == cluster_id)
    if status:
        filters.append(EsSnapshotTask.status == status)
    if index_name:
        filters.append(EsSnapshotTask.index_name.ilike(f"%{index_name}%"))
    where_clause = and_(*filters) if filters else True

    total = db.execute(select(func.count()).select_from(EsSnapshotTask).where(where_clause)).scalar_one()
    tasks = (
        db.execute(
            select(EsSnapshotTask)
            .where(where_clause)
            .order_by(EsSnapshotTask.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        .scalars()
        .all()
    )
    data = PageResult(
        total=total,
        page=page,
        size=size,
        items=[EsSnapshotTaskOut.model_validate(task).model_dump() for task in tasks],
    )
    return ApiResponse(data=data.model_dump())


@app.get("/api/v1/es/snapshots/tasks/{task_id}", response_model=ApiResponse)
def get_snapshot_task(task_id: int, db: Session = Depends(get_db)):
    task = db.execute(select(EsSnapshotTask).where(EsSnapshotTask.id == task_id)).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="snapshot task not found")
    logs = (
        db.execute(
            select(EsSnapshotTaskLog)
            .where(EsSnapshotTaskLog.task_id == task_id)
            .order_by(EsSnapshotTaskLog.id.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    return ApiResponse(
        data={
            "task": EsSnapshotTaskOut.model_validate(task).model_dump(),
            "logs": [EsSnapshotTaskLogOut.model_validate(log).model_dump() for log in logs],
        }
    )


@app.post("/api/v1/es/snapshots/tasks/{task_id}/terminate", response_model=ApiResponse)
def terminate_snapshot_task(task_id: int, db: Session = Depends(get_db)):
    task = db.execute(select(EsSnapshotTask).where(EsSnapshotTask.id == task_id)).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="snapshot task not found")
    
    if task.status != SNAPSHOT_TASK_STATUS_RUNNING:
        raise HTTPException(status_code=400, detail="only running tasks can be terminated")
    
    task.status = SNAPSHOT_TASK_STATUS_CANCELED
    task.next_run_at = None
    db.add(task)
    db.commit()
    db.refresh(task)
    return ApiResponse(data=EsSnapshotTaskOut.model_validate(task).model_dump())


@app.get("/api/v1/es/snapshots/tasks/logs", response_model=ApiResponse)
def list_snapshot_task_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    task_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    filters = []
    if task_id is not None:
        filters.append(EsSnapshotTaskLog.task_id == task_id)
    where_clause = and_(*filters) if filters else True
    total = db.execute(select(func.count()).select_from(EsSnapshotTaskLog).where(where_clause)).scalar_one()
    logs = (
        db.execute(
            select(EsSnapshotTaskLog)
            .where(where_clause)
            .order_by(EsSnapshotTaskLog.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        .scalars()
        .all()
    )
    data = PageResult(
        total=total,
        page=page,
        size=size,
        items=[EsSnapshotTaskLogOut.model_validate(log).model_dump() for log in logs],
    )
    return ApiResponse(data=data.model_dump())


@app.put("/api/v1/es/snapshots/tasks/{task_id}", response_model=ApiResponse)
def update_snapshot_task(task_id: int, payload: EsSnapshotTaskUpdate, db: Session = Depends(get_db)):
    task = db.execute(select(EsSnapshotTask).where(EsSnapshotTask.id == task_id)).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="snapshot task not found")
    if task.status == SNAPSHOT_TASK_STATUS_RUNNING:
        raise HTTPException(status_code=409, detail="snapshot task is running")
    if task.status == SNAPSHOT_TASK_STATUS_CANCELED:
        raise HTTPException(status_code=409, detail="snapshot task is canceled")

    updated = False
    if payload.index_name is not None:
        task.index_name = payload.index_name.strip()
        updated = True
    if payload.snapshot_name is not None:
        task.snapshot_name = payload.snapshot_name.strip() or None
        updated = True
    if payload.scheduled_at is not None:
        scheduled_at = _normalize_schedule_time(payload.scheduled_at)
        task.scheduled_at = scheduled_at
        task.next_run_at = scheduled_at if scheduled_at >= datetime.now() else datetime.now()
        updated = True
    if payload.max_retries is not None:
        task.max_retries = payload.max_retries
        updated = True
    if payload.retry_interval_minutes is not None:
        task.retry_interval_minutes = payload.retry_interval_minutes
        updated = True

    if updated:
        task.status = SNAPSHOT_TASK_STATUS_PENDING
        task.retry_count = 0
        task.last_error = None
        task.last_run_at = None
        task.last_success_at = None
        task.result_json = None

    db.add(task)
    db.commit()
    db.refresh(task)
    return ApiResponse(data=EsSnapshotTaskOut.model_validate(task).model_dump())


@app.post("/api/v1/es/snapshots/tasks/{task_id}/cancel", response_model=ApiResponse)
def cancel_snapshot_task(task_id: int, db: Session = Depends(get_db)):
    task = db.execute(select(EsSnapshotTask).where(EsSnapshotTask.id == task_id)).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="snapshot task not found")
    if task.status == SNAPSHOT_TASK_STATUS_RUNNING:
        raise HTTPException(status_code=409, detail="snapshot task is running")
    if task.status == SNAPSHOT_TASK_STATUS_CANCELED:
        raise HTTPException(status_code=409, detail="snapshot task is already canceled")

    task.status = SNAPSHOT_TASK_STATUS_CANCELED
    task.next_run_at = None
    db.add(task)
    db.commit()
    return ApiResponse(data={"canceled": task_id})


@app.delete("/api/v1/es/snapshots/tasks/{task_id}", response_model=ApiResponse)
def delete_snapshot_task(task_id: int, db: Session = Depends(get_db)):
    task = db.execute(select(EsSnapshotTask).where(EsSnapshotTask.id == task_id)).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="snapshot task not found")
    if task.status == SNAPSHOT_TASK_STATUS_RUNNING:
        raise HTTPException(status_code=409, detail="snapshot task is running")

    # 真正删除任务记录
    db.delete(task)
    db.commit()
    return ApiResponse(data={"deleted": task_id})


# 脚本管理相关API
@app.post("/api/v1/scripts/upload", response_model=ApiResponse)
async def upload_script(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")
    
    if not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="only Python scripts (.py) are allowed")
    
    # 生成唯一的文件名，避免冲突
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = file.filename.replace(" ", "_")
    unique_filename = f"{timestamp}_{safe_filename}"
    file_path = SCRIPTS_DIR / unique_filename
    
    # 保存文件
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save script: {str(e)}")
    
    # 构建脚本URL
    script_url = f"/scripts/{unique_filename}"
    
    return ApiResponse(data={
        "filename": unique_filename,
        "original_filename": file.filename,
        "url": script_url,
        "size": len(content),
        "uploaded_at": datetime.utcnow().isoformat()
    })


@app.get("/api/v1/scripts", response_model=ApiResponse)
def list_scripts():
    scripts = []
    try:
        for file_path in SCRIPTS_DIR.iterdir():
            if file_path.is_file() and file_path.suffix == ".py":
                stat = file_path.stat()
                scripts.append({
                    "filename": file_path.name,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "url": f"/scripts/{file_path.name}"
                })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list scripts: {str(e)}")
    
    return ApiResponse(data={"total": len(scripts), "items": scripts})


@app.get("/api/v1/scripts/{filename}", response_model=ApiResponse)
def get_script(filename: str):
    file_path = SCRIPTS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="script not found")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read script: {str(e)}")
    
    stat = file_path.stat()
    return ApiResponse(data={
        "filename": filename,
        "content": content,
        "size": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "url": f"/scripts/{filename}"
    })


@app.delete("/api/v1/scripts/{filename}", response_model=ApiResponse)
def delete_script(filename: str):
    file_path = SCRIPTS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="script not found")
    
    try:
        file_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete script: {str(e)}")
    
    return ApiResponse(data={"deleted": filename})


