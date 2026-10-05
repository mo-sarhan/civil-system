"""Authentication, refresh, and role-guard tests."""

from __future__ import annotations

from tests.conftest import TEST_PASSWORD, make_user


class TestLogin:
    def test_login_returns_both_tokens(self, client, users) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"] and body["refresh_token"]
        assert body["user"]["role"] == "admin"
        assert body["user"]["must_change_password"] is False

    def test_wrong_password_is_401(self, client, users) -> None:
        response = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
        )
        assert response.status_code == 401

    def test_unknown_user_is_401(self, client, users) -> None:
        response = client.post(
            "/api/v1/auth/login", json={"username": "ghost", "password": TEST_PASSWORD}
        )
        assert response.status_code == 401

    def test_inactive_user_cannot_log_in(self, client, db) -> None:
        from app.models.user import User

        make_user("sleepy", "editor")
        user = db.query(User).filter(User.username == "sleepy").one()
        user.is_active = False
        db.commit()
        response = client.post(
            "/api/v1/auth/login", json={"username": "sleepy", "password": TEST_PASSWORD}
        )
        assert response.status_code == 401

    def test_lockout_after_repeated_failures(self, client, users) -> None:
        for _ in range(5):
            client.post(
                "/api/v1/auth/login", json={"username": "editor", "password": "bad-password"}
            )
        response = client.post(
            "/api/v1/auth/login", json={"username": "editor", "password": TEST_PASSWORD}
        )
        # Correct password is refused while the lockout window is open.
        assert response.status_code == 401
        assert "قفل الحساب" in response.json()["detail"]

    def test_admin_can_unlock_an_account(self, client, auth, users) -> None:
        for _ in range(5):
            client.post(
                "/api/v1/auth/login", json={"username": "editor", "password": "bad-password"}
            )
        unlock = client.post(f"/api/v1/users/{users['editor'].id}/unlock", headers=auth("admin"))
        assert unlock.status_code == 200
        again = client.post(
            "/api/v1/auth/login", json={"username": "editor", "password": TEST_PASSWORD}
        )
        assert again.status_code == 200


class TestTokens:
    def test_me_requires_a_token(self, client) -> None:
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_me_returns_the_current_user(self, client, auth) -> None:
        response = client.get("/api/v1/auth/me", headers=auth("viewer"))
        assert response.status_code == 200
        assert response.json()["username"] == "viewer"

    def test_refresh_returns_a_new_access_token(self, client, users) -> None:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD}
        ).json()
        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_access_token_is_not_accepted_as_a_refresh_token(self, client, users) -> None:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD}
        ).json()
        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login["access_token"]}
        )
        assert response.status_code == 401

    def test_garbage_token_is_rejected(self, client) -> None:
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert response.status_code == 401


class TestChangePassword:
    def test_change_password_then_login_with_the_new_one(self, client, users) -> None:
        headers = {
            "Authorization": "Bearer "
            + client.post(
                "/api/v1/auth/login", json={"username": "editor", "password": TEST_PASSWORD}
            ).json()["access_token"]
        }
        response = client.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={
                "current_password": TEST_PASSWORD,
                "new_password": "Brand#New12345",
            },
        )
        assert response.status_code == 200
        again = client.post(
            "/api/v1/auth/login",
            json={"username": "editor", "password": "Brand#New12345"},
        )
        assert again.status_code == 200

    def test_short_password_is_rejected(self, client, auth) -> None:
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth("editor"),
            json={"current_password": TEST_PASSWORD, "new_password": "short"},
        )
        assert response.status_code in (400, 422)

    def test_wrong_current_password_is_rejected(self, client, auth) -> None:
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth("editor"),
            json={"current_password": "not-it", "new_password": "Brand#New12345"},
        )
        assert response.status_code in (400, 401)


class TestRoleGuards:
    def test_viewer_cannot_create_a_person(self, client, auth, sample_family) -> None:
        response = client.post(
            "/api/v1/persons",
            headers=auth("viewer"),
            json={"full_name": "شخص جديد", "gender": "M"},
        )
        assert response.status_code == 403

    def test_viewer_can_read(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/persons", headers=auth("viewer"))
        assert response.status_code == 200

    def test_editor_cannot_list_users(self, client, auth) -> None:
        assert client.get("/api/v1/users", headers=auth("editor")).status_code == 403

    def test_admin_can_list_users(self, client, auth) -> None:
        assert client.get("/api/v1/users", headers=auth("admin")).status_code == 200

    def test_editor_cannot_delete_a_person(self, client, auth, sample_family) -> None:
        response = client.delete(f"/api/v1/persons/{sample_family['1']}", headers=auth("editor"))
        assert response.status_code == 403
