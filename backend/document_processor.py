"""
Processador de documentos melhorado com pré-processamento, 
cache, retry e fallback OCR.
"""
import base64
import hashlib
import io
import json
import logging
import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageEnhance
from tenacity import retry, stop_after_attempt, retry_if_exception_type, wait_fixed

from ai_provider import OllamaProvider

logger = logging.getLogger(__name__)

# Cache simples em memória (em produção, use Redis ou similar)
_cache_resultados = {}

# Tipos de documentos suportados
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


def preprocessar_imagem(img: Image.Image, melhorar_contraste: bool = True) -> Image.Image:
    """
    Pré-processa a imagem para melhorar a extração OCR.
    Converte para RGB, ajusta contraste e brilho se necessário.
    """
    # Converte para RGB se necessário
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    if melhorar_contraste:
        # Aumenta contraste levemente para melhorar legibilidade
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)  # 20% mais contraste
        
        # Aumenta nitidez
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.5)
    
    # Converte para numpy para verificação de qualidade (opcional)
    img_array = np.array(img)
    
    # Verifica se a imagem está muito escura/clara e ajusta
    media_brilho = np.mean(img_array)
    if media_brilho < 50:  # Muito escura
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.3)
    elif media_brilho > 200:  # Muito clara
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(0.9)
    
    return img


