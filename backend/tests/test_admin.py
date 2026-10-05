"""Admin surface: audit trail browsing, filters, summaries and access control."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.audit import AuditLog

NEW_PERSON = {
    "national_id": "29105045100011",
    "full_name": "سعيد عبد الله سعيد",
    "gender": "M",
    "birth_date": "1991-05-04",
    "birth_place": "الإسكندرية",
}


def _payload(index: int = 0) -> dict:
    """A unique payload; ``index`` shifts the serial part of the national id."""
    payload = dict(NEW_PERSON)
    payload["national_id"] = f"291050451{index:03d}10"
    payload["full_name"] = f"سعيد عبد الله سعيد {index}"
    return payload


def _create_person(client, auth, role: str = "editor", index: int = 0) -> dict:
    response = client.post("/api/v1/persons", json=_payload(index), headers=auth(role))
    assert response.status_code == 201, response.text
    return response.json()


class TestAccessControl:
    def test_only_admin_may_read_the_audit_log(self, client, auth, sample_family) -> None:
        for role in ("viewer", "editor"):
            response = client.get("/api/v1/audit-log", headers=auth(role))
            assert response.status_code == 403, role

    def test_anonymous_access_is_rejected(self, client, sample_family) -> None:
        assert client.get("/api/v1/audit-log").status_code == 401

    def test_admin_may_read_it(self, client, auth, sample_family) -> None:
        assert client.get("/api/v1/audit-log", headers=auth("admin")).status_code == 200


class TestAuditTrail:
    def test_person_writes_are_recorded(self, client, auth, sample_family) -> None:
        created = _create_person(client, auth)
        person_id = created["id"]

        updated = client.patch(
            f"/api/v1/persons/{person_id}",
            json={"notes": "تحديث"},
            headers=auth("editor"),
        )
        assert updated.status_code == 200, updated.text
        client.delete(f"/api/v1/persons/{person_id}", headers=auth("admin"))

        body = client.get(
            "/api/v1/audit-log?entity=person&page_size=200", headers=auth("admin")
        ).json()
        actions = [entry["action"] for entry in body["items"]]
        assert {"CREATE", "UPDATE", "DELETE"} <= set(actions)

        entries = {entry["action"]: entry for entry in body["items"]}
        assert entries["CREATE"]["entity_id"] == person_id
        assert entries["CREATE"]["username"] == "editor"
        assert entries["UPDATE"]["details"]
        assert entries["DELETE"]["username"] == "admin"

    def test_login_is_recorded_with_the_client_ip(self, client, auth, sample_family) -> None:
        for role in ("admin", "editor", "viewer"):
            client.get("/api/v1/persons?page_size=1", headers=auth(role))
        body = client.get(
            "/api/v1/audit-log?action=LOGIN&page_size=50", headers=auth("admin")
        ).json()
        assert body["total"] >= 3  # admin, editor and viewer logged in
        assert {entry["username"] for entry in body["items"]} == {"admin", "editor", "viewer"}
        assert all(entry["ip"] for entry in body["items"])

    def test_search_and_view_are_recorded(self, client, auth, sample_family) -> None:
        client.get("/api/v1/persons?q=محمد", headers=auth("viewer"))
        client.get("/api/v1/persons/1", headers=auth("viewer"))
        body = client.get(
            "/api/v1/audit-log?action=SEARCH&page_size=50", headers=auth("admin")
        ).json()
        assert body["total"] >= 1
        assert body["items"][0]["entity"] == "person"

    def test_filters_by_action_and_username(self, client, auth, sample_family) -> None:
        _create_person(client, auth)
        by_action = client.get("/api/v1/audit-log?action=create", headers=auth("admin")).json()
        assert by_action["total"] >= 1
        assert all(entry["action"] == "CREATE" for entry in by_action["items"])

        by_user = client.get(
            "/api/v1/audit-log?username=admin&page_size=200", headers=auth("admin")
        ).json()
        assert all("admin" in entry["username"] for entry in by_user["items"])

        nobody = client.get("/api/v1/audit-log?username=no-such-user", headers=auth("admin")).json()
        assert nobody["total"] == 0
        assert nobody["items"] == []

    def test_filter_by_user_id_and_entity_id(self, client, auth, sample_family) -> None:
        created = _create_person(client, auth)
        editor_id = client.get("/api/v1/auth/me", headers=auth("editor")).json()["id"]

        by_user = client.get(
            f"/api/v1/audit-log?user_id={editor_id}&page_size=200",
            headers=auth("admin"),
        ).json()
        assert by_user["total"] >= 1
        assert all(entry["user_id"] == editor_id for entry in by_user["items"])

        by_entity_id = client.get(
            f"/api/v1/audit-log?entity=person&entity_id={created['id']}",
            headers=auth("admin"),
        ).json()
        assert by_entity_id["total"] == 1
        assert by_entity_id["items"][0]["entity_id"] == created["id"]

    def test_filter_by_date_range(self, client, auth, sample_family) -> None:
        _create_person(client, auth)
        now = datetime.now(UTC)
        inside = client.get(
            "/api/v1/audit-log",
            params={
                "date_from": (now - timedelta(minutes=5)).isoformat(),
                "date_to": (now + timedelta(minutes=5)).isoformat(),
            },
            headers=auth("admin"),
        ).json()
        assert inside["total"] >= 1

        outside = client.get(
            "/api/v1/audit-log",
            params={
                "date_from": (now + timedelta(days=1)).isoformat(),
                "date_to": (now + timedelta(days=2)).isoformat(),
            },
            headers=auth("admin"),
        ).json()
        assert outside["total"] == 0

    def test_results_are_paginated_newest_first(self, client, auth, sample_family) -> None:
        for index in range(5):
            _create_person(client, auth, index=index)

        first = client.get(
            "/api/v1/audit-log?action=CREATE&page=1&page_size=2", headers=auth("admin")
        ).json()
        assert first["total"] >= 5
        assert first["page"] == 1 and first["page_size"] == 2
        assert len(first["items"]) == 2

        second = client.get(
            "/api/v1/audit-log?action=CREATE&page=2&page_size=2", headers=auth("admin")
        ).json()
        assert first["items"][0]["id"] > second["items"][0]["id"]

    def test_page_size_is_capped(self, client, auth, sample_family) -> None:
        assert (
            client.get("/api/v1/audit-log?page_size=500", headers=auth("admin")).status_code == 422
        )


class TestAuditMetadataAndSummary:
    def test_actions_endpoint_lists_enum_values(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/audit-log/actions", headers=auth("admin")).json()
        assert "MERGE" in body["actions"]
        assert "IMPORT" in body["actions"]
        assert {"person", "marriage", "user"} <= set(body["entities"])

    def test_summary_groups_by_action_and_user(self, client, auth, sample_family) -> None:
        _create_person(client, auth, index=0)
        _create_person(client, auth, index=1)
        client.delete("/api/v1/persons/1", headers=auth("admin"))

        body = client.get("/api/v1/audit-log/export", headers=auth("admin")).json()
        assert body["total"] >= 4
        assert body["latest"] is not None
        assert body["by_action"]
        assert sum(row["count"] for row in body["by_action"]) == body["total"]
        assert {row["action"] for row in body["by_action"]} >= {"CREATE", "DELETE"}
        assert {row["username"] for row in body["top_users"]} >= {"editor", "admin"}
        assert body["by_action"][0]["count"] >= body["by_action"][-1]["count"]

    def test_summary_is_empty_on_a_fresh_database(self, client, auth, db) -> None:
        token = auth("admin")["Authorization"]
        db.query(AuditLog).delete()
        db.commit()
        body = client.get("/api/v1/audit-log/export", headers={"Authorization": token}).json()
        assert body["total"] == 0
        assert body["by_action"] == []
        assert body["top_users"] == []
        assert body["latest"] is None
