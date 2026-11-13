from tests.conftest import PASSWORD


def test_register_login_me(client):
    r = client.post("/auth/register", json={"email": "New@Example.com", "password": PASSWORD})
    assert r.status_code == 201
    assert r.json()["email"] == "new@example.com"  # stored lower-case
    assert "password" not in r.text and "password_hash" not in r.text

    token = client.post("/auth/login", json={"email": "new@example.com", "password": PASSWORD}).json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["is_admin"] is False


def test_duplicate_email_rejected(client):
    body = {"email": "a@example.com", "password": PASSWORD}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409


def test_short_password_rejected(client):
    r = client.post("/auth/register", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_wrong_password_and_unknown_email_give_same_error(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    wrong_pw = client.post("/auth/login", json={"email": "a@example.com", "password": "WrongPass999"})
    no_user = client.post("/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_protected_route_needs_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"}).status_code == 401


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
