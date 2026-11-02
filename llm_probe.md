# AI provider check (2026-11-02 08:08 UTC)

- **groq** (openai/gpt-oss-120b): ✅ HTTP 200 in 0.3s — "OK | model=openai/gpt-oss-120b usage={'queue_time': 0.169773693, 'prompt_tokens': 78, 'prompt_time': 0.003007192, 'completion_tokens': 38, 'completion_time': 0.080131464, 'total_tokens': 116, 'total_time': 0.083138656, 'completion_tokens_details': {'reasoning_tokens': 28}}"
- **cloudflare** (@cf/openai/gpt-oss-120b): ✅ HTTP 200 in 0.9s — "OK | model=@cf/openai/gpt-oss-120b usage={'prompt_tokens': 74, 'completion_tokens': 50, 'total_tokens': 124, 'prompt_tokens_details': {'cached_tokens': 0}, 'neurons': 5.763621807098389}"

## Full-size test (newest real ai_largemid prompt, every endpoint that answered)
- **cloudflare**: HTTP 200 in 22s, prompt 7432 / answer 1771 tokens, neurons 357.2213134765625, finish stop — ✅ valid trading answer
- **cloudflare (candidate, chat)**: HTTP 200 in 21s, prompt 7432 / answer 1636 tokens, neurons 348.01678466796875, finish stop — ✅ valid trading answer
