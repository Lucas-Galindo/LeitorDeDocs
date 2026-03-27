"""
API principal do sistema LeitorDeDocs.
Endpoints FastAPI para upload e processamento de documentos.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from document_processor import TIPOS_DOCUMENTOS, processar_documento
from models import RespostaProcessamento, ResultadoArquivo

# Carrega variáveis de ambiente
load_dotenv()

# Configuração de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Tamanho máximo de arquivo: 20MB
MAX_FILE_SIZE = 20 * 1024 * 1024

# Extensões permitidas
EXTENSOES_PERMITIDAS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}

# Instância global do modelo Gemini
modelo_gemini: Optional[genai.GenerativeModel] = None
gemini_disponivel: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação."""
    global modelo_gemini, gemini_disponivel

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        logger.warning(
            "⚠️  GEMINI_API_KEY não configurada. "
            "O servidor iniciou, mas o processamento de documentos estará desativado. "
            "Configure a chave no arquivo .env para ativar o processamento."
        )
        gemini_disponivel = False
    else:
        try:
            genai.configure(api_key=api_key)
            modelo_gemini = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config={
                    "temperature": 0.1,
                    "top_p": 0.95,
                    "max_output_tokens": 2048,
                }
            )
            gemini_disponivel = True
            logger.info("✅ Google Gemini configurado com sucesso")
        except Exception as e:
            logger.error(f"❌ Erro ao configurar Gemini: {e}")
            gemini_disponivel = False

    yield

    logger.info("Servidor encerrado")


# Cria a aplicação FastAPI
app = FastAPI(
    title="LeitorDeDocs API",
    description="Sistema de leitura e extração inteligente de documentos de transporte",
    version="1.0.0",
    lifespan=lifespan,
)

# Configuração CORS — permite requisições do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def raiz():
    """Endpoint de status da API."""
    return {
        "status": "online",
        "versao": "1.0.0",
        "gemini_disponivel": gemini_disponivel,
        "aviso": None if gemini_disponivel else (
            "GEMINI_API_KEY não configurada. "
            "Adicione a chave no arquivo .env para ativar o processamento."
        )
    }


@app.get("/status")
async def status():
    """Verifica o status da API e da integração com Gemini."""
    return {
        "api": "online",
        "gemini": "configurado" if gemini_disponivel else "não configurado",
        "tipos_suportados": TIPOS_DOCUMENTOS,
        "formatos_aceitos": list(EXTENSOES_PERMITIDAS),
        "tamanho_maximo_mb": MAX_FILE_SIZE // (1024 * 1024),
    }


@app.post("/processar", response_model=RespostaProcessamento)
async def processar_documentos(arquivos: list[UploadFile] = File(...)):
    """
    Processa múltiplos documentos enviados pelo usuário.

    Aceita: PDF, JPG, PNG, WEBP, BMP, TIFF
    Retorna: JSON estruturado com dados extraídos e níveis de confiança
    """
    if not gemini_disponivel:
        raise HTTPException(
            status_code=503,
            detail={
                "erro": "Serviço indisponível",
                "mensagem": (
                    "A chave da API do Google Gemini não está configurada. "
                    "Adicione GEMINI_API_KEY no arquivo .env e reinicie o servidor."
                )
            }
        )

    if not arquivos:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")

    if len(arquivos) > 20:
        raise HTTPException(status_code=400, detail="Máximo de 20 arquivos por requisição")

    resultados: list[ResultadoArquivo] = []
    tipos_encontrados: set[str] = set()

    for arquivo in arquivos:
        nome = arquivo.filename or "arquivo_sem_nome"
        logger.info(f"Processando: {nome}")

        # Valida extensão
        from pathlib import Path
        extensao = Path(nome).suffix.lower()
        if extensao not in EXTENSOES_PERMITIDAS:
            resultados.append(ResultadoArquivo(
                nome_arquivo=nome,
                erro=f"Formato não suportado: {extensao}. Use: {', '.join(EXTENSOES_PERMITIDAS)}",
                reconhecido=False
            ))
            continue

        # Lê o conteúdo do arquivo
        conteudo = await arquivo.read()

        # Valida tamanho
        if len(conteudo) > MAX_FILE_SIZE:
            resultados.append(ResultadoArquivo(
                nome_arquivo=nome,
                erro=f"Arquivo muito grande ({len(conteudo) // (1024*1024)}MB). Máximo: 20MB",
                reconhecido=False
            ))
            continue

        if len(conteudo) == 0:
            resultados.append(ResultadoArquivo(
                nome_arquivo=nome,
                erro="Arquivo vazio",
                reconhecido=False
            ))
            continue

        # Processa com Gemini
        try:
            resultado_doc = processar_documento(conteudo, nome, modelo_gemini)

            tipo = resultado_doc.get("tipo_documento", "DESCONHECIDO")
            dados = resultado_doc.get("dados", {})

            reconhecido = tipo != "DESCONHECIDO"
            if reconhecido:
                tipos_encontrados.add(tipo)

            resultados.append(ResultadoArquivo(
                nome_arquivo=nome,
                tipo_documento=tipo,
                dados=dados,
                reconhecido=reconhecido
            ))

        except ValueError as e:
            logger.error(f"Erro de validação em {nome}: {e}")
            resultados.append(ResultadoArquivo(
                nome_arquivo=nome,
                erro=str(e),
                reconhecido=False
            ))
        except Exception as e:
            logger.error(f"Erro ao processar {nome}: {e}")
            resultados.append(ResultadoArquivo(
                nome_arquivo=nome,
                erro=f"Erro interno ao processar o documento: {str(e)}",
                reconhecido=False
            ))

    # Calcula documentos faltantes
    todos_tipos = set(TIPOS_DOCUMENTOS)
    faltantes = sorted(todos_tipos - tipos_encontrados)

    return RespostaProcessamento(
        arquivos_processados=resultados,
        documentos_reconhecidos=sorted(tipos_encontrados),
        documentos_faltantes=faltantes,
        total_arquivos=len(arquivos),
        total_reconhecidos=sum(1 for r in resultados if r.reconhecido)
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
