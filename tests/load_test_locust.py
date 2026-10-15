"""
creditsense/tests/load_test_locust.py
-------------------------------------
Locust Load Testing Suite for CreditSense Underwriting Gateway.
Simulates concurrent applicants submitting loan applications, polling status, and fetching audit trails.

Usage:
    locust -f tests/load_test_locust.py --host=http://localhost:8000
    locust -f tests/load_test_locust.py --headless -u 50 -r 10 --run-time 1m --host=http://localhost:8000
"""

import random
from locust import HttpUser, task, between


class CreditSenseLoadUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(3)
    def submit_standard_application(self):
        payload = {
            "applicant_name": f"LoadTest User {random.randint(1000, 99999)}",
            "applicant_email": f"user{random.randint(1000, 99999)}@example.com",
            "annual_income": random.choice([45000, 75000, 120000, 250000]),
            "requested_amount": random.choice([5000, 15000, 30000, 50000]),
            "loan_purpose": random.choice(["debt_consolidation", "home_improvement", "small_business", "credit_card"]),
            "credit_score": random.randint(580, 820),
            "monthly_debt_obligations": random.choice([500, 1200, 2500, 4000]),
            "employment_length_years": random.randint(1, 15),
            "home_ownership": random.choice(["RENT", "MORTGAGE", "OWN"]),
            "citizenship_status": "US_CITIZEN",
            "tax_id": f"999-00-{random.randint(1000, 9999)}",
        }

        with self.client.post("/api/v1/applications", json=payload, catch_response=True) as response:
            if response.status_code in (200, 202):
                data = response.json()
                app_id = data.get("application_id")
                if app_id:
                    # Poll status
                    self.client.get(f"/api/v1/applications/{app_id}", name="/api/v1/applications/[id]")
            else:
                response.failure(f"Unexpected status code: {response.status_code}")

    @task(1)
    def check_health_and_metrics(self):
        self.client.get("/api/v1/health")
        self.client.get("/api/v1/metrics")
