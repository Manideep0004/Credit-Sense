# CreditSense - Disaster Recovery Runbook & Business Continuity Plan

This runbook outlines standard operating procedures for data backup, database point-in-time recovery (PITR), and disaster recovery (DR) failovers for CreditSense.

---

## 1. RTO and RPO Targets

| Metric | Target | Description |
| :--- | :--- | :--- |
| **Recovery Time Objective (RTO)** | **< 15 minutes** | Maximum allowable time to restore full underwriting operations after total cluster loss. |
| **Recovery Point Objective (RPO)** | **< 5 minutes** | Maximum allowable data loss window in the event of primary database corruption. |

---

## 2. Automated PostgreSQL Backup Procedures

### Daily Automated Snapshots
PostgreSQL data volumes and RDS instances are snapshot-backed daily at 02:00 UTC with a 30-day retention policy.

### WAL (Write-Ahead Logging) Archival
Continuous WAL archiving to an encrypted, immutable S3 bucket (`s3://creditsense-backups-wal/`) enables Point-in-Time Recovery (PITR) down to the second.

### Manual On-Demand Database Backup Command
```bash
# Export full encrypted schema & data dump
pg_dump -h $POSTGRES_HOST -U creditsense -d creditsense_db -F c -b -v -f "/backups/creditsense_$(date +%Y%m%d_%H%M%S).dump"
```

---

## 3. Disaster Recovery Restoration Procedure

### Step 1: Provision Infrastructure Target
```bash
# In local/DR cluster:
kubectl apply -k k8s/
```

### Step 2: Restore PostgreSQL Database
```bash
# Terminate existing active connections
psql -h $POSTGRES_HOST -U creditsense -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'creditsense_db';"

# Drop and recreate database
psql -h $POSTGRES_HOST -U creditsense -d postgres -c "DROP DATABASE IF EXISTS creditsense_db;"
psql -h $POSTGRES_HOST -U creditsense -d postgres -c "CREATE DATABASE creditsense_db OWNER creditsense;"

# Restore dump
pg_restore -h $POSTGRES_HOST -U creditsense -d creditsense_db -v "/backups/latest_verified.dump"
```

### Step 3: Run Alembic Database Schema Verification
```bash
alembic upgrade head
```

### Step 4: Verify Underwriting Pipeline Health
```bash
curl -f http://localhost:8000/api/v1/health
python verify_pipeline.py
```
