# Satellite Settings Database Schema

## Document scope

This document describes the complete database schema used by the Satellite
Settings page. It covers the three directory tables managed by the page and
the imported `satellites` table that consumes the canonical directory.

The schema was verified against the local MySQL `ccf_events` database on
September 3, 2026. The database was at Alembic revision `f7c2a8d5e913`.
Auto-increment counters and row counts are data-dependent and are intentionally
not treated as schema definitions.

For page behavior and workflows, see `docs/SATELLITE_SETTINGS_PAGE.md`.

## Schema overview

```text
hub_groups
    id PK
      │
      │ 1-to-many, ON DELETE RESTRICT
      ▼
satellite_hubs
    id PK
      │
      │ 1-to-many, ON DELETE SET NULL
      ▼
satellite_directory
    id PK
      │
      │ 1-to-many, ON DELETE SET NULL
      ▼
satellites
    id PK
    (event_id, batch_id) FK ──────► import_batches(event_id, id)
```

The ownership hierarchy is:

```text
Hub Group → Hub → canonical Satellite → imported Satellite evidence
```

The first three levels are global and independent of an Event or import batch.
The final `satellites` table is Event- and batch-scoped.

## Entity summary

| Table | Role | Managed by Settings |
| --- | --- | --- |
| `hub_groups` | Two fixed geographic Hub classifications | Read-only |
| `satellite_hubs` | User-managed Hubs inside a fixed Hub Group | Create and update |
| `satellite_directory` | Stable canonical Satellite identities | Create and update |
| `satellites` | Imported, batch-scoped Satellite evidence | Read through relationships only |

Satellite Settings currently exposes no delete action. The `ON DELETE`
behaviors documented below protect relationships if records are changed by a
future feature, migration, or direct administrative operation.

## `hub_groups`

### Purpose

`hub_groups` stores the two fixed system classifications used to organize all
Hubs. These rows are seeded by migration and are not free-form records in the
Satellite Settings interface.

### Columns

