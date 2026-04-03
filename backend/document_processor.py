"""
Processador de documentos usando Google Gemini AI.
"""
import io
import json
import logging
import base64
from pathlib import Path

import google.generativeai as genai
from PIL import Image

logger = logging.getLogger(__name__)

TIPOS_DOCUMENTOS = ["CNH", "MOPP", "NR20", "NR35", "Licenciamento", "CIV", "CIPP", "Calibragem", "Cronotacógrafo"]

PROMPT_EXTRACAO = """Você é um sistema especializado em leitura e extração de dados de documentos brasileiros de transporte e segurança do trabalho.

Analise a imagem fornecida e:

1. IDENTIFIQUE o tipo do documento. Os tipos possíveis são:
   - CNH (Carteira Nacional de Habilitação)
   - MOPP (Movimentação Operacional de Produtos Perigosos)
   - NR20 (Norma Regulamentadora 20 - Líquidos Combustíveis)
   - NR35 (Norma Regulamentadora 35 - Trabalho em Altura)
   - Licenciamento (Licenciamento de veículo / CRLV)
   - CIV (Certificado de Inspeção Veicular)
   - CIPP (Certificado de Inspeção de Pressão e Peso)
   - Calibragem (Certificado/Registro de calibragem de equipamento)
   - Cronotacógrafo (Certificado de aferição de cronotacógrafo)
   - DESCONHECIDO (se não for nenhum dos tipos acima)

2. EXTRAIA os dados conforme o tipo identificado.

3. Para cada campo extraído, indique se tem BAIXA CONFIANÇA (true/false):
   - baixa_confianca = true: quando o texto está borrado, cortado, ilegível ou você não tem certeza
   - baixa_confianca = false: quando o texto está claro e você tem certeza do valor

4. Retorne APENAS um JSON válido, sem texto adicional, sem markdown, sem explicações.

Estrutura do JSON por tipo de documento:

CNH:
{
  "tipo_documento": "CNH",
  "dados": {
    "nome": {"valor": "...", "baixa_confianca": false},
    "cpf": {"valor": "...", "baixa_confianca": false},
    "numero_cnh": {"valor": "...", "baixa_confianca": false},
    "data_nascimento": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "data_validade": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "categoria": {"valor": "...", "baixa_confianca": false}
  }
}

MOPP:
{
  "tipo_documento": "MOPP",
  "dados": {
    "nome": {"valor": "...", "baixa_confianca": false},
    "data_validade": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "numero_certificado": {"valor": "...", "baixa_confianca": false}
  }
}

NR20 ou NR35:
{
  "tipo_documento": "NR20",
  "dados": {
    "nome_trabalhador": {"valor": "...", "baixa_confianca": false},
    "tipo_curso": {"valor": "...", "baixa_confianca": false},
    "data_emissao": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "data_validade": {"valor": "DD/MM/AAAA", "baixa_confianca": false}
  }
}

Licenciamento:
{
  "tipo_documento": "Licenciamento",
  "dados": {
    "placa": {"valor": "...", "baixa_confianca": false},
    "renavam": {"valor": "...", "baixa_confianca": false},
    "ano": {"valor": "...", "baixa_confianca": false},
    "situacao": {"valor": "...", "baixa_confianca": false}
  }
}

CIV:
{
  "tipo_documento": "CIV",
  "dados": {
    "numero_civ": {"valor": "...", "baixa_confianca": false},
    "validade": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "placa": {"valor": "...", "baixa_confianca": false}
  }
}

CIPP:
{
  "tipo_documento": "CIPP",
  "dados": {
    "numero_cipp": {"valor": "...", "baixa_confianca": false},
    "validade": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "placa": {"valor": "...", "baixa_confianca": false}
  }
}

Calibragem:
{
  "tipo_documento": "Calibragem",
  "dados": {
    "data_calibracao": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "validade": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "identificacao_equipamento": {"valor": "...", "baixa_confianca": false}
  }
}

Cronotacógrafo:
{
  "tipo_documento": "Cronotacógrafo",
  "dados": {
    "numero_certificado": {"valor": "...", "baixa_confianca": false},
    "data_aferimento": {"valor": "DD/MM/AAAA", "baixa_confianca": false},
    "validade": {"valor": "DD/MM/AAAA", "baixa_confianca": false}
  }
}

DESCONHECIDO:
{
  "tipo_documento": "DESCONHECIDO",
  "dados": {}
}

IMPORTANTE:
- Use null para campos não encontrados no documento
- Corrija pequenos erros de OCR em nomes (ex: "JOÂO" → "JOÃO")
- Datas sempre no formato DD/MM/AAAA quando possível
- Retorne SOMENTE o JSON, sem nenhum texto antes ou depois
"""


def converter_pdf_para_imagens(pdf_bytes: bytes) -> list[Image.Image]:
    """
    Converte um PDF em lista de imagens PIL usando PyMuPDF (fitz).
    Não requer Poppler nem nenhuma dependência externa do sistema.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        imagens = []

        for numero_pagina in range(len(doc)):
            pagina = doc[numero_pagina]
            # DPI 200 → zoom = 200/72 ≈ 2.78
            matriz = fitz.Matrix(200 / 72, 200 / 72)
            pixmap = pagina.get_pixmap(matrix=matriz, colorspace=fitz.csRGB)
            img_bytes = pixmap.tobytes("jpeg")
            imagem = Image.open(io.BytesIO(img_bytes))
            imagens.append(imagem)

        doc.close()
        return imagens

    except Exception as e:
        logger.error(f"Erro ao converter PDF: {e}")
        raise ValueError(f"Não foi possível converter o PDF: {str(e)}")


def imagem_para_bytes(imagem: Image.Image, formato: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    imagem.save(buffer, format=formato, quality=95)
    return buffer.getvalue()


def processar_documento(
    arquivo_bytes: bytes,
    nome_arquivo: str,
    modelo_gemini: genai.GenerativeModel
) -> dict:
    extensao = Path(nome_arquivo).suffix.lower()
    imagens: list[Image.Image] = []

    if extensao == ".pdf":
        imagens = converter_pdf_para_imagens(arquivo_bytes)
    elif extensao in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"]:
        imagem = Image.open(io.BytesIO(arquivo_bytes))
        imagens = [imagem]
    else:
        raise ValueError(f"Formato de arquivo não suportado: {extensao}")

    if not imagens:
        raise ValueError("Nenhuma imagem pôde ser extraída do arquivo")

    imagens_para_processar = imagens[:3]
    partes = [PROMPT_EXTRACAO]

    for img in imagens_para_processar:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img_bytes = imagem_para_bytes(img)
        partes.append({
            "mime_type": "image/jpeg",
            "data": base64.b64encode(img_bytes).decode("utf-8")
        })

    resposta = modelo_gemini.generate_content(partes)
    texto_resposta = resposta.text.strip()

    if texto_resposta.startswith("```"):
        linhas = texto_resposta.split("\n")
        if linhas[0].startswith("```"):
            linhas = linhas[1:]
        if linhas and linhas[-1].strip() == "```":
            linhas = linhas[:-1]
        texto_resposta = "\n".join(linhas)

    return json.loads(texto_resposta)
