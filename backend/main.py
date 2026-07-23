from dotenv import load_dotenv
from openai import OpenAI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import json

load_dotenv()

app = FastAPI(title="AI Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)

MODEL_CONTEXT_LIMITS = {
    "gpt-3.5-turbo": 16384,
    "gpt-4": 8192,
    "qwen-turbo": 131072,
    "qwen-plus": 131072,
    "qwen-max": 32768,
    "deepseek-chat": 65536,
}

def estimate_tokens(text: str) -> int:
    return len(text) // 2 + 1

def truncate_context(messages: list[dict], model: str, max_context_tokens: int) -> list[dict]:
    limit = MODEL_CONTEXT_LIMITS.get(model, max_context_tokens)
    safe_limit = int(limit * 0.8)

    total = sum(estimate_tokens(m["content"]) + 4 for m in messages)

    if total <= safe_limit:
        return messages

    system_msgs = [m for m in messages if m["role"] == "system"]
    others = [m for m in messages if m["role"] != "system"]

    while total > safe_limit and len(others) > 1:
        removed = others.pop(0)
        total -= estimate_tokens(removed["content"]) + 4

    return system_msgs + others

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False

@app.get("/")
def root():
    return {"message": "AI Chat API is running"}

@app.post("/chat")
def chat(request: ChatRequest):
    try:
        truncated = truncate_context(
            [m.model_dump() for m in request.messages],
            request.model,
            request.max_tokens,
        )
        resp = client.chat.completions.create(
            model=request.model,
            messages=truncated,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return {
            "reply": resp.choices[0].message.content,
            "model": resp.model,
        }
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    truncated = truncate_context(
        [m.model_dump() for m in request.messages],
        request.model,
        request.max_tokens,
    )

    def generate():
        try:
            stream = client.chat.completions.create(
                model=request.model,
                messages=truncated,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'content': chunk.choices[0].delta.content})}\n\n"
            yield f"data: {json.dumps({'content': '[DONE]'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
