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
) => {
  const response = await api.post(
    "/agent/chat",
    { mensagem, session_id: sessionId, inquerito_id: inqueritoId ?? null },
    { headers: { "X-Chat-Secret": CHAT_SECRET }, timeout: 90000 },
  );
  return response.data as { resposta: string };
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
