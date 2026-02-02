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
    assert base["process_key"]["value"] == "123"
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


def test_map_fields_to_ficha_layout_blocks():
    text = "\n".join(
        [
            "PR 16",
            "TC",
            "6650/80",
            "to no 11 180",
            "INTERESSADO",
            "ANO",
            "1980",
            "ENCADERNADORA UNIVERSITARIA LTDA",
            "PROCEDÊNCIA",
            "Of. 496/80 SMC.DBP.",
            "ASSUNTO",
            "DATA",
            "23.10.80",
            "REPARTIÇÃO",
            "valor C$98.400,00",
            "CARTA CONVITE 19/80",
            "ENCADERNAÇÃO DE 41 VOLUMES DO JORNAL \"CORREIO PAULIS",
            "TANO\"DESENCADERNADOS PARA MICROFILMAGEM DENTRO",
            "PROJETO DO DEPARTAMENTO DE BIBLIOTECAS PUBLICAS",
            "DO",
            "OBS.:-",
            "IDT",
            "PROC. 02.046.799.80*17",
        ]
    )
    ocr_items = [{"text": line, "confidence": 0.85, "bbox": None} for line in text.splitlines()]
    suggestions = map_fields_to_ficha(text, ocr_items, None)

    base = suggestions["base"]
    assert base["tc_numero"]["value"] == "6650/80"
    assert base["ano"]["value"] == "1980"
    assert base["data"]["value"] == "1980-10-23"
    assert base["interessado"]["value"] == "ENCADERNADORA UNIVERSITARIA LTDA"
    assert base["procedencia"]["value"] == "Of. 496/80 SMC.DBP."
    assert base["valor"]["value"] == "98400.00"
    assert "assunto" in base
    assert "CARTA CONVITE 19/80" in base["assunto"]["value"]
    assert "REPARTICAO" not in base["assunto"]["value"]
    assert "PROJETO DO DEPARTAMENTO" in base["assunto"]["value"]
    assert base["observacoes"]["value"] == "IDT"
    assert base["process_key"]["value"] == "02.046.799.80*17"
