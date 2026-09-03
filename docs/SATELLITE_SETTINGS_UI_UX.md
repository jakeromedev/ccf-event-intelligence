# Satellite Settings UI/UX Specification

- Status: As built
- Last reviewed: 2026-09-03
- Primary page: `/satellites/settings`

## 1. Purpose

Satellite Settings is the administrative workspace for maintaining the shared,
canonical hierarchy used by Satellite reporting and registration
synchronization:

```text
Hub Group
└── Hub
    └── Satellite
```

The page supports:

- browsing the full canonical directory;
- searching and filtering Hubs and Satellites;
- adding one Hub or Satellite;
- bulk-adding Hubs or Satellites with a review step;
- renaming or moving existing Hubs and Satellites; and
- reviewing and confirming Event-scoped registration Satellite synchronization.

It does not support deleting records, merging records, editing Hub Groups, or
creating directory records automatically during synchronization.

## 2. Audience and access

The complete page and every mutation route require the
`satellites.settings.manage` capability.

- Approved administrators have this capability.
- Standard users and Registration operators do not have it.
- Unauthorized requests fail with HTTP `403`.
- Local environments with authentication explicitly disabled bypass the
  capability check.

The **Settings** action is shown on an Event's Satellites page only when the
current user may manage Satellite Settings.

## 3. Entry points and page modes

### 3.1 Event-scoped mode

```text
/satellites/settings?event_id=<event_id>
```

This is the primary entry point from an Event's Satellites page. The page:

- preserves the selected Event across create, edit, bulk, and sync requests;
- links the header breadcrumb back to that Event's Satellites page; and
- displays **Sync Registration Satellites** in the summary area.

### 3.2 Global directory mode

```text
/satellites/settings
```

This mode manages the same canonical directory without Event context. The
header breadcrumb links back to Events, and the registration synchronization
action is intentionally absent.

The directory itself is global in both modes. Event context changes navigation
and enables Event-specific synchronization; it does not create a separate
directory per Event.

## 4. Page anatomy

```text
Application header
└── Satellites / Settings breadcrumb

Summary panel
├── Page identity and description
├── Hub and Satellite totals
└── Sync Registration Satellites (Event mode only)

Directory controls
├── Search Directory
├── Hub Group segmented filter
├── Add Records menu
├── Expand All / Collapse All
└── Live result count

Directory
├── Within Metro Manila Hubs
│   └── Hub table
│       └── View Satellites
└── Outside Metro Manila Hubs
    └── Hub table
        └── View Satellites

Overlays
├── Add/Bulk Add dialog
├── Edit drawer
├── Satellite explorer (Satellite table → Registrant table)
└── Registration Satellite sync dialog
```

## 5. Application header

The page title area contains an accessible `Satellites / Settings` breadcrumb.

- **Satellites** returns to the selected Event's Satellites page when
  `event_id` is present; otherwise it returns to Events.
- **Settings** is marked as the current page.
- Supporting copy reads: “Manage the Hub and Satellite directory used by the
  system.”

## 6. Summary panel

The summary panel contains:

- Eyebrow: `Satellite Administration / Directory Management`
- Heading: `Satellite Settings`
- Description: `Browse, search, add, and maintain the canonical Hub and
  Satellite directory.`

Two metrics are shown:

- **Hubs**: Hubs assigned to a configured Hub Group.
- **Satellites**: canonical Satellites assigned to a configured Hub.

Canonical Satellite rows without a valid Hub are excluded from the displayed
Satellite total and directory.

In Event-scoped mode, the primary **Sync Registration Satellites** button is
shown below the totals. Submitting changes its label to
`Scanning Registration Satellites…` and disables repeated submission.

Event-scoped mode adds **Registrants** and **Need Review** metrics. Need Review
is a link to the Registrants view with the grouped review filter applied.
When review records exist, **View Issues** provides the same shortcut beside
the sync action. Review counts on Hub Groups, Hubs, and Satellites are also
links to the appropriately scoped Registrants view.

## 6.1 Event view switcher

Event-scoped Settings provides two URL-addressable views:

- **Directory** retains the canonical hierarchy and adds Event counts and
  a breadcrumb-driven Satellite and registrant explorer.
- **Registrants** presents a flat, sortable and paginated operational list.

The selected filters remain in the URL when switching views. Global mode does
not render the switcher or any participant records.

