from fichas.services.ocr import map_fields_to_ficha
from fichas.schemas import TemplateSchema, TemplateSection, TemplateField


def test_map_fields_to_ficha_base():
    text = "\n".join(
        [
            "Processo: PROC-123",
            "TC Numero: 456",
            "Ano: 2024",
            "Interessado: Fulano",
            "Assunto: Contrato",
            "Valor: R$ 1.234,56",
        ]
    )
    ocr_items = [{"text": line, "confidence": 0.9, "bbox": None} for line in text.splitlines()]
    suggestions = map_fields_to_ficha(text, ocr_items, None)

    base = suggestions["base"]
    assert base["process_key"]["value"] == "PROC-123"
    assert base["tc_numero"]["value"] == "456"
    assert base["ano"]["value"] == "2024"
    assert base["valor"]["value"] == "1234.56"


def test_map_fields_to_ficha_extras():
    text = "Setor: Financeiro"
    ocr_items = [{"text": text, "confidence": 0.85, "bbox": None}]
    schema = TemplateSchema(
        sections=[
            TemplateSection(
                section_id="geral",
                label="Geral",
                fields=[TemplateField(field_id="setor", label="Setor", type="text")],
            )
        ]
    )

    suggestions = map_fields_to_ficha(text, ocr_items, schema)
    extras = suggestions["extras"]
    assert extras["setor"]["value"] == "Financeiro"
