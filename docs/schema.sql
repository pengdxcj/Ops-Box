-- Core CMDB schema (MySQL 8.x style)

CREATE TABLE IF NOT EXISTS cmdb_asset (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_code VARCHAR(64) NOT NULL UNIQUE,
  asset_type VARCHAR(32) NOT NULL,
  name VARCHAR(128) NOT NULL,
  env VARCHAR(16) NOT NULL,
  status VARCHAR(16) NOT NULL,
  owner VARCHAR(64) NOT NULL,
  org VARCHAR(64) NOT NULL,
  region VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  INDEX idx_asset_type (asset_type),
  INDEX idx_asset_name (name)
);

CREATE TABLE IF NOT EXISTS cmdb_asset_cloud_server (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_id BIGINT NOT NULL UNIQUE,
  instance_id VARCHAR(128) NOT NULL UNIQUE,
  vpc_id VARCHAR(64) NOT NULL,
  cpu INT NOT NULL,
  memory_gb INT NOT NULL,
  os VARCHAR(64) NOT NULL,
  private_ip VARCHAR(64) NOT NULL,
  public_ip VARCHAR(64) NULL,
  expire_time DATETIME NULL,
  CONSTRAINT fk_cloud_asset FOREIGN KEY (asset_id) REFERENCES cmdb_asset(id)
);

CREATE TABLE IF NOT EXISTS cmdb_asset_database (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_id BIGINT NOT NULL UNIQUE,
  db_type VARCHAR(32) NOT NULL,
  version VARCHAR(32) NOT NULL,
  endpoint VARCHAR(128) NOT NULL,
  port INT NOT NULL,
  role VARCHAR(32) NOT NULL,
  storage_gb INT NOT NULL,
  backup_policy VARCHAR(128) NOT NULL,
  CONSTRAINT uk_db_endpoint_port UNIQUE (endpoint, port),
  CONSTRAINT fk_db_asset FOREIGN KEY (asset_id) REFERENCES cmdb_asset(id)
);

CREATE TABLE IF NOT EXISTS cmdb_asset_middleware (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_id BIGINT NOT NULL UNIQUE,
  mw_type VARCHAR(32) NOT NULL,
  cluster_name VARCHAR(64) NOT NULL,
  version VARCHAR(32) NOT NULL,
  node_count INT NOT NULL,
  ha_mode VARCHAR(32) NOT NULL,
  CONSTRAINT fk_mw_asset FOREIGN KEY (asset_id) REFERENCES cmdb_asset(id)
);

CREATE TABLE IF NOT EXISTS cmdb_asset_security_product (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_id BIGINT NOT NULL UNIQUE,
  product_type VARCHAR(32) NOT NULL,
  vendor VARCHAR(64) NOT NULL,
  version VARCHAR(32) NOT NULL,
  deploy_mode VARCHAR(32) NOT NULL,
  coverage_scope TEXT NOT NULL,
  license_expire DATETIME NULL,
  CONSTRAINT fk_sec_asset FOREIGN KEY (asset_id) REFERENCES cmdb_asset(id)
);

CREATE TABLE IF NOT EXISTS cmdb_asset_tag (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_id BIGINT NOT NULL,
  tag_key VARCHAR(64) NOT NULL,
  tag_value VARCHAR(128) NOT NULL,
  CONSTRAINT uk_asset_tag UNIQUE (asset_id, tag_key),
  CONSTRAINT fk_tag_asset FOREIGN KEY (asset_id) REFERENCES cmdb_asset(id),
  INDEX idx_tag_asset_id (asset_id)
);

CREATE TABLE IF NOT EXISTS cmdb_asset_relation (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  src_asset_id BIGINT NOT NULL,
  dst_asset_id BIGINT NOT NULL,
  relation_type VARCHAR(32) NOT NULL,
  direction TINYINT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL,
  CONSTRAINT uk_asset_relation UNIQUE (src_asset_id, dst_asset_id, relation_type),
  CONSTRAINT fk_relation_src FOREIGN KEY (src_asset_id) REFERENCES cmdb_asset(id),
  CONSTRAINT fk_relation_dst FOREIGN KEY (dst_asset_id) REFERENCES cmdb_asset(id)
);

CREATE TABLE IF NOT EXISTS cmdb_asset_change_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  asset_id BIGINT NOT NULL,
  change_type VARCHAR(32) NOT NULL,
  before_json JSON NOT NULL,
  after_json JSON NOT NULL,
  operator VARCHAR(64) NOT NULL,
  changed_at DATETIME NOT NULL,
  CONSTRAINT fk_log_asset FOREIGN KEY (asset_id) REFERENCES cmdb_asset(id),
  INDEX idx_log_asset_id (asset_id),
  INDEX idx_log_changed_at (changed_at)
);

