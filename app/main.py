import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import Base, engine, get_db
from app.models import (
    Asset,
    AssetChangeLog,
    AssetCloudServer,
    AssetDatabase,
    AssetMiddleware,
    AssetRelation,
    AssetSecurityProduct,
    AssetTag,
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
)

app = FastAPI(title=settings.app_name, version=settings.app_version)
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

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


def _create_or_replace_extension(asset: Asset, payload: dict | None, creator: Callable[[], object]):
    if payload is None:
        return
    extension = creator()
    for key, value in payload.items():
        setattr(extension, key, value)
    setattr(asset, extension.__class__.__name__.replace("Asset", "").lower(), extension)


def _sync_tags(asset: Asset, tags: list[dict]):
    asset.tags.clear()
    for tag in tags:
        asset.tags.append(AssetTag(tag_key=tag["tag_key"], tag_value=tag["tag_value"]))


def _apply_extensions(asset: Asset, payload: AssetCreate | AssetUpdate):
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


def _asset_filters(asset_type: str | None, env: str | None, status: str | None, owner: str | None):
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


def _serialize_tags(tags: list[AssetTag]) -> str:
    return ";".join(f"{tag.tag_key}={tag.tag_value}" for tag in tags)


def _parse_tags(text: str) -> list[dict]:
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


def _dedupe_tags(tags: list[dict]) -> list[dict]:
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


def _optional_int(row: dict, key: str) -> int | None:
    value = _optional_row_value(row, key)
    if not value:
        return None
    return int(value)


def _parse_datetime(value: str, row_index: int, key: str) -> datetime | None:
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
    asset_type: str | None = None,
    env: str | None = None,
    status: str | None = None,
    owner: str | None = None,
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
    asset_type: str | None = None,
    env: str | None = None,
    status: str | None = None,
    owner: str | None = None,
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
    asset_id: int | None = None,
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
