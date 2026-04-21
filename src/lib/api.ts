import axios from "axios";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// Instância do Axios (JSON)
export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Instância do Axios para upload de arquivos (multipart/form-data)
// Não definir Content-Type aqui — o browser seta o boundary automagicamente
export const apiMultipart = axios.create({
  baseURL: BASE_URL,
  timeout: 60000, // upload pode demorar mais
});

// APIs Inquéritos
export const getInqueritos = async () => {
  const response = await api.get("/inqueritos");
  return response.data;
};

export const criarInqueritoRapido = async (numero: string) => {
  const response = await api.post("/inqueritos", { numero });
  return response.data;
};

export const getInquerito = async (id: string) => {
  const response = await api.get(`/inqueritos/${id}`);
  return response.data;
};

export const deleteInquerito = async (id: string) => {
  await api.delete(`/inqueritos/${id}`);
};

export const getInqueritoResumo = async (id: string) => {
  const response = await api.get(`/inqueritos/${id}/indices/resumo`);
  return response.data;
};

export const getInqueritoIndices = async (id: string, tipo: string) => {
  const response = await api.get(`/inqueritos/${id}/indices/${tipo}`);
  return response.data;
};

// APIs Copiloto
export const createSessao = async (inqueritoId: string) => {
  const response = await api.post("/copiloto/sessoes", { inquerito_id: inqueritoId });
  return response.data;
};

export const sendMessage = async (
  sessaoId: string,
  _inqueritoId: string,
  query: string
) => {
  const response = await api.post(`/copiloto/chat/${sessaoId}`, {
    mensagem: query,
    auditar: true,
  });
  return response.data;
};

// APIs Agente OSINT
export const getPessoas = async (inqueritoId: string) => {
  const response = await api.get(`/inqueritos/${inqueritoId}/indices/pessoas`);
  return response.data;
};

export const getEmpresas = async (inqueritoId: string) => {
  const response = await api.get(`/inqueritos/${inqueritoId}/indices/empresas`);
  return response.data;
};

export const gerarFichaPessoa = async (inqueritoId: string, pessoaId: string) => {
  const response = await api.post(`/agentes/ficha/pessoa/${pessoaId}?inquerito_id=${inqueritoId}`);
  return response.data;
};

export const gerarFichaEmpresa = async (inqueritoId: string, empresaId: string) => {
  const response = await api.post(`/agentes/ficha/empresa/${empresaId}?inquerito_id=${inqueritoId}`);
  return response.data;
};

export const iniciarIngestao = async (formData: FormData) => {
  const response = await apiMultipart.post("/ingestao/iniciar", formData);
  return response.data;
};

// APIs OSINT
export const osintSugestao = async (inqueritoId: string) => {
  const response = await api.get(`/agentes/osint/sugestao/${inqueritoId}`, {
    timeout: 30000,
  });
  return response.data;
};

export const osintLote = async (
  inqueritoId: string,
  itens: { pessoa_id: string; modulos: string[] }[]
) => {
  const response = await api.post(
    "/agentes/osint/lote",
    { inquerito_id: inqueritoId, itens },
    { timeout: 120000 }
  );
  return response.data;
};

// APIs Consumo / Orçamento LLM
export const getConsumoSaldo = async () => {
  const response = await api.get("/consumo/saldo");
  return response.data;
};

export const getConsumoRanking = async () => {
  const response = await api.get("/consumo/ranking");
  return response.data;
};

export const getConsumoHistorico = async (dias = 30) => {
  const response = await api.get(`/consumo/historico?dias=${dias}`);
  return response.data;
};

export const getConsumoModelos = async () => {
  const response = await api.get("/consumo/modelos");
  return response.data;
};

export const getConsumoExternos = async (mes?: string) => {
  const response = await api.get("/consumo/externos", { params: mes ? { mes } : {} });
  return response.data;
};

export const salvarCustoExterno = async (
  servico: string,
  custo_usd: number,
  custo_brl: number,
  observacao?: string,
  mes?: string,
) => {
  const response = await api.put(
    `/consumo/externos/${servico}`,
    { custo_usd, custo_brl, observacao },
    { params: mes ? { mes } : {} },
  );
  return response.data;
};

export const getConsumoConfig = async () => {
  const response = await api.get("/consumo/config");
  return response.data;
};

export const salvarConsumoConfig = async (budget_brl: number, budget_alert_brl: number, cotacao_dolar: number) => {
  const response = await api.put("/consumo/config", { budget_brl, budget_alert_brl, cotacao_dolar });
  return response.data;
};

export const getConsumoOsintPorInquerito = async () => {
  const response = await api.get("/consumo/osint-por-inquerito");
  return response.data;
};

export const getConsumoProjecao = async () => {
  const response = await api.get("/consumo/projecao");
  return response.data;
};

