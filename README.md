# S6 LLM Gateway + MCP Agent

This folder contains a small multi-provider LLM gateway and an MCP-powered agent demo. The gateway gives you one local API for multiple LLM providers, and the agent uses that gateway to decide when to call tools.

## What This Can Do

- Route chat requests through multiple providers using one endpoint: `/v1/chat`.
- Try providers in your configured failover order, for example OpenAI first, then Gemini, then Groq.
- Support native tool calling through the gateway.
- Track provider usage, rate limits, latency, errors, cache tokens, and tool calls in SQLite.
- Serve a dashboard at `/` for provider status and recent calls.
- Serve a ChatGPT-style web UI at `/chat`.
- Run MCP tools from `mcp_server.py`, currently:
  - `add(a, b)`
  - `subtract(a, b)`
  - `get_temperature(city, units)` using OpenWeatherMap

## Important Files

- `llm_gatewayV2/main.py` - starts the FastAPI gateway and exposes all HTTP routes.
- `llm_gatewayV2/providers.py` - provider adapters for OpenAI, Gemini, Groq, NVIDIA, Cerebras, OpenRouter, GitHub Models, and Ollama.
- `llm_gatewayV2/router.py` - failover order, provider shortcuts, rate limits, cooldowns, and provider picking.
- `llm_gatewayV2/agent_web.py` - backend agent loop used by the browser chat UI.
- `llm_gatewayV2/static/chat.html` - ChatGPT-style browser UI.
- `llm_gatewayV2/static/dashboard.html` - provider dashboard.
- `llm_gatewayV2/client.py` - small Python client for calling the gateway.
- `mcp_server.py` - MCP tool server.
- `Agent.py` - terminal demo agent.
- `.env` - local API keys and settings. Do not commit this file.

## Environment Variables

Create or edit `s6/.env`.

Example:

```env
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4.1-mini

GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.1-flash-lite-preview

GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.3-70b-versatile

OPEN_ROUTER_API_KEY=your_openrouter_key
GITHUB_ACCESS_TOKEN=your_github_models_token
CEREBRAS_API_KEY=your_cerebras_key
NVIDIA_API_KEY=your_nvidia_key

WEATHER_API_KEY=your_openweathermap_key

LLM_ORDER=openai,gemini,groq,openrouter,github,cerebras,nvidia,ollama
GATEWAY_V2_PORT=8100
```

Only add keys for providers you want to use. Providers without keys are skipped.

## Install With uv

From the `s6` folder:

```bash
cd /Users/nawaz/Desktop/Vibe/s6
uv venv --python 3.11
uv pip install -r llm_gatewayV2/requirements.txt
```

You do not need to manually activate the virtual environment if you use `uv run`.

## How To Run

Run the gateway:

```bash
cd /Users/nawaz/Desktop/Vibe/s6
uv run python llm_gatewayV2/main.py
```

Then open:

```text
http://localhost:8100/chat
```

The dashboard is here:

```text
http://localhost:8100/
```

The provider list is here:

```text
http://localhost:8100/v1/providers
```

## Which Python Files To Execute

For normal use, execute only this:

```bash
uv run python llm_gatewayV2/main.py
```

That starts the gateway, dashboard, and chat UI.

You do not manually run `mcp_server.py`. The web agent starts it automatically when a chat request needs tools.

Optional terminal demo:

```bash
uv run python Agent.py
```

Use `Agent.py` only if you want the command-line demo. For the ChatGPT-style UI, use the `/chat` page.

## How Provider Failover Works

The gateway reads `LLM_ORDER` from `.env`.

Example:

```env
LLM_ORDER=openai,gemini,groq,openrouter,github,cerebras,nvidia,ollama
```

This means:

1. Try OpenAI first.
2. If OpenAI is unavailable, rate-limited, in backoff, or errors in an auto-failover request, try Gemini.
3. Continue down the list until a provider succeeds.

The browser agent pins a provider once a tool-using conversation starts. This avoids mixing provider-specific tool metadata, such as OpenAI tool calls with Gemini tool-call history.

## Chat UI Flow

When you use `http://localhost:8100/chat`:

1. Browser sends your message to `POST /agent/chat`.
2. `agent_web.py` starts an MCP session with `mcp_server.py`.
3. The agent sends each LLM turn through the gateway's `/v1/chat` logic.
4. If the LLM asks for a tool, the agent runs the MCP tool.
5. Tool results are sent back to the LLM through the gateway.
6. The final answer is shown in the browser.

## Example Questions

```text
What is (10 + 20) + (30 - 40)?
```

```text
What is the temperature in London?
```

The first question should use `add` and `subtract`. The second should use `get_temperature`.

## Notes

- Keep `.env` private. It is ignored by `.gitignore`.
- If you change Python code, restart the gateway.
- If `/chat` returns 404, you are probably running an old gateway process. Stop it with `Ctrl+C` and restart `llm_gatewayV2/main.py`.
