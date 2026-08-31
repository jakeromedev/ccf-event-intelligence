# Registrations Module UI/UX Enhancement Roadmap

> **Highest Priority:** Table workflow, Attestation Review modal, and group-based column visibility.

## Purpose

This roadmap defines the UI/UX enhancement of the **Registrations module page only**.

The goal is to improve usability, visual hierarchy, filtering, table readability, and the Attestation review workflow while preserving the current Event-scoped registration logic.

---

# Scope Guardrails

## In Scope

Work only on the Registrations module page content, including:

- Registrations page heading and module context
- Event and batch controls inside the module
- Search
- Summary cards
- Attestation quick filters
- Applied-filter chips
- Advanced filter drawer
- Group-based column visibility
- Registration table
- Sorting
- Attestation Form review workflow
- Attestation Status updates
- Payment Status display
- Pagination
- Loading, empty, and error states
- Responsive module behavior
- Accessibility
- Module-specific CSS and JavaScript
- Minimal backend/API adjustments only when required for the approved module workflow

## Explicitly Out of Scope

Do **not** modify:

- Application header
- Global top navigation
- Sidebar
- Sidebar items
- Sidebar collapse behavior
- Global app shell
- Global user/account controls
- Global notification controls
- Global branding
- Unrelated modules

The existing application header and sidebar must remain completely untouched.

---

# Existing Module Contract to Preserve

The Registrations page remains an **Event-scoped operational view of imported `registrants` records**.

Preserve:

- Event scope
- active/specific/all-batch behavior
- server-side search
- server-side filtering
- server-side sorting
- server-side pagination
- summary counts
- Attestation Status updates
- Payment Status matching
- safe Attestation Form URL validation
- server-side authorization

One displayed row continues to represent one imported `registrants` record.

Do not convert this page into a curated/deduplicated registrant view.

Do not expose excluded sensitive fields such as:

- medical details
- allergies
- emergency contacts
- complete residential addresses
- Dgroup leader contacts
- monetary fields

---

# Phase 1 — PRIORITY: Core Table and Attestation Workflow

## Objective

Implement the highest-priority operational changes first.

This phase determines the new table structure and primary Attestation review workflow and must be completed before broader visual enhancements.

## 1. Remove Registration Code and Ticket Code From the Visible Table

Remove these columns from the table UI:

- Registration Code
- Ticket Code

This is a **display-layer change only** unless a separate backend cleanup is explicitly required.

The fields may remain available to existing server-side search/query behavior.

Do not expose sorting controls for these hidden fields.

## 2. New Default Table Column Order

Use this default order:

1. Attestation Form
2. Attestation Status
3. Payment Status
4. First Name
5. Last Name
6. Email Address
7. Mobile Number
8. Gender
9. Birth Month
10. Birth Year
11. Life Stage
12. Satellite
13. Shirt Size
14. Transportation To MMRC
15. Transportation From MMRC
16. Plate Number
17. Last Reviewed By
18. Last Reviewed At

The first three columns are intentionally prioritized for operational review.

## 3. Attestation Form Action Button

The first column must contain a compact action button labeled:

`Attestation Form`

Place an **edit icon on the right side** of the label.

Example visual arrangement:

`Attestation Form   [edit icon]`

The button must:

- clearly look interactive
- have keyboard-focus styling
- have an accessible label
- open the Attestation Review modal
- keep the user on the Registrations page

Do not navigate directly away from the page when clicked.

## 4. Attestation Review Modal

Clicking the Attestation Form button opens a modal.

Suggested title:

`Attestation Review`

The modal should contain:

- registrant name
- Satellite
- current Payment Status
- large Attestation Form preview
- current Attestation Status
- Attestation Status control
- Save/Update action
- Cancel/Close action

Do not overload the modal with unrelated registration information.

## 5. Attestation Image Preview

Use the existing validated Attestation Form URL as the preview source.

For safe `http://` or `https://` URLs:

- attempt to render the image inside the modal
- preserve aspect ratio
- provide a large preview area
- allow scrolling where necessary
- avoid distortion

If the URL cannot be displayed as an image:

- show a clear preview-unavailable state
- optionally provide a safe `Open Original` action
- never activate unsafe or malformed URLs

Unsafe values such as the following must never become active links:

- `javascript:`
- `data:`
- `file:`
- malformed URLs

## 6. Change Attestation Status Inside the Modal

Authorized users must be able to change Attestation Status inside the same modal.

Allowed statuses:

- Pending
- Verified
- Invalid

Use clear semantic treatment:

- Pending — amber
- Verified — green
- Invalid — red

Do not rely on color alone.

The current status must be selected when the modal opens.

## 7. Save Status Update

Continue using the existing route:

`PATCH /events/<event_id>/registrations/<registrant_id>/attestation`

After a successful update:

