"""Marriage CRUD and validation tests."""

from __future__ import annotations


def marriage_payload(sample_family: dict[str, int], **overrides) -> dict:
    payload = {
        "husband_id": sample_family["11"],  # يوسف (M), unmarried in the sample
        "wife_id": sample_family["6"],  # دعاء (F), unmarried in the sample
        "start_date": "2020-01-01",
        "status": "married",
    }
    payload.update(overrides)
    return payload


class TestCreate:
    def test_create_and_read_back(self, client, auth, sample_family) -> None:
        created = client.post(
            "/api/v1/marriages", headers=auth("editor"), json=marriage_payload(sample_family)
        )
        assert created.status_code == 201, created.text
        listing = client.get("/api/v1/marriages", headers=auth("viewer")).json()
        assert listing["total"] == 6

    def test_husband_must_be_male(self, client, auth, sample_family) -> None:
        payload = marriage_payload(sample_family, husband_id=sample_family["10"])  # ياسمين (F)
        response = client.post("/api/v1/marriages", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_wife_must_be_female(self, client, auth, sample_family) -> None:
        payload = marriage_payload(sample_family, wife_id=sample_family["11"])  # يوسف (M)
        response = client.post("/api/v1/marriages", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_cannot_marry_yourself(self, client, auth, sample_family) -> None:
        payload = marriage_payload(
            sample_family, husband_id=sample_family["11"], wife_id=sample_family["11"]
        )
        response = client.post("/api/v1/marriages", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_duplicate_pair_conflicts(self, client, auth, sample_family) -> None:
        response = client.post(
            "/api/v1/marriages",
            headers=auth("editor"),
            json=marriage_payload(
                sample_family, husband_id=sample_family["1"], wife_id=sample_family["2"]
            ),
        )
        assert response.status_code == 409

    def test_end_before_start_is_rejected(self, client, auth, sample_family) -> None:
        payload = marriage_payload(sample_family, start_date="2020-01-01", end_date="2019-01-01")
        response = client.post("/api/v1/marriages", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_invalid_status_is_rejected(self, client, auth, sample_family) -> None:
        payload = marriage_payload(sample_family, status="pending")
        response = client.post("/api/v1/marriages", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_unknown_partner_is_404(self, client, auth, sample_family) -> None:
        payload = marriage_payload(sample_family, wife_id=99999)
        response = client.post("/api/v1/marriages", headers=auth("editor"), json=payload)
        assert response.status_code == 404

    def test_viewer_cannot_create(self, client, auth, sample_family) -> None:
        response = client.post(
            "/api/v1/marriages", headers=auth("viewer"), json=marriage_payload(sample_family)
        )
        assert response.status_code == 403


class TestReadAndUpdate:
    def test_filter_by_person(self, client, auth, sample_family) -> None:
        response = client.get(
            f"/api/v1/marriages?person_id={sample_family['1']}", headers=auth("viewer")
        )
        assert response.json()["total"] == 1

    def test_filter_by_status(self, client, auth, sample_family) -> None:
        # The sample has one ended marriage (widowed) and four current ones.
        assert (
            client.get("/api/v1/marriages?status=widowed", headers=auth("viewer")).json()["total"]
            == 1
        )
        assert (
            client.get("/api/v1/marriages?status=married", headers=auth("viewer")).json()["total"]
            == 4
        )

    def test_update_status_and_end_date(self, client, auth, sample_family) -> None:
        listing = client.get("/api/v1/marriages?status=married", headers=auth("viewer")).json()
        marriage_id = listing["items"][0]["id"]
        response = client.patch(
            f"/api/v1/marriages/{marriage_id}",
            headers=auth("editor"),
            json={"status": "widowed", "end_date": "2021-05-05"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "widowed"

    def test_delete(self, client, auth, sample_family) -> None:
        listing = client.get("/api/v1/marriages?status=married", headers=auth("viewer")).json()
        marriage_id = listing["items"][0]["id"]
        assert (
            client.delete(f"/api/v1/marriages/{marriage_id}", headers=auth("admin")).status_code
            == 200
        )
        assert (
            client.get("/api/v1/marriages?status=married", headers=auth("viewer")).json()["total"]
            == 3
        )
