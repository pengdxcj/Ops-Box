# CMDB Asset Management - Design Document

## 1. Purpose
This project delivers a practical CMDB backend for daily operations, with unified management for:
- Cloud servers
- Databases
- Middleware
- Security products

The system focuses on asset visibility, dependency management, change traceability, and security coverage tracking.

## 2. Architecture
- API framework: FastAPI
- ORM: SQLAlchemy 2.x
- DB: SQLite by default (switchable to MySQL via `CMDB_DATABASE_URL`)
- Runtime: Uvicorn

## 3. Domain Model
- `cmdb_asset`: common asset fields
- `cmdb_asset_cloud_server`: cloud server extension
- `cmdb_asset_database`: database extension
- `cmdb_asset_middleware`: middleware extension
- `cmdb_asset_security_product`: security product extension
- `cmdb_asset_tag`: key-value tags
- `cmdb_asset_relation`: dependency/protection edges
- `cmdb_asset_change_log`: audit records

## 4. Core Flows
1. Asset onboarding
   - Create asset with matching extension payload
   - Record tags
   - Write audit log
2. Asset update
   - Update base fields and extensions
   - Keep full before/after snapshots in audit log
3. Security coverage
   - Use `PROTECT_BY` relation to detect protected assets
   - Produce overall and per-type coverage statistics
4. Topology query
   - Input: one asset ID
   - Output: neighbor nodes and relation edges

## 5. API List (v1)
- `GET /healthz`
- `POST /api/v1/assets`
- `GET /api/v1/assets`
- `GET /api/v1/assets/{asset_id}`
- `PUT /api/v1/assets/{asset_id}`
- `POST /api/v1/relations`
- `GET /api/v1/relations/topology?asset_id=1`
- `POST /api/v1/discovery/sync`
- `GET /api/v1/security/coverage`
- `GET /api/v1/security/uncovered`
- `GET /api/v1/audit/changes`

## 6. Asset Type Rules
- `CLOUD_SERVER` requires `cloud_server`
- `DB` requires `database`
- `MIDDLEWARE` requires `middleware`
- `SECURITY_PRODUCT` requires `security_product`

## 7. Security and Audit
- All write operations to assets generate `cmdb_asset_change_log`.
- RBAC is left for V2 and can be added as middleware + token claims.

## 8. Deployment
- Start command:
  - `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- Swagger:
  - `http://127.0.0.1:8000/docs`