- update Attestation Status in the row
- update Last Reviewed By
- update Last Reviewed At
- refresh affected summary counts
- refresh affected quick-filter counts
- keep the user on the Registrations page
- close the modal after successful save

If the update fails:

- keep the modal open
- preserve the selected value
- show an error
- do not falsely update the table state

Server authorization remains authoritative.

## 8. Read-Only Behavior

Users without status-update permission may still preview the Attestation Form if their page access allows it.

For these users:

- show the preview
- show current status
- disable or omit editing controls
- do not expose a functional Save action

## 9. Group-Based Column Visibility

Add a `Columns` control that hides/unhides columns by **group**, not individually.

Use exactly these groups:

### Attestation & Payment

- Attestation Form
- Attestation Status
- Payment Status
- Last Reviewed By
- Last Reviewed At

### Registrant Details

- First Name
- Last Name
- Email Address
- Mobile Number
- Gender
- Birth Month
- Birth Year
- Life Stage
- Satellite

### Logistics

- Shirt Size
- Transportation To MMRC
- Transportation From MMRC
- Plate Number

Each group must have one show/hide control.

Examples:

- Hide Logistics → all Logistics columns disappear.
- Show Logistics → all Logistics columns return in their defined order.

Do not require operators to toggle every column one by one.

## 10. Group Ordering

Preserve this group order:

1. Attestation & Payment
2. Registrant Details
3. Logistics

Within Attestation & Payment, always preserve:

1. Attestation Form
2. Attestation Status
3. Payment Status
4. Last Reviewed By
5. Last Reviewed At

Showing/hiding groups must never rearrange columns.

## 11. Group Preference Persistence

Persist group visibility using browser local storage scoped to the Registrations module.

Provide:

`Reset to Default`

Default:

- Attestation & Payment — visible
- Registrant Details — visible
- Logistics — visible

Do not create a new database table solely for this preference.

## 12. Modal UX

Support:

- visible close button
- `Esc` close when safe
- keyboard focus trap
- focus restoration to the originating button
- loading state for image preview
- image-load error state
- save-loading state
- unsaved-change protection where appropriate

## Acceptance Criteria

Phase 1 is complete only when:

- Registration Code is not visible.
- Ticket Code is not visible.
- Attestation Form is column 1.
- Attestation Status is column 2.
- Payment Status is column 3.
- Attestation Form uses a button with an edit icon.
- Clicking it opens the Attestation Review modal.
- Valid image URLs can be previewed.
- Unsafe URLs remain blocked.
- Authorized users can update Attestation Status inside the modal.
- Successful updates refresh row metadata and affected counts.
- Failed updates do not create false UI state.
- Columns can be hidden/unhidden by the three defined groups.
- Group visibility persists locally.
- Header and sidebar remain unchanged.

---

# Phase 2 — Page Controls, Summary Cards, Search, and Filters

## Objective

Improve the page-level operational controls and make the current registration state easy to understand.

## 1. Module Heading

Inside the Registrations content area, provide:

- page title: `Registrations`
- short supporting description
- compact Event context

Suggested description:

> Event-scoped operational view of imported registration submissions.

Keep the heading compact.

## 2. Unified Control Bar

Create one clear toolbar containing:

- selected Event indicator
- Batch selector
- Search
- Filters button
- Columns button
- Reset control

Do not modify the global application header or sidebar.

## 3. Batch Selector

Preserve:

- active
- specific batch
- all batches

Changing batch must:

- retain Event scope
- reload server-side data
- reset page where appropriate
- refresh summary counts
- refresh filter options

## 4. Search

Use a prominent search field.

Placeholder:

`Search registration code, ticket code, name, email, or mobile`

Continue searching server-side across:

- Registration Code
- Ticket Code
- First Name
- Last Name
- Email Address
- Mobile Number

Registration Code and Ticket Code may remain searchable even though they are not displayed.

## 5. Summary Cards

Display:

1. Total Registrations
2. Attestation Pending
3. Attestation Verified
4. Attestation Invalid
5. Payment Validated

Use semantic visual treatment.

Do not invent trend percentages or sparklines unless the backend actually supplies historical comparison data.

Summary cards must use the same scoped and filtered query conditions as the table.

## 6. Attestation Quick Filters

Provide:

- All
- Pending
- Verified
- Invalid

Use a segmented or pill-style control.

Preserve existing behavior:

- All removes Attestation Status filter
- Pending applies pending
- Verified applies verified
- Invalid applies invalid

Quick-filter changes must:

- preserve Event/batch context
- preserve other filters
- reset page to 1
- remain synchronized with advanced filters

## 7. Advanced Filter Drawer

Use a right-side filter drawer/panel.

Include:

- title
- short description
- close action
- filter rows
- Add Filter
- Clear All
- Apply Filters

Supported fields remain:

