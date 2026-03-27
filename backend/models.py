"""
Modelos de dados para o sistema de leitura de documentos.
Define a estrutura de resposta JSON com níveis de confiança.
"""
from typing import Optional, Any
from pydantic import BaseModel


class Campo(BaseModel):
    """Representa um campo extraído com seu valor e nível de confiança."""
    valor: Optional[Any] = None
    baixa_confianca: bool = False


class DocumentoCNH(BaseModel):
    nome: Optional[Campo] = None
    cpf: Optional[Campo] = None
    numero_cnh: Optional[Campo] = None
    data_nascimento: Optional[Campo] = None
    data_validade: Optional[Campo] = None
    categoria: Optional[Campo] = None


class DocumentoMOPP(BaseModel):
    nome: Optional[Campo] = None
    data_validade: Optional[Campo] = None
    numero_certificado: Optional[Campo] = None


class DocumentoNR(BaseModel):
    nome_trabalhador: Optional[Campo] = None
    tipo_curso: Optional[Campo] = None
    data_emissao: Optional[Campo] = None
    data_validade: Optional[Campo] = None


class DocumentoLicenciamento(BaseModel):
    placa: Optional[Campo] = None
    renavam: Optional[Campo] = None
    ano: Optional[Campo] = None
    situacao: Optional[Campo] = None


class DocumentoCIV(BaseModel):
    numero_civ: Optional[Campo] = None
    validade: Optional[Campo] = None
    placa: Optional[Campo] = None


class DocumentoCIPP(BaseModel):
    numero_cipp: Optional[Campo] = None
    validade: Optional[Campo] = None
    placa: Optional[Campo] = None


class DocumentoCalibragem(BaseModel):
    data_calibracao: Optional[Campo] = None
    validade: Optional[Campo] = None
    identificacao_equipamento: Optional[Campo] = None


class DocumentoCronotacografo(BaseModel):
    numero_certificado: Optional[Campo] = None
    data_aferimento: Optional[Campo] = None
    validade: Optional[Campo] = None


class ResultadoArquivo(BaseModel):
    """Resultado do processamento de um único arquivo."""
    nome_arquivo: str
    tipo_documento: Optional[str] = None
    dados: Optional[dict] = None
    erro: Optional[str] = None
    reconhecido: bool = False


class RespostaProcessamento(BaseModel):
    """Resposta consolidada do processamento de múltiplos arquivos."""
    arquivos_processados: list[ResultadoArquivo]
    documentos_reconhecidos: list[str]
    documentos_faltantes: list[str]
    total_arquivos: int
    total_reconhecidos: int
