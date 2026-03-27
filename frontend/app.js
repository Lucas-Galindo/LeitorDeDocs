/**
 * LeitorDeDocs — Frontend Application
 * Gerencia upload, processamento e exibição de documentos.
 */

const API_BASE = "http://localhost:8000";

// ── Estado global ──────────────────────────────────────────────
let arquivosSelecionados = [];  // Array de File objects
let resultadosProcessados = {}; // Dados editados pelo usuário

// ── Referências DOM ────────────────────────────────────────────
const dropZone       = document.getElementById("drop-zone");
const fileInput      = document.getElementById("file-input");
const fileList       = document.getElementById("file-list");
const processBar     = document.getElementById("process-bar");
const fileCountEl    = document.getElementById("file-count");
const processBtnEl   = document.getElementById("process-btn");
const clearFilesBtn  = document.getElementById("clear-files");

const uploadSection  = document.getElementById("upload-section");
const loadingSection = document.getElementById("loading-section");
const resultsSection = document.getElementById("results-section");
const confirmSection = document.getElementById("confirm-section");

const progressBar    = document.getElementById("progress-bar");
const loadingText    = document.getElementById("loading-text");
const resultsSummary = document.getElementById("results-summary");
const docAlerts      = document.getElementById("doc-alerts");
const errorCards     = document.getElementById("error-cards");
const resultsForm    = document.getElementById("results-form");
const apiStatusEl    = document.getElementById("api-status");

// ── Inicialização ──────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  verificarStatusAPI();
  configurarDropZone();
  configurarBotoes();
});

// ── Status da API ──────────────────────────────────────────────
async function verificarStatusAPI() {
  try {
    const resp = await fetch(`${API_BASE}/status`, { signal: AbortSignal.timeout(5000) });
    const data = await resp.json();

    if (data.gemini === "configurado") {
      setApiStatus("online", "API Pronta");
    } else {
      setApiStatus("offline", "Chave API ausente");
    }
  } catch {
    setApiStatus("offline", "API offline");
  }
}

function setApiStatus(tipo, texto) {
  apiStatusEl.className = `api-status ${tipo}`;
  apiStatusEl.querySelector(".status-text").textContent = texto;
}

// ── Drop Zone ──────────────────────────────────────────────────
function configurarDropZone() {
  dropZone.addEventListener("dragover", e => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });

  dropZone.addEventListener("dragleave", e => {
    if (!dropZone.contains(e.relatedTarget)) {
      dropZone.classList.remove("drag-over");
    }
  });

  dropZone.addEventListener("drop", e => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    adicionarArquivos([...e.dataTransfer.files]);
  });

  dropZone.addEventListener("click", e => {
    if (e.target !== fileInput) fileInput.click();
  });

  fileInput.addEventListener("change", () => {
    adicionarArquivos([...fileInput.files]);
    fileInput.value = "";
  });
}

// ── Gerenciamento de Arquivos ──────────────────────────────────
function adicionarArquivos(novosArquivos) {
  const extensoesPermitidas = /\.(pdf|jpg|jpeg|png|webp|bmp|tiff|tif)$/i;
  const maxTamanho = 20 * 1024 * 1024;

  const validos = novosArquivos.filter(f => {
    if (!extensoesPermitidas.test(f.name)) {
      mostrarToast(`"${f.name}" — formato não suportado`, "erro");
      return false;
    }
    if (f.size > maxTamanho) {
      mostrarToast(`"${f.name}" — maior que 20MB`, "erro");
      return false;
    }
    return true;
  });

  // Evita duplicatas pelo nome
  validos.forEach(novo => {
    if (!arquivosSelecionados.some(ex => ex.name === novo.name)) {
      arquivosSelecionados.push(novo);
    }
  });

  if (arquivosSelecionados.length > 20) {
    arquivosSelecionados = arquivosSelecionados.slice(0, 20);
    mostrarToast("Máximo de 20 arquivos por vez", "aviso");
  }

  renderizarListaArquivos();
}

function removerArquivo(nome) {
  arquivosSelecionados = arquivosSelecionados.filter(f => f.name !== nome);
  renderizarListaArquivos();
}

