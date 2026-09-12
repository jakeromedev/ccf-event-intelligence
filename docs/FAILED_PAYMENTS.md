# Failed Payments

The Event sidebar links to `/events/<event_id>/failed-payments`. Approved standard
users and administrators can view the page. Registration-only operators and
unauthenticated visitors cannot access the list. Approved standard users and
administrators can record confirmed outreach and add remarks from each person's
follow-up dialog. History records the operator and Manila timestamp, newest first.
Opening a dialog or cancelling a confirmation does not create a follow-up.

The list uses the Event's active import. Failed purchases appear in the Buyers
export, often without a corresponding Registrant row, so Buyers are the source
of failed attempts. Only `Payment Failed` and `Failed` statuses qualify;
cancelled, pending, and blank statuses do not.

An attempt is excluded when a Registrant in the same batch has a ticket with
`Payment Validated`, a later source `Created At`, and a matching identity:

- Same normalized name plus matching email or mobile; or
- If a name is absent, both email and mobile must match.

Names and emails are Unicode-normalized, trimmed, and compared without case.
Mobile formatting is removed and Philippine local mobile prefixes are normalized
to `63`. Names alone, blank contacts, and shared contacts with different names
do not establish a match. The table contains only entries classified as
`No later paid registration`. Uncertain matches and incomplete identities are
excluded before search, pagination, and the People listed count.

Both ISO and month-name export timestamps are supported. Offset-free timestamps
are Manila time. Missing or tied creation timestamps do not prove a later
registration. A paid registration before the failed attempt also requires review.
These review cases are counted separately and excluded from the table.
Import upload times are never used to infer registration order.

Repeated failed attempts with the same normalized name, email, and mobile are
grouped. Each row shows the latest failure, outreach status, and latest remark.
Rows without adequate identity remain separate. Counts of recovered attempts and
listed people use different units and are labeled accordingly.

Follow-up history is stored separately from imports, keyed by Event and the
normalized name/contact identity. Re-importing the same identity preserves its
outreach and remarks. Changed contact details may create a different identity.
Writes require an authenticated, approved operator and CSRF validation; outreach
also requires explicit confirmation. Remarks are limited to 4,000 characters.

The module does not compare other Events or inactive imports, infer failure from
missing payment data, or treat a buyer who purchased on someone else's behalf as
that registrant. A fresh complete export is needed to reflect source changes.
