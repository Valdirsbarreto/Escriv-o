"""
Test Script: Validação da Arquitetura de 3 Camadas LLM
Verifica se as chamadas para Econômico, Standard e Premium estão roteadas e funcionando.
"""

import asyncio
import os
import sys

# Adiciona o diretório backend ao path para importar app
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.llm_service import LLMService

async def test_3_layers():
    llm = LLMService()
    
    tiers = ["economico", "standard", "premium"]
    results = []

    print("\n🚀 Iniciando teste de 3 Camadas LLM...\n")

    for tier in tiers:
        print(f"📡 Testando Tier: {tier.upper()}...")
        try:
            prompt = [{"role": "user", "content": f"Responda apenas 'OK-{tier.upper()}'"}]
            start_time = asyncio.get_event_loop().time()
            
            response = await llm.chat_completion(
                messages=prompt,
                tier=tier,
                max_tokens=10
            )
            
            end_time = asyncio.get_event_loop().time()
            duration = int((end_time - start_time) * 1000)
            
            print(f"✅ Sucesso: {response['content'].strip()}")
            print(f"   Modelo: {response['model']}")
            print(f"   Tempo: {duration}ms | Custo: ${response['custo_estimado']:.6f}")
            
            results.append({
                "tier": tier,
                "status": "PASS",
                "model": response['model'],
                "content": response['content'].strip()
            })
        except Exception as e:
            print(f"❌ Falha no Tier {tier}: {e}")
            results.append({"tier": tier, "status": "FAIL", "error": str(e)})
        print("-" * 30)

    print("\n📊 Resumo do Teste:")
    for res in results:
        status_icon = "🟢" if res["status"] == "PASS" else "🔴"
        print(f"{status_icon} {res['tier'].upper()}: {res['status']} ({res.get('model', 'N/A')})")

if __name__ == "__main__":
    asyncio.run(test_3_layers())
