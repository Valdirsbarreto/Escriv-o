"""
Escrivão AI — Copiloto Telegram (Sprint B + C)
Dispatcher via Gemini Function Calling nativo + contexto conversacional rico.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.inquerito import Inquerito
from app.models.intimacao import Intimacao
from app.models.pessoa import Pessoa
from app.services.llm_service import LLMService
from app.services.copiloto_service import CopilotoService

logger = logging.getLogger(__name__)

# ── Mapa de estados legíveis ──────────────────────────────────────────────────

ESTADO_LABEL = {
    "recebido": "Recebido",
    "indexando": "Indexando documentos",
    "triagem": "Em triagem",
    "investigacao": "Em investigação",
    "diligencias": "Diligências em andamento",
    "analise": "Em análise",
    "relatorio": "Elaborando relatório",
    "encerramento": "Em encerramento",
    "arquivamento": "Arquivado",
}

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é o Escrivão AI, copiloto investigativo do Comissário Valdir, da Polícia Civil.
Inquérito em foco: {inquerito_atual}
Última pessoa/CPF pesquisada: {ultimo_alvo}
Data e hora atual: {data_hoje}

Responda em português informal, direto e eficiente — como um assistente de confiança.
Ao receber um número de IP, sempre use o inquerito_atual do contexto se o usuário não informar um novo.
Quando o usuário pedir algo sobre "ele", "ela", "esse cara", "o endereço", "mais dados" sem especificar quem,
use o último_alvo do contexto (CPF ou nome da última pesquisa).
Se faltar alguma informação para executar uma ação, pergunte de forma concisa e aguarde a resposta.

## Abertura de Peças no PDF
Quando o usuário pedir para ABRIR, VER, MOSTRAR ou EXIBIR uma peça específica dos autos (ex: "abre o termo do João", "mostra o laudo", "exibe essa peça"), use a ferramenta abrir_peca_no_pdf com o UUID da peça encontrada via busca_autos. NUNCA invente UUIDs."""


# ── Tool declarations (lazy) ───────────────────────────────────────────────────

_FC_TOOLS = None


def _get_fc_tools():
    global _FC_TOOLS
    if _FC_TOOLS is not None:
        return _FC_TOOLS

    from google.genai import types as _gt

    str_ = _gt.Schema(type=_gt.Type.STRING)

    _FC_TOOLS = _gt.Tool(function_declarations=[
        _gt.FunctionDeclaration(
            name="listar_inqueritos",
            description="Lista todos os inquéritos policiais cadastrados no sistema.",
        ),
        _gt.FunctionDeclaration(
            name="status_inquerito",
            description="Exibe detalhes de um inquérito: estado, documentos, pessoas, delegacia.",
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={"numero_ip": _gt.Schema(type=_gt.Type.STRING, description="Número do IP, ex: 921-00332/2012")},
                required=["numero_ip"],
            ),
        ),
        _gt.FunctionDeclaration(
            name="busca_autos",
            description="Busca semântica nos documentos de um inquérito. Use para perguntas sobre fatos, pessoas ou eventos no caso.",
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={
                    "numero_ip": _gt.Schema(type=_gt.Type.STRING, description="Número do IP"),
                    "query": _gt.Schema(type=_gt.Type.STRING, description="O que pesquisar nos autos"),
                },
                required=["numero_ip", "query"],
            ),
        ),
        _gt.FunctionDeclaration(
            name="sintese_investigativa",
            description="Consulta ou gera a síntese investigativa completa de um inquérito. Use para: 'síntese', 'resumo do caso', 'análise do IP', 'relatório de situação'.",
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={"numero_ip": _gt.Schema(type=_gt.Type.STRING, description="Número do IP")},
                required=["numero_ip"],
            ),
        ),
        _gt.FunctionDeclaration(
            name="gerar_cautelar",
            description="Gera minuta de ato processual. Use para: ofício, requisição, mandado de busca, interceptação telefônica, quebra de sigilo bancário, prisão preventiva.",
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={
                    "numero_ip": _gt.Schema(type=_gt.Type.STRING, description="Número do IP"),
                    "tipo_cautelar": _gt.Schema(
                        type=_gt.Type.STRING,
                        description="Um de: oficio_requisicao | mandado_busca | interceptacao_telefonica | quebra_sigilo_bancario | autorizacao_prisao | oficio_generico",
                    ),
                    "instrucoes": _gt.Schema(type=_gt.Type.STRING, description="Instruções específicas sobre o conteúdo do ato"),
                },
                required=["numero_ip", "tipo_cautelar"],
            ),
        ),
        _gt.FunctionDeclaration(
            name="despachar_inquerito",
            description="Avança ou muda o estado de um inquérito. Use para: 'despacha', 'avança fase', 'manda para investigação/relatório/arquivo'.",
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={
                    "numero_ip": _gt.Schema(type=_gt.Type.STRING, description="Número do IP"),
                    "novo_estado": _gt.Schema(
                        type=_gt.Type.STRING,
                        description="Um de: triagem | investigacao | diligencias | analise | relatorio | encerramento | arquivamento",
                    ),
                },
                required=["numero_ip", "novo_estado"],
            ),
        ),
        _gt.FunctionDeclaration(
            name="agenda",
            description="Exibe as próximas oitivas e audiências agendadas.",
        ),
        _gt.FunctionDeclaration(
            name="ficha_pessoa",
            description="Consulta a ficha de uma pessoa nos autos de um inquérito.",
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={
                    "nome": _gt.Schema(type=_gt.Type.STRING, description="Nome da pessoa"),
                    "cpf": _gt.Schema(type=_gt.Type.STRING, description="CPF (opcional)"),
                    "numero_ip": _gt.Schema(type=_gt.Type.STRING, description="Número do IP (opcional se já em foco)"),
                },
            ),
        ),
        _gt.FunctionDeclaration(
            name="osint_avulso",
            description=(
                "Consulta OSINT em fontes EXTERNAS (fora do sistema). "
                "Use SOMENTE para: placas de veículo, ou quando o usuário JÁ confirmou que quer pesquisa externa "
                "após buscar internamente ('sim, pesquisa fora', 'faz o OSINT', 'pesquisa nas fontes externas'). "
                "NUNCA use como primeira opção para CPF ou nome — use buscar_pessoa_sistema primeiro."
            ),
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={
                    "cpf": _gt.Schema(type=_gt.Type.STRING, description="CPF somente dígitos"),
                    "cnpj": _gt.Schema(type=_gt.Type.STRING, description="CNPJ somente dígitos"),
                    "placa": _gt.Schema(type=_gt.Type.STRING, description="Placa do veículo"),
                    "nome": _gt.Schema(type=_gt.Type.STRING, description="Nome completo"),
                    "rg": _gt.Schema(type=_gt.Type.STRING, description="RG"),
                },
            ),
        ),
        _gt.FunctionDeclaration(
            name="buscar_pessoa_sistema",
            description=(
                "SEMPRE use esta ferramenta PRIMEIRO quando o usuário perguntar sobre uma pessoa ou CPF/CNPJ. "
                "Busca em TODO o sistema interno: autos dos inquéritos E intimações agendadas. "
                "Use para: 'tem fulano no sistema?', 've esse CPF', 'pesquisa esse CPF', 'quem é esse cara', "
                "'tem João Silva com intimação?', 'encontra essa pessoa', 'essa pessoa está nos autos?'. "
                "Só chame osint_avulso DEPOIS desta, se o usuário confirmar que quer pesquisa externa."
            ),
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={
                    "nome": _gt.Schema(type=_gt.Type.STRING, description="Nome (parcial) da pessoa"),
                    "cpf": _gt.Schema(type=_gt.Type.STRING, description="CPF somente dígitos (opcional)"),
                },
            ),
        ),
        _gt.FunctionDeclaration(
            name="salvar_documento",
            description=(
                "Salva um documento na área de trabalho do inquérito. "
                "Use quando o usuário pedir 'salva isso', 'salva o documento', 'guarda esse roteiro', "
                "'salva a cautelar', 'salva no IP'. Se o conteúdo não for informado, salva o último "
                "documento gerado na conversa."
            ),
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={
                    "numero_ip": _gt.Schema(type=_gt.Type.STRING, description="Número do IP"),
                    "titulo": _gt.Schema(type=_gt.Type.STRING, description="Título do documento"),
                    "tipo": _gt.Schema(
                        type=_gt.Type.STRING,
                        description="Um de: roteiro_oitiva | oficio | minuta_cautelar | relatorio | outro",
                    ),
                    "conteudo": _gt.Schema(
                        type=_gt.Type.STRING,
                        description="Conteúdo do documento. Se omitido, usa o último documento gerado na conversa.",
                    ),
                },
                required=["numero_ip", "titulo", "tipo"],
            ),
        ),
        _gt.FunctionDeclaration(
            name="ajuda",
            description="Exibe a lista de comandos e capacidades disponíveis.",
        ),
        _gt.FunctionDeclaration(
            name="abrir_peca_no_pdf",
            description=(
                "Abre uma peça específica no visualizador de PDF da interface, na página correta. "
                "Use quando o usuário pedir para ver/abrir/exibir uma peça dos autos. "
                "Primeiro use busca_autos para encontrar a peça e obter seu peca_id."
            ),
            parameters=_gt.Schema(
                type=_gt.Type.OBJECT,
                properties={
                    "peca_id": _gt.Schema(type=_gt.Type.STRING, description="UUID da peça extraída (campo id da tabela pecas_extraidas)"),
                    "mensagem": _gt.Schema(type=_gt.Type.STRING, description="Mensagem confirmando ao usuário o que está abrindo"),
                },
                required=["peca_id", "mensagem"],
            ),
        ),
    ])
    return _FC_TOOLS


