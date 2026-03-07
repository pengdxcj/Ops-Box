from sqlalchemy import select

from app.database import SessionLocal
from app.main import _record_change
from app.models import Asset, AssetRelation, AssetSecurityProduct, AssetTag


def run():
    db = SessionLocal()
    try:
        exists = db.execute(select(Asset).where(Asset.asset_code == "ecs-prod-001")).scalars().first()
        if exists:
            print("seed already loaded")
            return

        ecs = Asset(
            asset_code="ecs-prod-001",
            asset_type="CLOUD_SERVER",
            name="prod-app-ecs-001",
            env="prod",
            status="IN_USE",
            owner="ops_team",
            org="platform",
            region="cn-east-1",
        )
        ecs.tags.append(AssetTag(tag_key="service", tag_value="order"))
        ecs.tags.append(AssetTag(tag_key="tier", tag_value="app"))

        db_mysql = Asset(
            asset_code="mysql-prod-001",
            asset_type="DB",
            name="prod-order-mysql",
            env="prod",
            status="IN_USE",
            owner="dba_team",
            org="platform",
            region="cn-east-1",
        )
        db_mysql.tags.append(AssetTag(tag_key="service", tag_value="order"))
        db_mysql.tags.append(AssetTag(tag_key="tier", tag_value="data"))

        waf = Asset(
            asset_code="sec-waf-001",
            asset_type="SECURITY_PRODUCT",
            name="waf-main",
            env="prod",
            status="IN_USE",
            owner="sec_team",
            org="security",
            region="cn-east-1",
        )
        waf.security_product = AssetSecurityProduct(
            product_type="WAF",
            vendor="example-vendor",
            version="3.2.1",
            deploy_mode="gateway",
            coverage_scope="prod/order/*",
        )

        db.add_all([ecs, db_mysql, waf])
        db.flush()

        db.add(AssetRelation(src_asset_id=ecs.id, dst_asset_id=db_mysql.id, relation_type="CONNECT_TO", direction=1))
        db.add(AssetRelation(src_asset_id=ecs.id, dst_asset_id=waf.id, relation_type="PROTECT_BY", direction=1))

        _record_change(db, asset_id=ecs.id, change_type="CREATE", before_data={}, after_data={"asset_code": ecs.asset_code}, operator="seed")
        _record_change(
            db, asset_id=db_mysql.id, change_type="CREATE", before_data={}, after_data={"asset_code": db_mysql.asset_code}, operator="seed"
        )
        _record_change(db, asset_id=waf.id, change_type="CREATE", before_data={}, after_data={"asset_code": waf.asset_code}, operator="seed")
        db.commit()
        print("seed done")
    finally:
        db.close()


if __name__ == "__main__":
    run()

