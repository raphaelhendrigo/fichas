from fichas.schemas import normalize_template_schema
from fichas.services.fichas_service import parse_extras
from fichas.services.templates_service import import_template_payload


def template_payload():
    return {
        "nome": "Template Draft",
        "descricao": "Teste de importacao",
        "versao": 1,
        "origem_pdf": "exemplo.pdf",
        "is_active": True,
        "sections": [
            {
                "id": "geral",
                "label": "Geral",
                "order": 1,
                "fields": [
                    {
                        "id": "campo_obrigatorio",
                        "label": "Campo obrigatorio",
                        "type": "text",
                        "required": True,
                    }
                ],
            }
        ],
    }


def test_import_template_payload(db_session):
    payload = template_payload()
    template, created = import_template_payload(db_session, payload, user=None)
    assert created is True
    assert template.nome == "Template Draft"
    assert template.versao == 1

    template_again, created_again = import_template_payload(db_session, payload, user=None)
    assert created_again is False
    assert template_again.id == template.id


def test_parse_extras_required_field():
    payload = template_payload()
    schema = normalize_template_schema(payload)
    extras, errors = parse_extras({}, schema)
    assert extras.get("campo_obrigatorio") is None
    assert "campo_obrigatorio" in errors