- Gender
- Satellite
- Shirt Size
- Transportation To MMRC
- Transportation From MMRC
- Attestation Status
- Payment Status

Supported operators remain:

- Equals
- Is Any Of
- Is Empty
- Is Not Empty

For `Is Empty` and `Is Not Empty`, hide/disable the value selector.

For `Is Any Of`, support multi-select values.

Satellite values should be searchable when the option list is large.

## 8. Applied Filter Chips

Show applied filters outside the drawer.

Examples:

- `Gender: Female`
- `Satellite: B1G Cebu`
- `Payment Status: Payment Validated`

Each chip must be removable individually.

Removing a filter must:

- remove only that filter
- preserve other filters
- reset page to 1
- refresh data

## 9. Filter Count and Reset

The Filters button should show the number of active filters.

Example:

`Filters 3`

Inside the drawer:

`Clear All`

clears filters only.

Top-level:

`Reset`

clears:

- search
- filters
- quick filter
- sort
- page

Event context remains.

Batch should return to active-batch behavior unless existing UX explicitly requires otherwise.

## Acceptance Criteria

- Search remains server-side.
- Filter count is accurate.
- Applied chips match server query state.
- Quick filters remain synchronized with Attestation Status.
- Summary counts match the filtered table state.
- Filter validation remains server-side.
- Event and batch scope remain correct.
- No global layout components are modified.

---

# Phase 3 — Table UX, Sorting, Pagination, Responsive Behavior, and Accessibility

## Objective

Make the module comfortable to use with large datasets while preserving the existing server-side architecture.

## 1. Table Visual Design

Use a polished data-table surface with:

- clear table header
- subtle borders
- restrained row hover
- consistent padding
- compact density
- strong alignment
- semantic status badges
- consistent missing-value treatment

Missing values should display:

`—`

## 2. Sticky Table Header

When feasible, keep column headers visible while scrolling vertically inside the module.

Do not modify the global application header.

## 3. Status Badges

### Attestation Status

- Pending — amber
- Verified — green
- Invalid — red

### Payment Status

Display returned payment status as a clean badge.

Missing Payment Status:

`—`

## 4. Reviewer Information

Display:

- Last Reviewed By
- Last Reviewed At

If no verification record exists:

- Attestation Status = Pending
- Last Reviewed By = `—`
- Last Reviewed At = `—`

## 5. Sorting

Expose sorting only for supported **visible** fields:

- First Name
- Last Name
- Shirt Size
- Attestation Status
- Payment Status

Registration Code and Ticket Code are no longer visible and must not show table-header sort controls.

The backend may retain compatibility support if needed.

Preserve deterministic sorting with `registrants.id ASC` as a tie-breaker.

## 6. Pagination

Keep pagination fully server-side.

Provide:

- result range
- total count
- rows per page
- Previous
- page numbers
- Next

Example:

`Showing 1–50 of 12,458`

Rows per page:

- 25
- 50
- 100

Default:

- 50

Search/filter/batch/sort changes should reset to page 1 when appropriate.

## 7. URL State

Continue preserving:

- batch
- search / q
- filters
- sort
- direction
- page
- per_page

Browser back/forward should restore expected state.

## 8. Loading States

Provide:

- initial table skeleton/loading state
- search/filter refresh state
- Attestation image loading state
- status-save loading state

Avoid major layout jumping.

## 9. Empty States

Differentiate:

### No registrations

`No registrations found for this batch.`

### No filtered results

`No registrations match your current search and filters.`

Provide a clear `Clear filters` action.

### No active batch

Show a specific message.

Do not silently fall back to another batch.

## 10. Error States

Provide module-level errors with:

- concise message
- Retry action

Do not expose stack traces.

## 11. Responsive Behavior

### Desktop

Use:

- summary cards in a row
- full toolbar
- wide table
- right-side filter drawer

### Medium Width

Allow:

- wrapped summary cards
- intelligently wrapped controls
- table-only horizontal scrolling

### Smaller Width

Use:

- stacked controls where required
- 2-column or 1-column summary-card layout
- wider filter drawer
- horizontally scrollable table

Do not transform the table into unrelated mobile cards unless separately approved.

## 12. Accessibility

Include:

- visible keyboard focus
- semantic buttons
- accessible labels
- proper table headers
- `aria-sort`
- accessible modal title/close button
- focus trapping in modal
- status text in addition to color
- adequate contrast
- predictable tab order

Keyboard users must be able to operate:

- search
- filters
- grouped column visibility
- sorting
- pagination
- Attestation modal
- Attestation Status update

## 13. Performance

Continue using server-side:

- search
- filtering
- sorting
- pagination

Do not download the complete Event registration dataset into the browser.

Debounce search requests and prevent duplicate submissions/API requests.

## Acceptance Criteria