# ── Service principal ─────────────────────────────────────────────────────────


class TelegramCopilotoService:
    """
    Copiloto Telegram do Escrivão AI.

    Fluxo por mensagem:
    1. Carrega contexto (histórico multi-turno + inquerito_atual) do Redis
    2. Gemini Function Calling classifica intenção e extrai parâmetros tipados
       - mode=AUTO: Gemini pode chamar função OU perguntar parâmetro faltante em texto
    3. Executa a ação com os serviços existentes
    4. Atualiza contexto no Redis (TTL 24h)
    5. Retorna texto formatado em HTML
    """

    def __init__(self):
        self.llm = LLMService()
        self._copiloto: Optional[CopilotoService] = None
        self._redis = None
        self._fc_client = None

    def _get_copiloto(self):
        if self._copiloto is None:
            self._copiloto = CopilotoService()
        return self._copiloto

    def _get_fc_client(self):
        if self._fc_client is None:
            from google import genai as _genai
            self._fc_client = _genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._fc_client

    # ── Redis ─────────────────────────────────────────────────────────────────

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    async def _load_ctx(self, chat_id: int | str) -> dict:
        r = await self._get_redis()
        raw = await r.get(f"telegram:ctx:{chat_id}")
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        return {"historico": [], "inquerito_atual": None, "ultimo_alvo": None}

    async def _save_ctx(self, chat_id: int | str, ctx: dict) -> None:
        r = await self._get_redis()
        await r.setex(
            f"telegram:ctx:{chat_id}",
            86400,
            json.dumps(ctx, ensure_ascii=False, default=str),
        )

    # ── Entry point ───────────────────────────────────────────────────────────

    async def processar_mensagem(
        self, chat_id: int | str, mensagem: str, db: AsyncSession
    ) -> str:
        """Processa uma mensagem recebida e retorna a resposta formatada em HTML."""

        if mensagem.strip().lower() in ("/start", "/ajuda", "/help", "ajuda", "help"):
            return _mensagem_ajuda()

        ctx = await self._load_ctx(chat_id)

        # Dispatcher via Gemini Function Calling
        fc_name, fc_args, texto_resposta = await self._dispatch_fc(mensagem, ctx)

        # Se Gemini respondeu com texto (pergunta de clarificação ou conversa)
        if fc_name is None:
            resposta = texto_resposta or "Como posso ajudar, Valdir?"
            ctx["historico"].append({"role": "user", "content": mensagem[:200]})
            ctx["historico"].append({"role": "model", "content": resposta[:300]})
            if len(ctx["historico"]) > 20:
                ctx["historico"] = ctx["historico"][-20:]
            await self._save_ctx(chat_id, ctx)
            return resposta

        logger.info(f"[TG-COPILOTO] chat={chat_id} fc={fc_name} args={fc_args}")

        # Execução da função
        try:
            if fc_name == "listar_inqueritos":
                resposta = await self._listar_inqueritos(db)

            elif fc_name == "status_inquerito":
                numero = fc_args.get("numero_ip", "") or ctx.get("inquerito_atual", "")
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._status_inquerito(numero, db)

            elif fc_name == "busca_autos":
                numero = fc_args.get("numero_ip") or ctx.get("inquerito_atual", "")
                query = fc_args.get("query", mensagem)
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._busca_autos(numero, query, ctx, db)

            elif fc_name == "agenda":
                resposta = await self._agenda(db)

            elif fc_name == "ficha_pessoa":
                nome = fc_args.get("nome", "")
                cpf = fc_args.get("cpf", "")
                numero = fc_args.get("numero_ip") or ctx.get("inquerito_atual", "")
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._ficha_pessoa(nome, cpf, numero, db)

            elif fc_name == "sintese_investigativa":
                numero = fc_args.get("numero_ip") or ctx.get("inquerito_atual", "")
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._sintese_investigativa(numero, db, ctx)

            elif fc_name == "gerar_cautelar":
                numero = fc_args.get("numero_ip") or ctx.get("inquerito_atual", "")
                tipo = fc_args.get("tipo_cautelar", "oficio_generico")
                instrucoes = fc_args.get("instrucoes", "")
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._gerar_cautelar(numero, tipo, instrucoes, db, ctx)

            elif fc_name == "despachar_inquerito":
                numero = fc_args.get("numero_ip") or ctx.get("inquerito_atual", "")
                novo_estado = fc_args.get("novo_estado", "")
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._despachar_inquerito(numero, novo_estado, db)

            elif fc_name == "buscar_pessoa_sistema":
                nome = fc_args.get("nome", "")
                cpf = fc_args.get("cpf", "")
                if cpf:
                    ctx["ultimo_alvo"] = f"CPF {cpf} ({nome})" if nome else f"CPF {cpf}"
                elif nome:
                    ctx["ultimo_alvo"] = nome
                resposta, inqueritos_encontrados = await self._buscar_pessoa_sistema(nome, cpf, db)
                # Se apenas um inquérito contém essa pessoa, define-o como foco automático
                if len(inqueritos_encontrados) == 1:
                    ctx["inquerito_atual"] = inqueritos_encontrados[0]

            elif fc_name == "osint_avulso":
                cpf = fc_args.get("cpf", "")
                nome = fc_args.get("nome", "")
                placa = fc_args.get("placa", "")
                if cpf:
                    ctx["ultimo_alvo"] = f"CPF {cpf}" + (f" ({nome})" if nome else "")
                elif nome:
                    ctx["ultimo_alvo"] = nome
                elif placa:
                    ctx["ultimo_alvo"] = f"placa {placa}"
                resposta = await self._osint_avulso(fc_args)

            elif fc_name == "salvar_documento":
                numero = fc_args.get("numero_ip") or ctx.get("inquerito_atual", "")
                titulo = fc_args.get("titulo", "Documento sem título")
                tipo = fc_args.get("tipo", "outro")
                conteudo = fc_args.get("conteudo") or ctx.get("ultimo_documento_conteudo", "")
                if numero:
                    ctx["inquerito_atual"] = numero
                resposta = await self._salvar_documento(numero, titulo, tipo, conteudo, db)

            elif fc_name == "ajuda":
                resposta = _mensagem_ajuda()

            elif fc_name == "abrir_peca_no_pdf":
                peca_id = fc_args.get("peca_id", "")
                mensagem_confirmacao = fc_args.get("mensagem", "Abrindo peça no visualizador...")
                # Emite tag XML que o frontend detecta para abrir o PDF viewer
                resposta = f'<ABRIR_PECA peca_id="{peca_id}"/>\n{mensagem_confirmacao}'

            else:
                resposta = texto_resposta or "Como posso ajudar, Valdir?"

        except Exception as e:
            logger.error(f"[TG-COPILOTO] Erro na função {fc_name}: {e}", exc_info=True)
            resposta = f"⚠️ Erro ao executar <b>{fc_name}</b>: {_esc(str(e)[:200])}"

        # Atualizar histórico multi-turno
        ctx["historico"].append({"role": "user", "content": mensagem[:200]})
        ctx["historico"].append({"role": "model", "content": resposta[:300]})
        if len(ctx["historico"]) > 20:
            ctx["historico"] = ctx["historico"][-20:]
        await self._save_ctx(chat_id, ctx)

        return resposta

    # ── Dispatcher via Gemini Function Calling ────────────────────────────────

    async def _dispatch_fc(
        self, mensagem: str, ctx: dict
    ) -> tuple[Optional[str], dict, Optional[str]]:
        """
        Chama Gemini com function declarations.
        Retorna (nome_funcao, argumentos, texto_resposta).
        - Se Gemini chama função: (nome, args, None)
        - Se Gemini responde com texto (pergunta/conversa): (None, {}, texto)
        """
        from google.genai import types as _gt

        inquerito_atual = ctx.get("inquerito_atual") or "nenhum"
        ultimo_alvo = ctx.get("ultimo_alvo") or "nenhum"
        data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")

        system = SYSTEM_PROMPT.format(
            inquerito_atual=inquerito_atual,
            ultimo_alvo=ultimo_alvo,
            data_hoje=data_hoje,
        )

        # Montar histórico como contents multi-turno
        contents = []
        for h in ctx.get("historico", [])[-8:]:  # últimas 4 trocas
            role = h.get("role", "user")
            content = h.get("content", "")
            if content:
                contents.append({"role": role, "parts": [{"text": content}]})

        contents.append({"role": "user", "parts": [{"text": mensagem}]})

        config = _gt.GenerateContentConfig(
            system_instruction=system,
            tools=[_get_fc_tools()],
            tool_config=_gt.ToolConfig(
                function_calling_config=_gt.FunctionCallingConfig(
                    mode="AUTO",  # Gemini decide: chamar função OU responder em texto
                )
            ),
            temperature=0.1,
        )

        try:
            response = await asyncio.wait_for(
                self._get_fc_client().aio.models.generate_content(
                    model=settings.LLM_STANDARD_MODEL,
                    contents=contents,
                    config=config,
                ),
                timeout=180.0,
            )

            # Verificar se retornou function call
            candidates = response.candidates or []
            if candidates and candidates[0].content and candidates[0].content.parts:
                for part in candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        return fc.name, dict(fc.args), None

            # Resposta em texto (pergunta de clarificação ou conversa)
            texto = response.text.strip() if response.text else None
            return None, {}, texto

        except Exception as e:
            erro_tipo = type(e).__name__
            logger.error(f"[TG-COPILOTO] Dispatcher FC falhou [{erro_tipo}]: {e}", exc_info=True)
            return None, {}, f"[DEBUG] {erro_tipo}: {str(e)[:200]}"

    # ── Ação: listar inquéritos ───────────────────────────────────────────────

    async def _listar_inqueritos(self, db: AsyncSession) -> str:
        result = await db.execute(
            select(Inquerito).order_by(Inquerito.updated_at.desc()).limit(20)
        )
        inqueritos = result.scalars().all()

        if not inqueritos:
            return "📂 Nenhum inquérito cadastrado."

        linhas = ["📋 <b>Inquéritos</b>\n"]
        for ip in inqueritos:
            estado = ESTADO_LABEL.get(ip.estado_atual, ip.estado_atual)
            docs = ip.total_documentos
            prio = " 🔴" if ip.prioridade == "alta" else ""
            linhas.append(
                f"• <code>{_esc(ip.numero)}</code> — {_esc(estado)}{prio}\n"
                f"  {docs} doc(s) · {_esc(ip.delegacia_atual_nome or ip.delegacia or '—')}"
            )

        return "\n".join(linhas)

    # ── Ação: status de inquérito ─────────────────────────────────────────────

    async def _status_inquerito(self, numero: str, db: AsyncSession) -> str:
        if not numero:
            return "ℹ️ Informe o número do inquérito. Ex: <i>status do IP 915-001/2024</i>"

        result = await db.execute(
            select(Inquerito).where(Inquerito.numero.ilike(f"%{numero.strip()}%"))
        )
        ip = result.scalars().first()
        if not ip:
            return f"❌ Inquérito <code>{_esc(numero)}</code> não encontrado."

        estado = ESTADO_LABEL.get(ip.estado_atual, ip.estado_atual)
        delegacia = ip.delegacia_atual_nome or ip.delegacia or "—"
        criado = ip.created_at.strftime("%d/%m/%Y") if ip.created_at else "—"
        atualizado = ip.updated_at.strftime("%d/%m/%Y %H:%M") if ip.updated_at else "—"

        partes = [
            f"🔍 <b>IP {_esc(ip.numero)}</b>",
            f"📌 Estado: <b>{_esc(estado)}</b>",
            f"🏛️ Delegacia: {_esc(delegacia)}",
            f"📄 Documentos: {ip.total_documentos} ({ip.total_paginas} pgs)",
            f"📅 Criado: {criado} · Atualizado: {atualizado}",
        ]

        if ip.prioridade and ip.prioridade != "media":
            partes.append(f"⚡ Prioridade: {_esc(ip.prioridade)}")

        if ip.descricao:
            partes.append(f"\n📝 {_esc(ip.descricao[:300])}")

        try:
            p_result = await db.execute(
                select(Pessoa).where(Pessoa.inquerito_id == ip.id).limit(5)
            )
            pessoas = p_result.scalars().all()
            if pessoas:
                nomes = ", ".join(_esc(p.nome) for p in pessoas[:3])
                extra = f" (+{len(pessoas)-3})" if len(pessoas) > 3 else ""
                partes.append(f"\n👥 Pessoas: {nomes}{extra}")
        except Exception:
            pass

        return "\n".join(partes)

    # ── Ação: busca semântica nos autos ───────────────────────────────────────

    async def _busca_autos(
        self, numero: str, query: str, ctx: dict, db: AsyncSession
    ) -> str:
        if not numero:
            return (
                "ℹ️ Informe o inquérito para a busca.\n"
                "Ex: <i>no IP 915-001/2024 o que sabemos sobre Fulano?</i>"
            )

        result = await db.execute(
            select(Inquerito).where(Inquerito.numero.ilike(f"%{numero.strip()}%"))
        )
        ip = result.scalars().first()
        if not ip:
            return f"❌ Inquérito <code>{_esc(numero)}</code> não encontrado."

        if ip.total_documentos == 0:
            return (
                f"📂 O IP <code>{_esc(ip.numero)}</code> ainda não tem documentos indexados.\n"
                "Faça o upload dos autos na interface web para habilitar a busca."
            )

        try:
            resultado = await self._get_copiloto().processar_mensagem(
                query=query,
                inquerito_id=str(ip.id),
                historico=[
                    {"role": h.get("role", "user"), "content": h.get("content", "")}
                    for h in ctx.get("historico", [])[-6:]
                ],
                numero_inquerito=ip.numero,
                estado_atual=ip.estado_atual,
                total_paginas=ip.total_paginas,
                total_documentos=ip.total_documentos,
                auditar=False,
                db=db,
            )
        except Exception as e:
            logger.error(f"[TG-COPILOTO] Erro CopilotoService: {e}", exc_info=True)
            return f"⚠️ Erro ao consultar os autos: {_esc(str(e)[:200])}"

        resposta_texto = resultado.get("resposta", "Sem resposta.")
        fontes = resultado.get("fontes", [])

        if len(resposta_texto) > 3000:
            resposta_texto = resposta_texto[:2997] + "..."

        partes = [
            f"🔎 <b>Busca no IP {_esc(ip.numero)}</b>",
            f'<i>"{_esc(query[:100])}"</i>\n',
            resposta_texto,
        ]

        if fontes:
            docs_unicos = list({f.get("documento_id", "")[:20] for f in fontes[:3] if f.get("documento_id")})
            partes.append(f"\n📎 Fontes: {', '.join(_esc(d) for d in docs_unicos)}")

        return "\n".join(partes)

    # ── Ação: agenda ─────────────────────────────────────────────────────────

    async def _agenda(self, db: AsyncSession) -> str:
        agora = datetime.now(timezone.utc).replace(tzinfo=None)

        result = await db.execute(
            select(Intimacao)
            .where(Intimacao.data_oitiva >= agora)
            .where(Intimacao.status == "agendada")
            .order_by(Intimacao.data_oitiva.asc())
            .limit(10)
        )
        intimacoes = result.scalars().all()

        if not intimacoes:
            result_past = await db.execute(
                select(Intimacao)
                .where(Intimacao.status == "agendada")
                .order_by(Intimacao.data_oitiva.desc())
                .limit(5)
            )
            recentes = result_past.scalars().all()
            if not recentes:
                return "📅 Nenhuma oitiva ou audiência agendada."
            return "📅 Nenhuma oitiva futura. Consulte a interface web para ver o histórico."

        linhas = ["📅 <b>Próximas oitivas / audiências</b>\n"]
        for it in intimacoes:
            data_str = it.data_oitiva.strftime("%d/%m/%Y %H:%M") if it.data_oitiva else "data?"
            nome = _esc(it.intimado_nome or "—")
            qualif = it.intimado_qualificacao or ""
            local = _esc(it.local_oitiva or "local não informado")
            qualif_str = f" ({_esc(qualif)})" if qualif else ""

            linha = f"• <b>{data_str}</b> — {nome}{qualif_str}\n  📍 {local}"
            if it.google_event_url:
                linha += f'\n  <a href="{it.google_event_url}">→ Abrir no Google Agenda</a>'
            linhas.append(linha)

        return "\n".join(linhas)

    # ── Ação: ficha pessoa ────────────────────────────────────────────────────

    async def _ficha_pessoa(
        self, nome: str, cpf: str, numero_ip: str, db: AsyncSession
    ) -> str:
        if not nome and not cpf:
            return "ℹ️ Informe o nome ou CPF da pessoa. Ex: <i>ficha do João Silva no IP 915-001/2024</i>"

        query = select(Pessoa)
        if cpf:
            query = query.where(Pessoa.cpf == cpf.strip())
        elif nome:
            query = query.where(Pessoa.nome.ilike(f"%{nome.strip()}%"))

        if numero_ip:
            ip_result = await db.execute(
                select(Inquerito).where(Inquerito.numero.ilike(f"%{numero_ip.strip()}%"))
            )
            ip = ip_result.scalars().first()
            if ip:
                query = query.where(Pessoa.inquerito_id == ip.id)

        query = query.order_by(Pessoa.created_at.desc()).limit(5)
        result = await db.execute(query)
        pessoas = result.scalars().all()

        if not pessoas:
            alvo = cpf or nome
            return f"❌ Nenhuma pessoa encontrada para <i>{_esc(alvo)}</i> nos autos indexados."

        # Carregar inquéritos para mostrar o número do IP
        inq_ids = list({p.inquerito_id for p in pessoas if p.inquerito_id})
        inq_map: dict = {}
        if inq_ids:
            inq_res = await db.execute(select(Inquerito).where(Inquerito.id.in_(inq_ids)))
            for inq in inq_res.scalars().all():
                inq_map[inq.id] = inq

        linhas = ["👤 <b>Ficha(s) encontrada(s)</b>\n"]
        for p in pessoas:
            tipo = _esc(p.tipo_pessoa or "não classificado")
            cpf_str = f" · CPF: <code>{_esc(p.cpf)}</code>" if p.cpf else ""
            inq = inq_map.get(p.inquerito_id)
            ip_str = f"\n📂 IP: <code>{_esc(inq.numero)}</code>" if inq else ""
            linhas.append(f"<b>{_esc(p.nome)}</b> — {tipo}{cpf_str}{ip_str}")
            if inq and inq.descricao:
                linhas.append(f"  📌 {_esc(inq.descricao[:200])}")
            if p.resumo_contexto:
                linhas.append(f"<i>{_esc(p.resumo_contexto[:400])}</i>")
            if p.observacoes:
                linhas.append(f"📝 {_esc(p.observacoes[:200])}")
            linhas.append("")

        linhas.append("💡 Para enriquecimento OSINT (P1–P4) use a interface web.")
        return "\n".join(linhas)

    # ── Ação: buscar pessoa em todo o sistema ────────────────────────────────

    async def _buscar_pessoa_sistema(self, nome: str, cpf: str, db: AsyncSession) -> tuple[str, list[str]]:
        """
        Busca pessoa nos autos indexados E nas intimações agendadas.
        Retorna (texto_resposta, lista_de_numeros_ip_unicos_encontrados).
        """
        if not nome and not cpf:
            return "ℹ️ Informe o nome ou CPF da pessoa para buscar.", []

        partes = [f"🔍 <b>Busca por: {_esc(nome or cpf)}</b>\n"]
        encontrou = False
        numeros_ip_encontrados: list[str] = []

        # 1. Buscar nos autos (tabela Pessoa) — join com Inquerito para mostrar o IP
        query = select(Pessoa)
        if cpf:
            query = query.where(Pessoa.cpf == cpf.strip())
        else:
            query = query.where(Pessoa.nome.ilike(f"%{nome.strip()}%"))
        query = query.limit(5)

        result = await db.execute(query)
        pessoas = result.scalars().all()

        if pessoas:
            encontrou = True
            # Carregar os inquéritos associados
            inq_ids = list({p.inquerito_id for p in pessoas if p.inquerito_id})
            inq_map: dict = {}
            if inq_ids:
                inq_result = await db.execute(
                    select(Inquerito).where(Inquerito.id.in_(inq_ids))
                )
                for inq in inq_result.scalars().all():
                    inq_map[inq.id] = inq

            partes.append("👥 <b>Nos autos dos inquéritos:</b>")
            for p in pessoas:
                tipo = _esc(p.tipo_pessoa or "não classificado")
                cpf_str = f" · CPF: <code>{_esc(p.cpf)}</code>" if p.cpf else ""
                inq = inq_map.get(p.inquerito_id)
                ip_str = f" · IP <code>{_esc(inq.numero)}</code>" if inq else ""
                partes.append(f"• <b>{_esc(p.nome)}</b> — {tipo}{cpf_str}{ip_str}")
                if p.resumo_contexto:
                    partes.append(f"  <i>{_esc(p.resumo_contexto[:200])}</i>")
                if inq and inq.descricao:
                    partes.append(f"  📌 {_esc(inq.descricao[:150])}")
                if inq and inq.numero not in numeros_ip_encontrados:
                    numeros_ip_encontrados.append(inq.numero)
            partes.append("")

        # 2. Buscar nas intimações
        intim_query = select(Intimacao)
        if cpf:
            intim_query = intim_query.where(Intimacao.intimado_cpf == cpf.strip())
        else:
            intim_query = intim_query.where(Intimacao.intimado_nome.ilike(f"%{nome.strip()}%"))
        intim_query = intim_query.order_by(Intimacao.data_oitiva.desc()).limit(5)

        intim_result = await db.execute(intim_query)
        intimacoes = intim_result.scalars().all()

        if intimacoes:
            encontrou = True
            partes.append("📅 <b>Intimações encontradas:</b>")
            for it in intimacoes:
                data_str = it.data_oitiva.strftime("%d/%m/%Y %H:%M") if it.data_oitiva else "sem data"
                status = it.status or "—"
                local = _esc(it.local_oitiva or "local não informado")
                partes.append(f"• <b>{data_str}</b> — {_esc(it.intimado_nome or '—')} ({_esc(status)})")
                partes.append(f"  📍 {local}")
                if it.google_event_url:
                    partes.append(f'  <a href="{it.google_event_url}">→ Google Agenda</a>')
            partes.append("")

        if not encontrou:
            alvo = nome or cpf
            tipo = "CPF <code>" + _esc(cpf) + "</code>" if cpf else f"<i>{_esc(nome)}</i>"
            return (
                f"❌ {tipo} não encontrado nos autos nem nas intimações do sistema.\n\n"
                f"Quer que eu faça uma pesquisa complementar nas <b>fontes externas (OSINT)</b>?",
                [],
            )

        # Dica de foco automático
        if len(numeros_ip_encontrados) == 1:
            partes.append(f"💡 IP em foco: <code>{_esc(numeros_ip_encontrados[0])}</code> — pode perguntar diretamente sobre este inquérito.")
        elif len(numeros_ip_encontrados) > 1:
            partes.append(f"💡 Encontrada em {len(numeros_ip_encontrados)} IPs: {', '.join(_esc(n) for n in numeros_ip_encontrados)}. Informe qual IP para detalhes.")

        return "\n".join(partes), numeros_ip_encontrados

    # ── Ação: OSINT avulso ────────────────────────────────────────────────────

    async def _osint_avulso(self, params: dict) -> str:
        cpf = params.get("cpf", "").strip() or None
        cnpj = params.get("cnpj", "").strip() or None
        placa = params.get("placa", "").strip() or None
        nome = params.get("nome", "").strip() or None
        rg = params.get("rg", "").strip() or None

        if not any([cpf, cnpj, placa, nome, rg]):
            return (
                "ℹ️ Informe ao menos um dado para a consulta OSINT.\n"
                "Ex: <i>pesquisar CPF 000.000.000-00</i> ou <i>verificar placa ABC1234</i>"
            )

        from app.services.osint_service import OsintService
        osint = OsintService()

        try:
            dados = await osint.consulta_avulsa(
                cpf=cpf, cnpj=cnpj, placa=placa, nome=nome, rg=rg
            )
        except Exception as e:
            logger.error(f"[TG-COPILOTO] OSINT avulso falhou: {e}", exc_info=True)
            return f"⚠️ Erro na consulta OSINT: {_esc(str(e)[:200])}"

        fontes_ok = dados.get("fontes_consultadas", [])
        if not fontes_ok:
            alvo = cpf or cnpj or placa or nome or rg
            return f"❌ Nenhum dado encontrado para <code>{_esc(alvo)}</code> nas fontes consultadas."

        partes = ["🔍 <b>Consulta OSINT Avulsa</b>"]
        if cpf:
            partes.append(f"CPF: <code>{_esc(cpf)}</code>")
        if placa:
            partes.append(f"Placa: <code>{_esc(placa)}</code>")
        if cnpj:
            partes.append(f"CNPJ: <code>{_esc(cnpj)}</code>")
        if nome:
            partes.append(f"Nome: <i>{_esc(nome)}</i>")
        partes.append("")

        cad = dados.get("cadastro")
        if cad and isinstance(cad, dict):
            nome_ret = cad.get("nome") or cad.get("nome_completo") or ""
            nasc = cad.get("data_nascimento") or cad.get("nascimento") or ""
            mae = cad.get("nome_mae") or ""
            sit = cad.get("situacao_cpf") or cad.get("situacao") or ""
            sexo = cad.get("sexo") or ""
            if nome_ret:
                partes.append(f"👤 <b>{_esc(nome_ret)}</b>")
            if nasc:
                partes.append(f"🎂 Nascimento: {_esc(str(nasc))}" + (f" · {_esc(sexo)}" if sexo else ""))
            if mae:
                partes.append(f"👩 Mãe: {_esc(mae)}")
            if sit:
                partes.append(f"📋 CPF: {_esc(sit)}")

            # Endereços
            enderecos = cad.get("enderecos") or cad.get("endereco") or []
            if isinstance(enderecos, dict):
                enderecos = [enderecos]
            if isinstance(enderecos, list) and enderecos:
                partes.append("📍 <b>Endereços:</b>")
                for end in enderecos[:3]:
                    if isinstance(end, dict):
                        logr = end.get("logradouro") or end.get("endereco") or ""
                        num = end.get("numero") or ""
                        bairro = end.get("bairro") or ""
                        cidade = end.get("municipio") or end.get("cidade") or ""
                        uf_end = end.get("uf") or end.get("estado") or ""
                        cep = end.get("cep") or ""
                        linha = f"{logr} {num}, {bairro} — {cidade}/{uf_end}"
                        if cep:
                            linha += f" CEP {cep}"
                        partes.append(f"  • {_esc(linha.strip(', —'))}")
                    elif isinstance(end, str):
                        partes.append(f"  • {_esc(end)}")

            # Telefones
            telefones = cad.get("telefones") or cad.get("telefone") or []
            if isinstance(telefones, str):
                telefones = [telefones]
            if isinstance(telefones, list) and telefones:
                partes.append("📞 <b>Telefones:</b>")
                for t in telefones[:5]:
                    if isinstance(t, dict):
                        numero = t.get("telefoneComDDD") or t.get("numero") or t.get("telefone") or ""
                        tipo = t.get("tipoTelefone") or ""
                        operadora = t.get("operadora") or ""
                        whats = " · WhatsApp ✓" if t.get("whatsApp") else ""
                        bloqueado = " · Bloqueado" if t.get("telemarketingBloqueado") else ""
                        info = f"{tipo} · {operadora}".strip(" ·") if tipo or operadora else ""
                        partes.append(f"  • <code>{_esc(numero)}</code>" + (f" ({_esc(info)})" if info else "") + _esc(whats) + _esc(bloqueado))
                    else:
                        partes.append(f"  • <code>{_esc(str(t))}</code>")

            # Emails
            emails = cad.get("emails") or cad.get("email") or []
            if isinstance(emails, str):
                emails = [emails]
            if isinstance(emails, list) and emails:
                partes.append("✉️ <b>Emails:</b>")
                for e in emails[:3]:
                    if isinstance(e, dict):
                        addr = e.get("enderecoEmail") or e.get("email") or e.get("endereco") or str(e)
                    else:
                        addr = str(e)
                    partes.append(f"  • {_esc(addr)}")

        veiculo = (
            dados.get("veiculo")
            or (dados.get("historico_veiculos") or [None])[0]
            if isinstance(dados.get("historico_veiculos"), list)
            else None
        )
        if isinstance(veiculo, dict) and veiculo:
            marca = veiculo.get("marca_modelo") or veiculo.get("marca") or ""
            cor = veiculo.get("cor") or ""
            ano = veiculo.get("ano_fabricacao") or ""
            prop = veiculo.get("proprietario") or veiculo.get("nome_proprietario") or ""
            if marca:
                partes.append(f"\n🚗 Veículo: {_esc(marca)} {_esc(cor)} {_esc(str(ano))}")
            if prop:
                partes.append(f"   Proprietário: {_esc(prop)}")

        alertas = []
        if dados.get("mandados_prisao") and isinstance(dados["mandados_prisao"], list) and dados["mandados_prisao"]:
            alertas.append("⚠️ MANDADO DE PRISÃO")
        if dados.get("pep") and dados["pep"]:
            alertas.append("🏛️ PEP (pessoa politicamente exposta)")
        if dados.get("aml") and dados["aml"]:
            alertas.append("💰 Restrição AML/lavagem")
        if dados.get("obito") and isinstance(dados["obito"], dict) and dados["obito"].get("data_obito"):
            alertas.append("💀 ÓBITO registrado")
        if alertas:
            partes.append("\n" + " | ".join(alertas))

        partes.append(f"\n📡 Fontes: {', '.join(_esc(f) for f in fontes_ok)}")
        return "\n".join(partes)

    # ── Ação: síntese investigativa ───────────────────────────────────────────

    async def _sintese_investigativa(
        self, numero_ip: str, db: AsyncSession, ctx: dict | None = None
    ) -> str:
        if not numero_ip:
            return "ℹ️ Informe o número do IP. Ex: <i>síntese do IP 915-001/2024</i>"

        result = await db.execute(
            select(Inquerito).where(Inquerito.numero.ilike(f"%{numero_ip.strip()}%"))
        )
        ip = result.scalars().first()
        if not ip:
            return f"❌ Inquérito <code>{_esc(numero_ip)}</code> não encontrado."

        try:
            from app.services.summary_service import SummaryService
            resumo = await SummaryService().obter_resumo_caso(db, ip.id)
        except Exception as e:
            logger.error(f"[TG-COPILOTO] Erro ao buscar síntese: {e}", exc_info=True)
            return f"⚠️ Erro ao consultar síntese: {_esc(str(e)[:200])}"

        if not resumo:
            return (
                f"⚠️ Síntese não disponível para o IP <code>{_esc(ip.numero)}</code>.\n"
                "Acesse a interface web e clique em <b>✨ Gerar Síntese</b>."
            )

        if ctx is not None:
            ctx["ultimo_documento_conteudo"] = resumo
            ctx["ultimo_documento_titulo"] = f"Síntese Investigativa — IP {ip.numero}"
            ctx["ultimo_documento_tipo"] = "relatorio"

        preview = resumo[:3200]
        if len(resumo) > 3200:
            preview += "\n\n<i>… (acesse a interface web para a síntese completa)</i>"

        return (
            f"📊 <b>Síntese — IP {_esc(ip.numero)}</b>\n\n{_esc(preview)}\n\n"
            f"💾 <i>Diga 'salva esse documento' para guardar na área de trabalho do inquérito.</i>"
        )

    # ── Ação: gerar cautelar ──────────────────────────────────────────────────

    _TIPOS_CAUTELAR_VALIDOS = {
        "oficio_requisicao", "mandado_busca", "interceptacao_telefonica",
        "quebra_sigilo_bancario", "autorizacao_prisao", "oficio_generico",
    }

    async def _gerar_cautelar(
        self, numero_ip: str, tipo_cautelar: str, instrucoes: str, db: AsyncSession,
        ctx: dict | None = None
    ) -> str:
        if not numero_ip:
            return (
                "ℹ️ Informe o IP e o tipo de ato.\n"
                "Ex: <i>faz um ofício de requisição para o IP 915-001/2024</i>"
            )

        result = await db.execute(
            select(Inquerito).where(Inquerito.numero.ilike(f"%{numero_ip.strip()}%"))
        )
        ip = result.scalars().first()
        if not ip:
            return f"❌ Inquérito <code>{_esc(numero_ip)}</code> não encontrado."

        if tipo_cautelar not in self._TIPOS_CAUTELAR_VALIDOS:
            tipo_cautelar = "oficio_generico"

        try:
            from app.services.agente_cautelar import AgenteCautelar
            resultado = await AgenteCautelar().gerar_cautelar(
                db=db,
                inquerito_id=ip.id,
                tipo_cautelar=tipo_cautelar,
                instrucoes=instrucoes or "Redija conforme os fatos do inquérito.",
            )
        except Exception as e:
            logger.error(f"[TG-COPILOTO] Erro ao gerar cautelar: {e}", exc_info=True)
            return f"⚠️ Erro ao gerar o ato: {_esc(str(e)[:200])}"

        titulo = resultado["tipo"]
        texto = resultado["texto_gerado"]

        if ctx is not None:
            ctx["ultimo_documento_conteudo"] = texto
            ctx["ultimo_documento_titulo"] = titulo
            ctx["ultimo_documento_tipo"] = "minuta_cautelar"

        preview = texto[:1800]
        if len(texto) > 1800:
            preview += "\n\n<i>… (acesse Cautelares na interface web para o documento completo)</i>"

        return (
            f"📄 <b>{_esc(titulo)}</b>\n"
            f"IP: <code>{_esc(ip.numero)}</code>\n\n"
            f"{_esc(preview)}\n\n"
            f"💾 <i>Diga 'salva esse documento' para guardar na área de trabalho do inquérito.</i>"
        )

    # ── Ação: salvar documento ────────────────────────────────────────────────

    _TIPOS_DOC_VALIDOS = {
        "roteiro_oitiva", "oficio", "minuta_cautelar", "relatorio", "outro",
    }

    async def _salvar_documento(
        self, numero_ip: str, titulo: str, tipo: str, conteudo: str, db: AsyncSession
    ) -> str:
        if not numero_ip:
            return (
                "ℹ️ Informe o inquérito para salvar o documento.\n"
                "Ex: <i>salva esse documento no IP 921-00332/2012</i>"
            )

        if not conteudo:
            return (
                "⚠️ Nenhum documento recente para salvar.\n"
                "Gere um ato (cautelar, roteiro, síntese) primeiro e então diga 'salva isso'."
            )

        result = await db.execute(
            select(Inquerito).where(Inquerito.numero.ilike(f"%{numero_ip.strip()}%"))
        )
        ip = result.scalars().first()
        if not ip:
            return f"❌ Inquérito <code>{_esc(numero_ip)}</code> não encontrado."

        if tipo not in self._TIPOS_DOC_VALIDOS:
            tipo = "outro"

        import re as _re
        # Remove tags HTML do Telegram antes de salvar (bold, italic, code, etc.)
        conteudo_limpo = _re.sub(r"<b>(.*?)</b>", r"**\1**", conteudo, flags=_re.DOTALL)
        conteudo_limpo = _re.sub(r"<i>(.*?)</i>", r"*\1*", conteudo_limpo, flags=_re.DOTALL)
        conteudo_limpo = _re.sub(r"<code>(.*?)</code>", r"`\1`", conteudo_limpo, flags=_re.DOTALL)
        conteudo_limpo = _re.sub(r"<pre>(.*?)</pre>", r"```\n\1\n```", conteudo_limpo, flags=_re.DOTALL)
        conteudo_limpo = _re.sub(r"<[^>]+>", "", conteudo_limpo)
        conteudo_limpo = conteudo_limpo.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')

        from app.models.documento_gerado import DocumentoGerado
        doc = DocumentoGerado(
            inquerito_id=ip.id,
            titulo=titulo,
            tipo=tipo,
            conteudo=conteudo_limpo,
        )
        db.add(doc)
        await db.commit()

        logger.info(f"[TG-COPILOTO] Documento salvo: {titulo!r} tipo={tipo} ip={ip.numero}")

        return (
            f"✅ <b>Documento salvo!</b>\n"
            f"📄 <b>{_esc(titulo)}</b>\n"
            f"IP: <code>{_esc(ip.numero)}</code> · Tipo: {_esc(tipo)}\n\n"
            f"Acesse a <b>Área de Trabalho</b> na interface web para visualizar e editar."
        )

    # ── Ação: despachar inquérito ─────────────────────────────────────────────

    async def _despachar_inquerito(
        self, numero_ip: str, novo_estado: str, db: AsyncSession
    ) -> str:
        if not numero_ip or not novo_estado:
            return (
                "ℹ️ Informe o IP e o novo estado.\n"
                "Ex: <i>despacha o IP 915-001/2024 para investigação</i>\n"
                f"Estados: {', '.join(ESTADO_LABEL.values())}"
            )

        result = await db.execute(
            select(Inquerito).where(Inquerito.numero.ilike(f"%{numero_ip.strip()}%"))
        )
        ip = result.scalars().first()
        if not ip:
            return f"❌ Inquérito <code>{_esc(numero_ip)}</code> não encontrado."

        if novo_estado not in ESTADO_LABEL:
            return (
                f"❌ Estado inválido: <code>{_esc(novo_estado)}</code>\n"
                f"Estados válidos: {', '.join(ESTADO_LABEL.keys())}"
            )

        estado_anterior = ESTADO_LABEL.get(ip.estado_atual, ip.estado_atual)
        ip.estado_atual = novo_estado
        await db.commit()

        estado_novo_label = ESTADO_LABEL[novo_estado]
        return (
            f"✅ IP <code>{_esc(ip.numero)}</code> despachado.\n"
            f"{_esc(estado_anterior)} → <b>{_esc(estado_novo_label)}</b>"
        )