function renderizarListaArquivos() {
  fileList.innerHTML = "";

  if (arquivosSelecionados.length === 0) {
    fileList.classList.add("hidden");
    processBar.classList.add("hidden");
    return;
  }

  fileList.classList.remove("hidden");
  processBar.classList.remove("hidden");
  fileCountEl.textContent = `${arquivosSelecionados.length} arquivo${arquivosSelecionados.length !== 1 ? "s" : ""} selecionado${arquivosSelecionados.length !== 1 ? "s" : ""}`;

  arquivosSelecionados.forEach(arquivo => {
    const ext = arquivo.name.split(".").pop().toLowerCase();
    const tipoIcone = ext === "pdf" ? "pdf" : ["jpg","jpeg","png","webp","bmp","tiff","tif"].includes(ext) ? "img" : "other";
    const tamanho = formatarTamanho(arquivo.size);

    const item = document.createElement("div");
    item.className = "file-item";
    item.innerHTML = `
      <div class="file-icon ${tipoIcone}">${ext.slice(0,4)}</div>
      <div class="file-info">
        <div class="file-name" title="${escaparHTML(arquivo.name)}">${escaparHTML(arquivo.name)}</div>
        <div class="file-size">${tamanho}</div>
      </div>
      <button class="file-remove" title="Remover" data-nome="${escaparHTML(arquivo.name)}">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
      </button>
    `;

    item.querySelector(".file-remove").addEventListener("click", e => {
      e.stopPropagation();
      removerArquivo(arquivo.name);
    });

    fileList.appendChild(item);
  });
}

// ── Botões ─────────────────────────────────────────────────────
function configurarBotoes() {
  processBtnEl.addEventListener("click", processarDocumentos);

  clearFilesBtn.addEventListener("click", () => {
    arquivosSelecionados = [];
    renderizarListaArquivos();
  });

  document.getElementById("new-upload-btn").addEventListener("click", voltarParaUpload);
  document.getElementById("restart-btn").addEventListener("click", voltarParaUpload);

  document.getElementById("confirm-btn").addEventListener("click", confirmarCadastro);
  document.getElementById("export-json-btn").addEventListener("click", exportarJSON);
}

// ── Processamento ──────────────────────────────────────────────
async function processarDocumentos() {
  if (arquivosSelecionados.length === 0) return;

  mostrarSecao("loading");
  animarProgresso();

  const formData = new FormData();
  arquivosSelecionados.forEach(f => formData.append("arquivos", f));

  try {
    loadingText.textContent = "Enviando arquivos para análise com IA...";

    const resp = await fetch(`${API_BASE}/processar`, {
      method: "POST",
      body: formData,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: "Erro desconhecido" }));
      const msg = err.detail?.mensagem || err.detail || `Erro ${resp.status}`;
      throw new Error(msg);
    }

    loadingText.textContent = "Organizando resultados...";
    progressBar.style.width = "90%";

    const dados = await resp.json();
    progressBar.style.width = "100%";

    setTimeout(() => {
      exibirResultados(dados);
    }, 400);

  } catch (e) {
    mostrarSecao("upload");
    mostrarToast(`Erro ao processar: ${e.message}`, "erro");
  }
}

// Anima a barra de progresso de forma gradual
function animarProgresso() {
  progressBar.style.width = "0%";
  let prog = 0;
  const intervalId = setInterval(() => {
    prog = Math.min(prog + Math.random() * 8, 80);
    progressBar.style.width = `${prog}%`;
    if (prog >= 80) clearInterval(intervalId);
  }, 300);
}