export const coletarBillingAgora = async () => {
  const response = await api.post("/consumo/billing/coletar-agora");
  return response.data;
};

export const getBillingStatus = async (taskId: string) => {
  const response = await api.get(`/consumo/billing/status/${taskId}`);
  return response.data;
};

export const getSupabaseUsage = async () => {
  const response = await api.get("/consumo/supabase-usage");
  return response.data;
};

export const getAlertasContagem = async (): Promise<{ nao_lidos: number }> => {
  const response = await api.get("/alertas/contagem");
  return response.data;
};

export const getAlertas = async () => {
  const response = await api.get("/alertas");
  return response.data;
};

export const marcarAlertaLido = async (id: string) => {
  const response = await api.put(`/alertas/${id}/lido`);
  return response.data;
};

export const marcarTodosAlertasLidos = async () => {
  const response = await api.put("/alertas/marcar-todos-lidos");
  return response.data;
};

export const deletarTodosAlertas = async () => {
  const response = await api.delete("/alertas");
  return response.data;
};

export const osintGratuito = async (inqueritoId: string, pessoaId: string) => {
  const response = await api.get(
    `/agentes/osint/gratuito/${inqueritoId}/${pessoaId}`,
    { timeout: 45000 }
  );
  return response.data;
};

// ── Documentos Gerados ─────────────────────────────────────────────────────
export const getDocsGerados = (inqId: string) =>
  api.get(`/inqueritos/${inqId}/docs-gerados`);

export const createDocGerado = (inqId: string, data: { titulo: string; tipo: string; conteudo: string }) =>
  api.post(`/inqueritos/${inqId}/docs-gerados`, data);

export const getDocGerado = (inqId: string, docId: string) =>
  api.get(`/inqueritos/${inqId}/docs-gerados/${docId}`);

export const deleteDocGerado = (inqId: string, docId: string) =>
  api.delete(`/inqueritos/${inqId}/docs-gerados/${docId}`);

export const updateDocGerado = (inqId: string, docId: string, data: { titulo: string; tipo: string; conteudo: string }) =>
  api.put(`/inqueritos/${inqId}/docs-gerados/${docId}`, data);

export const sendMessageComAnexo = async (
  sessaoId: string,
  mensagem: string,
  file: File,
) => {
  const formData = new FormData();
  formData.append("mensagem", mensagem);
  formData.append("auditar", "false");
  formData.append("file", file);
  const response = await apiMultipart.post(`/copiloto/chat/${sessaoId}/com-anexo`, formData, {
    timeout: 120000,
  });
  return response.data;
};

// ── Peças Extraídas ────────────────────────────────────────────────────────
export const getPecasExtraidas = (inqId: string) =>
  api.get(`/inqueritos/${inqId}/pecas-extraidas`);

export const getPecaExtraida = (inqId: string, pecaId: string) =>
  api.get(`/inqueritos/${inqId}/pecas-extraidas/${pecaId}`);

export const reextrairPecas = (inqId: string, docId: string) =>
  api.post(`/inqueritos/${inqId}/documentos/${docId}/reextrair-pecas`);

// ── Agente Chat Web (Sprint D) ──────────────────────────────────────────────

const CHAT_SECRET = process.env.NEXT_PUBLIC_CHAT_SECRET || "";

export const agentChat = async (
  mensagem: string,
  sessionId: string,
  inqueritoId?: string | null,
  textoAnexo?: string | null,
  nomeAnexo?: string | null,
) => {
  const response = await api.post(
    "/agent/chat",
    {
      mensagem,
      session_id: sessionId,
      inquerito_id: inqueritoId ?? null,
      texto_anexo: textoAnexo ?? null,
      nome_anexo: nomeAnexo ?? null,
    },
    { headers: { "X-Chat-Secret": CHAT_SECRET }, timeout: 90000 },
  );
  return response.data as { resposta: string; inquerito_id?: string | null };
};

export interface AnalisarDocumentoResult {
  descricao: string;
  tipo: "intimacao" | "outro";
  nome: string;
  dados_intimacao?: {
    intimado_nome: string;
    data_oitiva: string | null;
    local_oitiva: string | null;
    numero_inquerito: string | null;
    qualificacao: string | null;
  } | null;
}

/** Envia imagem ou PDF para Gemini Vision e retorna descrição + dados estruturados. */
export const analisarDocumento = async (arquivo: Blob, filename: string): Promise<AnalisarDocumentoResult> => {
  const form = new FormData();
  form.append("arquivo", arquivo, filename);
  const response = await apiMultipart.post("/agent/analisar-documento", form, {
    headers: { "X-Chat-Secret": CHAT_SECRET },
    timeout: 60000,
  });
  return response.data as AnalisarDocumentoResult;
};

