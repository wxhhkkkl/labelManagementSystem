# 数据备份配置（T162）

**日期**：2026-10-12

覆盖两项要求：

- **MySQL 每日自动备份，保留 30 天**（非功能需求·部署）
- **操作日志保留不少于 2 年**（FR-063）

---

## 一、MySQL 每日备份

数据库跑在数据库机（内网 `172.20.68.219`）上，**从应用机发起备份**——
3306 只允许应用机连入（见 `deploy-topology`）。

### 备份脚本

放在应用机的 `/opt/lms/scripts/backup.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

# 凭据从环境文件读，不写在脚本里
source /opt/lms/.env

BACKUP_DIR=/opt/lms/backups
STAMP=$(date +%Y%m%d-%H%M%S)
DB=labelManagementSystemDB

mkdir -p "$BACKUP_DIR"

mysqldump \
  --host="$MYSQL_DB_SERVER" \
  --user="$MYSQL_DB_USER" \
  --password="$MYSQL_DB_PSW" \
  --single-transaction \
  --routines --triggers \
  --default-character-set=utf8mb4 \
  "$DB" | gzip > "$BACKUP_DIR/${DB}-${STAMP}.sql.gz"

# 保留 30 天：删掉更早的
find "$BACKUP_DIR" -name "${DB}-*.sql.gz" -mtime +30 -delete

echo "备份完成：${DB}-${STAMP}.sql.gz"
```

**`--single-transaction` 是必须的**：InnoDB 下它让备份在一个一致性快照里完成，
不停写、不锁表。少了它，备份期间正在打印的码可能处于半截状态。

### 定时任务

```cron
# 每天凌晨 2:17 备份。刻意避开整点——整点是各类定时任务的集中时刻
17 2 * * * /opt/lms/scripts/backup.sh >> /var/log/lms/backup.log 2>&1
```

### 验证备份可用（重要）

**没验证过能恢复的备份等于没有备份。** 建议每月做一次：

```bash
# 恢复到临时库，确认能建起来且行数合理
gunzip -c /opt/lms/backups/labelManagementSystemDB-*.sql.gz \
  | mysql --host="$MYSQL_DB_SERVER" --user="$MYSQL_DB_USER" --password="$MYSQL_DB_PSW" \
      labelManagementSystemDB_restore_test

mysql -e "SELECT COUNT(*) FROM code" labelManagementSystemDB_restore_test
mysql -e "DROP DATABASE labelManagementSystemDB_restore_test"
```

- [ ] 已配置定时任务
- [ ] 已完成一次恢复演练，日期：______

---

## 二、操作日志保留 ≥ 2 年（FR-063）

**不需要额外配置。** 系统里**根本没有删除或修改审计日志的入口**：

- `AuditLog` 是 append-only（FR-060）
- 审计服务 `app/services/audit.py` 不暴露任何 update / delete 方法
- 接口层也没有对应的 HTTP 端点（有测试专门断言这一点）

因此日志的保留期等价于**数据库的保留期**——只要不被整库清理，日志就在。
上述 30 天保留策略**只作用于 `mysqldump` 的备份文件**，不作用于库内数据。

### 需要人工确认的边界

| 项 | 说明 |
|----|------|
| 数据库磁盘容量 | 审计日志只增不减，需预估两年增长量并确认磁盘够用 |
| 不设日志清理任务 | 若将来要清理，MUST NOT 清 AuditLog——那会直接违反 FR-063 |
| 归档而非删除 | 若两年后确需瘦身，应导出归档而不是 DELETE |

### 增长量粗估

按每天 200 次关键操作估算：`200 × 365 × 2 ≈ 15 万行`。
单行约 200 字节，两年合计约 **30MB** —— 相对于码库本身可以忽略。

**真正的增长点是 `PrintLog` 与 `CodeEvent`**，它们随打印量线性增长。
若担心容量，优先关注这两张表，而**不是**审计日志。

---

## 三、需要人工执行的事项

- [ ] 在应用机创建 `/opt/lms/scripts/backup.sh` 并 `chmod +x`
- [ ] 创建 `/opt/lms/.env`（含 MySQL 凭据，权限设 `600`）
- [ ] 配置 cron 定时任务
- [ ] 确认 `/opt/lms/backups` 所在磁盘容量
- [ ] 完成一次恢复演练
- [ ] 评估数据库机磁盘容量与两年增长量

**注意**：`.env` 权限必须是 `600`，否则同机其他用户能读到数据库口令。
