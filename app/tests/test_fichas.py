from fichas.auth import get_password_hash
from sqlalchemy import select

from fichas.models import Ficha, FichaTemplate, Process, User


def login(client, db_session):
    user = User(email="admin@test.com", hashed_password=get_password_hash("secret"), is_admin=True)
    db_session.add(user)
    db_session.commit()
    response = client.post("/login", data={"email": "admin@test.com", "password": "secret"}, follow_redirects=False)
    assert response.status_code == 303
    return response.cookies


def test_create_ficha(client, db_session):
    cookies = login(client, db_session)

    process = Process(process_key="PROC-002", tc_numero="TC456", ano=2024)
    template = FichaTemplate(
        nome="Template X",
        descricao="",
        schema_json=[{"name": "campo_extra", "label": "Campo Extra", "type": "text", "required": True}],
    )
    db_session.add(process)
    db_session.add(template)
    db_session.commit()

    response = client.post(
        "/fichas/nova",
        data={
            "process_id": str(process.id),
            "template_id": str(template.id),
            "tc_numero": "TC456",
            "ano": "2024",
            "interessado": "Fulano",
            "assunto": "Assunto",
            "extra__campo_extra": "Valor",
        },
        cookies=cookies,
        follow_redirects=False,
    )
    assert response.status_code == 303

    list_response = client.get("/fichas", cookies=cookies)
    assert "Template X" in list_response.text


def test_create_ficha_manual(client, db_session):
    cookies = login(client, db_session)

    template = FichaTemplate(
        nome="Template Manual",
        descricao="",
        schema_json=[{"name": "campo_extra", "label": "Campo Extra", "type": "text", "required": True}],
    )
    db_session.add(template)
    db_session.commit()

    response = client.post(
        "/fichas/nova",
        data={
            "manual": "1",
            "template_id": str(template.id),
            "process_key": "PROC-003",
            "tc_numero": "TC789",
            "ano": "2024",
            "interessado": "Beltrano",
            "assunto": "Assunto manual",
            "extra__campo_extra": "Valor",
        },
        cookies=cookies,
        follow_redirects=False,
    )
    assert response.status_code == 303

    list_response = client.get("/fichas", cookies=cookies)
    assert "Template Manual" in list_response.text


def test_delete_ficha(client, db_session):
    cookies = login(client, db_session)

    process = Process(process_key="PROC-DELETE", tc_numero="TC000", ano=2024)
    template = FichaTemplate(
        nome="Template Delete",
        descricao="",
        schema_json=[{"name": "campo_extra", "label": "Campo Extra", "type": "text", "required": False}],
    )
    db_session.add(process)
    db_session.add(template)
    db_session.commit()

    response = client.post(
        "/fichas/nova",
        data={
            "process_id": str(process.id),
            "template_id": str(template.id),
            "tc_numero": "TC000",
            "ano": "2024",
            "interessado": "Teste",
            "assunto": "Assunto",
        },
        cookies=cookies,
        follow_redirects=False,
    )
    assert response.status_code == 303

    list_response = client.get("/fichas", cookies=cookies)
    assert "Template Delete" in list_response.text

    ficha_id = db_session.execute(select(Ficha.id).where(Ficha.process_id == process.id)).scalar_one()
    delete_response = client.post(f"/fichas/{ficha_id}/excluir", cookies=cookies, follow_redirects=False)
    assert delete_response.status_code == 303

    db_session.expire_all()
    ficha_row = db_session.execute(select(Ficha).where(Ficha.process_id == process.id)).scalar_one_or_none()
    assert ficha_row is None
