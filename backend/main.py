# 加载 .env 文件中的环境变量（API Key、Base URL 等）
from dotenv import load_dotenv
# OpenAI 客户端，用来调大模型的 API
from openai import OpenAI
# FastAPI 框架，用来搭后端服务
from fastapi import FastAPI
# 跨域中间件，让前端能访问后端
from fastapi.middleware.cors import CORSMiddleware
# 流式响应，实现打字机效果
from fastapi.responses import StreamingResponse
# 数据模型，定义请求和返回的格式
from pydantic import BaseModel
import os
import json

load_dotenv()

# 创建 FastAPI 应用实例
app = FastAPI(title="AI Chat API")

# 配置跨域，允许所有来源访问（开发环境用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建 OpenAI 客户端，从 .env 读取 API Key 和接口地址
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)

# 各型号模型的上下文窗口大小（能接受的最大 Token 数）
# 不同的模型能力不同，支持的上下文长度也不一样
MODEL_CONTEXT_LIMITS = {
    "gpt-3.5-turbo": 16384,
    "gpt-4": 8192,
    "qwen-turbo": 131072,
    "qwen-plus": 131072,
    "qwen-max": 32768,
    "deepseek-chat": 65536,
}

# 估算一段文字占多少 Token（按中文字符估算）
def estimate_tokens(text: str) -> int:
    return len(text) // 2 + 1

# 智能截断上下文，防止 Token 超限
# 优先保留 system 消息，从最早的非 system 消息开始删
def truncate_context(messages: list[dict], model: str, max_context_tokens: int) -> list[dict]:
    limit = MODEL_CONTEXT_LIMITS.get(model, max_context_tokens)
    safe_limit = int(limit * 0.8)  # 留 20% 余量给回复

    total = sum(estimate_tokens(m["content"]) + 4 for m in messages)

    if total <= safe_limit:
        return messages

    system_msgs = [m for m in messages if m["role"] == "system"]
    others = [m for m in messages if m["role"] != "system"]

    # 从最早的消息开始删，直到不超过上限
    while total > safe_limit and len(others) > 1:
        removed = others.pop(0)
        total -= estimate_tokens(removed["content"]) + 4

    return system_msgs + others

# 定义消息的格式：role（角色）和 content（内容）
class ChatMessage(BaseModel):
    role: str
    content: str

# 定义聊天请求的格式：消息列表、模型、参数等
class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False

# 根路径，用来验证服务是否启动成功
@app.get("/")
def root():
    return {"message": "AI Chat API is running"}

# 普通对话接口（非流式），发消息等全部回复回来
@app.post("/chat")
def chat(request: ChatRequest):
    try:
        # 先做上下文截断，防止超限
        truncated = truncate_context(
            [m.model_dump() for m in request.messages],
            request.model,
            request.max_tokens,
        )
        # 调大模型接口
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

# 流式对话接口，一句一句返回，实现打字机效果
@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    truncated = truncate_context(
        [m.model_dump() for m in request.messages],
        request.model,
        request.max_tokens,
    )

    # 生成器函数，逐块返回 SSE 格式数据
    def generate():
        try:
            stream = client.chat.completions.create(
                model=request.model,
                messages=truncated,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
            )
            # 遍历流式返回的每个 chunk
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'content': chunk.choices[0].delta.content})}\n\n"
            yield f"data: {json.dumps({'content': '[DONE]'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