# ── Alerta proativo (chamado pelo Celery beat) ────────────────────────────────

async def enviar_alertas_intimacoes(db: AsyncSession) -> list[str]:
    """
    Verifica intimações nas próximas 48h e retorna mensagens de alerta.
    Chamado pelo Celery beat task telegram_alertas.
    """
    from datetime import timedelta

    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    em_48h = agora + timedelta(hours=48)

    result = await db.execute(
        select(Intimacao)
        .where(Intimacao.data_oitiva >= agora)
        .where(Intimacao.data_oitiva <= em_48h)
        .where(Intimacao.status == "agendada")
        .order_by(Intimacao.data_oitiva.asc())
    )
    intimacoes = result.scalars().all()

    if not intimacoes:
        return []

    alertas = []
    for it in intimacoes:
        data_str = it.data_oitiva.strftime("%d/%m %H:%M") if it.data_oitiva else "?"
        delta = it.data_oitiva - agora if it.data_oitiva else None
        horas = int(delta.total_seconds() / 3600) if delta else 0
        nome = it.intimado_nome or "—"
        local = it.local_oitiva or "local não informado"

        urgencia = "🔴" if horas <= 24 else "🟡"
        msg = (
            f"{urgencia} <b>Oitiva em {horas}h</b>\n"
            f"👤 {_esc(nome)}\n"
            f"📅 {data_str}\n"
            f"📍 {_esc(local)}"
        )
        if it.google_event_url:
            msg += f'\n<a href="{it.google_event_url}">→ Google Agenda</a>'
        alertas.append(msg)

    return alertas


