import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from .cors import CorsMiddleware
from .models import LoginAttemptBucket, Store, StoreMembership


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
        response = self.client.get("/api/reports/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "store_access_denied")

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
        self.assertEqual(response.json()["code"], "store_access_denied")


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

    def test_deeply_nested_login_json_has_controlled_error(self):
        response = self.client.post(
            "/api/auth/login/", "[" * 2000 + "0" + "]" * 2000,
            content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())

    def test_invalid_unicode_and_null_usernames_are_rejected_before_authentication(self):
        for username, password in [("cash\x00ier", "password"), ("\ud800", "password"), ("cashier", "\ud800")]:
            with self.subTest(username=repr(username), password=repr(password)):
                with patch("stores.views.authenticate") as authenticate:
                    response = self.client.post(
                        "/api/auth/login/", json.dumps({"username": username, "password": password}),
                        content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf,
                    )
                self.assertEqual(response.status_code, 400)
                authenticate.assert_not_called()

    def test_auth_mutations_reject_get(self):
        for url in ["/api/auth/login/", "/api/auth/logout/"]:
            self.assertEqual(self.client.get(url).status_code, 405)


@override_settings(LOGIN_ACCOUNT_LIMIT=2, LOGIN_IP_LIMIT=4, LOGIN_WINDOW_SECONDS=900, LOGIN_TRUST_VERCEL_IP=False)
class LoginThrottlingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="cashier", password="test-password-cashier")

    def attempt(self, username="cashier", password="wrong", **headers):
        # Separate clients emulate separate sessions/workers; budgets live in DB.
        client = Client(enforce_csrf_checks=True)
        token = client.get("/api/auth/session/").json()["csrfToken"]
        return client.post(
            "/api/auth/login/", {"username": username, "password": password},
            content_type="application/json", HTTP_X_CSRFTOKEN=token, **headers,
        )

    def test_account_limit_survives_new_clients_and_ip_changes(self):
        for address in ["192.0.2.1", "192.0.2.2"]:
            self.assertEqual(self.attempt(REMOTE_ADDR=address).status_code, 401)
        with patch("stores.views.authenticate") as authenticate:
            blocked = self.attempt(password="test-password-cashier", REMOTE_ADDR="192.0.2.3")
        self.assertEqual(blocked.status_code, 429)
        self.assertGreater(int(blocked.headers["Retry-After"]), 0)
        self.assertIn("no-store", blocked.headers["Cache-Control"])
        authenticate.assert_not_called()
        self.assertEqual(self.attempt(username="different-account", REMOTE_ADDR="192.0.2.4").status_code, 401)

    def test_ip_limit_blocks_password_spray_and_spoofed_forwarded_headers(self):
        for number in range(4):
            response = self.attempt(username=f"unknown-{number}", HTTP_X_FORWARDED_FOR=f"192.0.2.{number}", HTTP_X_VERCEL_FORWARDED_FOR=f"198.51.100.{number}")
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.attempt(username="another-user").status_code, 429)
        self.assertEqual(LoginAttemptBucket.objects.count(), 5)
        for bucket in LoginAttemptBucket.objects.all():
            self.assertRegex(bucket.key, r"^[0-9a-f]{64}$")

    @override_settings(LOGIN_TRUST_VERCEL_IP=True, LOGIN_IP_LIMIT=1)
    def test_vercel_uses_its_trusted_ip_header(self):
        first = self.attempt(username="first-user", HTTP_X_VERCEL_FORWARDED_FOR="192.0.2.1")
        second = self.attempt(username="second-user", HTTP_X_VERCEL_FORWARDED_FOR="192.0.2.2")
        blocked = self.attempt(username="third-user", HTTP_X_VERCEL_FORWARDED_FOR="192.0.2.1", HTTP_X_FORWARDED_FOR="192.0.2.3")
        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(blocked.status_code, 429)

    @override_settings(LOGIN_IP_LIMIT=1)
    def test_ipv6_address_rotation_in_one_subnet_cannot_bypass_ip_limit(self):
        self.assertEqual(self.attempt(username="first-user", REMOTE_ADDR="2001:db8::1").status_code, 401)
        self.assertEqual(self.attempt(username="second-user", REMOTE_ADDR="2001:db8::2").status_code, 429)

    def test_blocked_retries_do_not_extend_expiry_and_login_recovers(self):
        now = timezone.now()
        with patch("stores.throttling.timezone.now", return_value=now):
            self.attempt()
            self.attempt()
        with patch("stores.throttling.timezone.now", return_value=now + timedelta(seconds=850)):
            blocked = self.attempt()
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers["Retry-After"], "50")
        with patch("stores.throttling.timezone.now", return_value=now + timedelta(seconds=901)):
            self.assertEqual(self.attempt(password="test-password-cashier").status_code, 200)

    def test_api_and_admin_share_account_budget(self):
        self.assertEqual(self.attempt().status_code, 401)
        client = Client(enforce_csrf_checks=True)
        client.get("/admin/login/")
        token = client.cookies["csrftoken"].value
        first = client.post("/admin/login/", {"username": "cashier", "password": "wrong", "csrfmiddlewaretoken": token})
        self.assertEqual(first.status_code, 200)
        self.assertContains(first, "Please enter the correct username and password")
        second = client.post("/admin/login/", {"username": "cashier", "password": "wrong", "csrfmiddlewaretoken": token})
        self.assertEqual(second.status_code, 429)
        self.assertIn("Retry-After", second.headers)
        self.assertEqual(self.attempt().status_code, 429)

    def test_csrf_rejections_do_not_consume_account_budget(self):
        response = Client(enforce_csrf_checks=True).post(
            "/api/auth/login/", {"username": "cashier", "password": "wrong"}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(LoginAttemptBucket.objects.count(), 0)

    def test_expired_abandoned_keys_are_removed(self):
        LoginAttemptBucket.objects.create(key="expired-key", attempts=1, expires_at=timezone.now() - timedelta(days=2))
        self.attempt()
        self.assertFalse(LoginAttemptBucket.objects.filter(key="expired-key").exists())


@override_settings(CORS_ALLOWED_ORIGINS=["https://frontend.example"])
class CorsProtectionTests(TestCase):
    def test_origin_variation_preserves_session_cookie_variation(self):
        response = self.client.get("/api/auth/session/", HTTP_ORIGIN="https://frontend.example")
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://frontend.example")
        self.assertEqual(response.headers["Access-Control-Allow-Credentials"], "true")
        variation = {part.strip().lower() for part in response.headers["Vary"].split(",")}
        self.assertTrue({"cookie", "origin"}.issubset(variation))

    def test_unknown_and_missing_origins_do_not_grant_credentialed_access(self):
        for headers in [{}, {"HTTP_ORIGIN": "https://attacker.example"}]:
            response = self.client.get("/api/auth/session/", **headers)
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)
            self.assertIn("origin", response.headers["Vary"].lower())

    def test_preflight_is_only_short_circuited_for_allowed_origin(self):
        middleware = CorsMiddleware(lambda request: HttpResponse(status=405))
        factory = RequestFactory()
        self.assertEqual(middleware(factory.options("/api/reports/", HTTP_ORIGIN="https://frontend.example")).status_code, 204)
        self.assertEqual(middleware(factory.options("/api/reports/", HTTP_ORIGIN="https://attacker.example")).status_code, 405)
