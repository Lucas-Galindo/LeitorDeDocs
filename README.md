# LeitorDeDocs

Sistema de leitura e extração inteligente de documentos de transporte, usando Google Gemini AI.

## Documentos suportados

| Documento | Dados extraídos |
|-----------|----------------|
| CNH | Nome, CPF, Nº CNH, Data nasc., Validade, Categoria |
| MOPP | Nome, Validade, Nº Certificado |
| NR20 / NR35 | Nome, Tipo de curso, Emissão, Validade |
| Licenciamento | Placa, RENAVAM, Ano, Situação |
| CIV | Nº CIV, Validade, Placa |
| CIPP | Nº CIPP, Validade, Placa |
| Calibragem | Data calibração, Validade, Identificação |
| Cronotacógrafo | Nº Certificado, Data aferição, Validade |

## Requisitos

- Python 3.10+
- Poppler (para conversão de PDFs)
- Chave da API do Google Gemini

### Instalando o Poppler

```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler

# Windows — baixe em: https://github.com/oschwartz10612/poppler-windows/releases
```

## Configuração

```bash
# 1. Clone o repositório
git clone <url-do-repo>
cd LeitorDeDocs

# 2. Configure a chave da API
cp backend/.env.example backend/.env
# Edite backend/.env e adicione sua GEMINI_API_KEY
# Obtenha em: https://aistudio.google.com/app/apikey

# 3. Instale as dependências do backend
cd backend
pip install -r requirements.txt

# 4. Inicie o servidor
python main.py
```

O servidor estará disponível em `http://localhost:8000`.

## Executando o Frontend

Abra `frontend/index.html` diretamente no navegador, ou sirva com qualquer servidor HTTP:

```bash
# Python (da raiz do projeto)
python -m http.server 3000 --directory frontend
# Acesse: http://localhost:3000
```

## Uso

1. Abra o frontend no navegador
2. Arraste os arquivos ou clique em **Selecionar Arquivos**
3. Clique em **Processar Documentos**
4. Revise os dados extraídos — campos com borda vermelha têm baixa confiança
5. Edite os campos necessários
6. Clique em **Confirmar e Salvar Cadastro** ou **Exportar JSON**

## API

### `GET /status`
Retorna status da API e da integração com Gemini.

### `POST /processar`
Processa múltiplos documentos.

**Body:** `multipart/form-data` com campo `arquivos` (múltiplos arquivos)

**Resposta:**
```json
{
  "arquivos_processados": [
    {
      "nome_arquivo": "cnh.jpg",
      "tipo_documento": "CNH",
      "dados": {
        "nome": { "valor": "João da Silva", "baixa_confianca": false },
        "cpf":  { "valor": "123.456.789-00", "baixa_confianca": true }
      },
      "reconhecido": true
    }
  ],
  "documentos_reconhecidos": ["CNH"],
  "documentos_faltantes": ["MOPP", "NR20", "NR35", "..."],
  "total_arquivos": 1,
  "total_reconhecidos": 1
}
```

## Segurança

- A `GEMINI_API_KEY` é lida exclusivamente da variável de ambiente / arquivo `.env`
- Arquivos enviados são processados em memória e não são armazenados em disco
- O servidor funciona normalmente sem a chave, exibindo aviso claro ao tentar processar