## 7. Directory controls

The controls update the rendered directory client-side, except for add/edit
actions.

In Event-scoped mode, these controls are replaced by a server-backed unified
toolbar shared by Directory and Registrants views. It includes Search, Hub
Group, Hub, Satellite, Sync Status, Apply, and Clear All. Hub choices cascade
from Hub Group, and Satellite choices cascade from both Hub Group and Hub.
Active values appear as individually removable chips.

Event search is Unicode-normalized and case-insensitive across group, Hub,
Satellite, participant, source values, registration identifiers, and sync
status. Directory names can still match even if that directory record has no
Event registrants. Filters, sorting, and page number are query parameters, so
views are refresh-safe and shareable.

### 7.1 Search Directory or Registrant

Event mode provides an explicit **Search For** choice:

- **Directory** locates a Hub Group, Hub, or Satellite.
- **Registrant** locates a participant or registration identifier and shows
  the participant's Hub Group, Hub, Satellite, and sync status. **View
  Satellite** opens that Satellite's registrants in the explorer.

Global Directory search:

- has the placeholder `Search hubs or satellites...`;
- matches case-insensitively against Hub Group, Hub, and Satellite names;
- updates on every input event;
- filters Hub table rows by Hub and Satellite name; and
- retains matching Hub Group tables.

### 7.2 Hub Group filter

The segmented radio control provides:

- **All**;
- **Within Metro Manila**; and
- **Outside Metro Manila**.

Search and group filtering are combined, so a record must satisfy the selected
group and active query.

### 7.3 Live results and empty state

An `aria-live="polite"` line announces visible totals:

```text
<n> Hubs · <n> Satellites
```

If a search matches only a Hub Group, the result begins with its visible Hub
Group count.

When no Hub Group remains visible, a no-results panel presents a search icon,
`No matching directory records`, guidance, and **Clear Search**. Clear Search
empties the query, selects **All**, reapplies filters, and focuses the search
field.

### 7.4 Add Records menu

The primary **Add Records** disclosure contains:

- Add Hub;
- Add Satellite;
- Bulk Add Hubs; and
- Bulk Add Satellites.

Choosing an action closes the menu and opens the shared add dialog in the
appropriate mode.

## 8. Directory hierarchy

The page renders configured Hub Groups in configured sort order. The expected
groups are:

1. Within Metro Manila Hubs
2. Outside Metro Manila Hubs

Hubs and Satellites are alphabetized case-insensitively within their parents.

### 8.1 Hub Group panel

Each group shows a `Hub Group` eyebrow, group name, Hub and Satellite totals,
and **Add Hub** preconfigured for that group.

If a group has no Hubs, it displays `No Hubs encoded yet.`, guidance, and an
**Add Hub** action bound to that group.

### 8.2 Hub table

Each Hub Group contains a table. A Hub row shows its Satellite count, Event
registrant/sync/review totals or global source-record total, **View
Satellites**, and **Edit**. No accordion is used.

### 8.3 Satellite explorer

**View Satellites** opens one modal and lists the Hub's Satellites in a table.
Each row shows:

- canonical Satellite name;
- total imported source records linked to that canonical Satellite; and
- **View Registrants** in Event mode; and
- **Edit**.

The imported-record count is aggregated across linked Event Satellite data; it
is not limited to the Event used to enter the page.

An empty Hub displays `No Satellites are assigned to this Hub.` The modal's
**Add Satellite** action is preconfigured for its Hub.

In Event mode, each level also shows filtered Event counts:

- Hub Groups: Registrants and Need Review;
- Hubs: Registrants and Need Review; and
- Satellites: Registrants, Synced, Ready, and Need Review.

Satellites provide **View Registrants**. The same modal transforms into a
registrant table and fetches a 10-row page only for that Satellite;
registration rows are not embedded in the initial directory HTML. A breadcrumb
shows Hub Groups / Hub Group / Hub / Satellites / Satellite / Registrants.
**Satellites** returns to the Satellite table and **Hub Groups** closes the
explorer. Local search is debounced by 300 ms, status filtering is scoped to
the selected Satellite, and Previous/Next remain server-paginated. Loading,
empty, and recoverable failure states are displayed in the modal.

## 8.4 Registrants view