// ── Exibição de Resultados ─────────────────────────────────────
function exibirResultados(dados) {
  resultadosProcessados = {};
  docAlerts.innerHTML = "";
  errorCards.innerHTML = "";
  resultsForm.innerHTML = "";

  // Resumo
  resultsSummary.textContent =
    `${dados.total_reconhecidos} de ${dados.total_arquivos} arquivo${dados.total_arquivos !== 1 ? "s" : ""} reconhecido${dados.total_reconhecidos !== 1 ? "s" : ""}`;

  // Alerta de documentos reconhecidos
  if (dados.documentos_reconhecidos.length > 0) {
    docAlerts.appendChild(criarAlerta(
      "success",
      `<strong>Reconhecidos:</strong> ${dados.documentos_reconhecidos.join(", ")}`,
      iconCheck()
    ));
  }

  // Alerta de documentos faltantes
  if (dados.documentos_faltantes.length > 0) {
    docAlerts.appendChild(criarAlerta(
      "warning",
      `<strong>Não encontrados:</strong> ${dados.documentos_faltantes.join(", ")}`,
      iconWarn()
    ));
  }

  // Erros por arquivo
  dados.arquivos_processados.forEach(arq => {
    if (arq.erro) {
      const card = document.createElement("div");
      card.className = "error-card";
      card.innerHTML = `${iconX()} <strong>${escaparHTML(arq.nome_arquivo)}:</strong>&nbsp;${escaparHTML(arq.erro)}`;
      errorCards.appendChild(card);
    }
  });

  // Cards de documentos reconhecidos
  dados.arquivos_processados.forEach((arq, idx) => {
    if (!arq.reconhecido || !arq.dados) return;

    const chave = `${arq.tipo_documento}_${idx}`;
    resultadosProcessados[chave] = { tipo: arq.tipo_documento, campos: { ...arq.dados } };

    const temBaixaConfianca = Object.values(arq.dados).some(c => c?.baixa_confianca);
    const card = criarCardDocumento(arq, chave, temBaixaConfianca);
    resultsForm.appendChild(card);
  });

  mostrarSecao("results");
}

