from django.test import SimpleTestCase
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
