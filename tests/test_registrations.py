import csv
import io
import json
import logging
import os
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.db import get_db, get_engine
from app.importer import process_batch, store_validation, validate_batch
from app.models import Base, User
from app.observability import JsonLogFormatter
from app.url_safety import safe_external_url


CSRF_PATTERN = re.compile(rb'name="csrf_token"[^>]*value="([^"]+)"')
TICKET_FIELDS = [
    "Id", "Slug", "Event Name", "Ticket Code", "Control Number", "Ticket Status",
    "Payment Status", "Buyer Reference Number", "Check-in Date Time",
]
BUYER_FIELDS = [
    "Id", "Slug", "Event Name", "Buyer Reference Number", "Payment Status",
    "Quantity", "Gross Amount", "Amount Paid",
]
REGISTRANT_FIELDS = [
    "ID", "Event Name", "Event Slug", "Registration Code", "Ticket Code",
    "Ticket Status", "Ticket Name", "First Name", "Last Name", "Email Address",
    "Mobile Number", "Gender", "Birth Month", "Birth Year", "Life Stage",
    "Are You Attending Ccf", "Are You From A Local Or International Satellite",
    "Which Local Satellite", "Which International Satellite", "Shirt Size",
    "Transportation From Ccf To Mmrc", "Transportation From Mmrc To Ccf",
    "Plate No", "Upload Your Accomplished Attestation Form Here",
]


def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys = ON")


def create_test_schema(app, reset=False):
    with app.app_context():
        engine = get_engine()
        if engine.dialect.name == "sqlite":
            sqlalchemy_event.listen(engine, "connect", enable_sqlite_foreign_keys)
        if reset:
            Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class SafeExternalUrlTests(unittest.TestCase):
    def test_only_complete_http_and_https_urls_are_allowed(self):
        self.assertEqual(
            "https://files.example.com/form.pdf",
            safe_external_url(" https://files.example.com/form.pdf "),
        )
        self.assertEqual(
            "http://files.example.com/form.pdf",
            safe_external_url("http://files.example.com/form.pdf"),
        )
        for value in (
            None,
            "",
            "javascript:alert(1)",
            "data:text/html,test",
            "file:///tmp/form.pdf",
            "not a url",
            "https://",
            "https://files.example.com/\nunsafe",
        ):
            with self.subTest(value=value):
                self.assertIsNone(safe_external_url(value))


class RegistrationsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        mysql_test_url = os.environ.get("MYSQL_TEST_DATABASE_URL")
        if mysql_test_url and "test" not in (
            make_url(mysql_test_url).database or ""
        ).casefold():
            self.fail("MYSQL_TEST_DATABASE_URL must name a dedicated test database.")
        self.database_url = mysql_test_url or "sqlite+pysqlite:///{}".format(
            root / "registrations.sqlite3"
        )
        self.paths = {
            "tickets": root / "tickets.csv",
            "buyers": root / "buyers.csv",
            "registrants": root / "registrants.csv",
        }
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "registrations-test-secret",
                "DATABASE_URL": self.database_url,
                "STAGING_DIR": str(root / "staging"),
                "AUTHENTICATION_DISABLED": True,
                "WTF_CSRF_ENABLED": False,
            }
        )
        create_test_schema(self.app, reset=bool(mysql_test_url))
        self._write_fixture(30)
        with self.app.app_context():
            self.event_a = get_db().execute(
                "INSERT INTO events (name) VALUES ('Registration Event A')"
            ).lastrowid
            self.event_b = get_db().execute(
                "INSERT INTO events (name) VALUES ('Registration Event B')"
            ).lastrowid
            get_db().commit()

    def tearDown(self):
        self.temp.cleanup()

    def _write_fixture(self, count, prefix=""):
        write_csv(
            self.paths["buyers"],
            BUYER_FIELDS,
            [
                {
                    "Id": "1",
                    "Slug": "registration-event",
                    "Event Name": "Registration Event",
                    "Buyer Reference Number": "B-1",
                    "Payment Status": "Payment Validated",
                    "Quantity": str(count),
                    "Gross Amount": "100",
                    "Amount Paid": "100",
                }
            ],
        )
        tickets = []
        registrants = []
        attestation_values = {
            1: "https://files.example.com/form-1.pdf",
            2: "http://files.example.com/form-2.pdf",
            3: "javascript:alert(1)",
            4: "data:text/html,unsafe",
            5: "file:///tmp/form.pdf",
            6: "not a url",
        }
        for number in range(1, count + 1):
            identifier = "{}{:03d}".format(prefix, number)
            ticket_code = "T-{}".format(identifier)
            payment_status = "Payment Validated" if number % 2 else "Payment Failed"
            first_name = "Jane" if number == 1 else "John" if number == 2 else "Name{:03d}".format(number)
            last_name = "Alpha" if number == 1 else "Beta" if number == 2 else "Person{:03d}".format(number)
            gender = "Female" if number % 2 else "Male"
            satellite = "Eastwood" if number % 2 else "CCF Main"
            shirt_size = "S" if number % 3 == 1 else "M" if number % 3 == 2 else "L"
            transportation_to = "Bus" if number % 2 else "Private Vehicle"
            transportation_from = "Van" if number % 2 else "Private Vehicle"
            tickets.append(
                {
                    "Id": identifier,
                    "Slug": "registration-event",
                    "Event Name": "Registration Event",
                    "Ticket Code": ticket_code,
                    "Control Number": "C-{}".format(identifier),
                    "Ticket Status": "Assigned",
                    "Payment Status": payment_status,
                    "Buyer Reference Number": "B-1",
                    "Check-in Date Time": "",
                }
            )
            registrants.append(
                {
                    "ID": identifier,
                    "Event Name": "Registration Event",
                    "Event Slug": "registration-event",
                    "Registration Code": "R-{}".format(identifier),
                    "Ticket Code": ticket_code,
                    "Ticket Status": "Assigned",
                    "Ticket Name": "Participant",
                    "First Name": first_name,
                    "Last Name": last_name,
                    "Email Address": "person{}@example.com".format(identifier),
                    "Mobile Number": "0917{}".format(identifier),
                    "Gender": gender,
                    "Birth Month": "January",
                    "Birth Year": str(1980 + number),
                    "Life Stage": "Single",
                    "Are You Attending Ccf": "Yes",
                    "Are You From A Local Or International Satellite": "Local Satellite",
                    "Which Local Satellite": satellite,
                    "Which International Satellite": "",
                    "Shirt Size": shirt_size,
                    "Transportation From Ccf To Mmrc": transportation_to,
                    "Transportation From Mmrc To Ccf": transportation_from,
                    "Plate No": "PLATE-{}".format(identifier),
                    "Upload Your Accomplished Attestation Form Here": attestation_values.get(number, ""),
                }
            )
        write_csv(self.paths["tickets"], TICKET_FIELDS, tickets)
        write_csv(self.paths["registrants"], REGISTRANT_FIELDS, registrants)

    def _process(self, event_id):
        staged = {key: (str(path), path.name) for key, path in self.paths.items()}
        validation = validate_batch(staged)
        self.assertTrue(validation.valid)
        with self.app.app_context():
            batch_id = store_validation(get_db(), validation, event_id)
            process_batch(get_db(), batch_id)
        return batch_id

    def _data(self, event_id=None, **parameters):
        response = self.app.test_client().get(
            "/events/{}/registrations/data".format(event_id or self.event_a),
            query_string=parameters,
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        return response.get_json()

    def test_page_and_composed_registration_rows(self):
        batch_id = self._process(self.event_a)
        client = self.app.test_client()
        page = client.get("/events/{}/registrations".format(self.event_a))
        self.assertEqual(200, page.status_code)
        self.assertIn(b">Registrations</span>", page.data)
        self.assertIn(b"Event-scoped operational view of imported registration submissions.", page.data)
        self.assertIn(b'class="application-header-page"', page.data)
        self.assertNotIn(b"overview-header admin-tables-header", page.data)
        self.assertIn(b"registrations.js", page.data)
        self.assertIn(b'data-attestation-quick="all"', page.data)
        self.assertIn(b'data-attestation-quick="pending"', page.data)
        self.assertIn(b'data-attestation-quick="verified"', page.data)
        self.assertIn(b'data-attestation-quick="invalid"', page.data)
        self.assertIn(b'data-attestation-modal', page.data)
        self.assertIn(b'aria-labelledby="attestation-review-title"', page.data)
        self.assertIn(b'data-attestation-zoom-out', page.data)
        self.assertIn(b'data-attestation-zoom-in', page.data)
        self.assertIn(b'data-attestation-fit', page.data)
        self.assertIn(b'data-attestation-actual-size', page.data)
        self.assertIn(b'data-attestation-canvas', page.data)
        self.assertIn(b'Loading form', page.data)
        self.assertIn(b'data-columns-toggle', page.data)
        self.assertIn(b'class="admin-table-toolbar registrations-control-bar"', page.data)
        self.assertIn(b'aria-label="Selected Event"', page.data)
        self.assertIn(
            b'placeholder="Search registration code, ticket code, name, email, or mobile"',
            page.data,
        )
        self.assertIn(b'data-reset-view', page.data)
        self.assertIn(b'data-filter-drawer', page.data)
        self.assertIn(b"Advanced Filters", page.data)
        self.assertIn(b'data-clear-filter-draft', page.data)
        self.assertIn(b'data-apply-filters', page.data)
        self.assertIn(b'Attestation &amp; Payment', page.data)
        self.assertIn(b'Reset to Default', page.data)
        self.assertNotIn(b'data-attestation-save', page.data)

        payload = self._data(per_page=25)
        self.assertEqual(batch_id, payload["batch"])
        self.assertEqual(30, payload["pagination"]["total"])
        labels = [column["label"] for column in payload["columns"]]
        self.assertEqual(
            [
                "Attestation Form", "Attestation Status", "Payment Status",
                "First Name", "Last Name", "Email Address", "Mobile Number",
                "Gender", "Birth Month", "Birth Year", "Life Stage", "Satellite", "Shirt Size",
                "Transportation To MMRC", "Transportation From MMRC",
                "Plate Number", "Last Reviewed By", "Last Reviewed At",
            ],
            labels,
        )
        self.assertNotIn("Registration Code", labels)
        self.assertNotIn("Ticket Code", labels)
        self.assertEqual(
            ["Attestation & Payment", "Attestation & Payment", "Attestation & Payment"],
            [column["group"] for column in payload["columns"][:3]],
        )
        row = next(item for item in payload["rows"] if item["registration_code"] == "R-001")
        self.assertEqual("T-001", row["ticket_code"])
        self.assertEqual("Jane", row["first_name"])
        self.assertEqual("Alpha", row["last_name"])
        self.assertEqual("person001@example.com", row["email_address"])
        self.assertEqual("0917001", row["mobile_number"])
        self.assertEqual("Female", row["gender"])
        self.assertEqual("January", row["birth_month"])
        self.assertEqual("1981", row["birth_year"])
        self.assertEqual("Single", row["life_stage"])
        self.assertEqual("Eastwood", row["satellite"])
        self.assertEqual("S", row["shirt_size"])
        self.assertEqual("Bus", row["transportation_to_mmrc"])
        self.assertEqual("Van", row["transportation_from_mmrc"])
        self.assertEqual("PLATE-001", row["plate_number"])
        self.assertEqual("https://files.example.com/form-1.pdf", row["attestation_form"])
        self.assertEqual("pending", row["attestation_status"])
        self.assertIsNone(row["last_reviewed_by"])
        self.assertIsNone(row["last_reviewed_at"])
        self.assertEqual("Payment Validated", row["payment_status"])
        self.assertEqual(
            ["pending", "verified", "invalid"],
            [item["value"] for item in payload["column_options"]["attestation_status"]],
        )
        self.assertEqual(
            {
                "total_registrations": 30,
                "attestation_pending": 30,
                "attestation_verified": 0,
                "attestation_invalid": 0,
                "payment_validated": 15,
            },
            payload["summary"],
        )
        self.assertEqual(
            {
                "total_registrations": 30,
                "attestation_pending": 30,
                "attestation_verified": 0,
                "attestation_invalid": 0,
            },
            payload["quick_filter_counts"],
        )

    def test_attestation_values_are_sanitized_and_ui_contract_is_safe(self):
        self._process(self.event_a)
        payload = self._data(per_page=25)
        by_code = {row["registration_code"]: row for row in payload["rows"]}
        self.assertEqual(
            "https://files.example.com/form-1.pdf", by_code["R-001"]["attestation_form"]
        )
        self.assertEqual(
            "http://files.example.com/form-2.pdf", by_code["R-002"]["attestation_form"]
        )
        for number in range(3, 7):
            self.assertIsNone(by_code["R-{:03d}".format(number)]["attestation_form"])

        script = (Path(__file__).parents[1] / "app/static/registrations.js").read_text()
        self.assertIn('["http:", "https:"]', script)
        self.assertIn('label.textContent = "Attestation Form"', script)
        self.assertIn('button.setAttribute("aria-haspopup", "dialog")', script)
        self.assertIn('openOriginal.href = url', script)
        self.assertIn('previewImage.src = url', script)
        self.assertIn('previewImage.onerror', script)
        self.assertIn('method: "PATCH"', script)
        self.assertIn('"X-CSRFToken": root.dataset.csrfToken', script)
        self.assertIn('const allowedStatuses = ["pending", "verified", "invalid"]', script)
        self.assertIn('filters.filter((item) => item.field !== "attestation_status")', script)
        self.assertIn("window.localStorage.setItem", script)
        self.assertIn("hasUnsavedModalChange", script)
        self.assertIn('event.key === "Escape"', script)
        self.assertNotIn("innerHTML", script)

        registration_routes = {
            rule.rule for rule in self.app.url_map.iter_rules()
            if "/registrations" in rule.rule
        }
        self.assertFalse(any("export" in route or "download" in route for route in registration_routes))

        self.assertEqual(
            403,
            self.app.test_client().patch(
                "/events/{}/registrations/{}/attestation".format(
                    self.event_a, payload["rows"][0]["id"]
                ),
                json={"status": "verified"},
            ).status_code,
        )

    def test_attestation_document_viewer_interaction_contract(self):
        self._process(self.event_a)
        page = self.app.test_client().get(
            "/events/{}/registrations".format(self.event_a)
        ).get_data(as_text=True)
        root = Path(__file__).parents[1]
        script = (root / "app/static/registrations.js").read_text()
        styles = (root / "app/static/app.css").read_text()

        open_flow = script[
            script.index("const openAttestationModal"):
            script.index("const saveAttestationStatus")
        ]
        self.assertLess(
            open_flow.index("modal.hidden = false"),
            open_flow.index("loadPreview(row.attestation_form, session)"),
        )
        self.assertIn("const session = preparePreview(name)", open_flow)
        self.assertIn("window.requestAnimationFrame", open_flow)

        self.assertIn('aria-busy="true"', page)
        self.assertIn('role="status" aria-live="polite"', page)
        self.assertIn('aria-label="Zoom out"', page)
        self.assertIn('aria-label="Zoom in"', page)
        self.assertIn('aria-label="Fit document to view"', page)
        self.assertIn('aria-label="Show document at 100 percent"', page)
        self.assertIn('target="_blank" rel="noopener noreferrer"', page)
        self.assertNotIn("<iframe", page)

        self.assertIn("previewImage.onload", script)
        self.assertIn("fitDocumentToView(true)", script)
        self.assertIn("const minimumZoom = 0.25", script)
        self.assertIn("const maximumZoom = 3", script)
        self.assertIn("const zoomStep = 0.25", script)
        self.assertIn("Math.min(Math.max(scale, minimumZoom), maximumZoom)", script)
        self.assertIn('previewImage.style.width = `${renderedWidth}px`', script)
        self.assertIn('previewImage.style.height = "auto"', script)
        self.assertNotIn("transform: scale", script)
        self.assertIn('actualSizeButton.addEventListener("click", () => setManualZoom(1))', script)
        self.assertIn('zoomOutButton.addEventListener("click", () => changeZoom(-1))', script)
        self.assertIn('zoomInButton.addEventListener("click", () => changeZoom(1))', script)
        self.assertIn('fitButton.addEventListener("click", () => fitDocumentToView(true))', script)

        self.assertIn("previewImage.onerror = () => showPreviewFailure(session)", script)
        self.assertIn("window.setTimeout(() => showPreviewFailure(session), 15000)", script)
        self.assertIn("session !== previewSession", script)
        self.assertIn("previewSession += 1", script)
        self.assertIn('previewImage.removeAttribute("src")', script)
        self.assertIn("previewViewer.scrollLeft = 0", script)
        self.assertIn("previewViewer.scrollTop = 0", script)
        self.assertIn('openOriginal.href = url', script)
        self.assertIn('return ["http:", "https:"].includes(parsed.protocol)', script)

        self.assertIn(".attestation-preview { position: relative;", styles)
        self.assertIn("overflow: auto", styles)
        self.assertIn("max-width: 100%", styles)
        self.assertIn(".attestation-document-canvas { position: relative", styles)
        self.assertIn(".attestation-status-panel", styles)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 285px", styles)
        self.assertIn("height: min(820px, 92vh)", styles)

    def test_search_uses_codes_names_email_and_mobile(self):
        self._process(self.event_a)
        for query, expected in (
            ("R-001", "R-001"),
            ("T-002", "R-002"),
            ("Jane", "R-001"),
            ("Beta", "R-002"),
            ("person001@example.com", "R-001"),
            ("0917002", "R-002"),
        ):
            with self.subTest(query=query):
                payload = self._data(search=query, per_page=25)
                self.assertEqual(1, payload["pagination"]["total"])
                self.assertEqual(expected, payload["rows"][0]["registration_code"])

    def test_phase2_filter_drawer_and_reset_interaction_contract(self):
        self._process(self.event_a)
        page = self.app.test_client().get(
            "/events/{}/registrations".format(self.event_a)
        ).get_data(as_text=True)
        root = Path(__file__).parents[1]
        script = (root / "app/static/registrations.js").read_text()
        styles = (root / "app/static/app.css").read_text()

        self.assertIn('aria-haspopup="dialog"', page)
        self.assertIn('role="dialog" aria-modal="true"', page)
        self.assertIn("Selected filters", page)
        self.assertIn("No filters selected yet.", page)
        self.assertIn("Clear All", page)
        self.assertIn("Apply Filters", page)

        self.assertIn("let draftFilters = []", script)
        self.assertIn("draftFilters = cloneFilters(filters)", script)
        self.assertIn("filters = cloneFilters(draftFilters)", script)
        self.assertIn("setFilterDrawerOpen(false)", script)
        self.assertIn('optionSearch.placeholder = "Search Satellite options"', script)
        self.assertIn('filterField.value === "satellite"', script)
        self.assertIn('batchSelect.value = "active"', script)
        self.assertIn('pageSize.value = "50"', script)
        self.assertIn('search.value = ""', script)
        self.assertIn('sort = defaultSort', script)
        self.assertIn('event.key === "Escape"', script)

        self.assertIn(".registrations-filter-drawer { position: fixed", styles)
        self.assertIn("grid-template-columns: 1fr minmax(390px, 32vw)", styles)
        self.assertIn("body.registrations-filter-open { overflow: hidden; }", styles)
        self.assertIn(".registrations-control-bar", styles)

    def test_phase3_table_ux_accessibility_and_state_contract(self):
        self._process(self.event_a)
        page = self.app.test_client().get(
            "/events/{}/registrations".format(self.event_a)
        ).get_data(as_text=True)
        root = Path(__file__).parents[1]
        script = (root / "app/static/registrations.js").read_text()
        styles = (root / "app/static/app.css").read_text()

        self.assertIn('data-has-active-batch="true"', page)
        self.assertIn('data-table-state role="status" aria-live="polite"', page)
        self.assertIn("registrations-table-skeleton", page)
        self.assertIn("Loading registrations", page)
        self.assertIn("data-table-clear", page)
        self.assertIn("data-table-retry", page)
        self.assertIn('aria-label="Scrollable registration table"', page)
        self.assertIn('aria-busy="true" tabindex="0"', page)
        self.assertIn("<caption class=\"sr-only\">", page)
        self.assertIn('aria-live="polite"', page)

        self.assertIn('th.scope = "col"', script)
        self.assertIn('th.setAttribute("aria-sort"', script)
        self.assertIn('button.setAttribute("aria-current", "page")', script)
        self.assertIn("No registrations match your current search and filters.", script)
        self.assertIn("No active batch is available for this Event.", script)
        self.assertIn("No registrations found for this batch.", script)
        self.assertIn("Registrations could not be loaded.", script)
        self.assertIn('stateRetry.addEventListener("click"', script)
        self.assertIn("if (requestController !== controller) return", script)
        self.assertIn('updateUrl("push")', script)
        self.assertIn('mode === "push" ? "pushState" : "replaceState"', script)
        self.assertIn('window.addEventListener("popstate"', script)

        self.assertIn(".admin-data-table th { position: sticky", styles)
        self.assertIn(".admin-table-scroll { position: relative; max-width: 100%;", styles)
        self.assertIn("overflow: auto", styles)
        self.assertIn(".registrations-table-skeleton", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertIn('.registrations-data-table th[aria-sort="ascending"]', styles)

        payload = self._data(per_page=25)
        sortable = [column["key"] for column in payload["columns"] if column["sortable"]]
        self.assertEqual(
            ["attestation_status", "payment_status", "first_name", "last_name", "shirt_size"],
            sortable,
        )

    def test_phase3_no_active_batch_contract(self):
        page = self.app.test_client().get(
            "/events/{}/registrations".format(self.event_a)
        )
        self.assertEqual(200, page.status_code)
        self.assertIn(b'data-has-active-batch="false"', page.data)

        payload = self._data()
        self.assertIsNone(payload["batch"])
        self.assertEqual(0, payload["pagination"]["total"])
        self.assertEqual([], payload["rows"])

    def test_filters_are_allow_listed_and_composable(self):
        self._process(self.event_a)
        cases = (
            ("payment_status", "Payment Validated"),
            ("shirt_size", "S"),
            ("gender", "Female"),
            ("satellite", "Eastwood"),
            ("transportation_to_mmrc", "Bus"),
            ("transportation_from_mmrc", "Van"),
            ("attestation_status", "pending"),
        )
        for field, value in cases:
            with self.subTest(field=field):
                filters = json.dumps([{"field": field, "operator": "equals", "value": value}])
                payload = self._data(filters=filters, per_page=25)
                self.assertGreater(payload["pagination"]["total"], 0)
                self.assertTrue(all(row[field] == value for row in payload["rows"]))

        combined = json.dumps(
            [
                {"field": "gender", "operator": "equals", "value": "Female"},
                {"field": "satellite", "operator": "equals", "value": "Eastwood"},
                {"field": "payment_status", "operator": "equals", "value": "Payment Validated"},
                {"field": "shirt_size", "operator": "equals", "value": "S"},
            ]
        )
        payload = self._data(filters=combined, per_page=25)
        self.assertGreater(payload["pagination"]["total"], 0)
        self.assertTrue(
            all(
                row["gender"] == "Female"
                and row["satellite"] == "Eastwood"
                and row["payment_status"] == "Payment Validated"
                and row["shirt_size"] == "S"
                for row in payload["rows"]
            )
        )

        rejected = self.app.test_client().get(
            "/events/{}/registrations/data".format(self.event_a),
            query_string={
                "filters": json.dumps(
                    [{"field": "email_address", "operator": "contains", "value": "example"}]
                )
            },
        )
        self.assertEqual(400, rejected.status_code)

    def test_phase4_filter_operators_and_filter_limit(self):
        batch_id = self._process(self.event_a)
        any_gender = self._data(
            filters=json.dumps(
                [{"field": "gender", "operator": "in", "value": ["Female", "Male"]}]
            ),
            per_page=50,
        )
        self.assertEqual(30, any_gender["pagination"]["total"])

        with self.app.app_context():
            get_db().execute(
                "DELETE FROM tickets WHERE batch_id = ? AND ticket_code = 'T-001'",
                (batch_id,),
            )
            get_db().commit()
        empty_payment = self._data(
            filters=json.dumps(
                [{"field": "payment_status", "operator": "is_empty", "value": ""}]
            )
        )
        populated_payment = self._data(
            filters=json.dumps(
                [{"field": "payment_status", "operator": "is_not_empty", "value": ""}]
            )
        )
        self.assertEqual(1, empty_payment["pagination"]["total"])
        self.assertEqual(29, populated_payment["pagination"]["total"])

        too_many = self.app.test_client().get(
            "/events/{}/registrations/data".format(self.event_a),
            query_string={
                "filters": json.dumps(
                    [
                        {"field": "gender", "operator": "equals", "value": "Female"}
                        for _ in range(21)
                    ]
                )
            },
        )
        self.assertEqual(400, too_many.status_code)
        self.assertIn("at most 20 filters", too_many.get_json()["error"])

    def test_phase4_rows_per_page_and_sensitive_field_exclusion(self):
        self._process(self.event_a)
        for size, expected_rows in ((25, 25), (50, 30), (100, 30)):
            with self.subTest(size=size):
                payload = self._data(per_page=size)
                self.assertEqual(size, payload["pagination"]["per_page"])
                self.assertEqual(expected_rows, len(payload["rows"]))
        fallback = self._data(per_page=75)
        self.assertEqual(50, fallback["pagination"]["per_page"])

        excluded = {
            "source_data_json", "medical_details", "allergies", "emergency_contact",
            "complete_address", "dgroup_leader_contact", "gross_amount", "amount_paid",
        }
        payload = self._data(per_page=25)
        self.assertTrue(excluded.isdisjoint(payload["rows"][0]))
        self.assertTrue(excluded.isdisjoint({column["key"] for column in payload["columns"]}))
        for rule in self.app.url_map.iter_rules():
            if "/registrations" not in rule.rule:
                continue
            mutations = rule.methods - {"GET", "HEAD", "OPTIONS"}
            if mutations:
                self.assertEqual({"PATCH"}, mutations)
                self.assertTrue(rule.rule.endswith("/<int:registrant_id>/attestation"))

    def test_phase4_grouped_columns_performance_and_b1g_polish_contract(self):
        self._process(self.event_a)
        root = Path(__file__).parents[1]
        page = self.app.test_client().get(
            "/events/{}/registrations".format(self.event_a)
        ).get_data(as_text=True)
        script = (root / "app/static/registrations.js").read_text()
        styles = (root / "app/static/app.css").read_text()
        phase4_styles = styles.split(
            "/* Registrations Phase 4 module-only B1G polish */", 1
        )[1]

        for group in ("Attestation &amp; Payment", "Registrant Details", "Logistics"):
            self.assertIn(group, page)
        self.assertIn('const columnGroupOrder = ["Attestation & Payment", "Registrant Details", "Logistics"]', script)
        self.assertIn("loadGroupPreference()", script)
        self.assertIn("saveGroupPreference()", script)
        self.assertIn("visibleTableColumns()", script)
        self.assertIn("groupVisibility[control.value] = control.checked", script)
        self.assertIn("columnGroupOrder.forEach((group) => { groupVisibility[group] = true; })", script)
        self.assertIn("if (latestPayload) renderTable(latestPayload)", script)

        self.assertIn("searchTimer = window.setTimeout", script)
        self.assertIn("}, 300);", script)
        self.assertIn("requestController.abort()", script)
        self.assertIn("window.requestAnimationFrame(() => loadPreview", script)
        self.assertNotIn("innerHTML", script)

        self.assertIn("--registrations-control-height", phase4_styles)
        self.assertIn("var(--b1g-red)", phase4_styles)
        self.assertIn("var(--b1g-off-white)", phase4_styles)
        self.assertIn("var(--b1g-border)", phase4_styles)
        self.assertIn(".registrations-panel", phase4_styles)
        self.assertIn(".registrations-filter-drawer", phase4_styles)
        self.assertIn(".attestation-review-modal", phase4_styles)
        self.assertNotIn("--teal", phase4_styles)
        self.assertNotIn("blue", phase4_styles.casefold())
        self.assertNotIn("indigo", phase4_styles.casefold())

    def test_sorting_pagination_and_invalid_sort_fallback(self):
        self._process(self.event_a)
        descending = self._data(sort="last_name", direction="desc", per_page=25)
        values = [row["last_name"] for row in descending["rows"]]
        self.assertEqual(sorted(values, reverse=True), values)

        second_page = self._data(page=2, per_page=25)
        self.assertEqual(2, second_page["pagination"]["page"])
        self.assertEqual(5, len(second_page["rows"]))
        self.assertTrue(second_page["pagination"]["has_previous"])
        self.assertFalse(second_page["pagination"]["has_next"])

        fallback = self._data(sort="source_data_json", direction="sideways", per_page=25)
        self.assertEqual("registration_code", fallback["query"]["sort"])
        self.assertEqual("asc", fallback["query"]["direction"])
        codes = [row["registration_code"] for row in fallback["rows"]]
        self.assertEqual(sorted(codes), codes)

    def test_event_and_historical_batch_boundaries(self):
        historical_a = self._process(self.event_a)
        batch_b = self._process(self.event_b)
        self._write_fixture(2, prefix="NEW-")
        active_a = self._process(self.event_a)

        active = self._data()
        self.assertEqual(active_a, active["batch"])
        self.assertEqual(2, active["pagination"]["total"])

        historical = self._data(batch=historical_a, per_page=25)
        self.assertEqual(30, historical["pagination"]["total"])
        all_batches = self._data(batch="all", per_page=25)
        self.assertEqual(32, all_batches["pagination"]["total"])
        self.assertNotIn(batch_b, {row["batch_id"] for row in all_batches["rows"]})

        manipulated = self.app.test_client().get(
            "/events/{}/registrations/data?batch={}".format(self.event_a, batch_b)
        )
        self.assertEqual(400, manipulated.status_code)
        page_manipulation = self.app.test_client().get(
            "/events/{}/registrations?batch={}".format(self.event_a, batch_b)
        )
        self.assertEqual(404, page_manipulation.status_code)

    def test_missing_ticket_keeps_registration_with_empty_payment_status(self):
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            get_db().execute(
                "DELETE FROM tickets WHERE batch_id = ? AND ticket_code = 'T-001'",
                (batch_id,),
            )
            get_db().commit()
        payload = self._data(search="R-001", per_page=25)
        self.assertEqual(1, payload["pagination"]["total"])
        self.assertIsNone(payload["rows"][0]["payment_status"])

    def test_attestation_summaries_filters_and_combined_scope_reconcile(self):
        batch_id = self._process(self.event_a)
        with self.app.app_context():
            db = get_db()
            rows = db.execute(
                "SELECT id FROM registrants WHERE batch_id = ? ORDER BY registration_code",
                (batch_id,),
            ).fetchall()
            for row in rows[:2]:
                db.execute(
                    "INSERT INTO attestation_verifications (registrant_id, status) VALUES (?, 'verified')",
                    (row["id"],),
                )
            for row in rows[2:5]:
                db.execute(
                    "INSERT INTO attestation_verifications (registrant_id, status) VALUES (?, 'invalid')",
                    (row["id"],),
                )
            db.commit()

        unfiltered = self._data(per_page=25)
        self.assertEqual(30, unfiltered["summary"]["total_registrations"])
        self.assertEqual(25, unfiltered["summary"]["attestation_pending"])
        self.assertEqual(2, unfiltered["summary"]["attestation_verified"])
        self.assertEqual(3, unfiltered["summary"]["attestation_invalid"])
        for status, expected in (("pending", 25), ("verified", 2), ("invalid", 3)):
            filters = json.dumps(
                [{"field": "attestation_status", "operator": "equals", "value": status}]
            )
            payload = self._data(filters=filters, per_page=25)
            self.assertEqual(expected, payload["pagination"]["total"])
            self.assertEqual(expected, payload["summary"]["total_registrations"])
            self.assertEqual(expected, payload["summary"]["attestation_{}".format(status)])
            self.assertTrue(all(row["attestation_status"] == status for row in payload["rows"]))
            self.assertEqual(
                {
                    "total_registrations": 30,
                    "attestation_pending": 25,
                    "attestation_verified": 2,
                    "attestation_invalid": 3,
                },
                payload["quick_filter_counts"],
            )

        combined = json.dumps(
            [
                {"field": "attestation_status", "operator": "equals", "value": "verified"},
                {"field": "gender", "operator": "equals", "value": "Female"},
            ]
        )
        payload = self._data(filters=combined, per_page=25)
        self.assertEqual(1, payload["pagination"]["total"])
        self.assertEqual(1, payload["summary"]["attestation_verified"])


class RegistrationsAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "registrations-authorization-secret",
                "DATABASE_URL": "sqlite+pysqlite:///{}".format(root / "auth.sqlite3"),
                "STAGING_DIR": str(root / "staging"),
                "AUTHENTICATION_DISABLED": False,
                "WTF_CSRF_ENABLED": True,
            }
        )
        create_test_schema(self.app)
        with self.app.app_context():
            now = datetime.now()
            admin = User(username="admin", role="admin", status="approved", approved_at=now)
            admin.set_password("Admin-Registrations-Password-1!")
            user = User(username="operator", role="user", status="approved", approved_at=now)
            user.set_password("User-Registrations-Password-1!")
            registration_user = User(
                username="registration-operator",
                role="registration",
                status="approved",
                approved_at=now,
            )
            registration_user.set_password("Registration-Operator-Password-1!")
            get_db().session.add_all([admin, user, registration_user])
            get_db().session.flush()
            self.event_id = get_db().execute(
                "INSERT INTO events (name) VALUES ('Protected Event')"
            ).lastrowid
            self.other_event_id = get_db().execute(
                "INSERT INTO events (name) VALUES ('Other Protected Event')"
            ).lastrowid
            self.batch_id = get_db().execute(
                """
                INSERT INTO import_batches (
                    event_id, event_slug, event_name, status, active_event_id,
                    processed_at, activated_at
                ) VALUES (?, 'protected', 'Protected Event', 'active', ?,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (self.event_id, self.event_id),
            ).lastrowid
            self.other_batch_id = get_db().execute(
                """
                INSERT INTO import_batches (
                    event_id, event_slug, event_name, status, active_event_id,
                    processed_at, activated_at
                ) VALUES (?, 'other-protected', 'Other Protected Event', 'active', ?,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (self.other_event_id, self.other_event_id),
            ).lastrowid
            self.registrant_id = self._insert_registrant(
                get_db(), self.batch_id, "R-PROTECTED", "T-PROTECTED"
            )
            self.other_registrant_id = self._insert_registrant(
                get_db(), self.other_batch_id, "R-OTHER", "T-OTHER"
            )
            get_db().commit()
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def _login(self, username, password):
        page = self.client.get("/login")
        token = CSRF_PATTERN.search(page.data).group(1).decode()
        return self.client.post(
            "/login",
            data={"username": username, "password": password, "csrf_token": token},
            follow_redirects=False,
        )

    @staticmethod
    def _insert_registrant(db, batch_id, registration_code, ticket_code):
        return db.execute(
            """
            INSERT INTO registrants (
                batch_id, registration_code, ticket_code, first_name, last_name,
                affiliation, satellite_name, registration_type, source_data_json
            ) VALUES (?, ?, ?, 'Protected', 'Registrant', 'CCF Main', 'CCF Main',
                      'participant', ?)
            """,
            (
                batch_id,
                registration_code,
                ticket_code,
                json.dumps(
                    {
                        "Email Address": "protected@example.test",
                        "Upload Your Accomplished Attestation Form Here":
                            "https://files.example.test/protected.pdf",
                    }
                ),
            ),
        ).lastrowid

    def test_page_data_and_navigation_require_registration_capability(self):
        page_url = "/events/{}/registrations".format(self.event_id)
        data_url = page_url + "/data"
        update_url = "{}/{}/attestation".format(page_url, self.registrant_id)
        unauthenticated = self.client.get(page_url)
        self.assertEqual(302, unauthenticated.status_code)
        self.assertIn("/login", unauthenticated.headers["Location"])
        self.assertEqual(
            302,
            self.client.patch(update_url, json={"status": "verified"}).status_code,
        )

        self._login("operator", "User-Registrations-Password-1!")
        self.assertEqual(403, self.client.get(page_url).status_code)
        self.assertEqual(403, self.client.get(data_url).status_code)
        csrf_token = self._csrf_token()
        self.assertEqual(
            403,
            self.client.patch(
                update_url,
                json={"status": "verified"},
                headers={"X-CSRFToken": csrf_token},
            ).status_code,
        )
        overview = self.client.get("/events/{}".format(self.event_id))
        self.assertNotIn(page_url.encode(), overview.data)
        self.client.post("/logout", data={"csrf_token": self._csrf_token()})

        self._login("admin", "Admin-Registrations-Password-1!")
        page = self.client.get(page_url)
        self.assertEqual(200, page.status_code)
        self.assertIn(('href="{}"'.format(page_url)).encode(), page.data)
        self.assertIn(b'class="nav-link active"', page.data)
        self.assertIn(b'data-attestation-save', page.data)
        self.assertIn(b'data-attestation-status', page.data)
        self.assertEqual(200, self.client.get(data_url).status_code)

        self.client.post("/logout", data={"csrf_token": self._csrf_token()})
        self._login(
            "registration-operator", "Registration-Operator-Password-1!"
        )
        page = self.client.get(page_url)
        self.assertEqual(200, page.status_code)
        self.assertEqual(200, self.client.get(data_url).status_code)
        self.assertIn(b'data-attestation-save', page.data)
        self.assertIn(b">Dashboard</span>", page.data)
        self.assertIn(b">Registrations</span>", page.data)
        for label in (
            b">Analytics</span>",
            b">Satellites</span>",
            b">Data Quality</span>",
            b">Imports</span>",
            b">Admin Tables</span>",
            b">Users</span>",
        ):
            self.assertNotIn(label, page.data)

    def test_registration_role_dashboard_is_read_only_and_modules_are_denied(self):
        self._login(
            "registration-operator", "Registration-Operator-Password-1!"
        )
        overview_url = "/events/{}".format(self.event_id)
        overview = self.client.get(overview_url)
        self.assertEqual(200, overview.status_code)
        self.assertEqual(
            200,
            self.client.get(
                "/events/{}/dashboard".format(self.event_id)
            ).status_code,
        )
        self.assertNotIn(b"Dashboard configuration", overview.data)
        self.assertNotIn(b"Manage Satellite Targets", overview.data)
        self.assertNotIn(b"Open Imports", overview.data)
        self.assertNotIn(b"Create Event", self.client.get("/events").data)

        denied_gets = (
            "/events/new",
            "/events/{}/analytics".format(self.event_id),
            "/api/events/{}/analytics".format(self.event_id),
            "/api/events/{}/analytics/trends".format(self.event_id),
            "/events/{}/overview/registrants".format(self.event_id),
            "/analytics/compare?events={},{}".format(
                self.event_id, self.other_event_id
            ),
            "/api/analytics/compare?events={},{}".format(
                self.event_id, self.other_event_id
            ),
            "/events/{}/data-quality".format(self.event_id),
            "/events/{}/data-quality/issues".format(self.event_id),
            "/events/{}/admin-tables/registrants".format(self.event_id),
            "/events/{}/admin-tables/registrants/data".format(self.event_id),
            "/events/{}/admin-tables/registrants/curated/1/sources".format(
                self.event_id
            ),
            "/events/{}/imports".format(self.event_id),
            "/events/{}/satellites".format(self.event_id),
            "/events/{}/satellites/registrants".format(self.event_id),
            "/admin/users",
        )
        for path in denied_gets:
            with self.subTest(path=path):
                self.assertEqual(403, self.client.get(path).status_code)

        token = self._csrf_token()
        denied_posts = (
            ("/events", {"name": "Denied Event"}),
            (
                "/events/{}/settings".format(self.event_id),
                {"participant_target": "99"},
            ),
            (
                "/events/{}/satellite-datasets".format(self.event_id),
                {"name": "Denied", "participant_target": "10"},
            ),
            ("/events/{}/imports/validate".format(self.event_id), {}),
            (
                "/events/{}/imports/{}/process".format(
                    self.event_id, self.batch_id
                ),
                {},
            ),
            (
                "/events/{}/imports/{}/activate".format(
                    self.event_id, self.batch_id
                ),
                {},
            ),
            (
                "/events/{}/imports/{}/delete".format(
                    self.event_id, self.batch_id
                ),
                {},
            ),
            ("/admin/users/1/approve", {"role": "registration"}),
            ("/admin/users/1/role", {"role": "registration"}),
        )
        for path, data in denied_posts:
            with self.subTest(path=path):
                data["csrf_token"] = token
                self.assertEqual(403, self.client.post(path, data=data).status_code)

    def test_registration_role_updates_attestation_with_own_audit_identity(self):
        self._login(
            "registration-operator", "Registration-Operator-Password-1!"
        )
        response = self.client.patch(
            "/events/{}/registrations/{}/attestation".format(
                self.event_id, self.registrant_id
            ),
            json={"status": "verified"},
            headers={"X-CSRFToken": self._csrf_token()},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("registration-operator", response.get_json()["updated_by"])
        with self.app.app_context():
            reviewer = get_db().execute(
                """
                SELECT u.username
                FROM attestation_verifications av
                JOIN users u ON u.id = av.updated_by_user_id
                WHERE av.registrant_id = ?
                """,
                (self.registrant_id,),
            ).fetchone()
            self.assertEqual("registration-operator", reviewer["username"])

    def test_registration_role_cannot_cross_event_batch_boundaries(self):
        self._login(
            "registration-operator", "Registration-Operator-Password-1!"
        )
        data_url = "/events/{}/registrations/data".format(self.event_id)
        self.assertEqual(
            400,
            self.client.get(
                data_url, query_string={"batch": self.other_batch_id}
            ).status_code,
        )
        response = self.client.patch(
            "/events/{}/registrations/{}/attestation".format(
                self.event_id, self.other_registrant_id
            ),
            json={"status": "invalid"},
            headers={"X-CSRFToken": self._csrf_token()},
        )
        self.assertEqual(404, response.status_code)

    def test_attestation_workflow_is_csrf_protected_attributed_and_reconciled(self):
        self._login("admin", "Admin-Registrations-Password-1!")
        page_url = "/events/{}/registrations".format(self.event_id)
        data_url = page_url + "/data"
        update_url = "{}/{}/attestation".format(page_url, self.registrant_id)

        initial = self.client.get(data_url).get_json()
        self.assertEqual("pending", initial["rows"][0]["attestation_status"])
        self.assertIsNone(initial["rows"][0]["last_reviewed_by"])
        self.assertIsNone(initial["rows"][0]["last_reviewed_at"])
        self.assertEqual(1, initial["summary"]["attestation_pending"])

        no_csrf = self.client.patch(update_url, json={"status": "verified"})
        self.assertEqual(400, no_csrf.status_code)
        csrf_token = self._csrf_token()
        for status in ("verified", "invalid", "pending"):
            with self.subTest(status=status):
                response = self.client.patch(
                    update_url,
                    query_string={"batch": "active"},
                    json={"status": status},
                    headers={"X-CSRFToken": csrf_token},
                )
                self.assertEqual(200, response.status_code, response.get_data(as_text=True))
                payload = response.get_json()
                self.assertEqual(status, payload["status"])
                self.assertEqual("admin", payload["updated_by"])
                self.assertTrue(payload["updated_at"])
                self.assertEqual(
                    {"batch_id", "status", "label", "updated_by", "updated_at"},
                    set(payload),
                )

        filtered = self.client.get(
            data_url,
            query_string={
                "filters": json.dumps(
                    [{"field": "attestation_status", "operator": "equals", "value": "pending"}]
                )
            },
        ).get_json()
        self.assertEqual(1, filtered["pagination"]["total"])
        self.assertEqual(1, filtered["summary"]["attestation_pending"])
        with self.app.app_context():
            verification = get_db().execute(
                "SELECT * FROM attestation_verifications WHERE registrant_id = ?",
                (self.registrant_id,),
            ).fetchone()
            admin = get_db().execute(
                "SELECT id FROM users WHERE username = 'admin'"
            ).fetchone()
            source = get_db().execute(
                "SELECT source_data_json FROM registrants WHERE id = ?",
                (self.registrant_id,),
            ).fetchone()
        self.assertEqual("pending", verification["status"])
        self.assertEqual(admin["id"], verification["updated_by_user_id"])
        self.assertIn("protected.pdf", source["source_data_json"])
        with self.app.app_context():
            self.assertEqual(
                1,
                get_db().execute(
                    "SELECT COUNT(*) FROM attestation_verifications WHERE registrant_id = ?",
                    (self.registrant_id,),
                ).fetchone()[0],
            )

    def test_attestation_updates_validate_status_event_batch_and_json(self):
        self._login("admin", "Admin-Registrations-Password-1!")
        csrf_token = self._csrf_token()
        headers = {"X-CSRFToken": csrf_token}
        update_url = "/events/{}/registrations/{}/attestation".format(
            self.event_id, self.registrant_id
        )
        self.assertEqual(
            400,
            self.client.patch(update_url, data="not-json", headers=headers).status_code,
        )
        self.assertEqual(
            400,
            self.client.patch(
                update_url, json={"status": "approved"}, headers=headers
            ).status_code,
        )
        self.assertEqual(
            400,
            self.client.patch(
                update_url,
                query_string={"batch": self.other_batch_id},
                json={"status": "verified"},
                headers=headers,
            ).status_code,
        )
        cross_event_url = "/events/{}/registrations/{}/attestation".format(
            self.event_id, self.other_registrant_id
        )
        self.assertEqual(
            404,
            self.client.patch(
                cross_event_url, json={"status": "verified"}, headers=headers
            ).status_code,
        )

    def test_attestation_verification_cascades_with_registration_batch(self):
        self._login("admin", "Admin-Registrations-Password-1!")
        response = self.client.patch(
            "/events/{}/registrations/{}/attestation".format(
                self.event_id, self.registrant_id
            ),
            json={"status": "verified"},
            headers={"X-CSRFToken": self._csrf_token()},
        )
        self.assertEqual(200, response.status_code)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(
                1,
                db.execute(
                    "SELECT COUNT(*) FROM attestation_verifications WHERE registrant_id = ?",
                    (self.registrant_id,),
                ).fetchone()[0],
            )
            db.execute("DELETE FROM import_batches WHERE id = ?", (self.batch_id,))
            db.commit()
            self.assertEqual(
                0,
                db.execute(
                    "SELECT COUNT(*) FROM attestation_verifications WHERE registrant_id = ?",
                    (self.registrant_id,),
                ).fetchone()[0],
            )

    def test_historical_and_active_registrations_have_independent_state(self):
        self._login("admin", "Admin-Registrations-Password-1!")
        with self.app.app_context():
            db = get_db()
            historical_batch_id = db.execute(
                """
                INSERT INTO import_batches (
                    event_id, event_slug, event_name, status, processed_at
                ) VALUES (?, 'historical', 'Protected Event', 'inactive', CURRENT_TIMESTAMP)
                """,
                (self.event_id,),
            ).lastrowid
            historical_registrant_id = self._insert_registrant(
                db, historical_batch_id, "R-HISTORICAL", "T-HISTORICAL"
            )
            db.commit()

        headers = {"X-CSRFToken": self._csrf_token()}
        historical_update = self.client.patch(
            "/events/{}/registrations/{}/attestation".format(
                self.event_id, historical_registrant_id
            ),
            query_string={"batch": historical_batch_id},
            json={"status": "verified"},
            headers=headers,
        )
        self.assertEqual(200, historical_update.status_code)
        active_update = self.client.patch(
            "/events/{}/registrations/{}/attestation".format(
                self.event_id, self.registrant_id
            ),
            query_string={"batch": "active"},
            json={"status": "invalid"},
            headers=headers,
        )
        self.assertEqual(200, active_update.status_code)

        active = self.client.get(
            "/events/{}/registrations/data".format(self.event_id)
        ).get_json()
        historical = self.client.get(
            "/events/{}/registrations/data".format(self.event_id),
            query_string={"batch": historical_batch_id},
        ).get_json()
        self.assertEqual("invalid", active["rows"][0]["attestation_status"])
        self.assertEqual("verified", historical["rows"][0]["attestation_status"])

    def test_reviewer_deletion_retains_state_and_database_rejects_invalid_status(self):
        with self.app.app_context():
            db = get_db()
            operator = db.execute(
                "SELECT id FROM users WHERE username = 'operator'"
            ).fetchone()
            db.execute(
                """
                INSERT INTO attestation_verifications (
                    registrant_id, status, updated_by_user_id
                ) VALUES (?, 'verified', ?)
                """,
                (self.registrant_id, operator["id"]),
            )
            db.commit()
            db.execute("DELETE FROM users WHERE id = ?", (operator["id"],))
            db.commit()
            retained = db.execute(
                "SELECT status, updated_by_user_id FROM attestation_verifications"
            ).fetchone()
            self.assertEqual("verified", retained["status"])
            self.assertIsNone(retained["updated_by_user_id"])

            with self.assertRaises(IntegrityError):
                db.execute(
                    "UPDATE attestation_verifications SET status = 'approved'"
                )
                db.commit()
            db.rollback()

    def test_attestation_update_log_is_structured_and_excludes_registration_pii(self):
        self._login("admin", "Admin-Registrations-Password-1!")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonLogFormatter())
        previous_handlers = list(self.app.logger.handlers)
        previous_level = self.app.logger.level
        self.app.logger.handlers = [handler]
        self.app.logger.setLevel(logging.INFO)
        try:
            response = self.client.patch(
                "/events/{}/registrations/{}/attestation".format(
                    self.event_id, self.registrant_id
                ),
                json={"status": "verified"},
                headers={"X-CSRFToken": self._csrf_token()},
            )
        finally:
            self.app.logger.handlers = previous_handlers
            self.app.logger.setLevel(previous_level)
        self.assertEqual(200, response.status_code)
        output = stream.getvalue()
        self.assertIn("attestation_verification_updated", output)
        self.assertIn('"registrant_id":{}'.format(self.registrant_id), output)
        self.assertIn('"event_id":{}'.format(self.event_id), output)
        self.assertNotIn("Protected Registrant", output)
        self.assertNotIn("protected@example.test", output)
        self.assertNotIn("protected.pdf", output)

    def _csrf_token(self):
        page = self.client.get("/events")
        return CSRF_PATTERN.search(page.data).group(1).decode()