| Column | Type | Nullable | Default | Description |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT UNSIGNED` | No | Auto-increment | Primary identifier |
| `code` | `VARCHAR(32)` | No | None | Stable machine-readable classification code |
| `name` | `VARCHAR(160)` | No | None | Human-readable group name |
| `sort_order` | `INT` | No | None | Display order in the page hierarchy |

### Keys and constraints

| Name | Type | Definition |
| --- | --- | --- |
| `PRIMARY` | Primary key | (`id`) |
| `uq_hub_groups_code` | Unique | (`code`) |
| `uq_hub_groups_name` | Unique | (`name`) |
| `ck_hub_groups_code` | Check | `code IN ('outside_metro_manila', 'within_metro_manila')` |

### Seeded rows

| ID | Code | Name | Sort order |
| ---: | --- | --- | ---: |
| 1 | `within_metro_manila` | Within Metro Manila Hubs | 1 |
| 2 | `outside_metro_manila` | Outside Metro Manila Hubs | 2 |

The application depends on these codes for filtering and display labels. They
should be treated as stable identifiers.

### Equivalent MySQL DDL

```sql
CREATE TABLE hub_groups (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(32) COLLATE utf8mb4_unicode_ci NOT NULL,
    name VARCHAR(160) COLLATE utf8mb4_unicode_ci NOT NULL,
    sort_order INT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_hub_groups_code UNIQUE (code),
    CONSTRAINT uq_hub_groups_name UNIQUE (name),
    CONSTRAINT ck_hub_groups_code CHECK (
        code IN ('outside_metro_manila', 'within_metro_manila')
    )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
```

## `satellite_hubs`

### Purpose

`satellite_hubs` stores every Hub managed by an administrator. Each Hub belongs
to exactly one of the fixed Hub Groups.

### Columns

| Column | Type | Nullable | Default | Description |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT UNSIGNED` | No | Auto-increment | Primary identifier |
| `hub_group_id` | `BIGINT UNSIGNED` | No | None | Owning `hub_groups.id` |
| `name` | `VARCHAR(160)` | No | None | Canonical Hub display name |
| `normalized_name` | `VARCHAR(160)` | No | None | Application-normalized duplicate key |
| `created_at` | `DATETIME` | No | `CURRENT_TIMESTAMP` | Creation timestamp |
| `updated_at` | `DATETIME` | No | `CURRENT_TIMESTAMP` | Last application-managed update timestamp |

`updated_at` does not use a database-level `ON UPDATE` clause. The application
sets it to `CURRENT_TIMESTAMP` in its update statement.

### Keys, indexes, and constraints

| Name | Type | Definition |
| --- | --- | --- |
| `PRIMARY` | Primary key | (`id`) |
| `uq_satellite_hubs_group_name` | Unique | (`hub_group_id`, `normalized_name`) |
| `idx_satellite_hubs_group` | Index | (`hub_group_id`, `name`) |
| `satellite_hubs_ibfk_1` | Foreign key | `hub_group_id → hub_groups.id ON DELETE RESTRICT` |

The composite unique key makes a Hub name unique within one Hub Group while
allowing the same normalized name in the other Hub Group.

`ON DELETE RESTRICT` prevents removal of a Hub Group that still owns Hubs.

### Equivalent MySQL DDL

```sql
CREATE TABLE satellite_hubs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    hub_group_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(160) COLLATE utf8mb4_unicode_ci NOT NULL,
    normalized_name VARCHAR(160) COLLATE utf8mb4_unicode_ci NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_satellite_hubs_group_name
        UNIQUE (hub_group_id, normalized_name),
    KEY idx_satellite_hubs_group (hub_group_id, name),
    CONSTRAINT satellite_hubs_ibfk_1
        FOREIGN KEY (hub_group_id)
        REFERENCES hub_groups (id)
        ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
```

## `satellite_directory`

### Purpose

`satellite_directory` provides a stable, global identity for a canonical
Satellite. Imported Event data refers to this identity instead of using its
batch-scoped display name as the permanent key.

### Columns

| Column | Type | Nullable | Default | Description |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT UNSIGNED` | No | Auto-increment | Stable canonical Satellite identifier |
| `hub_id` | `BIGINT UNSIGNED` | Yes | `NULL` | Owning Hub; null for preserved unassigned records |
| `name` | `VARCHAR(512)` | No | None | Canonical display name |
| `normalized_name` | `VARCHAR(512)` | No | None | Application-normalized duplicate key |
| `created_at` | `DATETIME` | No | `CURRENT_TIMESTAMP` | Creation timestamp |
| `updated_at` | `DATETIME` | No | `CURRENT_TIMESTAMP` | Last application-managed update timestamp |

`hub_id` is intentionally nullable. The foundation migration created canonical
directory entries for existing imported names without guessing their Hub
assignment.

As with Hubs, `updated_at` is changed explicitly by the application rather than
by an `ON UPDATE` clause.

### Keys, indexes, and constraints

| Name | Type | Definition |
| --- | --- | --- |
| `PRIMARY` | Primary key | (`id`) |
| `uq_satellite_directory_hub_name` | Unique | (`hub_id`, `normalized_name`) |
| `idx_satellite_directory_hub` | Index | (`hub_id`, `name`) |
| `satellite_directory_ibfk_1` | Foreign key | `hub_id → satellite_hubs.id ON DELETE SET NULL` |

The composite unique key makes a Satellite name unique inside one Hub while
allowing the same normalized name in another Hub.

MySQL unique constraints permit multiple rows when a constrained column is
`NULL`. Consequently, the database can contain multiple unassigned rows with
the same `normalized_name`. Assigned record creation and movement are also
validated by the application before the database constraint is reached.

`ON DELETE SET NULL` preserves canonical Satellite records if their parent Hub
is removed outside the current page.

### Equivalent MySQL DDL

```sql
CREATE TABLE satellite_directory (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    hub_id BIGINT UNSIGNED NULL DEFAULT NULL,
    name VARCHAR(512) COLLATE utf8mb4_unicode_ci NOT NULL,
    normalized_name VARCHAR(512) COLLATE utf8mb4_unicode_ci NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_satellite_directory_hub_name
        UNIQUE (hub_id, normalized_name),
    KEY idx_satellite_directory_hub (hub_id, name),
    CONSTRAINT satellite_directory_ibfk_1
        FOREIGN KEY (hub_id)
        REFERENCES satellite_hubs (id)
        ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
```

## `satellites`

### Purpose

`satellites` stores normalized Satellite evidence for a specific Event import
batch. It is not edited by Satellite Settings, but its `directory_id` is the
critical bridge from imported evidence to the canonical directory.

The table also belongs to the broader import and analytics schema. This section
includes the complete current table definition because Satellite Settings
reads aggregate counts through it and canonical renames affect views that join
through it.

### Columns

| Column | Type | Nullable | Default | Description |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT UNSIGNED` | No | Auto-increment | Imported Satellite row identifier |
| `event_id` | `BIGINT UNSIGNED` | No | None | Owning Event |
| `batch_id` | `BIGINT UNSIGNED` | No | None | Owning import batch |
| `name` | `VARCHAR(512)` | No | None | Display name retained from the import |
| `normalized_name` | `VARCHAR(512)` | No | None | Normalized imported name |
| `affiliation` | `VARCHAR(32)` | No | None | Imported affiliation classification |
| `affiliation_conflict` | `TINYINT(1)` | No | `0` | Whether source rows disagree on affiliation |
| `source_record_count` | `BIGINT UNSIGNED` | No | `0` | Source registration rows represented |
| `created_at` | `DATETIME` | No | Current time | Creation timestamp |
| `updated_at` | `DATETIME` | No | Current time | Update timestamp |
| `directory_id` | `BIGINT UNSIGNED` | Yes | `NULL` | Canonical `satellite_directory.id` |

### Keys, indexes, and constraints

| Name | Type | Definition |
| --- | --- | --- |
| `PRIMARY` | Primary key | (`id`) |
| `uq_satellites_batch_name` | Unique | (`batch_id`, `normalized_name`) |
| `uq_satellites_scope_id` | Unique | (`event_id`, `batch_id`, `id`) |
| `idx_satellites_event_batch` | Index | (`event_id`, `batch_id`) |
| `idx_satellites_directory` | Index | (`directory_id`) |
| `satellites_ibfk_1` | Foreign key | (`event_id`, `batch_id`) → `import_batches(event_id, id) ON DELETE CASCADE` |
| `fk_satellites_directory` | Foreign key | `directory_id → satellite_directory.id ON DELETE SET NULL` |
| `ck_satellites_affiliation` | Check | See allowed values below |
| `ck_satellites_affiliation_conflict` | Check | `affiliation_conflict IN (0, 1)` |
| `ck_satellites_source_count` | Check | `source_record_count >= 0` |

Allowed `affiliation` values are:

- `CCF Main`;
- `Local Satellite`;
- `International Satellite`.

Deleting an import batch cascades to its imported Satellite evidence. Deleting
a canonical directory entry does not delete imported evidence; it clears
`directory_id` instead.

### Equivalent MySQL DDL

```sql
CREATE TABLE satellites (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_id BIGINT UNSIGNED NOT NULL,
    batch_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(512) COLLATE utf8mb4_unicode_ci NOT NULL,
    normalized_name VARCHAR(512) COLLATE utf8mb4_unicode_ci NOT NULL,
    affiliation VARCHAR(32) COLLATE utf8mb4_unicode_ci NOT NULL,
    affiliation_conflict TINYINT(1) NOT NULL DEFAULT 0,
    source_record_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    directory_id BIGINT UNSIGNED NULL DEFAULT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_satellites_batch_name
        UNIQUE (batch_id, normalized_name),
    CONSTRAINT uq_satellites_scope_id
        UNIQUE (event_id, batch_id, id),
    KEY idx_satellites_event_batch (event_id, batch_id),
    KEY idx_satellites_directory (directory_id),
    CONSTRAINT satellites_ibfk_1
        FOREIGN KEY (event_id, batch_id)
        REFERENCES import_batches (event_id, id)
        ON DELETE CASCADE,
    CONSTRAINT fk_satellites_directory
        FOREIGN KEY (directory_id)
        REFERENCES satellite_directory (id)
        ON DELETE SET NULL,
    CONSTRAINT ck_satellites_affiliation CHECK (
        affiliation IN (
            'CCF Main',
            'Local Satellite',
            'International Satellite'
        )
    ),
    CONSTRAINT ck_satellites_affiliation_conflict CHECK (
        affiliation_conflict IN (0, 1)
    ),
    CONSTRAINT ck_satellites_source_count CHECK (
        source_record_count >= 0
    )
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
```

## Referenced external key

The module does not own `import_batches`, but the `satellites` composite
foreign key requires a unique or primary key over this column pair:

```text
import_batches(event_id, id)
```

The full import schema is outside this document's scope. Its relevant behavior
is that removing a batch deletes the corresponding imported `satellites` rows,
not the global `satellite_directory` identities.

## Name normalization and uniqueness

The schema stores both a display name and a normalized comparison name. The
application creates `normalized_name` by:

1. converting the value to Unicode NFKC form;
2. trimming leading and trailing whitespace;
3. collapsing internal whitespace runs to one space;
4. applying Unicode `casefold()`.

The database then enforces parent-scoped uniqueness using the normalized value:

```text
Hub:       UNIQUE(hub_group_id, normalized_name)
Satellite: UNIQUE(hub_id, normalized_name)
```

This division is intentional: normalization is application behavior, while the
unique constraints are the final concurrency-safe guard.

Maximum application and database lengths are aligned:

| Name | Maximum length |
| --- | ---: |
| Hub | 160 characters |
| Satellite | 512 characters |

## Relationship behavior

| Operation | Database effect |
| --- | --- |
| Move a Hub to another Hub Group | Update `satellite_hubs.hub_group_id`; child directory records keep the same `hub_id` |
| Rename a Hub | Update `name` and `normalized_name`; IDs and child links remain unchanged |
| Move a Satellite to another Hub | Update `satellite_directory.hub_id`; imported links keep the same `directory_id` |
| Rename a Satellite | Update `name` and `normalized_name`; imported evidence remains linked |
| Delete a Hub Group with Hubs | Rejected by `ON DELETE RESTRICT` |
| Delete a Hub | Child `satellite_directory.hub_id` values become `NULL` |
| Delete a directory entry | Imported `satellites.directory_id` values become `NULL` |
| Delete an import batch | Batch-scoped `satellites` rows are deleted |

## Read model used by the page

The page constructs its hierarchy in three ordered queries:

```sql
SELECT id, code, name, sort_order
FROM hub_groups
ORDER BY sort_order, id;

SELECT id, hub_group_id, name
FROM satellite_hubs
ORDER BY LOWER(name), id;

SELECT
    directory.id,
    directory.hub_id,
    directory.name,
    COUNT(satellite.id) AS import_count,
    COALESCE(SUM(satellite.source_record_count), 0) AS source_records,
    COUNT(DISTINCT satellite.event_id) AS event_count
FROM satellite_directory AS directory
LEFT JOIN satellites AS satellite
    ON satellite.directory_id = directory.id
GROUP BY directory.id, directory.hub_id, directory.name
ORDER BY LOWER(directory.name), directory.id;
```

The application assembles these results into Hub Group → Hub → Satellite
objects. Directory entries with `hub_id IS NULL` or a missing parent are kept
in an `unassigned` collection and are not rendered on the current page.

The summary values are derived as follows:

```text
Hubs       = number of satellite_hubs attached to a known Hub Group
Satellites = number of satellite_directory rows attached to a known Hub
```

## Mutation statements

The page performs inserts and updates only. The essential shapes are:

```sql
INSERT INTO satellite_hubs (
    hub_group_id,
    name,
    normalized_name
) VALUES (?, ?, ?);

UPDATE satellite_hubs
SET hub_group_id = ?,
    name = ?,
    normalized_name = ?,
    updated_at = CURRENT_TIMESTAMP
WHERE id = ?;

INSERT INTO satellite_directory (
    hub_id,
    name,
    normalized_name
) VALUES (?, ?, ?);

UPDATE satellite_directory
SET hub_id = ?,
    name = ?,
    normalized_name = ?,
    updated_at = CURRENT_TIMESTAMP
WHERE id = ?;
```

Bulk confirmation uses the same insert columns through `executemany`. It
revalidates normalized duplicates immediately before insertion.

## Migration history

### `e6b1d9a4c702` — Satellite Settings foundation

This migration:

- creates `hub_groups` and seeds the two fixed rows;
- creates `satellite_hubs`;
- creates `satellite_directory`;
- adds `satellites.directory_id`, its index, and foreign key;
- backfills one canonical directory row per existing imported normalized name;
- links existing imported `satellites` rows to those canonical records.

The foundation initially enforced global uniqueness on
`satellite_directory.normalized_name`.

### `f7c2a8d5e913` — Satellite Settings management

This migration replaces the original global directory-name constraint with:

```text
UNIQUE(hub_id, normalized_name)
```

That change supports the current rule that identical Satellite names may exist
under different Hubs. Its downgrade consolidates same-name directory entries,
repoints imported links to the retained entry, and restores global uniqueness.

## Source-of-truth files

| Concern | File |
| --- | --- |
| ORM definitions | `app/models.py` |
| Foundation migration | `migrations/versions/e6b1d9a4c702_add_satellite_settings_foundation.py` |
| Parent-scoped uniqueness migration | `migrations/versions/f7c2a8d5e913_add_satellite_settings_management.py` |
| Validation and SQL operations | `app/satellite_settings.py` |
| Route transaction boundaries | `app/routes.py` |
| Database overview | `docs/CURRENT_DATABASE_STRUCTURE.md` |
| Page behavior | `docs/SATELLITE_SETTINGS_PAGE.md` |

## Schema verification queries

Use these read-only MySQL statements to compare a deployed database with this
document:

```sql
SELECT version_num FROM alembic_version;

SHOW CREATE TABLE hub_groups;
SHOW CREATE TABLE satellite_hubs;
SHOW CREATE TABLE satellite_directory;
SHOW CREATE TABLE satellites;

SELECT
    table_name,
    column_name,
    column_type,
    is_nullable,
    column_default,
    column_key,
    extra
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name IN (
      'hub_groups',
      'satellite_hubs',
      'satellite_directory',
      'satellites'
  )
ORDER BY FIELD(
    table_name,
    'hub_groups',
    'satellite_hubs',
    'satellite_directory',
    'satellites'
), ordinal_position;
```

