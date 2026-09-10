# Attestation resubmissions

In an Event's Imports page, upload the AF resubmission export under
**Resubmitted Attestation Forms**. Only the single CSV is needed. This does not
replace the active registration batch. The upload requires both Event import
permission and attestation review permission, and uses the normal CSRF protection.

The CSV must include `Reupload Your Accomplished Attestation Form Here` and
contact or registration columns. UTF-8 CSV exports with a BOM are supported,
up to 8 MB and 5,000 rows.

Matches are confined to participants in the current Event's active batch.
Unique email or mobile matches are used, with Philippine mobile prefixes
normalized. Original registration identifiers are considered only when the CSV
Event Slug matches the original export's slug: a separate resubmission form has
its own generated IDs. Conflicting identifiers, shared contacts, and unmatched
rows are skipped and reported. Names alone never assign documents.

A new, safe HTTP(S) form link sets the participant's status to **Re-verify**.
This status can only be assigned by the importer, not by a manual status update.
Registration displays the replacement form and offers a Re-verify quick filter.
Reviewers can then mark it Verified or Invalid through the existing review flow.
The review window loads the current re-upload by default. **Form history** lists
distinct original forms and accepted re-uploads with import dates. Selecting any
entry loads it in the same preview. Previous versions are read-only: select the
Current form to change its status. Saving also checks that the current URL has
not changed while the reviewer was looking at the form.

Repeated links, previously accepted links, and unchanged original links do not
reset statuses. Verified participants are protected even when the upload contains
a different URL: neither their status nor the verified document changes.
Multiple different links for one participant in a single file are skipped for
manual correction of the CSV. Blank links never clear an existing document.

Accepted links and import reports are stored against the durable Event participant
identity. Replacement registration imports preserve these links and statuses.
The original registration source JSON and existing remarks remain untouched.

Migration `b9f2d5a7c310` adds the new status, current replacement URL, import audit
reports, and accepted-link history. Apply it before running the updated app.
