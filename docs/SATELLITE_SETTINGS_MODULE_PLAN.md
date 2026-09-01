# Satellite Settings Module Plan

## Overview

Create a new **Satellite Settings** module accessible from the existing **Satellites page**.

The purpose of this module is to centralize the management of all encoded hubs and satellites and provide a structured way to add, edit, and maintain satellite records.

The hierarchy will be:

```text
Hub Group
└── Hub Name
    └── Satellite
```

There are two fixed Hub Groups:

1. **Outside Metro Manila Hubs**
2. **Within Metro Manila Hubs**

A Hub Group can contain multiple Hub Names.

Each Hub Name can contain multiple Satellites.

---

# Core Navigation

## Satellites Page

Add a **Settings** button on the **upper-left area of the Satellites page**.

Suggested button:

```text
⚙ Settings
```

When clicked, navigate to a dedicated Satellite Settings page.

Suggested route:

```text
/satellites/settings
```

The Settings page must be separate from the main Satellites page.

---

# Satellite Settings Page

The page should allow users to:

- View all currently encoded Hub Groups.
- View all Hub Names under each Hub Group.
- View all Satellites under each Hub Name.
- Add new Hub Names.
- Add new Satellites.
- Edit Hub Names individually.
- Edit Satellites individually.
- Perform bulk encoding/editing.
- Copy and paste values directly from spreadsheet applications such as Google Sheets or Microsoft Excel.

The page should make the hierarchy visually clear.

Example:

```text
Within Metro Manila Hubs

├── Hub: East Metro
│   ├── B1G Antipolo
│   ├── B1G Cainta
│   └── B1G Taytay
│
└── Hub: Central Metro
    ├── B1G Main
    └── B1G Greenhills


Outside Metro Manila Hubs

├── Hub: CALABARZON
│   ├── B1G Batangas
│   ├── B1G Calamba
│   └── B1G Lipa
│
└── Hub: Visayas
    ├── B1G Cebu
    └── B1G Iloilo
```

The names above are examples only.

---

# Encoding Workflow

## Step 1 — Select Hub Group

The user must first choose one of the two fixed classifications:

- **Outside Metro Manila Hubs**
- **Within Metro Manila Hubs**

This classification should not be entered manually as free text.

Use a controlled field such as:

- select field,
- segmented control, or
- radio selection.

---

## Step 2 — Encode Hub Names

After selecting the Hub Group, allow the user to encode one or multiple Hub Names.

Example:

```text
Selected Group:
Outside Metro Manila Hubs

Hub Names:
CALABARZON
Bicol
Visayas
Mindanao
```

Each Hub Name becomes its own record.

A Hub Name must belong to exactly one Hub Group.

---

## Step 3 — Encode Satellites

Under every Hub Name, allow the user to encode multiple Satellites.

Example:

```text
Hub:
CALABARZON

Satellites:
B1G Batangas
B1G Calamba
B1G Lipa
B1G Lucena
```

Each Satellite should be stored as an individual record associated with its Hub Name.

---

# Editing Modes

The Settings module must support two editing modes.

## 1. Individual Editing

Each Hub Name and Satellite should have its own edit action.

Example:

```text
B1G Batangas        [Edit]
B1G Calamba         [Edit]
B1G Lipa            [Edit]
```

Users should be able to edit one record without affecting the other records.

Individual Hub editing should allow:

- changing the Hub Name;
- moving the Hub to the other Hub Group, if necessary.

Individual Satellite editing should allow:

- changing the Satellite Name;
- moving the Satellite to another Hub, if necessary.

Changes should only be persisted after the user explicitly saves them.

---

## 2. Bulk Editing / Bulk Encoding

Provide a **Bulk Edit** or **Bulk Add** action for Hub Names and Satellites.

Bulk entry should use a large text area.

The user must be able to copy values directly from Google Sheets or Excel and paste them into the field.

Example:

```text
B1G Batangas
B1G Calamba
B1G Lipa
B1G Lucena
```

The system should also recognize comma-separated values:

```text
B1G Batangas, B1G Calamba, B1G Lipa, B1G Lucena
```

Recommended accepted delimiters:

- comma
- new line
- spreadsheet row paste
- tab-separated cells

This allows users to paste a spreadsheet column without manually formatting every record.

Before saving:

1. Parse the pasted text.
2. Split the values into individual records.
3. Trim unnecessary spaces.
4. Ignore empty values.
5. Detect duplicates.
6. Show the parsed records to the user for review.
7. Require an explicit **Save** or **Confirm** action.

Example:

```text
Paste values:

B1G Batangas
B1G Calamba, B1G Lipa
B1G Lucena
```

Parsed result:

```text
4 records detected

• B1G Batangas
• B1G Calamba
• B1G Lipa
• B1G Lucena
```

---

# Duplicate Protection

The Settings module should prevent accidental duplicate records.

## Hub Names

A duplicate Hub Name under the same Hub Group should be detected before saving.

## Satellites

A duplicate Satellite under the same Hub should be detected before saving.

The system should show the duplicate records instead of silently creating another copy.

Example:

```text
3 new records
1 duplicate

Duplicate:
B1G Calamba
```

The valid new records may still be saved after user confirmation.

Duplicate matching should:

- trim leading/trailing spaces;
- be case-insensitive for validation purposes.

Example:

```text
B1G Calamba
b1g calamba
 B1G Calamba
```

should be considered the same value for duplicate detection.

The original saved capitalization should remain unchanged unless the user edits it.

---

# Suggested Page Structure

```text
Satellite Settings

[Back to Satellites]

Manage the Hub and Satellite hierarchy used by the system.

--------------------------------------------------

[ + Add Hub ]    [ Bulk Add Hubs ]

Within Metro Manila Hubs
--------------------------------------------------

Hub Name                                    Actions

East Metro                                  [Edit]
    B1G Antipolo                            [Edit]
    B1G Cainta                              [Edit]
    B1G Taytay                              [Edit]

    [+ Add Satellite] [Bulk Add Satellites]

Central Metro                               [Edit]
    B1G Main                                [Edit]
    B1G Greenhills                          [Edit]

    [+ Add Satellite] [Bulk Add Satellites]


Outside Metro Manila Hubs
--------------------------------------------------

CALABARZON                                  [Edit]
    B1G Batangas                            [Edit]
    B1G Calamba                             [Edit]
    B1G Lipa                                [Edit]

    [+ Add Satellite] [Bulk Add Satellites]

--------------------------------------------------
```

The final UI may use cards, collapsible sections, or tables, but the Hub → Satellite relationship must always remain visually obvious.

---

# Data Model Direction

The implementation should maintain explicit relationships instead of storing all information as plain text.

Suggested conceptual structure:

## Hub Groups

```text
hub_groups
- id
- name
```

Initial fixed records:

```text
Within Metro Manila Hubs
Outside Metro Manila Hubs
```

---

## Hubs

```text
hubs
- id
- hub_group_id
- name
- created_at
- updated_at
```

Relationship:

```text
hub_groups
    1
    |
    └── many hubs
```

---

## Satellites

If an existing satellites table already exists, extend or reuse it instead of unnecessarily creating another competing satellite table.

Conceptually, each Satellite should have:

```text
satellites
- id
- hub_id
- satellite_name
- created_at
- updated_at
```

Relationship:

```text
hub
  1
  |
  └── many satellites
```

Before making schema changes, inspect the current database structure and reuse existing tables and relationships wherever practical.

Do not duplicate existing satellite records simply because this Settings page is being introduced.

---

# Implementation Phases

## Phase 1 — Current Structure Review and Settings Foundation

### Goal

Create the Satellite Settings entry point and prepare the data structure without disrupting existing satellite functionality.

### Scope

1. Review the current Satellites page.
2. Review the existing satellite-related database tables and relationships.
3. Determine whether the existing satellite table can be reused.
4. Add the **Settings** button to the upper-left area of the Satellites page.
5. Create the new Satellite Settings route/page.
6. Define the two fixed Hub Groups:
   - Outside Metro Manila Hubs
   - Within Metro Manila Hubs
7. Create or update the necessary database relationship between:
   - Hub Group
   - Hub
   - Satellite
8. Display all currently encoded satellites on the new Settings page.
9. Ensure existing satellite records are preserved during schema changes or migration.

### Completion Criteria

Phase 1 is complete when:

- the Settings button opens the new page;
- both Hub Groups exist;
- the database can represent Hub Group → Hub → Satellite;
- existing satellite data remains intact;
- the Settings page can read and display the current data hierarchy.

---

## Phase 2 — Individual Hub and Satellite Management

### Goal

Allow normal record-by-record management of the hierarchy.

### Scope

Implement:

- Add Hub
- Edit Hub
- Add Satellite
- Edit Satellite

### Hub Creation Flow

```text
Select Hub Group
        ↓
Enter Hub Name
        ↓
Save
```

Allow multiple Hub Names to eventually be encoded, while individual mode handles one Hub at a time.

### Satellite Creation Flow

```text
Select / Open Hub
        ↓
Enter Satellite Name
        ↓
Save
```

### Hub Editing

Allow the user to:

- rename a Hub;
- transfer the Hub between Metro Manila and Outside Metro Manila classifications.