The flat Event view contains Participant, Registration, Hub, Satellite, and
Sync Status columns. Each heading is sortable in both directions. Pagination
uses 25 rows by default; the read endpoint caps requested page size at 100.

Status badges always include text:

- **Already Synced** uses the informational synced treatment;
- **Ready to Sync** uses the ready treatment; and
- Satellite Not Configured, Hub Not Found, Missing Satellite, and Ambiguous
  use the Need Review treatment.

On small screens, the table becomes stacked cards containing the same fields.
A zero-result state offers Clear All Filters.

## 9. Add one Hub or Satellite

Individual creation uses a centered modal dialog.

### 9.1 Add Hub

- **Hub Group**: required select.
- **Hub Name**: required text input, maximum 160 characters.
- Primary action: **Add Hub**.
- Loading label: `Adding Hub…`.

### 9.2 Add Satellite

- **Hub**: required select grouped by Hub Group.
- **Satellite Name**: required text input, maximum 512 characters.
- Primary action: **Add Satellite**.
- Loading label: `Adding Satellite…`.

### 9.3 Context-aware creation

Actions launched from a Hub Group or Hub preselect their parent. The selected
parent is presented as read-only context and removed from the tab order for
that dialog session. Global Add Records actions require the administrator to
select the parent.

### 9.4 Dialog behavior

- Initial focus moves to the parent select.
- Cancel, the close icon, or clicking the backdrop closes the dialog.
- Closing through a handled control returns focus to the trigger.
- Submit sets `aria-busy="true"`, disables submit, and shows a loading label.
- Successful creation redirects to `#hub-<id>` or `#satellite-<id>` and
  displays a success flash.

## 10. Bulk add workflow

Bulk creation is a review-before-save flow in the same add dialog.

### 10.1 Input

The administrator selects a destination Hub Group or Hub and pastes names into
a textarea. The parser accepts new lines, commas, tabs, and spreadsheet rows or
columns copied from Excel or Google Sheets.

Whitespace is trimmed and internal whitespace is collapsed. A live
`<n> entries detected` count updates the primary label to `Review <n> Hubs` or
`Review <n> Satellites`.

Limits:

- 100,000 input characters;
- 1,000 parsed records;
- 160 characters per Hub name; and
- 512 characters per Satellite name.

### 10.2 Review

Review is read-only. The modal reopens with destination, Detected count, New
count, Existing count, and a row-by-row **New** or **Already exists** result.

Duplicates include names already in the destination and repeated normalized
names in the same paste. If every entry exists, the UI states there are no new
records and omits confirmation.

### 10.3 Edit and confirm

**Edit Paste** returns to bulk input, restores parsed values one per line,
keeps the destination, and focuses the textarea.

Confirmation states the exact number and record type to add. Only new names
are inserted. Existing/repeated names are skipped, and the flash message
reports both counts. A server-side recheck protects against changes made after
review; incompatible changes roll back and prompt another review.

## 11. Edit and move workflow

Editing uses a right-side, full-height drawer.

### 11.1 Edit Hub

Fields are Hub Name and Hub Group. Changing Hub Group moves the Hub and all of
its assigned Satellites.

### 11.2 Edit Satellite

Fields are Satellite Name and Hub. Changing Hub preserves imported data and
existing analytical relationships.

### 11.3 Move safeguards

When the parent changes:

- an inline warning names the source and destination;
- submit opens a native confirmation dialog;
- Hub confirmation says all assigned Satellites move with it; and
- Satellite confirmation says imported data and analytical relationships are
  preserved.

Canceling confirmation keeps the drawer open and prevents submission.

### 11.4 Drawer behavior

- The name receives initial focus.
- Cancel, close, or backdrop click closes the drawer.
- Handled close actions return focus to the row's **Edit** button.
- Saving sets `aria-busy="true"`, disables submit, and shows
  `Saving Changes…`.
- Success returns to the edited record's anchor and displays a flash.

## 12. Naming, validation, and duplicate rules

Names use Unicode NFKC normalization, trim leading/trailing whitespace,
collapse internal whitespace, and compare using case-folded text.

- Hub names are required and unique within one Hub Group.
- Satellite names are required and unique within one Hub.
- The same Satellite name may exist under different Hubs.
- The same Hub name may exist under different Hub Groups.
- Missing or invalid parents are rejected.
- Database integrity errors roll back the operation.