- Large result sets remain responsive.
- Table remains readable and navigable.
- Horizontal overflow is limited to the table region where possible.
- Sorting is exposed only on supported visible fields.
- Pagination remains server-side.
- Loading, empty, and error states are clear.
- Modal and table interactions are keyboard accessible.
- Responsive behavior does not require changes to the app shell.

---

# Phase 4 — Visual Polish, Testing, and Regression Validation

## Objective

Finish the module visually and validate that the redesign did not break existing behavior, authorization, or performance.

## 1. Module-Specific Visual Polish

Standardize:

- button heights
- input heights
- border radius
- card spacing
- table-cell spacing
- typography
- icon sizing
- status badges
- filter chips
- focus rings
- hover states
- modal spacing
- drawer spacing
- empty-state spacing

Use a polished SaaS-style visual direction:

- clean light background
- restrained cards
- subtle borders/shadows
- blue/indigo primary accent
- green success
- amber pending
- red invalid/error
- muted neutral states

Avoid excessive visual decoration.

## 2. CSS Scope

Prefer Registrations-specific styling.

Example:

`app/static/registrations.css`

Do not introduce broad global CSS changes that alter unrelated pages.

## 3. Primary Implementation Files

The existing authoritative module surfaces remain:

- `app/registrations.py`
- `app/templates/registrations.html`
- `app/static/registrations.js`

Add module-specific assets only where necessary.

Do not refactor global layout templates as part of this work.

## 4. Functional Regression Tests

Verify:

- Event scope
- active batch
- specific batch
- all batches
- no active batch
- search
- filter operators
- multiple filters
- quick filters
- filter removal
- reset
- sorting
- pagination
- rows per page
- URL-state restoration

## 5. Priority Workflow Tests

Verify:

- Registration Code hidden
- Ticket Code hidden
- correct first-three column order
- Attestation Form button
- edit icon placement
- modal open/close
- valid image preview
- preview loading
- preview failure state
- unsafe URL handling
- status selection
- successful PATCH update
- failed PATCH update
- reviewer metadata update
- summary count refresh
- quick-filter count refresh
- read-only permission behavior

## 6. Grouped Column Tests

Verify:

- hide/show Attestation & Payment
- hide/show Registrant Details
- hide/show Logistics
- correct restoration order
- local persistence
- Reset to Default
- no change to filtering/query behavior
- no unauthorized fields exposed

## 7. Security Regression

Confirm:

- unknown filters remain rejected
- unsupported operators remain rejected
- filter-count limit remains enforced
- unsafe Attestation URLs remain blocked
- authorization remains server-side
- imported fields remain read-only
- excluded sensitive data remains excluded

## 8. Performance Regression

Confirm:

- pagination remains server-side
- browser does not download full datasets
- search is debounced
- filter requests do not duplicate unnecessarily
- modal image loading does not block the complete page
- table interaction remains responsive

## 9. Final Visual Regression

Confirm that no changes occurred to:

- application header
- sidebar
- global navigation
- unrelated modules
- global application shell

## Acceptance Criteria

Phase 4 is complete only when:

- all priority workflows are implemented and tested
- automated tests pass
- server-side authorization remains intact
- large datasets remain performant
- responsive behavior is acceptable
- module styling is visually consistent
- no unrelated UI regressions exist
- header and sidebar remain completely untouched

---

# Recommended Implementation Order

Execute exactly in this order:

1. **Phase 1 — PRIORITY: Core Table and Attestation Workflow**
2. **Phase 2 — Page Controls, Summary Cards, Search, and Filters**
3. **Phase 3 — Table UX, Sorting, Pagination, Responsive Behavior, and Accessibility**
4. **Phase 4 — Visual Polish, Testing, and Regression Validation**

Do not start Phase 2 ahead of the priority Phase 1 table workflow.

A phase is complete only when:

- its UI is implemented
- interactions work
- server-side behavior remains correct
- applicable tests pass
- no unrelated module is modified
- header and sidebar remain unchanged

---

# Final Definition of Done

The Registrations module is considered complete when an authorized operator can:

1. use a table without Registration Code and Ticket Code
2. see Attestation Form as column 1
3. see Attestation Status as column 2
4. see Payment Status as column 3
5. open an Attestation Review modal from the Attestation Form button
6. review the submitted form image
7. safely handle invalid/non-renderable URLs
8. update Attestation Status in the same modal when authorized
9. see row metadata and counts update after successful changes
10. hide/unhide columns by the three defined groups
11. retain group visibility preferences
12. search and filter efficiently
13. understand current Event/batch context
14. navigate large datasets using server-side pagination
15. use the module with keyboard navigation
16. recover clearly from loading, empty, preview-error, and request-error states
17. use the module across common desktop and tablet widths

The entire implementation must remain limited to the **Registrations module page**.

The **global application header and sidebar must remain completely untouched**.
