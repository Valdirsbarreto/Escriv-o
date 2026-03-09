import axios from "axios";

// Instância do Axios
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
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