Representative feedback:

- `Hub Name is required.`
- `Satellite Name is required.`
- `Select a valid Hub Group.`
- `Select a valid Hub.`
- `That Hub already exists in the selected Hub Group.`
- `That Satellite already exists in the selected Hub.`

## 13. Registration Satellite synchronization

Synchronization appears only in Event-scoped mode and applies only to the
selected Event's active import batch.

### 13.1 Review-first flow

**Sync Registration Satellites** runs read-only analysis and opens a large
modal. The review contains the selected Event, safety explanation, Source
Satellite Records, Represented Registrations, Ready to Sync, Already Synced,
Not Synced, and Registrations to Review.

If there is no active import, the Event block states that no active
registration import is available.

### 13.2 Matching model

The analyzer uses the source Hub and corresponding Hub-specific Satellite
field. It requires one exact canonical path after the same Unicode, whitespace,
and case normalization used by Settings. It does not use fuzzy matching,
automatic aliases, cross-Hub fallback, or automatic directory creation.

### 13.3 Statuses

| Status | Meaning | Confirmation behavior |
| --- | --- | --- |
| Ready to Sync | One exact configured path exists and the imported Satellite has no link | Link it |
| Already Synced | The imported Satellite already has a canonical link, including a different established link | Leave unchanged |
| Satellite Not Configured | Expected Hub exists but its Satellite is absent | Skip and list |
| Hub Not Found | Source Hub has no canonical Hub | Skip and list |
| Missing Satellite | No usable Satellite value or imported evidence exists | Skip and list |
| Ambiguous | More than one valid interpretation exists | Skip and list |

An established canonical link is never replaced by synchronization.

### 13.4 Exception review

Unsynchronized rows show registration identifier, secondary registration code
when different, participant, source Hub, source Satellite, and reason. The
reason select filters rows client-side and updates an `aria-live` result. An
empty filter state and an all-clear state are provided.

### 13.5 Confirmation

**Confirm Sync** appears only when at least one record is ready. Confirmation:

- requires the one-time review token;
- re-runs the complete analysis;
- locks the Event and canonical directory during MySQL confirmation;
- updates only currently null `satellites.directory_id` links;
- commits all eligible links in one transaction; and
- rolls back every update on database failure.

A missing, expired, reused, or mismatched token displays:

`This synchronization review is missing, expired, or was already used. Review
the registrations again.`

### 13.6 Completion report

Post/Redirect/Get returns to Settings and opens a one-time completion modal
with Source Satellite Records, Newly Synchronized, Registrations Synchronized,
Already Synced, Not Synchronized, and Registrations to Review.

If exceptions remain, **View Not Synced Registrations** scrolls to and focuses
the reason filter or table. Refreshing does not replay the report because its
aggregate session payload is consumed once.

## 14. Feedback and loading states

All writes use server-rendered flash feedback after redirect.

Success examples:

- `Hub ‘<name>’ created.`
- `Satellite ‘<name>’ created.`
- `Hub ‘<name>’ updated.`
- `Satellite ‘<name>’ updated.`
- `Created <n> Hubs in <group>. Skipped <n> duplicates.`
- `Created <n> Satellites in <hub>. Skipped <n> duplicates.`

Forms receive `aria-busy="true"`, submit buttons are disabled, and action copy
changes to a contextual loading label during network operations.

## 15. Responsive behavior

### Desktop

- Summary content and actions share a row.
- Directory controls use four columns.
- Sync metrics use six columns.
- Edit uses a right-side drawer up to 520 px wide.

### Up to 1050 px

- Controls reflow to two columns.
- Add and Directory View actions move to a second row.

### Up to 900 px

- Summary content stacks.
- Totals stretch to available width.
- Sync metrics become three columns over two rows.

### Up to 640 px

- Controls become one column.
- Add Records and sync actions become full width.
- Expand/Collapse actions share available width.
- Group headers and Hub metadata reflow.
- Edit drawer becomes full width.
- Add and sync dialogs become full-screen.
- Sync metrics use two columns.
- Exception tables remain horizontally scrollable.
- Sync footer actions stack for touch use.
- Event search remains directly available, while **Filters** opens a
  bottom-sheet dialog containing Hub Group, Hub, Satellite, Sync Status,
  Reset, and Apply Filters. A badge shows the number of active structured
  filters.
