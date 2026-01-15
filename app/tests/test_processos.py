from fichas.auth import get_password_hash
from fichas.models import User


def login(client, db_session):
    user = User(email="admin@test.com", hashed_password=get_password_hash("secret"), is_admin=True)
    db_session.add(user)
    db_session.commit()
    response = client.post("/login", data={"email": "admin@test.com", "password": "secret"}, follow_redirects=False)
    assert response.status_code == 303
    return response.cookies


def test_create_process(client, db_session):
    cookies = login(client, db_session)
    response = client.post(
        "/processos/novo",
        data={
            "process_key": "PROC-001",
            "tc_numero": "TC123",
            "ano": "2024",
            "interessado": "Interessado 1",
            "assunto": "Assunto 1",
        },
        cookies=cookies,
        follow_redirects=False,
    )
    assert response.status_code == 303

    list_response = client.get("/processos", cookies=cookies)
    assert "PROC-001" in list_response.text