# ── Helpers ───────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mensagem_ajuda() -> str:
    return (
        "🤖 <b>Escrivão AI — Copiloto</b>\n\n"
        "<b>📋 Inquéritos</b>\n"
        "• <i>listar inquéritos</i> — todos os IPs\n"
        "• <i>status do IP 921-00332/2012</i> — detalhes\n"
        "• <i>síntese do IP 921-00332/2012</i> — análise completa\n"
        "• <i>despacha o 921-00332 para investigação</i>\n\n"
        "<b>🔎 Busca e pessoas</b>\n"
        "• <i>no IP 921-00332, o que sabemos sobre X?</i>\n"
        "• <i>ficha do João Silva no IP 921-00332</i>\n\n"
        "<b>📄 Atos processuais</b>\n"
        "• <i>faz um ofício de requisição para o 921-00332</i>\n"
        "• <i>manda um mandado de busca para o juiz</i>\n"
        "• <i>quebra de sigilo bancário do investigado</i>\n"
        "• <i>salva esse documento</i> — guarda o último ato gerado na área de trabalho\n\n"
        "<b>🔍 OSINT e agenda</b>\n"
        "• <i>ve esse CPF: 000.000.000-00</i>\n"
        "• <i>verifica placa ABC1D23</i>\n"
        "• <i>agenda</i> — próximas oitivas\n\n"
        "💡 Mantenho o inquérito em foco entre mensagens.\n"
        "Pode falar naturalmente — entendo português informal.\n"
        "/ajuda — exibe esta mensagem"
    )
