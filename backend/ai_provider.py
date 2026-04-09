"""
Provedores de IA para o sistema LeitorDeDocs.

Suporta três provedores:
  - Gemini   → Google Gemini (API Key necessária)
  - Groq     → Llama na nuvem via Groq (API Key necessária, tier gratuito disponível)
  - Ollama   → Llama local via Ollama (gratuito, sem internet)

Configure o provedor desejado com a variável AI_PROVIDER no arquivo .env.
"""
import base64
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Interface base para todos os provedores de IA."""

    @abstractmethod
    def gerar_conteudo(self, prompt: str, imagens_base64: list[str]) -> str:
        """
        Envia o prompt e as imagens para a IA e retorna o texto de resposta.

        Args:
            prompt: Texto de instrução para a IA
            imagens_base64: Lista de imagens codificadas em base64 (JPEG)

        Returns:
            Texto da resposta da IA (esperado: JSON)
        """
        ...

    @property
    @abstractmethod
    def nome(self) -> str:
        """Nome legível do provedor."""
        ...


# ── Gemini ────────────────────────────────────────────────────────────────────

class GeminiProvider(AIProvider):
    """Provedor Google Gemini."""

    def __init__(self, api_key: str, model: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._modelo = genai.GenerativeModel(
            model_name=model,
            generation_config={"temperature": 0.1, "top_p": 0.95, "max_output_tokens": 2048}
        )
        self._model_name = model

    @property
    def nome(self) -> str:
        return f"Gemini ({self._model_name})"

    def gerar_conteudo(self, prompt: str, imagens_base64: list[str]) -> str:
        partes = [prompt]
        for img_b64 in imagens_base64:
            partes.append({"mime_type": "image/jpeg", "data": img_b64})
        resposta = self._modelo.generate_content(partes)
        return resposta.text.strip()


def detectar_modelo_gemini(api_key: str) -> str:
    """Lista modelos Gemini disponíveis e retorna o melhor para visão."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    preferidos = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
    ]

    try:
        disponiveis = set()
        for m in genai.list_models():
            if "generateContent" in (m.supported_generation_methods or []):
                disponiveis.add(m.name.replace("models/", ""))

        logger.info(f"Modelos Gemini disponíveis: {sorted(disponiveis)}")

        for pref in preferidos:
            if pref in disponiveis:
                return pref

        if disponiveis:
            escolhido = sorted(disponiveis)[0]
            logger.warning(f"Nenhum modelo preferido encontrado. Usando: {escolhido}")
            return escolhido

    except Exception as e:
        logger.warning(f"Não foi possível listar modelos Gemini: {e}")

    return "gemini-2.0-flash"


# ── Groq (Llama na nuvem) ─────────────────────────────────────────────────────

# Modelos Llama com suporte a visão disponíveis no Groq
MODELOS_GROQ_VISAO = [
    "llama-3.2-90b-vision-preview",
    "llama-3.2-11b-vision-preview",
]


class GroqProvider(AIProvider):
    """
    Provedor Groq — executa modelos Llama na nuvem com suporte a visão.
    Obtenha sua chave gratuita em: https://console.groq.com
    """

    def __init__(self, api_key: str, model: str = "llama-3.2-11b-vision-preview"):
        from groq import Groq
        self._client = Groq(api_key=api_key)
        self._model = model

    @property
    def nome(self) -> str:
        return f"Groq / Llama ({self._model})"

    def gerar_conteudo(self, prompt: str, imagens_base64: list[str]) -> str:
        # Monta as partes do conteúdo — texto + imagens
        conteudo = [{"type": "text", "text": prompt}]

        for img_b64 in imagens_base64:
            conteudo.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })

        resposta = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": conteudo}],
            temperature=0.1,
            max_tokens=2048,
        )
        return resposta.choices[0].message.content.strip()


def detectar_modelo_groq(api_key: str, modelo_preferido: str = "") -> str:
    """Lista modelos Groq disponíveis e retorna o melhor com suporte a visão."""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        modelos = [m.id for m in client.models.list().data]
        logger.info(f"Modelos Groq disponíveis: {sorted(modelos)}")

        # Usa o modelo preferido se especificado e disponível
        if modelo_preferido and modelo_preferido in modelos:
            return modelo_preferido

        # Seleciona o melhor modelo de visão disponível
        for pref in MODELOS_GROQ_VISAO:
            if pref in modelos:
                return pref

        # Fallback: qualquer modelo com "vision" ou "llama" no nome
        for m in sorted(modelos):
            if "vision" in m.lower():
                return m

    except Exception as e:
        logger.warning(f"Não foi possível listar modelos Groq: {e}")

    return modelo_preferido or MODELOS_GROQ_VISAO[1]  # llama-3.2-11b-vision-preview