Moving a Hub should preserve the Satellites already assigned to it.

### Satellite Editing

Allow the user to:

- rename a Satellite;
- transfer a Satellite to another Hub.

### Validation

Prevent:

- blank records;
- invalid Hub Group assignment;
- duplicate Hub Names within the same Hub Group;
- duplicate Satellite Names within the same Hub.

### Completion Criteria

Phase 2 is complete when administrators can fully maintain Hub and Satellite records individually without directly modifying the database.

---

## Phase 3 — Bulk Encoding and Spreadsheet Paste

### Goal

Make large-scale Hub and Satellite encoding efficient.

### Scope

Add bulk entry interfaces for:

- Hub Names
- Satellites

Use a multiline text area that supports spreadsheet copy/paste.

### Supported Input

Example 1 — New lines:

```text
B1G Batangas
B1G Calamba
B1G Lipa
```

Example 2 — Commas:

```text
B1G Batangas, B1G Calamba, B1G Lipa
```

Example 3 — Copied spreadsheet cells:

```text
B1G Batangas    B1G Calamba    B1G Lipa
```

The parser should support:

```text
comma
newline
tab
```

as record separators.

### Bulk Hub Flow

```text
Select Hub Group
        ↓
Open Bulk Add Hubs
        ↓
Paste / Type Hub Names
        ↓
Parse Records
        ↓
Review Records
        ↓
Duplicate Validation
        ↓
Confirm
        ↓
Create Individual Hub Records
```

### Bulk Satellite Flow

```text
Select Hub
        ↓
Open Bulk Add Satellites
        ↓
Paste / Type Satellite Names
        ↓
Parse Records
        ↓
Review Records
        ↓
Duplicate Validation
        ↓
Confirm
        ↓
Create Individual Satellite Records
```

Bulk operations must never store the entire pasted text as one database record.

Each detected Hub or Satellite must become an individual record.

### Completion Criteria

Phase 3 is complete when users can copy a list directly from Sheets/Excel, paste it into the system, review the parsed values, and create multiple individual records in a single operation.

---

## Phase 4 — Management UX, Safety, and Final Integration

### Goal

Polish the Settings module and make large datasets practical to maintain.

### Scope

Add:

- search;
- filtering by Hub Group;
- collapsible Hub sections;
- record counts;
- clear validation messages;
- success/error notifications;
- confirmation dialogs for sensitive changes;
- bulk-edit safeguards;
- empty states;
- loading states.

Suggested counts:

```text
Within Metro Manila Hubs
8 Hubs • 42 Satellites

Outside Metro Manila Hubs
15 Hubs • 76 Satellites
```

Each Hub may also display:

```text
CALABARZON
4 Satellites
```

### Bulk Review Safety

Before saving bulk changes, display:

- total detected;
- valid new records;
- duplicates;
- invalid or empty records.

Example:

```text
12 entries detected

9 New
2 Existing
1 Invalid
```

The user should clearly understand what the system will save before confirming.

### Integration Checks

Verify that edits made in Satellite Settings are reflected anywhere else that consumes Satellite data.

The Settings module should become the administrative source for maintaining Hub and Satellite names.

Do not create parallel values that cause the Satellites page and Settings page to use different sources of truth.

### Completion Criteria

Phase 4 is complete when:

- the module is usable with a large number of Hubs and Satellites;
- bulk operations are safe and reviewable;
- duplicate data is controlled;
- changes propagate correctly to the rest of the system;
- existing satellite-related functionality continues to work.

---

# Final Expected User Flow

```text
Satellites Page
       ↓
Click Settings
       ↓
Satellite Settings
       ↓
Choose:
Within Metro Manila Hubs
OR
Outside Metro Manila Hubs
       ↓
Create / Select Hub
       ↓
Create Satellites
       ↓
Individual Edit
OR
Bulk Edit / Spreadsheet Paste
       ↓
Review
       ↓
Save
```

---

# Scope Boundary

For this implementation, focus only on:

- Satellite Settings navigation;
- Hub Group management structure;
- Hub Names;
- Satellite Names;
- individual encoding/editing;
- bulk encoding/editing;
- spreadsheet-friendly paste;
- validation and duplicate protection.

Do not add unrelated satellite analytics, targets, registration counts, participant allocation, or dashboard features as part of this module unless they are required to preserve an existing dependency.

---

# Phase Summary

| Phase | Focus |
|---|---|
| **Phase 1** | Current structure review, Settings page, and data hierarchy |
| **Phase 2** | Individual Hub and Satellite management |
| **Phase 3** | Bulk encoding and spreadsheet copy/paste |
| **Phase 4** | UX refinement, safeguards, and system integration |