function criarCardDocumento(arq, chave, temBaixaConfianca) {
  const card = document.createElement("div");
  card.className = "doc-card";

  card.innerHTML = `
    <div class="doc-card-header">
      <div class="doc-card-title">
        <span class="doc-type-badge">${escaparHTML(arq.tipo_documento)}</span>
        <span class="doc-filename">${escaparHTML(arq.nome_arquivo)}</span>
      </div>
      ${temBaixaConfianca ? `<div class="low-confidence-badge">${iconWarnSmall()} Revisar campos</div>` : ""}
    </div>
    <div class="doc-card-body" id="body-${chave}"></div>
  `;

  const body = card.querySelector(`#body-${chave}`);

  const rotulos = obterRotulos(arq.tipo_documento);

  Object.entries(arq.dados).forEach(([campo, info]) => {
    if (!info) return;

    const rotulo = rotulos[campo] || formatarNomeCampo(campo);
    const valor  = info.valor ?? "";
    const baixa  = info.baixa_confianca ?? false;

    const grupo = document.createElement("div");
    grupo.className = "field-group";
    grupo.innerHTML = `
      <label class="field-label" for="field-${chave}-${campo}">
        ${baixa ? `<svg class="warn-icon" width="13" height="13" viewBox="0 0 16 16"><path d="M8 2l6 12H2L8 2z" fill="currentColor" opacity=".15"/><path d="M8 2l6 12H2L8 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 7v3M8 12v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>` : ""}
        ${escaparHTML(rotulo)}
      </label>
      <input
        class="field-input${baixa ? " low-confidence" : ""}"
        id="field-${chave}-${campo}"
        type="text"
        value="${escaparHTML(String(valor))}"
        data-chave="${chave}"
        data-campo="${campo}"
        placeholder="${valor ? "" : "Não encontrado"}"
      />
      ${baixa ? `<span class="field-hint">${iconWarnSmall()} Verifique este campo</span>` : ""}
    `;

    grupo.querySelector("input").addEventListener("input", e => {
      resultadosProcessados[e.target.dataset.chave].campos[e.target.dataset.campo].valor = e.target.value;
    });

    body.appendChild(grupo);
  });

  return card;
}

// ── Rótulos amigáveis por tipo de documento ────────────────────
function obterRotulos(tipo) {
  const mapa = {
    CNH: {
      nome: "Nome completo", cpf: "CPF", numero_cnh: "Nº da CNH",
      data_nascimento: "Data de nascimento", data_validade: "Validade", categoria: "Categoria"
    },
    MOPP: {
      nome: "Nome", data_validade: "Validade", numero_certificado: "Nº do Certificado"
    },
    NR20: {
      nome_trabalhador: "Nome do trabalhador", tipo_curso: "Tipo de curso",
      data_emissao: "Data de emissão", data_validade: "Validade"
    },
    NR35: {
      nome_trabalhador: "Nome do trabalhador", tipo_curso: "Tipo de curso",
      data_emissao: "Data de emissão", data_validade: "Validade"
    },
    Licenciamento: {
      placa: "Placa", renavam: "RENAVAM", ano: "Ano", situacao: "Situação"
    },
    CIV: {
      numero_civ: "Nº do CIV", validade: "Validade", placa: "Placa"
    },
    CIPP: {
      numero_cipp: "Nº do CIPP", validade: "Validade", placa: "Placa"
    },
    Calibragem: {
      data_calibracao: "Data da calibração", validade: "Validade",
      identificacao_equipamento: "Identificação do equipamento"
    },
    "Cronotacógrafo": {
      numero_certificado: "Nº do Certificado", data_aferimento: "Data de aferição", validade: "Validade"
    }
  };
  return mapa[tipo] || {};
}

function formatarNomeCampo(campo) {
  return campo.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
}

// ── Confirmar e Exportar ───────────────────────────────────────
function confirmarCadastro() {
  const docs = Object.values(resultadosProcessados);

  const confirmedList = document.getElementById("confirm-summary");
  confirmedList.innerHTML = `<ul>${docs.map(d =>
    `<li><strong>${d.tipo}:</strong> dados confirmados</li>`
  ).join("")}</ul>`;

  mostrarSecao("confirm");
}

function exportarJSON() {
  const exportData = {};
  Object.values(resultadosProcessados).forEach(doc => {
    const tipo = doc.tipo;
    const campos = {};
    Object.entries(doc.campos).forEach(([campo, info]) => {
      campos[campo] = info?.valor ?? null;
    });

    if (!exportData[tipo]) exportData[tipo] = [];
    exportData[tipo].push(campos);
  });

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `leitordedocs_${formatarDataArquivo()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Navegação entre seções ─────────────────────────────────────
function mostrarSecao(nome) {
  uploadSection.classList.add("hidden");
  loadingSection.classList.add("hidden");
  resultsSection.classList.add("hidden");
  confirmSection.classList.add("hidden");

  const mapa = {
    upload:  uploadSection,
    loading: loadingSection,
    results: resultsSection,
    confirm: confirmSection,
  };

  mapa[nome]?.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function voltarParaUpload() {
  arquivosSelecionados = [];
  resultadosProcessados = {};
  renderizarListaArquivos();
  mostrarSecao("upload");
  verificarStatusAPI();
}

// ── Helpers ────────────────────────────────────────────────────
function criarAlerta(tipo, html, icone) {
  const el = document.createElement("div");
  el.className = `alert alert-${tipo}`;
  el.innerHTML = `<span class="alert-icon">${icone}</span><span>${html}</span>`;
  return el;
}

function mostrarToast(mensagem, tipo = "info") {
  const cores = { erro: "#ef4444", aviso: "#f59e0b", info: "#2563eb", sucesso: "#10b981" };
  const toast = document.createElement("div");
  toast.style.cssText = `
    position: fixed; bottom: 24px; right: 24px; z-index: 9999;
    background: ${cores[tipo] || cores.info}; color: white;
    padding: 12px 20px; border-radius: 10px; font-size: .875rem;
    font-weight: 600; box-shadow: 0 4px 20px rgba(0,0,0,.2);
    max-width: 360px; animation: slideIn .2s ease;
  `;
  toast.textContent = mensagem;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function escaparHTML(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatarTamanho(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatarDataArquivo() {
  return new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-");
}

// ── Ícones SVG inline ──────────────────────────────────────────
function iconCheck() {
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M5 8l2 2 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function iconWarn() {
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 2l6 12H2L8 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 7v2.5M8 11.5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`;
}

function iconWarnSmall() {
  return `<svg width="11" height="11" viewBox="0 0 16 16" fill="none"><path d="M8 2l6 12H2L8 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 7v2.5M8 11.5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`;
}

function iconX() {
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`;
}
