from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse


class HealthEndpointTests(SimpleTestCase):
    def test_health_is_public_and_does_not_require_a_database(self):
        # SimpleTestCase rejects database queries, keeping this a liveness check.
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "service": "register-report-api"},
        )

    def test_health_rejects_write_methods(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(reverse("health"))

                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.headers["Allow"], "GET")


class ApiSecurityTests(SimpleTestCase):
    def test_oversized_login_rejected_before_authentication_or_csrf_parsing(self):
        response = Client(enforce_csrf_checks=True).post(
            reverse("login"), "x" * (16 * 1024 + 1), content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("too large", response.json()["errors"])
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_oversized_report_rejected_before_any_database_queries(self):
        response = self.client.post("/api/reports/", "x" * (1024 * 1024 + 1), content_type="application/json")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.headers["Content-Type"], "application/json")

    def test_unauthenticated_reports_cannot_be_cached(self):
        response = self.client.get("/api/reports/")
        self.assertEqual(response.status_code, 401)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertTrue({"Cookie", "X-Store-ID"}.issubset(set(response.headers["Vary"].split(", "))))

    def test_csrf_failure_cannot_be_cached(self):
        response = Client(enforce_csrf_checks=True).post(reverse("login"), {}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("no-store", response.headers["Cache-Control"])

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_trusted_proxy_https_does_not_cause_redirect_loops(self):
        response = self.client.get(reverse("health"), HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("health")).status_code, 301)

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=None)
    def test_untrusted_proxy_header_cannot_bypass_https_redirect(self):
        response = self.client.get(reverse("health"), HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response.status_code, 301)
