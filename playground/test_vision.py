import os
import asyncio
from openai import AsyncOpenAI
from tools.settings import load_settings
from pathlib import Path

async def test_vision():
    load_settings()
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("VISION_MODEL_NAME", "gpt-4o-mini")
    
    print("Testing Vision API with:")
    print(f"  Base URL: {base_url}")
    print(f"  Model: {model}")
    print(f"  Key: {api_key[:10]}...")
    
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    try:
        # Minimal test: ask about a tiny black dot image
        dot_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{dot_b64}"}}
                    ]
                }
            ],
            max_tokens=10
        )
        print("Success!")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_vision())
