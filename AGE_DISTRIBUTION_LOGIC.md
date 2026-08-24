# Age Distribution Logic

## Purpose

Age Distribution describes the age profile of unique curated **participants**
for one selected Event.

Volunteers are not included. Records from other Events are never included.

The authoritative implementation lives in:

- `app/normalization.py`
  - `parse_date()`
  - `calculate_age_at_event()`
  - `get_age_bucket()`
- `app/aggregation.py`
  - `curated_participant_profile_metrics()`
  - `event_dashboard_metrics()`

## Population

A row is included in Age Distribution when it satisfies all of these rules:

1. It belongs to the selected Event's active import batch.
2. It exists in the batch's `curated_registrants` analytical layer.
3. Its resolved registration type is `participant`.

Each unique participant appears exactly once, including participants whose age
cannot be resolved. Every curated person remains traceable to one or more raw
`registrants` rows through `curated_registrant_sources`.

## Reference Date

Age is calculated relative to:

```text
selected_event.event_date
```

The current date, import date, check-in date, and a hardcoded calendar year are
not used as substitutes.

If Event Date is not configured, every participant is placed in `Unknown`. This
keeps the distribution reconcilable while making the missing configuration
visible in the dashboard.

## Source Date Mapping

The importer preserves these possible source values:

```text
Date of Birth / Birth Date -> registrants.birth_date_raw -> curated_registrants.birth_date
Birth Month               -> registrants.birth_month_raw -> curated_registrants.birth_month
Birth Year                -> registrants.birth_year_raw  -> curated_registrants.birth_year
```

The supplied CCF exports contain Birth Month and Birth Year, but not the birth
day. The implementation also supports an optional full DOB if a future export
provides one.

## Full Date-of-Birth Calculation

When a valid full DOB exists, age is birthday-day accurate:

```text
age = event year - birth year

if event month/day is before birth month/day:
    age = age - 1
```

Equivalent implementation:

```python
age = event.year - birth.year - (
    (event.month, event.day) < (birth.month, birth.day)
)
```

Example:

```text
Event Date: September 12, 2026
DOB:        September 13, 2000
Age:        25
```

The participant does not turn 26 until the day after the Event.

```text
Event Date: September 12, 2026
DOB:        September 12, 2000
Age:        26
```

The birthday has occurred on the Event Date, so the participant is 26.

## Birth Month/Year Fallback

The current exports do not contain a birth day. When only Birth Month and Birth
Year are available, the application uses this reproducible estimate:

```text
age = event year - birth year

if event month is before birth month:
    age = age - 1
```

Conceptually, this treats the birthday as having occurred at the beginning of
the supplied birth month. The UI identifies these records as month/year age
estimates rather than claiming day-level precision.

Example:

```text
Event Date:  September 12, 2026
Birth Month: October
Birth Year:  2000
Estimated Age: 25
```

October has not occurred by the Event Date, so the participant is not yet
estimated as 26.

## Accepted Date Formats

For optional full DOB values, the normalization layer accepts:

```text
YYYY-MM-DD
MM/DD/YYYY
Month DD, YYYY
Mon DD, YYYY
```

Birth Month accepts full month names, abbreviated month names, or month numbers
from 1 through 12.

## Validation

Age becomes unresolved when any applicable condition is true:

- Event Date is missing or invalid.
- DOB is missing and Birth Month/Year are incomplete.
- DOB, Birth Month, or Birth Year cannot be parsed.
- Birth Month is outside 1 through 12.
- The calculated age is below 0.
- The calculated age is above 120.

An unresolved value is assigned to `Unknown`. The participant is never silently
removed from the distribution.

## Age Buckets

The normalized age is mapped to exactly one category:

| Age | Dashboard bucket |
|---:|---|
| 0–19 | Below 20 |
| 20–25 | 20–25 |
| 26–30 | 26–30 |
| 31–35 | 31–35 |
| 36–40 | 36–40 |
| 41 or older | 41+ |
| Missing, invalid, or unresolved | Unknown |

`Below 20` is explicit because the supplied dataset contains legitimate
participant records in this population. They must not be discarded.

Boundary examples:

```text
19 -> Below 20
20 -> 20–25
25 -> 20–25
26 -> 26–30
30 -> 26–30
31 -> 31–35
35 -> 31–35
36 -> 36–40
40 -> 36–40
41 -> 41+
```

## Counts and Percentages

For each bucket:

```text
bucket_count = number of participants assigned to the bucket

bucket_percentage =
    bucket_count / total_participants * 100
```

When there are no participants, every bucket count and percentage is zero.

The percentage denominator is always the complete participant population—not
only participants with valid birth data.

## Reconciliation Rule

The following invariant must always hold:

```text
Below 20
+ 20–25
+ 26–30
+ 31–35
+ 36–40
+ 41+
+ Unknown
= Total Participants
```

The dashboard response exposes `age_reconciles` so this invariant can be checked
automatically.

## Supplied Dataset Result

Using the supplied B1G Converge 2025 participant export and an Event Date of
September 5, 2025:

| Age bucket | Participants |
|---|---:|
| Below 20 | 20 |
| 20–25 | 640 |
| 26–30 | 1,262 |
| 31–35 | 808 |
| 36–40 | 280 |
| 41+ | 194 |
| Unknown | 1,108 |
| **Total** | **4,312** |

The 1,108 Unknown records remain part of the participant population. The raw
file has 4,334 valid registration rows; 22 duplicate source rows form 22
complete-identity groups, producing 4,312 unique people. No manual adjustment
is applied to reproduce legacy Excel totals.

## Test Coverage

Automated tests cover:

- Ages 19, 20, 25, 26, 30, 31, 35, 36, 40, and 41.
- A birthday one day after the Event Date.
- A birthday on the Event Date.
- Month/year estimation.
- Missing Event Date.
- Missing and invalid DOB values.
- Invalid month values.
- Implausible ages.
- Unknown reconciliation.
- Cross-Event isolation.
- Participant-only filtering that excludes volunteers.