/** Cria intimação manual e agenda no Google Calendar. */
export const criarIntimacaoManual = async (dados: {
  intimado_nome: string;
  data_oitiva: string;
  local_oitiva?: string | null;
  numero_inquerito_extraido?: string | null;
  intimado_qualificacao?: string | null;
  inquerito_id?: string | null;
}) => {
  const response = await api.post("/intimacoes/manual", dados);
  return response.data;
};

export const setAgentInquerito = async (sessionId: string, inqueritoId: string) => {
  await api.post(
    "/agent/chat/set-inquerito",
    { session_id: sessionId, inquerito_id: inqueritoId },
    { headers: { "X-Chat-Secret": CHAT_SECRET } },
  );
};

export const clearAgentContext = async (sessionId: string) => {
  await api.delete(`/agent/chat/context?session_id=${sessionId}`, {
    headers: { "X-Chat-Secret": CHAT_SECRET },
  });
};

// ── OSINT ──────────────────────────────────────────────────────────────────

export const osintConsultaAvulsa = async (params: {
  cpf?: string;
  cnpj?: string;
  placa?: string;
  nome?: string;
  data_nascimento?: string;
  rg?: string;
  uf?: string;
  inquerito_id?: string;
}) => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v) query.append(k, v); });
  const response = await api.post(`/agentes/osint/consulta-avulsa?${query.toString()}`, null, {
    timeout: 60000,
  });
  return response.data;
};

export const osintConsultasInquerito = async (inqueritoId: string) => {
  const response = await api.get(`/agentes/osint/consultas/${inqueritoId}`);
  return response.data;
};

export const osintAnalisePreliminar = async (
  inqueritoId: string,
  pessoaId: string,
  aprimorar = false
) => {
  const response = await api.get(
    `/agentes/osint/preliminar/${inqueritoId}/${pessoaId}`,
    { params: { aprimorar }, timeout: 45000 }
  );
  return response.data;
};

export const osintGerarRelatorioWeb = async (inqueritoId: string, pessoaId: string) => {
  const response = await api.post(
    `/agentes/osint/web/${inqueritoId}/${pessoaId}/relatorio`,
    {},
    { timeout: 120000 },
  );
  return response.data;
};

export const osintBuscaWeb = async (inqueritoId: string, pessoaId: string) => {
  const response = await api.get(
    `/agentes/osint/web/${inqueritoId}/${pessoaId}`,
    { timeout: 60000 }
  );
  return response.data;
};

// ── Agente Sherlock ────────────────────────────────────────────────────────────

export const ingestaoIniciarUrl = async (url: string, nome_arquivo: string) => {
  const response = await api.post(
    "/ingestao/iniciar-url",
    { url, nome_arquivo },
    { timeout: 90000 },
  );
  return response.data as { id_sessao: string; status: string; mensagem: string; arquivos_recebidos: string[] };
};

export const uploadPorUrl = async (inqueritoId: string, url: string, nome_arquivo: string) => {
  const response = await api.post(
    `/inqueritos/${inqueritoId}/upload-url`,
    { url, nome_arquivo },
    { timeout: 90000 },
  );
  return response.data;
};

export const sherlockAnalise = async (inqueritoId: string, forcar = false) => {
  const response = await api.post(
    `/agentes/sherlock/${inqueritoId}?forcar=${forcar}`,
    {},
    { timeout: 120000 },
  );
  return response.data as { status: string; analise: any };
};

// APIs Oitiva
export const transcreverOitiva = async (audioBlob: Blob, filename = "oitiva.webm") => {
  const form = new FormData();
  form.append("audio", audioBlob, filename);
  const response = await apiMultipart.post("/oitiva/transcrever", form, { timeout: 300000 });
  return response.data as { transcricao: string; tamanho_bytes: number };
};

export const lavrarTermo = async (body: {
  transcricao: string;
  data_hora?: string;
  local?: string;
  comissario?: string;
  qualificacao?: string;
  papel?: string;
}) => {
  const response = await api.post("/oitiva/lavrar", body, { timeout: 120000 });
  return response.data as { termo: string; modelo: string; chars: number };
};

export const transcreverAudio = async (audioBlob: Blob, filename = "audio.webm") => {
  const form = new FormData();
  form.append("audio", audioBlob, filename);
  const response = await apiMultipart.post("/agentes/transcrever", form, { timeout: 60000 });
  return response.data as { transcricao: string };
};

/** Gera áudio TTS (Gemini — mesma voz do Telegram) e retorna URL de blob para tocar. */
export const ttsVoz = async (texto: string): Promise<string> => {
  const headers: Record<string, string> = {};
  const secret = process.env.NEXT_PUBLIC_CHAT_SECRET || "";
  if (secret) headers["x-chat-secret"] = secret;
  const response = await api.post(
    "/agent/tts",
    { texto },
    { responseType: "arraybuffer", timeout: 30000, headers }
  );
  const blob = new Blob([response.data], { type: "audio/wav" });
  return URL.createObjectURL(blob);
};
