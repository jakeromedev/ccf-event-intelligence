# Event Overview Number Logic

The dashboard is not using the event capacity of 450. It is counting the records in the three uploaded exports according to the approved Phase 1 definitions.

## How the Current Numbers Were Calculated

| Metric | Logic | Result |
|---|---|---:|
| Total Registrants | Registrant rows whose `Ticket Code` matches a generated ticket | 4,334 |
| Checked-In Attendees | Those registrants whose matched ticket has a valid `Check-in Date Time` | 3,869 |
| Attendance Rate | `3,869 / 4,334 x 100` | 89.3% |
| CCF Main | Classified registrants | 1,280 |
| Satellite Churches | Local Satellite + International Satellite | 1,506 |
| Non-CCF | `Are You Attending Ccf = No` | 440 |
| Unknown | Missing or invalid affiliation answers | 1,108 |

The affiliation totals reconcile exactly:

```text
1,280 + 1,506 + 440 + 1,108 = 4,334
```

Satellite Churches consists of:

- Local Satellite: 1,498
- International Satellite: 8
- Total Satellites: 1,506

## What Is Actually in the CSV Files

The current active batch contains:

- 8,000 generated-ticket records
- 4,334 registrant records
- 4,334 distinct registrant Ticket Codes
- All 4,334 Ticket Codes match generated tickets
- All 4,334 matched tickets are marked `Assigned`
- 3,869 matched tickets have check-in timestamps

The registrants were created through:

| Source | Records |
|---|---:|
| Workshop Registration Form | 3,224 |
| Seeder | 1,041 |
| Check-In Form | 69 |
| **Total** | **4,334** |

Most Seeder and Check-In Form records have incomplete profiles. However, even if those records were excluded, there would still be **3,224 Workshop Registration Form registrations**, not approximately 450.

Similarly, counting normalized unique email addresses produces approximately **3,146**. Deduplicating by email therefore would not explain the difference, and email is not a sufficiently reliable permanent person identifier.

## Conclusion

The application appears to be correctly summarizing the uploaded files, but the uploaded data does not appear to represent only a 450-participant event.

The strongest warning sign is that the generated-tickets export itself contains **3,869 check-in timestamps**. That cannot reasonably be reconciled with a 450-person event without an additional scope or filtering rule.

Possible explanations are:

- The exports were generated for the wrong event.
- `B1G Converge 2025` is a parent event containing several sessions or sub-events.
- The intended 450 participants belong to one workshop or session, but the exports cover the whole conference.
- Seeder or system-generated records are included, although excluding them still leaves 3,224 registrations.
- The figure 450 represents event capacity rather than the scope of these exports.

## Recommendation

Do not change the formulas or force the count to 450. First identify the correct event-scoping information, such as:

- Session
- Workshop
- Sub-event
- Ticket category
- Event-specific identifier

If the source system can provide another export, it should contain each registrant's `Ticket Code` and the session or sub-event identifier that identifies the intended 450-person group. That dataset can then be joined to the existing records through `Ticket Code` and used as an explicit event filter.

Event capacity may also be stored later as separate event metadata, but it should not cap or replace the actual registration and check-in counts.