def converter_pdf_para_imagens(pdf_bytes: bytes, dpi: int = 200) -> list[Image.Image]:
    """
    Converte PDF em imagens usando PyMuPDF (fitz).
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        imagens = []

        for numero_pagina in range(len(doc)):
            pagina = doc[numero_pagina]
            # DPI configurável
            matriz = fitz.Matrix(dpi / 72, dpi / 72)
            pixmap = pagina.get_pixmap(matrix=matriz, colorspace=fitz.csRGB)
            img_bytes = pixmap.tobytes("jpeg")
            imagem = Image.open(io.BytesIO(img_bytes))
            
            # Pré-processamento imediato
            imagem = preprocessar_imagem(imagem)
            imagens.append(imagem)

        doc.close()
        return imagens

    except Exception as e:
        logger.error(f"Erro ao converter PDF: {e}")
        raise ValueError(f"Não foi possível converter o PDF: {str(e)}")


def imagem_para_bytes(imagem: Image.Image, qualidade: int = 95) -> bytes:
    """Converte imagem PIL para bytes JPEG."""
    buffer = io.BytesIO()
    if imagem.mode not in ("RGB", "L"):
        imagem = imagem.convert("RGB")
    imagem.save(buffer, format="JPEG", quality=qualidade, optimize=True)
    return buffer.getvalue()


def extrair_json_resposta(texto: str) -> dict:
    """
    Extrai JSON da resposta do modelo, limpando markdown e outros textos.
    """
    texto_limpo = texto.strip()
    
    # Remove marcadores de código markdown
    if texto_limpo.startswith("```"):
        linhas = texto_limpo.split("\n")
        # Remove primeira linha (```json ou ```)
        if linhas[0].startswith("```"):
            linhas = linhas[1:]
        # Remove última linha se for ```
        if linhas and linhas[-1].strip() == "```":
            linhas = linhas[:-1]
        texto_limpo = "\n".join(linhas).strip()
    
    # Tenta encontrar JSON entre chaves se houver texto antes/depois
    if not texto_limpo.startswith("{"):
        inicio = texto_limpo.find("{")
        if inicio != -1:
            fim = texto_limpo.rfind("}")
            if fim != -1:
                texto_limpo = texto_limpo[inicio:fim+1]
    
    return json.loads(texto_limpo)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(1),
    retry=retry_if_exception_type((json.JSONDecodeError, KeyError)),
    reraise=True
)
def tentar_extracao_json(provider: OllamaProvider, prompt: str, imagens_base64: list[str]) -> dict:
    """
    Tenta extrair JSON com retry automático se o parsing falhar.
    """
    texto_resposta = provider.gerar_conteudo(prompt, imagens_base64)
    return extrair_json_resposta(texto_resposta)


def fallback_ocr_extracao(img_bytes: bytes) -> dict:
    """
    Fallback usando OCR tradicional + LLM (se disponível).
    Só executa se pytesseract estiver instalado.
    """
    try:
        import pytesseract
        from PIL import Image
        
        img = Image.open(io.BytesIO(img_bytes))
        texto = pytesseract.image_to_string(img, lang='por')
        
        # Aqui você poderia chamar um segundo LLM só para estruturar o texto
        # Por enquanto, retorna estrutura básica
        return {
            "tipo_documento": "DESCONHECIDO",
            "dados": {},
            "texto_bruto": texto,
            "metodo": "ocr_tradicional"
        }
    except ImportError:
        raise Exception("PyTesseract não instalado e extração via Vision falhou")


def calcular_hash_conteudo(conteudo: bytes) -> str:
    """Calcula hash MD5 do conteúdo para cache."""
    return hashlib.md5(conteudo).hexdigest()


def processar_documento(
    arquivo_bytes: bytes,
    nome_arquivo: str,
    provider: OllamaProvider,
    usar_cache: bool = True,
    tentar_fallback: bool = False
) -> dict:
    """
    Processa um único documento e retorna os dados extraídos.
    
    Args:
        arquivo_bytes: Conteúdo do arquivo em bytes
        nome_arquivo: Nome original do arquivo
        provider: Instância do provedor de IA configurado
        usar_cache: Se deve usar cache (default: True)
        tentar_fallback: Se deve tentar OCR tradicional em caso de falha (default: False)
    
    Returns:
        Dicionário com tipo_documento e dados extraídos
    """
    extensao = Path(nome_arquivo).suffix.lower()
    
    # Verifica cache
    if usar_cache:
        cache_key = calcular_hash_conteudo(arquivo_bytes)
        if cache_key in _cache_resultados:
            logger.info(f"Cache hit para {nome_arquivo}")
            return _cache_resultados[cache_key]
    
    imagens: list[Image.Image] = []

    if extensao == ".pdf":
        imagens = converter_pdf_para_imagens(arquivo_bytes)
    elif extensao in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}:
        img = Image.open(io.BytesIO(arquivo_bytes))
        img = preprocessar_imagem(img)
        imagens = [img]
    else:
        raise ValueError(f"Formato de arquivo não suportado: {extensao}")

    if not imagens:
        raise ValueError("Nenhuma imagem pôde ser extraída do arquivo")

    # Processa até 3 páginas/imagens por arquivo
    imagens_base64 = []
    for img in imagens[:3]:
        img_bytes = imagem_para_bytes(img, qualidade=90)  # Qualidade ligeiramente reduzida para performance
        imagens_base64.append(base64.b64encode(img_bytes).decode("utf-8"))

    try:
        # Tenta extração com retry automático
        resultado = tentar_extracao_json(provider, PROMPT_EXTRACAO, imagens_base64)
        
        # Valida estrutura básica
        if "tipo_documento" not in resultado:
            raise KeyError("Campo 'tipo_documento' não encontrado na resposta")
            
        # Adiciona metadados de processamento
        resultado["_metadados"] = {
            "paginas_processadas": len(imagens_base64),
            "arquivo": nome_arquivo
        }
        
        # Salva no cache
        if usar_cache:
            cache_key = calcular_hash_conteudo(arquivo_bytes)
            _cache_resultados[cache_key] = resultado
            
        return resultado

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Erro ao parsear JSON do modelo para {nome_arquivo}: {e}")
        
        if tentar_fallback:
            logger.info(f"Tentando fallback OCR para {nome_arquivo}")
            try:
                # Usa apenas a primeira imagem para fallback
                img_bytes = base64.b64decode(imagens_base64[0])
                return fallback_ocr_extracao(img_bytes)
            except Exception as e_fallback:
                logger.error(f"Fallback também falhou: {e_fallback}")
                raise ValueError(f"Falha na extração: {str(e)}. Fallback: {str(e_fallback)}")
        else:
            raise ValueError(f"Resposta da IA não é JSON válido: {str(e)}. Resposta: {getattr(e, 'ultima_resposta', 'N/A')}")
    
    except Exception as e:
        logger.error(f"Erro inesperado ao processar {nome_arquivo}: {e}")
        raise ValueError(f"Erro no processamento: {str(e)}")


def limpar_cache():
    """Limpa o cache em memória."""
    global _cache_resultados
    _cache_resultados.clear()
    logger.info("Cache limpo")
