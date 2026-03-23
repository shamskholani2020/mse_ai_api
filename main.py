import os
import uuid
import time
import json
import re
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import anthropic

API_SECRET_KEY = os.getenv("API_SECRET_KEY", "change-secret-key-2026")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = os.getenv("MODEL", "claude-sonnet-4-6")
OPENAI_MODEL_ALIAS = "gpt-4o-mini"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ====================================================================
# Format Converters  (OpenAI ↔ Anthropic)
# ====================================================================

def openai_tools_to_anthropic(tools):
    if not tools:
        return None
    result = []
    for tool in tools:
        func = tool.get("function", tool)
        result.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def parse_args(args):
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            return json.loads(args)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def openai_messages_to_anthropic(messages):
    """Return (system_str_or_None, [anthropic_message, ...])"""
    system_parts = []
    anthropic_msgs = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        msg_type = msg.get("type", "")

        # --- system ---
        if role == "system":
            if isinstance(content, list):
                for item in content:
                    system_parts.append(item.get("text", str(item)) if isinstance(item, dict) else str(item))
            else:
                system_parts.append(str(content) if content else "")
            continue

        # --- tool result (chat/completions style) ---
        if role == "tool":
            tool_use_id = msg.get("tool_call_id", "")
            text = _content_to_str(content)
            anthropic_msgs.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": text}],
            })
            continue

        # --- function_call_output (responses API style) ---
        if msg_type == "function_call_output":
            call_id = msg.get("call_id", "")
            output = msg.get("output", content)
            anthropic_msgs.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": call_id, "content": str(output) if output else ""}],
            })
            continue

        # --- function_call (responses API style, assistant side) ---
        if msg_type == "function_call":
            tool_id = msg.get("call_id", f"call_{uuid.uuid4().hex[:24]}")
            anthropic_msgs.append({
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": tool_id,
                    "name": msg.get("name", ""),
                    "input": parse_args(msg.get("arguments", "{}")),
                }],
            })
            continue

        # --- assistant ---
        if role == "assistant":
            parts = []
            if content:
                parts.append({"type": "text", "text": _content_to_str(content)})
            for tc in msg.get("tool_calls", []):
                func = tc.get("function", {})
                parts.append({
                    "type": "tool_use",
                    "id": tc.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                    "name": func.get("name", ""),
                    "input": parse_args(func.get("arguments", "{}")),
                })
            if parts:
                anthropic_msgs.append({"role": "assistant", "content": parts})
            continue

        # --- user ---
        if role == "user" or (msg_type == "message"):
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append({"type": "text", "text": item.get("text", "")})
                    else:
                        parts.append({"type": "text", "text": str(item)})
                anthropic_msgs.append({"role": "user", "content": parts})
            else:
                anthropic_msgs.append({"role": "user", "content": _content_to_str(content)})
            continue

    system = "\n\n".join(system_parts) if system_parts else None
    return system, anthropic_msgs


def _content_to_str(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", item.get("content", str(item))))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content) if content else ""


def call_claude(messages, tools=None, model=None, max_tokens=4096):
    """Core call — returns raw Anthropic response."""
    system, anthropic_msgs = openai_messages_to_anthropic(messages)
    anthropic_tools = openai_tools_to_anthropic(tools)

    kwargs = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "messages": anthropic_msgs,
    }
    if system:
        kwargs["system"] = system
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools

    return client.messages.create(**kwargs)


def estimate_tokens(text):
    return max(1, len(text.split()))


# ====================================================================
# FastAPI App
# ====================================================================
app = FastAPI(title="mse_ai_api for n8n")


def _check_auth(request: Request):
    auth = request.headers.get("authorization", "")
    key = auth.replace("Bearer ", "").strip()
    if key != API_SECRET_KEY:
        return False
    return True


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON payload"}})

    if not _check_auth(request):
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API Key"}})

    messages = data.get("messages", [])
    if not messages:
        return JSONResponse(status_code=400, content={"error": {"message": "messages field is required"}})

    try:
        tools = data.get("tools") or None
        start_time = time.time()
        response = call_claude(messages, tools=tools)

        p_tokens = response.usage.input_tokens
        c_tokens = response.usage.output_tokens

        # Check if response contains tool use
        tool_calls = []
        text_parts = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input, ensure_ascii=False),
                    },
                })
            elif block.type == "text":
                text_parts.append(block.text)

        if tool_calls:
            message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
            finish_reason = "tool_calls"
        else:
            message = {"role": "assistant", "content": "\n".join(text_parts)}
            finish_reason = "stop"

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
            "object": "chat.completion",
            "created": int(start_time),
            "model": OPENAI_MODEL_ALIAS,
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            "usage": {
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens,
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/v1/responses")
async def responses_endpoint(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON payload"}})

    if not _check_auth(request):
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API Key"}})

    input_data = data.get("input", "")
    if isinstance(input_data, str):
        messages = [{"role": "user", "content": input_data}]
    elif isinstance(input_data, list):
        messages = input_data
    else:
        messages = data.get("messages", [])

    if not messages:
        return JSONResponse(status_code=400, content={"error": {"message": "input field is required"}})

    try:
        tools = data.get("tools") or None
        instructions = data.get("instructions", "")
        if instructions:
            messages = [{"role": "system", "content": instructions}] + list(messages)

        start_time = time.time()
        response = call_claude(messages, tools=tools)

        p_tokens = response.usage.input_tokens
        c_tokens = response.usage.output_tokens

        output_items = []
        for block in response.content:
            if block.type == "tool_use":
                output_items.append({
                    "type": "function_call",
                    "id": block.id,
                    "call_id": block.id,
                    "name": block.name,
                    "arguments": json.dumps(block.input, ensure_ascii=False),
                    "status": "completed",
                })
            elif block.type == "text":
                output_items.append({
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": block.text}],
                })

        return {
            "id": f"resp-{uuid.uuid4().hex[:29]}",
            "object": "response",
            "created_at": int(start_time),
            "model": OPENAI_MODEL_ALIAS,
            "status": "completed",
            "output": output_items,
            "usage": {
                "input_tokens": p_tokens,
                "output_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens,
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": OPENAI_MODEL_ALIAS, "object": "model", "owned_by": "mse_ai_api"}],
    }


@app.get("/")
async def health_check():
    return {"status": "running", "message": "mse_ai_api Server is active!"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7777)
