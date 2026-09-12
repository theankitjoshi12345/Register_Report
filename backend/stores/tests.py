import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from .models import Store, StoreMembership


def close_payload(**changes):
    values = dict.fromkeys(
        (
            "lottery_terminal_sales", "lottery_terminal_payout", "phone_card_actual_sales",
            "bodega_net_difference", "bodega_lottery_sales", "bodega_lottery_payout",
            "bodega_phone_card_sales", "bodega_gas_sales", "gas_cash_sales",
            "gas_lottery_sales", "gas_lottery_payout", "gas_phone_card_sales",
            "gas_card_payment_sales",
        ),
        "0.00",
    )
    return {
        **values, "report_date": "2026-09-10", "close_type": "day", "close_label": "",
        "scratch_offs": [], "tickets": [], "vendor_payouts": [], "safe_drops": [],
        **changes,
    }


class StoreAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_user(username="owner", password="test-password-owner")
        cls.other_owner = users.objects.create_user(username="other", password="test-password-other")
        cls.unassigned = users.objects.create_user(username="unassigned", password="test-password-unassigned")
        cls.admin = users.objects.create_superuser(username="admin", password="test-password-admin")
        cls.store = Store.objects.create(name="North store")
        cls.other_store = Store.objects.create(name="South store")
        StoreMembership.objects.create(user=cls.owner, store=cls.store)
        StoreMembership.objects.create(user=cls.other_owner, store=cls.other_store)

    def setUp(self):
        self.client.force_login(self.owner)

    def post_close(self, store, **changes):
        return self.client.post(
            "/api/reports/", close_payload(**changes), content_type="application/json",
            HTTP_X_STORE_ID=str(store.pk),
        )

    def test_anonymous_report_access_is_rejected(self):
        response = Client().get("/api/reports/")
        self.assertEqual(response.status_code, 401)

    def test_session_only_lists_assigned_stores(self):
        response = self.client.get("/api/auth/session/")
        self.assertEqual(response.json()["stores"], [{"id": self.store.pk, "name": "North store"}])
        self.assertEqual(response.json()["user"]["username"], "owner")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_superuser_can_access_all_stores(self):
        self.client.force_login(self.admin)
        ids = {store["id"] for store in self.client.get("/api/auth/session/").json()["stores"]}
        self.assertEqual(ids, set(Store.objects.values_list("id", flat=True)))

    def test_unassigned_account_cannot_access_reports(self):
        self.client.force_login(self.unassigned)
        self.assertEqual(self.client.get("/api/reports/").status_code, 403)

    def test_invalid_store_id_has_controlled_error(self):
        for value in ["-1", "0", "abc", "1.0", "９", "9" * 100]:
            with self.subTest(value=value):
                self.assertEqual(self.client.get("/api/reports/", HTTP_X_STORE_ID=value).status_code, 400)

    def test_store_header_cannot_grant_access(self):
        response = self.post_close(self.other_store)
        self.assertEqual(response.status_code, 404)

    def test_report_details_and_edits_are_scoped_to_selected_store(self):
        own = self.post_close(self.store)
        self.assertEqual(own.status_code, 201, own.content)
        report_id = own.json()["id"]
        self.client.force_login(self.other_owner)
        url = f"/api/reports/{report_id}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        response = self.client.patch(url, {"bodega_net_difference": "10.00"}, content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/api/reports/").json()["reports"], [])

    def test_same_date_and_scratch_history_are_independent_between_stores(self):
        first = self.post_close(self.store, scratch_offs=[{"slot_number": 1, "ending_number": 15}])
        self.assertEqual(first.status_code, 201, first.content)
        self.client.force_login(self.other_owner)
        other = self.post_close(self.other_store, scratch_offs=[{"slot_number": 1, "ending_number": 2}])
        self.assertEqual(other.status_code, 201, other.content)
        self.assertEqual(other.json()["calculated"]["scratch_off"]["sales"], "40.00")
        next_day = self.post_close(self.other_store, report_date="2026-09-11", scratch_offs=[{"slot_number": 1, "ending_number": 3}])
        self.assertEqual(next_day.status_code, 201, next_day.content)
        self.assertEqual(next_day.json()["calculated"]["scratch_off"]["sales"], "20.00")

    def test_superuser_can_switch_stores_but_still_gets_scoped_reports(self):
        own = self.post_close(self.store)
        self.assertEqual(own.status_code, 201, own.content)
        self.client.force_login(self.admin)
        response = self.client.get("/api/reports/", HTTP_X_STORE_ID=str(self.other_store.pk))
        self.assertEqual(response.json()["reports"], [])
        self.assertEqual(self.client.get(f"/api/reports/{own.json()['id']}/", HTTP_X_STORE_ID=str(self.other_store.pk)).status_code, 404)

    def test_membership_revocation_takes_effect_without_new_login(self):
        StoreMembership.objects.filter(user=self.owner, store=self.store).delete()
        response = self.client.get("/api/reports/", HTTP_X_STORE_ID=str(self.store.pk))
        self.assertEqual(response.status_code, 404)


class SessionProtectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="cashier", password="test-password-cashier")
        cls.store = Store.objects.create(name="Test store")
        StoreMembership.objects.create(user=cls.user, store=cls.store)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.csrf = self.client.get("/api/auth/session/").json()["csrfToken"]

    def sign_in(self):
        return self.client.post(
            "/api/auth/login/", {"username": "cashier", "password": "test-password-cashier"},
            content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf,
        )

    def test_anonymous_session_can_bootstrap_csrf(self):
        data = self.client.get("/api/auth/session/").json()
        self.assertIsNone(data["user"])
        self.assertEqual(data["stores"], [])
        self.assertTrue(data["csrfToken"])

    def test_login_requires_csrf(self):
        response = self.client.post("/api/auth/login/", {"username": "cashier", "password": "test-password-cashier"}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("errors", response.json())

    def test_login_rotates_token_and_protects_report_writes_and_logout(self):
        response = self.sign_in()
        self.assertEqual(response.status_code, 200)
        token = response.json()["csrfToken"]
        self.assertNotEqual(token, self.csrf)
        rejected = self.client.post("/api/reports/", close_payload(), content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(rejected.status_code, 403)
        created = self.client.post("/api/reports/", close_payload(), content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(self.client.post("/api/auth/logout/", {}, content_type="application/json").status_code, 403)
        logged_out = self.client.post("/api/auth/logout/", {}, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(logged_out.status_code, 200)
        self.assertIsNone(logged_out.json()["user"])
        self.assertEqual(self.client.get("/api/reports/").status_code, 401)

    def test_wrong_password_does_not_start_authenticated_session(self):
        response = self.client.post("/api/auth/login/", {"username": "cashier", "password": "wrong"}, content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(self.client.get("/api/auth/session/").json()["user"])

    def test_invalid_login_payloads_are_controlled(self):
        for payload in [[], None, {"username": [], "password": "x"}, {"username": "cashier"}]:
            with self.subTest(payload=payload):
                response = self.client.post("/api/auth/login/", json.dumps(payload), content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)
                self.assertEqual(response.status_code, 400)

    def test_inactive_user_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.sign_in().status_code, 401)

    def test_auth_mutations_reject_get(self):
        for url in ["/api/auth/login/", "/api/auth/logout/"]:
            self.assertEqual(self.client.get(url).status_code, 405)
