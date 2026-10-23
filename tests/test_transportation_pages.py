import json
import re
import unittest

from app.db import get_db
from app.aggregation import participant_transportation_metrics
from app.models import hash_password
from app.transportation import transportation_history
from app.transportation_pages import transportation_roster
from tests import test_phase1 as fixtures


CSRF = re.compile(rb'name="csrf_token"[^>]*value="([^"]+)"')


class TransportationPageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.EventIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.app = self.fixture.app
        self.event = self.fixture.event_a
        self.batch = self.fixture._process(self.event)
        self.app.config.update(AUTHENTICATION_DISABLED=False, WTF_CSRF_ENABLED=True)
        password = hash_password("TravelPassword123!")
        with self.app.app_context():
            db = get_db()
            self.users = {}
            for name, role, status in (("admin", "admin", "approved"), ("travel-user", "user", "approved"),
                                       ("registration-user", "registration", "approved"),
                                       ("pending-user", "user", "pending"), ("blocked-user", "user", "blocked")):
                self.users[name] = db.execute(
                    """INSERT INTO users (username, password_hash, role, status, approved_at)
                       VALUES (?, ?, ?, ?, CASE WHEN ? = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END)""",
                    (name, password, role, status, status),
                ).lastrowid
            row = db.execute("SELECT id, source_data_json FROM registrants WHERE batch_id = ? AND registration_code = 'R-1'", (self.batch,)).fetchone()
            answers = json.loads(row["source_data_json"])
            answers.update({"Transportation From Ccf To Mmrc": "Bus to MMRC", "Transportation From Mmrc To Ccf": "Carpool"})
            db.execute("UPDATE registrants SET source_data_json = ? WHERE id = ?", (json.dumps(answers), row["id"]))
            self.person = db.execute("SELECT attestation_participant_id FROM attestation_participant_registrants WHERE registrant_id = ?", (row["id"],)).fetchone()["attestation_participant_id"]
            db.commit()
        self.url = f"/events/{self.event}/transportation"
        self.detail = f"{self.url}/{self.person}"
        self.client = self.app.test_client()

    def login(self, username="travel-user", client=None):
        client = client or self.client
        token = CSRF.search(client.get("/login").data).group(1).decode()
        return client.post("/login", data=dict(username=username, password="TravelPassword123!", csrf_token=token))

    def token(self):
        response = self.client.get(self.url)
        self.assertEqual(200, response.status_code)
        return CSRF.search(response.data).group(1).decode()

    def payload(self, changes=None):
        state = self.client.get(self.detail).get_json()
        changes = changes or {"to_mmrc": "public_transportation"}
        return dict(changes=changes, expected_batch_id=state["active_batch_id"],
                    expected_revisions={d: state["trips"][d]["revision"] for d in changes}, reason="Changed travel plans")

    def test_page_button_edit_and_audit_attribution(self):
        self.login()
        token = self.token()
        self.assertIn(b"Manage Transportation", self.client.get(f"/events/{self.event}").data)
        page = self.client.get(self.url)
        self.assertIn(b"5 people in the active import", page.data)
        self.assertIn(b"Bus", page.data)
        self.assertIn("no-store", page.headers["Cache-Control"])
        response = self.client.post(self.detail, json=self.payload(), headers={"X-CSRFToken": token})
        self.assertEqual(200, response.status_code)
        updated = self.client.get(self.url)
        self.assertIn(b"Manual override", updated.data)
        self.assertIn(b"By travel-user", updated.data)
        self.assertIn(b"PHT", updated.data)
        with self.app.app_context():
            history = transportation_history(get_db(), self.event, self.person)
            self.assertEqual(1, len(history))
            self.assertEqual(self.users["travel-user"], history[0]["changed_by_user_id"])
        # GET/opening and cancelling the dialog do not create history.
        self.client.get(self.detail)
        with self.app.app_context():
            self.assertEqual(1, len(transportation_history(get_db(), self.event, self.person)))

    def test_dashboard_uses_effective_values_and_counts_missing_answers(self):
        self.login()
        token = self.token()

        def metrics():
            with self.app.app_context():
                db = get_db()
                result = participant_transportation_metrics(db, self.batch)
                roster = transportation_roster(db, self.event, self.batch)
                self.assertEqual(len(roster), result['registrants'])
                for trip in result['directions']:
                    for item in trip['items']:
                        self.assertEqual(sum(p['trips'][trip['key']]['mode'] == item['key'] for p in roster), item['count'])
                    self.assertEqual(result['registrants'], trip['total'] + trip['other'] + trip['conflicts'] + trip['unreported'])
                return result

        original = metrics()
        self.assertEqual(5, original['registrants'])
        for mode in ('other', 'unreported', 'public_transportation', None):
            response = self.client.post(self.detail, json=self.payload({'to_mmrc': mode}), headers={'X-CSRFToken': token})
            self.assertEqual(200, response.status_code)
            updated = metrics()
            self.assertEqual(original['directions'][1], updated['directions'][1])
        self.assertEqual(original, updated)
        self.assertIn(b'Current travel arrangements', self.client.get(f'/events/{self.event}').data)

    def test_history_view_snapshots_reset_and_access(self):
        path = self.detail + '/history'
        self.assertEqual(302, self.client.get(path).status_code)
        self.login()
        self.assertIn(b'No transportation updates yet', self.client.get(path).data)
        token = self.token()
        payload = self.payload()
        payload['reason'] = '<script>alert(1)</script>'
        self.assertEqual(200, self.client.post(self.detail, json=payload, headers={'X-CSRFToken': token}).status_code)
        self.assertEqual(200, self.client.post(self.detail, json=self.payload({'to_mmrc': None}), headers={'X-CSRFToken': token}).status_code)
        with self.app.app_context():
            db = get_db()
            db.execute('UPDATE users SET username = ? WHERE id = ?', ('renamed-user', self.users['travel-user']))
            db.commit()
        page = self.client.get(path)
        self.assertEqual(200, page.status_code)
        self.assertIn('no-store', page.headers['Cache-Control'])
        for text in (b'Reset to imported value', b'Before: Bus', b'After: Public Transportation', b'By travel-user', b'PHT', b'&lt;script&gt;'):
            self.assertIn(text, page.data)
        self.assertNotIn(b'<script>alert(1)</script>', page.data)
        self.assertEqual(404, self.client.get(f'/events/{self.fixture.event_b}/transportation/{self.person}/history').status_code)
        for cursor in ('0', '-1', 'bad'):
            self.assertEqual(400, self.client.get(path + '?before_id=' + cursor).status_code)
        other = self.app.test_client()
        self.login('registration-user', other)
        self.assertEqual(403, other.get(path).status_code)

    def test_dashboard_conflicts_and_reimports_respect_manual_override(self):
        self.login()
        token = self.token()
        with self.app.app_context():
            db = get_db()
            row = db.execute("SELECT id, source_data_json FROM registrants WHERE batch_id = ? AND registration_code = 'R-1'", (self.batch,)).fetchone()
            answers = json.loads(row['source_data_json'])
            answers['Transportation To MMRC'] = 'Carpool'
            db.execute('UPDATE registrants SET source_data_json = ? WHERE id = ?', (json.dumps(answers), row['id']))
            db.commit()
            metrics = participant_transportation_metrics(db, self.batch)
            self.assertEqual(1, metrics['directions'][0]['conflicts'])
        self.assertEqual(200, self.client.post(self.detail, json=self.payload({'to_mmrc': 'bus'}), headers={'X-CSRFToken': token}).status_code)
        replacement = self.fixture._process(self.event)
        with self.app.app_context():
            db = get_db()
            metrics = participant_transportation_metrics(db, replacement)
            self.assertEqual(0, metrics['directions'][0]['conflicts'])
            self.assertEqual(1, next(item['count'] for item in metrics['directions'][0]['items'] if item['key'] == 'bus'))
        self.assertIn(b'After: Bus', self.client.get(self.detail + '/history').data)

    def test_history_pagination_and_absent_participant(self):
        self.login()
        token = self.token()
        self.client.post(self.detail, json=self.payload(), headers={'X-CSRFToken': token})
        with self.app.app_context():
            db = get_db()
            for revision in range(2, 53):
                db.execute('''INSERT INTO participant_transportation_history
                    (event_id, attestation_participant_id, direction, action, revision,
                     previous_value_json, new_value_json, reason, changed_by_user_id, changed_by_username)
                    SELECT event_id, attestation_participant_id, direction, action, ?,
                           previous_value_json, new_value_json, reason, changed_by_user_id, changed_by_username
                    FROM participant_transportation_history WHERE event_id = ? ORDER BY id LIMIT 1''',
                           (revision, self.event))
            db.commit()
        path = self.detail + '/history'
        page = self.client.get(path)
        self.assertEqual(50, page.data.count(b'class="transportation-history-entry"'))
        older = re.search(rb'href="([^"]+before_id=[0-9]+)"', page.data).group(1).decode()
        next_page = self.client.get(older)
        self.assertEqual(2, next_page.data.count(b'class="transportation-history-entry"'))
        self.assertNotIn(b'Older changes', next_page.data)
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE import_batches SET status = 'inactive', active_event_id = NULL WHERE id = ?", (self.batch,))
            db.commit()
        absent = self.client.get(path)
        self.assertEqual(200, absent.status_code)
        self.assertIn(b'not in the active import', absent.data)

    def test_admin_access_and_registration_denied(self):
        self.login("admin")
        self.assertEqual(200, self.client.get(self.url).status_code)
        other = self.app.test_client()
        self.login("registration-user", other)
        for method in (other.get, other.post):
            self.assertEqual(403, method(self.detail).status_code)
        self.assertEqual(403, other.get(self.url).status_code)
        self.assertNotIn(b"Manage Transportation", other.get(f"/events/{self.event}").data)

    def test_unauthenticated_and_public_access_do_not_grant_management(self):
        for path in (self.url, self.detail):
            self.assertEqual(302, self.client.get(path).status_code)
        self.assertEqual(302, self.client.post(self.detail, json={}).status_code)
        # The explicit operator check remains active even with development read-auth bypass.
        self.app.config["AUTHENTICATION_DISABLED"] = True
        self.assertEqual(403, self.client.get(self.url).status_code)
        self.assertNotIn(b"Manage Transportation", self.client.get(f"/events/{self.event}").data)

    def test_public_presentation_hides_management_even_for_signed_in_admin(self):
        self.login("admin")
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE events SET public_dashboard_password_hash = ? WHERE id = ?",
                       (hash_password("PresentationPassword123!"), self.event))
            db.commit()
        path = f"/public/events/{self.event}/dashboard"
        token = CSRF.search(self.client.get(path).data).group(1).decode()
        response = self.client.post(path, data={"csrf_token": token, "password": "PresentationPassword123!"}, follow_redirects=True)
        self.assertEqual(200, response.status_code)
        self.assertNotIn(b"Manage Transportation", response.data)

    def test_both_directions_save_together_without_forged_operator(self):
        self.login()
        token = self.token()
        payload = self.payload({"to_mmrc": "other", "from_mmrc": "bus"})
        payload["changed_by_user_id"] = self.users["admin"]
        response = self.client.post(self.detail, json=payload, headers={"X-CSRFToken": token})
        self.assertEqual(200, response.status_code)
        trips = self.client.get(self.detail).get_json()["trips"]
        self.assertEqual("other", trips["to_mmrc"]["mode"])
        self.assertEqual("bus", trips["from_mmrc"]["mode"])
        with self.app.app_context():
            history = transportation_history(get_db(), self.event, self.person)
            self.assertEqual(2, len(history))
            self.assertEqual({self.users["travel-user"]}, {row["changed_by_user_id"] for row in history})

    def test_blocked_and_pending_users_cannot_access(self):
        for username in ("pending-user", "blocked-user"):
            client = self.app.test_client()
            self.login(username, client)
            self.assertEqual(302, client.get(self.url).status_code)
        self.login()
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE users SET status = 'blocked' WHERE id = ?", (self.users["travel-user"],))
            db.commit()
        self.assertEqual(302, self.client.get(self.url).status_code)

    def test_csrf_validation_and_event_isolation(self):
        self.login()
        payload = self.payload()
        self.assertEqual(400, self.client.post(self.detail, json=payload).status_code)
        token = self.token()
        foreign = f"/events/{self.fixture.event_b}/transportation/{self.person}"
        self.assertEqual(404, self.client.get(foreign).status_code)
        self.assertEqual(404, self.client.post(foreign, json=payload, headers={"X-CSRFToken": token}).status_code)
        self.assertEqual(404, self.client.get("/events/999999/transportation").status_code)
        with self.app.app_context():
            self.assertEqual([], transportation_history(get_db(), self.event, self.person))

    def test_stale_forms_and_invalid_payloads(self):
        self.login()
        token = self.token()
        payload = self.payload()
        headers = {"X-CSRFToken": token}
        self.assertEqual(200, self.client.post(self.detail, json=payload, headers=headers).status_code)
        self.assertEqual(409, self.client.post(self.detail, json=payload, headers=headers).status_code)
        fresh = self.payload({"from_mmrc": "bus"})
        self.assertEqual(409, self.client.post(self.detail, json=dict(fresh, expected_batch_id=999999), headers=headers).status_code)
        for body in ([], {}, dict(fresh, changes={}), dict(fresh, changes={"to_mmrc": "taxi"}), dict(fresh, expected_revisions=None)):
            with self.subTest(body=body):
                self.assertEqual(400, self.client.post(self.detail, json=body, headers=headers).status_code)

    def test_filters_apply_before_pagination_and_match_the_same_trip(self):
        self.login()
        token = self.token()
        self.client.post(self.detail, json=self.payload(), headers={"X-CSRFToken": token})
        for query in ("q=test1%40example.com", "mode=public_transportation&source=manual&direction=to_mmrc"):
            self.assertIn(b"1 result", self.client.get(self.url + "?" + query).data)
        response = self.client.get(self.url + "?mode=carpool&source=manual&direction=all")
        self.assertIn(b"No matches found", response.data)
        self.assertEqual(400, self.client.get(self.url + "?direction=invalid").status_code)
        self.assertEqual(400, self.client.get(self.url + "?per_page=10000").status_code)
        with self.app.app_context():
            db = get_db()
            for index in range(30):
                person = db.execute("INSERT INTO attestation_participants (event_id) VALUES (?)", (self.event,)).lastrowid
                record = db.execute("""INSERT INTO registrants
                    (batch_id, registration_code, ticket_code, affiliation, first_name, last_name, registration_type, source_data_json)
                    VALUES (?, ?, ?, 'Unknown', 'Extra', ?, 'participant', '{}')""",
                    (self.batch, f"R-EXTRA-{index}", f"T-EXTRA-{index}", str(index))).lastrowid
                db.execute("""INSERT INTO attestation_participant_registrants
                    (event_id, batch_id, registrant_id, attestation_participant_id) VALUES (?, ?, ?, ?)""",
                    (self.event, self.batch, record, person))
            db.commit()
            self.assertEqual(35, len(transportation_roster(db, self.event, self.batch)))
        first = self.client.get(self.url + "?q=Extra&per_page=25")
        self.assertEqual(25, first.data.count(b"data-transportation-edit "))
        self.assertIn(b"q=Extra", first.data)
        second = self.client.get(self.url + "?q=Extra&per_page=25&page=999")
        self.assertEqual(5, second.data.count(b"data-transportation-edit "))
        self.assertIn(b"Page 2 of 2", second.data)

    def test_empty_state_reset_and_escaped_user_data(self):
        self.login()
        self.assertIn(b"No active import yet", self.client.get(f"/events/{self.fixture.event_b}/transportation").data)
        token = self.token()
        self.client.post(self.detail, json=self.payload(), headers={"X-CSRFToken": token})
        response = self.client.post(self.detail, json=self.payload({"to_mmrc": None}), headers={"X-CSRFToken": token})
        self.assertEqual(200, response.status_code)
        self.assertEqual("bus", self.client.get(self.detail).get_json()["trips"]["to_mmrc"]["mode"])
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE registrants SET first_name = '<script>alert(1)</script>' WHERE batch_id = ?", (self.batch,))
            db.commit()
        page = self.client.get(self.url)
        self.assertNotIn(b"<script>alert(1)</script>", page.data)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", page.data)
