# AI provider check (2026-10-14 07:56 UTC)

- **groq** (openai/gpt-oss-120b): ✅ HTTP 200 in 0.6s — "OK | model=openai/gpt-oss-120b usage={'queue_time': 0.264943808, 'prompt_tokens': 78, 'prompt_time': 0.002854448, 'completion_tokens': 45, 'completion_time': 0.093083766, 'total_tokens': 123, 'total_time': 0.095938214, 'completion_tokens_details': {'reasoning_tokens': 35}}"
- **openrouter** (openai/gpt-oss-120b:free): ❌ HTTP 404 in 0.1s — '{"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: openai/gpt-oss-120b","code":404},"user_id":"user_3KfyeosVXBV4zZYAPXu0o0Zpcv6"}'
- **cloudflare (candidate, chat)** (@cf/openai/gpt-oss-120b): ✅ HTTP 200 in 0.6s — "OK | model=@cf/openai/gpt-oss-120b usage={'prompt_tokens': 74, 'completion_tokens': 46, 'total_tokens': 120, 'prompt_tokens_details': {'cached_tokens': 0}, 'neurons': 5.490894794464111}"

## Full-size test (newest real ai_largemid prompt, every endpoint that answered)
- ❌ full-size test failed to run: KeyError: 'universe'
