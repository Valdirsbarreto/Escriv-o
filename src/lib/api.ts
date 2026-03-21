import axios from "axios";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// Instância do Axios (JSON)
export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
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
  const response = await api.post("/copiloto/sessao", { inquerito_id: inqueritoId });
  return response.data;
};

export const sendMessage = async (
  sessaoId: string, 
  inqueritoId: string, 
  query: string
) => {
  // O endpoint real é POST /copiloto/chat
  const response = await api.post("/copiloto/chat", {
    sessao_id: sessaoId,
    inquerito_id: inqueritoId,
    query: query,
    auditar_fatos: true
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
export const osintLote = async (
  inqueritoId: string,
  itens: { pessoa_id: string; perfil: number | null }[]
) => {
  const response = await api.post(
    "/agentes/osint/lote",
    { inquerito_id: inqueritoId, itens },
    { timeout: 120000 }
  );
  return response.data;
};

export const osintConsultaAvulsa = async (params: {
  cpf?: string;
  cnpj?: string;
  placa?: string;
  nome?: string;
  data_nascimento?: string;
  rg?: string;
  uf?: string;
}) => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v) query.append(k, v); });
  const response = await api.post(`/agentes/osint/consulta-avulsa?${query.toString()}`, null, {
    timeout: 60000,
  });
  return response.data;
};
