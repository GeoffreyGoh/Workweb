"""Login, tokens, and route protection."""

import pytest
from jose import jwt

import auth


class TestLogin:
    def test_valid_credentials_return_a_token(self, client, users):
        response = client.post("/auth/login",
                               json={"username": "admin", "password": "admin123"})
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        claims = jwt.decode(body["access_token"], auth.SECRET_KEY,
                            algorithms=[auth.ALGORITHM])
        assert claims["sub"] == "admin"
        assert claims["role"] == "admin"
        assert "exp" in claims

    def test_wrong_password_is_401(self, client, users):
        response = client.post("/auth/login",
                               json={"username": "admin", "password": "nope"})
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_unknown_user_is_401(self, client, users):
        response = client.post("/auth/login",
                               json={"username": "ghost", "password": "whatever"})
        assert response.status_code == 401

    def test_deactivated_user_cannot_log_in(self, client, users):
        response = client.post("/auth/login",
                               json={"username": "gone", "password": "gone123"})
        assert response.status_code == 401

    def test_error_does_not_reveal_which_field_was_wrong(self, client, users):
        bad_user = client.post("/auth/login",
                               json={"username": "ghost", "password": "x"}).json()
        bad_pass = client.post("/auth/login",
                               json={"username": "admin", "password": "x"}).json()
        assert bad_user["detail"] == bad_pass["detail"]

    def test_missing_fields_are_422(self, client, users):
        assert client.post("/auth/login", json={"username": "admin"}).status_code == 422


class TestPasswordHashing:
    def test_hash_is_not_the_plain_text(self):
        hashed = auth.hash_password("secret123")
        assert hashed != "secret123"
        assert hashed.startswith("$2")

    def test_verify_round_trip(self):
        hashed = auth.hash_password("secret123")
        assert auth.verify_password("secret123", hashed)
        assert not auth.verify_password("secret124", hashed)

    def test_same_password_hashes_differently(self):
        # bcrypt salts, so two hashes of one password must not match
        assert auth.hash_password("same") != auth.hash_password("same")


class TestCurrentUser:
    def test_me_returns_the_signed_in_user(self, client, admin):
        body = client.get("/auth/me", headers=admin).json()
        assert body["username"] == "admin"
        assert body["role"] == "admin"

    def test_me_never_leaks_the_password_hash(self, client, admin):
        assert "password_hash" not in client.get("/auth/me", headers=admin).json()

    def test_no_token_is_401(self, client, users):
        assert client.get("/auth/me").status_code == 401

    def test_garbage_token_is_401(self, client, users):
        response = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
        assert response.status_code == 401

    def test_token_signed_with_another_key_is_rejected(self, client, users):
        forged = jwt.encode({"sub": "admin", "role": "admin"}, "wrong-key",
                            algorithm=auth.ALGORITHM)
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401

    def test_expired_token_is_rejected(self, client, users, monkeypatch):
        monkeypatch.setattr(auth, "ACCESS_TOKEN_EXPIRE_MINUTES", -1)
        stale = auth.create_access_token("admin", "admin")
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {stale}"})
        assert response.status_code == 401

    def test_token_for_a_deleted_user_is_rejected(self, client, users, db):
        import models
        token = auth.create_access_token("budi", "user")
        db.query(models.User).filter(models.User.username == "budi").delete()
        db.commit()
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_token_for_a_deactivated_user_is_rejected(self, client, users, db):
        import models
        token = auth.create_access_token("budi", "user")
        db.query(models.User).filter(models.User.username == "budi").update(
            {"is_active": False})
        db.commit()
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


PROTECTED = [
    ("get", "/products"),
    ("get", "/customers"),
    ("get", "/suppliers"),
    ("get", "/quotations"),
    ("get", "/sales-orders"),
    ("get", "/purchase-orders"),
    ("get", "/receipts"),
    ("get", "/reports/sales"),
    ("get", "/reports/financial"),
    ("get", "/documents/quotations/1.pdf"),
    ("post", "/quotations"),
    ("post", "/sales-orders"),
    ("post", "/purchase-orders"),
    ("post", "/receipts"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_route_requires_a_token(client, users, method, path):
    response = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert response.status_code == 401, f"{method.upper()} {path} was reachable"


def test_health_and_login_stay_public(client, users):
    assert client.get("/health").status_code == 200
