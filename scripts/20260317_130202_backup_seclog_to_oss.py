#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
import urllib.request
import json
import sys
import os

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup_old_unbacked.log')
def log(msg):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}\n"
    sys.stdout.write(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line)

# ========== ⚙️ 配置 ==========
ES_URL = "http://10.249.0.29:19200"
REPO_NAME = "ailpha_repo"
INDEX_PREFIX = "ailpha-baas-log"

TODAY = datetime.date.today()
CUTOFF_DATE = TODAY - datetime.timedelta(days=30)
START_DATE = datetime.date(2025, 1, 1)
END_DATE = CUTOFF_DATE

log("🚀 开始备份 30 天前及更早的未备份索引...")

# ========== 1. 获取所有 old open 索引 ==========
all_indices = set()
current = START_DATE
while current <= END_DATE:
    date_str = current.strftime("%Y%m%d")
    pattern = f"{INDEX_PREFIX}-{date_str}-*"
    url = f"{ES_URL}/_cat/indices/{pattern}?format=json&h=index,status"
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            for item in data:
                if item.get('status') == 'open':
                    all_indices.add(item['index'])
    except Exception as e:
        log(f"⚠️ 获取 {pattern} 失败: {e}")
    current += datetime.timedelta(days=1)

# ========== 2. 获取已备份索引 ==========
backed = set()
try:
    url = f"{ES_URL}/_snapshot/{REPO_NAME}/_all"
    with urllib.request.urlopen(url) as resp:
        snaps = json.loads(resp.read().decode('utf-8'))
        for snap in snaps.get('snapshots', []):
            for idx in snap.get('indices', []):
                if idx.startswith(INDEX_PREFIX):
                    backed.add(idx)
except Exception as e:
    log(f"❌ 获取快照列表失败: {e}")
    sys.exit(1)

# ========== 3. 计算待备份索引 ==========
to_backup = sorted(all_indices - backed)
if not to_backup:
    log("🎉 无旧索引需要备份。")
    sys.exit(0)

log(f"📌 将备份 {len(to_backup)} 个 30 天前的索引...")

# ========== 4. 执行备份 ==========
success = 0
failed = 0

for index in to_backup:
    snapshot_name = f"snapshot_{index}"
    url = f"{ES_URL}/_snapshot/{REPO_NAME}/{snapshot_name}?wait_for_completion=true"
    payload = {
        "indices": index,
        "ignore_unavailable": True,
        "include_global_state": False,
        "partial": True
    }

    log(f"📤 备份 [{index}] → [{snapshot_name}]")
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method='PUT')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
    except Exception as e:
        log(f"❌ 请求异常: {e}")
        failed += 1
        continue

    state = result.get('snapshot', {}).get('state', 'UNKNOWN')
    if state == "SUCCESS":
        duration = result['snapshot'].get('duration_in_millis', 0)
        shards = result['snapshot'].get('shards', {})
        log(f"✅ 成功! 耗时: {duration}ms, 分片: {shards.get('successful',0)}/{shards.get('total',0)}")
        success += 1
    else:
        log(f"❌ 失败! 状态: {state}")
        failed += 1

# ========== 5. 总结 ==========
log("")
log("=" * 50)
log("📊 旧索引备份任务完成!")
log(f"✅ 成功: {success}")
log(f"❌ 失败: {failed}")
log(f"📁 总共处理: {len(to_backup)}")
log("=" * 50)