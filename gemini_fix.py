import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERRO: Chave GEMINI_API_KEY não encontrada no .env")
    exit()

genai.configure(api_key=api_key)

# Tenta o mais capaz, cai para o estável se não disponível
MODELOS = ["gemini-2.0-flash", "gemini-1.5-pro"]

model = None
MODEL = None
for m in MODELOS:
    try:
        model = genai.GenerativeModel(m)
        MODEL = m
        break
    except Exception:
        continue

if not model:
    print("ERRO: Nenhum modelo Gemini disponível.")
    exit()

arquivo_alvo = "src/components/Sidebar.tsx"  # Ajuste o caminho aqui

try:
    with open(arquivo_alvo, "r", encoding="utf-8") as f:
        conteudo = f.read()

    print(f"--- Enviando {arquivo_alvo} para {MODEL} ---")

    prompt = f"""
Analise este código do projeto Escrivão e faça os ajustes finais de lógica:

{conteudo}

Retorne apenas o código corrigido, sem explicações.
"""

    response = model.generate_content(prompt)

    saida = f"{arquivo_alvo}.fixed"
    with open(saida, "w", encoding="utf-8") as f:
        f.write(response.text)

    print(f"Sucesso! Arquivo corrigido salvo em: {saida}")

except FileNotFoundError:
    print(f"ERRO: Arquivo '{arquivo_alvo}' não encontrado.")
except Exception as e:
    print(f"Erro ao processar: {e}")