# ── Ollama (Llama local) ──────────────────────────────────────────────────────

# Modelos Ollama recomendados para visão (em ordem de preferência)
MODELOS_OLLAMA_VISAO = [
    "llama3.2-vision",
    "llama3.2-vision:11b",
    "llama3.2-vision:90b",
    "llava",
    "llava:13b",
    "llava:34b",
    "minicpm-v",
    "moondream",
]


class OllamaProvider(AIProvider):
    """
    Provedor Ollama — executa Llama localmente, sem internet e sem custo.
    Instale em: https://ollama.com
    Modelos recomendados: ollama pull llama3.2-vision
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2-vision"):
        from openai import OpenAI
        self._client = OpenAI(base_url=f"{base_url.rstrip('/')}/v1", api_key="ollama")
        self._model = model
        self._base_url = base_url

    @property
    def nome(self) -> str:
        return f"Ollama / Llama local ({self._model})"

    def gerar_conteudo(self, prompt: str, imagens_base64: list[str]) -> str:
        conteudo = [{"type": "text", "text": prompt}]

        for img_b64 in imagens_base64:
            conteudo.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })

        resposta = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": conteudo}],
            temperature=0.1,
            max_tokens=2048,
        )
        return resposta.choices[0].message.content.strip()


def detectar_modelo_ollama(base_url: str, modelo_preferido: str = "") -> str:
    """Lista modelos Ollama instalados e retorna o melhor com suporte a visão."""
    try:
        import urllib.request, json as _json
        url = f"{base_url.rstrip('/')}/api/tags"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = _json.loads(r.read())

        modelos = [m["name"].split(":")[0] for m in data.get("models", [])]
        nomes_completos = [m["name"] for m in data.get("models", [])]
        logger.info(f"Modelos Ollama instalados: {nomes_completos}")

        if modelo_preferido and modelo_preferido in nomes_completos:
            return modelo_preferido

        for pref in MODELOS_OLLAMA_VISAO:
            if pref in nomes_completos or pref in modelos:
                # Retorna o nome completo se disponível
                for nc in nomes_completos:
                    if nc.startswith(pref):
                        return nc
                return pref

    except Exception as e:
        logger.warning(f"Não foi possível listar modelos Ollama em {base_url}: {e}")

    return modelo_preferido or MODELOS_OLLAMA_VISAO[0]


# ── Factory ───────────────────────────────────────────────────────────────────

def criar_provedor(config: dict) -> AIProvider:
    """
    Cria o provedor de IA com base na configuração do ambiente.

    config esperado:
      {
        "provider":         "gemini" | "groq" | "ollama",
        "gemini_api_key":   "...",
        "groq_api_key":     "...",
        "groq_model":       "llama-3.2-11b-vision-preview",  # opcional
        "ollama_base_url":  "http://localhost:11434",         # opcional
        "ollama_model":     "llama3.2-vision",                # opcional
      }
    """
    provider = config.get("provider", "gemini").lower().strip()

    if provider == "gemini":
        api_key = config.get("gemini_api_key", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY não configurada")
        model = detectar_modelo_gemini(api_key)
        return GeminiProvider(api_key=api_key, model=model)

    elif provider == "groq":
        api_key = config.get("groq_api_key", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY não configurada. Obtenha em https://console.groq.com")
        modelo_pref = config.get("groq_model", "")
        model = detectar_modelo_groq(api_key, modelo_pref)
        return GroqProvider(api_key=api_key, model=model)

    elif provider == "ollama":
        base_url = config.get("ollama_base_url", "http://localhost:11434")
        modelo_pref = config.get("ollama_model", "")
        model = detectar_modelo_ollama(base_url, modelo_pref)
        return OllamaProvider(base_url=base_url, model=model)

    else:
        raise ValueError(
            f"Provedor '{provider}' não suportado. "
            "Use: gemini, groq ou ollama"
        )
