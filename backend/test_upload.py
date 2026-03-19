import httpx
import asyncio

async def test_upload():
    async with httpx.AsyncClient() as client:
        with open("requirements.txt", "rb") as f:
            files = {"files": ("req.txt", f, "text/plain")}
            response = await client.post(
                "https://escriv-o-production.up.railway.app/api/v1/ingestao/iniciar", 
                files=files, 
                timeout=60.0
            )
            print(f"Status: {response.status_code}")
            print(f"Body: {response.text}")

asyncio.run(test_upload())
