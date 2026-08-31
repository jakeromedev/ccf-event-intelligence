# Registrations Page Header Design

This document defines the header pattern used by the **Registrations** page and how to reuse it on other pages in the B1G Admin Internal System.

The pattern provides two related levels of hierarchy:

1. **Application header** — sticky page identity, event selector, and dataset metadata.
2. **Content-panel header** — the title and context for the primary module below it.

Do not copy the registration summary cards, quick filters, search controls, or table toolbar when adopting this header. Those are module-specific controls rather than part of the header design.

## Visual hierarchy

```text
Deep B1G red sidebar
└── White sticky application header
    ├── Menu toggle
    ├── Event selector
    ├── Page title and short description
    └── Dataset status, import date, and batch number

Warm cream page canvas
└── White content panel
    └── Panel header
        ├── Uppercase breadcrumb
        ├── Primary module title
        └── One-line module description
```

The application header establishes the user's location in the system. The panel header explains the specific workspace or dataset shown beneath it.

## Current implementation sources

- Application shell: `app/templates/base.html`
- Registrations implementation: `app/templates/registrations.html`
- Header and panel styles: `app/static/app.css`
- Legacy/shared page-header macro: `app/templates/_page_header.html`

The Registrations pattern uses the `application_header_page` block directly. It intentionally disables the older `page_header` block to prevent a second hero-style page header from appearing.

## 1. Application header

### Registrations markup

Place this near the top of a template that extends `base.html`:

```jinja
{% block application_header_page %}
<div class="application-header-page">
    <h1><span class="application-header-module">Registrations</span></h1>
    <p>Review operational registration, logistics, attestation, and payment-status information.</p>
</div>
{% endblock %}

{% block page_header %}{% endblock %}
```

For another page, replace only the module name and description:

```jinja
{% block application_header_page %}
<div class="application-header-page">
    <h1><span class="application-header-module">Data Quality</span></h1>
    <p>Review validation findings and resolve issues in the active event dataset.</p>
</div>
{% endblock %}

{% block page_header %}{% endblock %}
```

### Responsibilities of `base.html`

The shared shell already supplies:

- The sticky white header container.
- The sidebar/menu toggle.
- The current event selector.
- Active or empty dataset status.
- Import timestamp and batch number when an active batch exists.
- Responsive truncation and spacing.

Pages should not duplicate these elements in `application_header_page`.

### Copy rules

- Use a short page/module name, preferably one to three words.
- Use one concise sentence for the description.
- Describe the page's task, not implementation details.
- Do not repeat the event name; the event selector already provides it.
- Do not repeat dataset status or batch information; the shell already provides it.

## 2. Content-panel header

Use this header when the page's primary content is contained in a white panel, especially for tables, lists, and operational tools.

### Registrations markup

```jinja
<section class="admin-table-panel registrations-panel">
    <header class="admin-table-heading">
        <div>
            <p class="admin-breadcrumb">Event Operations <span>/</span> Registrations</p>
            <h1>Registrations</h1>
            <p>Event-scoped operational view of imported registration submissions.</p>
        </div>
    </header>

    {# Page-specific content begins here. #}
</section>
```

### Reusable example

```jinja
<section class="admin-table-panel">
    <header class="admin-table-heading">
        <div>
            <p class="admin-breadcrumb">Event Operations <span>/</span> Data Quality</p>
            <h1>Data Quality</h1>
            <p>Validation findings for the selected event and active dataset.</p>
        </div>
    </header>

    {# Data-quality content begins here. #}
</section>
```

### Optional header actions

If a module needs a small set of primary actions, place them as a sibling of the title wrapper. Keep actions task-specific and avoid moving the full table toolbar into the heading.

```jinja
<header class="admin-table-heading">
    <div>
        <p class="admin-breadcrumb">Event Operations <span>/</span> Imports</p>
        <h1>Imports</h1>
        <p>Upload and activate event datasets.</p>
    </div>
    <a class="button primary" href="{{ url_for('dashboard.event_imports', event_id=event['id']) }}">
        New Import
    </a>
</header>
```

Prefer no more than two actions. Search, filters, column controls, and pagination belong in a separate toolbar below the heading.

## Styling contract

The design relies on existing shared classes. Pages adopting the pattern should reuse these classes instead of creating page-specific copies.

| Element | Shared selector | Intended appearance |
|---|---|---|
| Sticky shell header | `.application-header` | White, 74px high, subtle warm border and shadow |
| Page identity wrapper | `.application-header-page` | Compact title/description with a left divider |
| Page title accent | `.application-header-module` | B1G red |
| Dataset metadata | `.application-header-meta` | Muted text with separators |
| Main canvas | `.app-main` | Warm cream `var(--b1g-page-background)` |
| Primary data surface | `.admin-table-panel` | White surface with warm beige border |
| Panel heading | `.admin-table-heading` | Approximately 92px high with balanced spacing |
| Breadcrumb | `.admin-breadcrumb` | Small uppercase muted text |
| Panel title | `.admin-table-heading h1` | Dark, compact, high-emphasis title |
| Panel description | `.admin-table-heading > div > p:last-child` | Muted supporting copy |

Use the centralized B1G tokens:

```css
--b1g-red: #7a0b0b;
--b1g-page-background: #faead2;
--b1g-surface: #ffffff;
--b1g-border: #e6d2b9;
--b1g-text: #2b1a1a;
--b1g-text-muted: #755d5d;
```

Do not add hard-coded white, gray, or red values to a page-specific header unless a new semantic state requires them.

## Responsive behavior

The application shell owns responsive behavior for the sticky header:

- Long titles and descriptions truncate rather than expanding the header vertically.
- Dataset metadata progressively reduces on narrower screens.
- The menu toggle remains available when the sidebar becomes collapsible.
- The event selector remains the source of event context.

For panel headers:

- Allow the title wrapper to shrink with `min-width: 0`.
- Keep descriptions concise so they remain readable on small screens.
- Let optional actions wrap or collapse to icon-only controls where an existing responsive rule supports it.
- Do not introduce fixed widths that cause horizontal page scrolling.

## Accessibility requirements

- Keep the page title as a heading; do not replace it with styled plain text.
- Preserve visible keyboard focus for header actions.
- Use descriptive action labels and `aria-label` when an action becomes icon-only.
- Keep dataset metadata in the shared shell so its existing accessible label remains intact.
- Do not communicate dataset state through color alone; retain status text and the status indicator.
- Maintain dark text on white or cream surfaces and B1G red only where contrast remains sufficient.

## Adoption checklist

- [ ] The template extends `base.html`.
- [ ] `application_header_page` supplies a short module title and description.
- [ ] The old `page_header` block is explicitly empty.
- [ ] Event and dataset metadata are not duplicated.
- [ ] The primary module uses a white surface on the cream page canvas.
- [ ] The panel header uses `admin-table-heading` and `admin-breadcrumb` where applicable.
- [ ] Page-specific controls remain below the header in their own toolbar or section.
- [ ] Heading levels and focus behavior remain accessible.
- [ ] The page is checked at desktop, tablet, and mobile widths.
- [ ] Existing functionality and route behavior remain unchanged.

## Recommended rollout

Adopt the pattern page by page. Start with other data-heavy modules such as Admin Tables and Data Quality, then apply it to Imports, Satellites, Analytics, and Users where the same two-level hierarchy is appropriate.

Pages with a deliberately prominent workspace hero may retain that design until the team explicitly decides to standardize them. Do not show both the legacy hero header and the Registrations-style panel header on the same page without a clear hierarchy need.
