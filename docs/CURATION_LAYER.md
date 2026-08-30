# Registrant and Satellite Curation

## Contract

The raw `registrants` table is the immutable imported registration truth. The
curation layer is a rebuildable analytical interpretation of unique people:

```text
Dashboard metric
  -> curated_registrants
      -> curated_registrant_sources
          -> registrants
```

Satellite analytics follow:

```text
Satellite metric
  -> satellites
      -> curated_registrant_satellites
          -> curated_registrants
              -> curated_registrant_sources
                  -> registrants
```

## Person deduplication

Automatic matching requires all four canonical fields:

```text
normalized last name + birth month + birth year + gender
```

- Last name is Unicode-normalized, trimmed, internal whitespace is collapsed,
  and casing is folded.
- Full, abbreviated, and numeric months become `01` through `12`.
- Valid four-digit years from 1900 through 2100 are canonicalized.
- Only unambiguous Male/Female source representations become identity values.

Example:

```text
" DE LA CRUZ " | January | 1995 | Male
"De La Cruz"   | Jan     | 1995 | male

-> de la cruz|01|1995|male
```

If any required identity field is absent or invalid, the raw row becomes its
own curated record with `dedupe_complete = 0`. Two incomplete records are never
automatically merged.

## Group resolution

- `checked_in` is true when any linked raw source is checked in.
- A mixed participant/volunteer group uses `participant` for participant-target
  reporting and sets `registration_type_conflict = 1` for review.
- Life Stage uses the most frequent normalized source value with a stable
  category tie-breaker.
- Every raw member remains linked through `curated_registrant_sources`.

## Satellite normalization

Whitespace/casing differences and an optional `CCF` prefix normalize to one CCF
satellite. `Eastwood`, `CCF Eastwood`, and `CCF EASTWOOD` become `CCF Eastwood`.
B1G-prefixed names remain in a distinct B1G namespace to avoid aggressive
merging.

Every distinct source spelling and its source affiliation/count are retained in
`satellite_source_variations`. Separate valid associations from duplicate raw
registrations are unioned, so a curated person may be linked to multiple
satellites without losing either relationship.

## Processing lifecycle

Curation runs inside the raw import transaction before the batch becomes active:

1. Read ticket-matched raw registrants.
2. Normalize and group complete identities.
3. Keep incomplete identities separate.
4. Create curated people and source mappings.
5. Resolve check-in, registration type, and conflicts.
6. Normalize satellites, variations, and person associations.
7. Activate the successfully processed batch.

If any step fails, the transaction rolls back and the previous active batch is
unchanged. A rerun deletes and recreates only that batch's derived layer, so it
does not duplicate mappings or associations.

## Dashboard and Data Quality behavior

Unique Participants, Unique Volunteers, participant target progress,
demographics, unique check-ins, and satellite distributions use curated people.
Raw Registration counts continue to use ticket-matched `registrants` rows.

The Data Quality page keeps two explicit sections:

- Import Quality: validation errors and warnings from `validation_issues`.
- Curation Quality: raw/unique reconciliation, duplicate groups, incomplete
  identities, type conflicts, multiple satellites, normalized satellites, and
  source drill-downs.

## Supplied-data reconciliation

The supplied B1G Converge 2025 dataset currently reconciles as:

```text
Raw Registrations:           4,334
Unique Curated Registrants:  4,312
Duplicate Records Merged:       22
Duplicate Groups:                22
Incomplete Identity:          1,108
Multiple-Satellite People:        7
Unique Satellites:                80
```

These differences are produced by the documented identity rule, not by manual
adjustment to legacy Excel totals.