- The flat Registrants table becomes readable record cards.
- Drill-down controls stack above their horizontally scrollable table.

## 16. Accessibility behavior

The implementation includes:

- semantic headings and labelled sections;
- breadcrumb navigation with `aria-current="page"`;
- labelled native dialogs;
- native buttons, inputs, selects, radios, and details disclosure;
- `aria-expanded` and `aria-controls` for Hub toggles;
- `aria-expanded` and `aria-controls` for Satellite registrant toggles;
- dynamic toggle labels containing the Hub name;
- `aria-live="polite"` for results, bulk counts, and sync filtering;
- visible keyboard focus treatment;
- initial focus in add, edit, and sync overlays;
- focus return for handled close actions;
- Escape/cancel handling in the sync modal;
- native modal focus containment, initial Hub Group focus, Escape handling,
  backdrop close, and trigger focus return for the mobile filter sheet;
- a keyboard-focusable, scrollable exception-table region; and
- keyboard-focusable, labelled flat and drill-down registrant table regions;
- disabled submit controls with `aria-busy` during requests.

Color reinforces but does not replace text: ready/success is green,
already-synced information is blue, warnings are amber, and unsynchronized
reasons are red.

Active filter chips include explicit accessible removal labels identifying
their Search, Hub Group, Hub, Satellite, or Sync Status dimension.

## 17. Route and interaction contract

| Method | Route | UI purpose |
| --- | --- | --- |
| GET | `/satellites/settings` | Render global or Event-scoped workspace |
| GET | `/satellites/settings/registrants` | Return one Event-scoped, filtered registrant page; optionally scoped to one canonical Satellite |
| POST | `/satellites/settings/hubs` | Create one Hub |
| POST | `/satellites/settings/hubs/<hub_id>` | Rename or move one Hub |
| POST | `/satellites/settings/satellites` | Create one canonical Satellite |
| POST | `/satellites/settings/satellites/<satellite_id>` | Rename or move one Satellite |
| POST | `/satellites/settings/bulk/hubs/review` | Parse and review Hub paste |
| POST | `/satellites/settings/bulk/hubs/confirm` | Create reviewed Hubs |
| POST | `/satellites/settings/bulk/satellites/review` | Parse and review Satellite paste |
| POST | `/satellites/settings/bulk/satellites/confirm` | Create reviewed Satellites |
| POST | `/satellites/settings/sync/review` | Analyze Event registration links |
| POST | `/satellites/settings/sync/confirm` | Revalidate and synchronize links |

Every POST includes CSRF protection. Event-scoped forms carry `event_id` so
the user returns to the same Event context.

## 18. Data-impact boundaries

| Action | Creates | Updates | Never does |
| --- | --- | --- | --- |
| Add Hub | `satellite_hubs` | — | Create or edit a Hub Group |
| Add Satellite | `satellite_directory` | — | Create imported Satellite evidence |
| Edit Hub | — | Hub name and/or Hub Group | Delete child Satellites |
| Edit Satellite | — | Satellite name and/or Hub | Rewrite linked imported evidence |
| Registration sync | — | Eligible null `satellites.directory_id` values | Create, rename, merge, delete, or overwrite established links |

## 19. Deliberate limitations

- Hub Groups are fixed configuration, not editable page content.
- There is no delete or archive action.
- The canonical directory itself is not paginated; Event registrants are.
- Unassigned canonical Satellite rows are not shown.
- Bulk review rows cannot be edited individually; use **Edit Paste**.
- Registration sync is unavailable without Event context.
- Sync does not correct an existing assignment; established links are reported
  as **Already Synced** and preserved.

## 20. Source-of-truth files

- `app/templates/satellite_settings.html` — structure and displayed copy
- `app/static/satellite_settings.js` — filters, dialogs, focus, bulk review,
  move confirmation, and loading behavior
- `app/static/app.css` — layout, visual states, breakpoints, dialogs, and drawer
- `app/routes.py` — actions, redirects, messages, transactions, and sync session
- `app/satellite_settings.py` — hierarchy, normalization, validation, and writes
- `app/satellite_settings_registrants.py` — Event registrant enrichment,
  filters, aggregates, sorting, and pagination
- `app/satellite_sync.py` — matching, statuses, and safe link execution
- `app/auth.py` — capability enforcement
