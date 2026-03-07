# CMDB Service

A runnable CMDB backend prototype for ops teams, covering cloud servers, databases, middleware, and security products.

## 1. Quick Start
1. Create virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. Optional environment config:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Start service:
   ```powershell
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
4. Open API docs:
   - `http://127.0.0.1:8000/docs`

## 2. Demo Data
After service starts once (tables auto-created), seed sample assets:
```powershell
python scripts/seed_demo.py
```

## 3. Main Endpoints
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

## 4. Example Payload: Create Cloud Server
```json
{
  "asset_code": "ecs-prod-002",
  "asset_type": "CLOUD_SERVER",
  "name": "prod-app-ecs-002",
  "env": "prod",
  "status": "IN_USE",
  "owner": "ops_team",
  "org": "platform",
  "region": "cn-east-1",
  "tags": [
    {"tag_key": "service", "tag_value": "order"},
    {"tag_key": "tier", "tag_value": "app"}
  ],
  "cloud_server": {
    "instance_id": "i-ecs-prod-002",
    "vpc_id": "vpc-001",
    "cpu": 4,
    "memory_gb": 8,
    "os": "Ubuntu 22.04",
    "private_ip": "10.0.1.12",
    "public_ip": "1.2.3.4"
  }
}
```

## 5. Config
- Environment variable:
  - `CMDB_DATABASE_URL` (default: `sqlite:///./cmdb.db`)

Example for MySQL:
```env
CMDB_DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/cmdb?charset=utf8mb4
```

## 6. Design Doc
- [docs/CMDB_Design.md](docs/CMDB_Design.md)

