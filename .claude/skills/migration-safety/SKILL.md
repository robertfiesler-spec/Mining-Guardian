---
name: migration-safety
description: Database migration risk assessment and safety patterns. Use when deploying changes that include schema migrations, or when reviewing migration files for destructive operations, dry-run validation, and rollback planning.
---

# Migration Safety

Detect, classify, and validate database migrations before deployment. Framework-agnostic coverage for the most common ORMs and migration tools.

## Migration File Detection

### Framework Directory Patterns

| Framework | Migration Path(s) | File Pattern |
|-----------|-------------------|-------------|
| **Prisma** | `prisma/migrations/` | `migration.sql` per timestamped dir |
| **Drizzle** | `drizzle/`, `src/db/migrations/` | `*.sql` |
| **Knex** | `migrations/`, `db/migrations/` | `*_migration_name.{js,ts}` |
| **TypeORM** | `src/migrations/`, `migrations/` | `*-MigrationName.ts` |
| **Sequelize** | `migrations/`, `db/migrate/` | `*-migration-name.{js,ts}` |
| **Raw SQL** | `db/migrate/`, `sql/`, `src/db/migrations/` | `*.sql` |

### Schema File Patterns

Also detect schema file changes (may indicate pending migrations):

| Framework | Schema File |
|-----------|------------|
| Prisma | `prisma/schema.prisma`, `prisma/schema/*.prisma` |
| Drizzle | `src/db/schema.ts`, `drizzle.config.ts` |
| TypeORM | Entity files with `@Entity()` decorator |

## Risk Classification

### Destructive (HIGH risk)

Operations that lose data or break existing queries. **Must require explicit confirmation before deploy.**

| Operation | SQL Pattern | Impact |
|-----------|------------|--------|
| Drop table | `DROP TABLE` | Data loss, all referencing queries break |
| Drop column | `ALTER TABLE ... DROP COLUMN` | Data loss, queries referencing column break |
| Rename table | `ALTER TABLE ... RENAME TO` | All referencing queries break |
| Rename column | `ALTER TABLE ... RENAME COLUMN` | Queries and ORM mappings break |
| Change column type | `ALTER TABLE ... ALTER COLUMN ... TYPE` | Data truncation or conversion errors |
| Truncate | `TRUNCATE TABLE` | All data in table deleted |

### Additive (LOW risk)

Operations that extend the schema without affecting existing data or queries.

| Operation | SQL Pattern | Impact |
|-----------|------------|--------|
| Create table | `CREATE TABLE` | None (new entity) |
| Add column | `ALTER TABLE ... ADD COLUMN` | None if nullable or has DEFAULT |
| Add index | `CREATE INDEX` | Possible lock on large tables |
| Add constraint | `ALTER TABLE ... ADD CONSTRAINT` | May fail if existing data violates |

### Data-Only (MEDIUM risk)

DML operations that modify data without schema changes.

| Operation | SQL Pattern | Impact |
|-----------|------------|--------|
| Backfill | `UPDATE ... SET` | May lock rows, long-running on large tables |
| Seed data | `INSERT INTO` | Generally safe, check for conflicts |
| Delete data | `DELETE FROM` | Data loss, check for cascade |

## Dry-Run Commands

### Prisma

```bash
# Compare schema changes without applying
npx prisma migrate diff \
  --from-schema-datamodel prisma/schema.prisma \
  --to-migrations prisma/migrations \
  --script

# Validate migration against the schema
npx prisma migrate resolve --applied <migration_name>

# Reset and reapply (staging only)
npx prisma migrate reset --skip-seed
```

### Drizzle

```bash
# Generate migration SQL from schema diff
npx drizzle-kit generate

# Preview what would be applied
npx drizzle-kit push --dry-run

# Check migration status
npx drizzle-kit check
```

### Knex

```bash
# Check migration status
npx knex migrate:status

# Run migrations (use rollback if needed)
npx knex migrate:latest --env staging
npx knex migrate:rollback --env staging
```

### TypeORM

```bash
# Show pending migrations
npx typeorm migration:show -d src/data-source.ts

# Generate migration from entity changes
npx typeorm migration:generate -d src/data-source.ts src/migrations/AutoMigration

# Run pending migrations
npx typeorm migration:run -d src/data-source.ts

# Revert last migration
npx typeorm migration:revert -d src/data-source.ts
```

### Sequelize

```bash
# Check migration status
npx sequelize-cli db:migrate:status

# Run pending migrations
npx sequelize-cli db:migrate

# Undo last migration
npx sequelize-cli db:migrate:undo
```

### Raw SQL

For raw SQL migrations without an ORM, parse the SQL directly:

```bash
# Review the SQL content
cat db/migrate/001_add_status_column.sql

# Check for destructive patterns
grep -iE 'DROP|TRUNCATE|RENAME|ALTER.*TYPE' db/migrate/*.sql
```

## Pre-Deploy Checklist

Before deploying with migrations:

1. **Review the SQL** — read every migration file, not just the diff
2. **Check for NOT NULL without DEFAULT** — will fail on tables with existing rows
3. **Check for index creation on large tables** — may lock the table
4. **Run dry-run in staging** — apply to a staging DB before production
5. **Verify rollback path** — ensure the down migration reverses the change
6. **Check for data backfills** — long-running UPDATEs may lock rows
7. **Coordinate with team** — destructive changes may affect other developers

## Rollback Assessment

| Scenario | Rollback Strategy |
|----------|------------------|
| Added column (nullable) | `ALTER TABLE ... DROP COLUMN` (safe) |
| Added column (NOT NULL + DEFAULT) | Drop column, but existing code may depend on it |
| Created index | `DROP INDEX` (safe, fast) |
| Dropped column | **Cannot rollback** — data is lost. Restore from backup |
| Changed column type | Reverse ALTER, but data may be truncated |
| Data backfill | Reverse UPDATE if original values are known |

## Common Failure Patterns

| Failure | Cause | Prevention |
|---------|-------|-----------|
| NOT NULL violation | Adding NOT NULL column to table with existing rows | Use DEFAULT or make nullable first, backfill, then add NOT NULL |
| Unique constraint violation | Adding UNIQUE to column with duplicate values | Clean duplicates before adding constraint |
| Foreign key violation | Adding FK to column with orphaned references | Clean orphaned rows first |
| Lock timeout | CREATE INDEX on large table | Use `CREATE INDEX CONCURRENTLY` (Postgres) |
| Type mismatch | ALTER COLUMN TYPE with incompatible data | Cast data first, then change type |
