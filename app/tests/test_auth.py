from fichas.auth import get_password_hash
from fichas.models import User


def test_login_success(client, db_session):
    user = User(email="admin@test.com", hashed_password=get_password_hash("secret"), is_admin=True)
    db_session.add(user)
    db_session.commit()

    response = client.post("/login", data={"email": "admin@test.com", "password": "secret"}, follow_redirects=False)
    assert response.status_code == 303
    assert "session=" in response.headers.get("set-cookie", "")


def test_login_failure(client, db_session):
    user = User(email="admin@test.com", hashed_password=get_password_hash("secret"), is_admin=True)
    db_session.add(user)
    db_session.commit()

    response = client.post("/login", data={"email": "admin@test.com", "password": "wrong"})
    assert response.status_code == 401
    assert "Credenciais invalidas" in response.text
