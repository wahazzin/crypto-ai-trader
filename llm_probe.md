# AI provider check (2026-10-14 08:01 UTC)

- **groq** (openai/gpt-oss-120b): ✅ HTTP 200 in 0.4s — "OK | model=openai/gpt-oss-120b usage={'queue_time': 0.177704772, 'prompt_tokens': 78, 'prompt_time': 0.01636009, 'completion_tokens': 48, 'completion_time': 0.099234539, 'total_tokens': 126, 'total_time': 0.115594629, 'completion_tokens_details': {'reasoning_tokens': 38}}"
- **openrouter** (openai/gpt-oss-120b:free): ❌ HTTP 404 in 0.2s — '{"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: openai/gpt-oss-120b","code":404},"user_id":"user_3KfyeosVXBV4zZYAPXu0o0Zpcv6"}'
- **cloudflare (candidate, chat)** (@cf/openai/gpt-oss-120b): ✅ HTTP 200 in 2.6s — "OK | model=@cf/openai/gpt-oss-120b usage={'prompt_tokens': 74, 'completion_tokens': 36, 'total_tokens': 110, 'prompt_tokens_details': {'cached_tokens': 0}, 'neurons': 4.80907678604126}"

## Full-size test (newest real ai_largemid prompt, every endpoint that answered)
- **openrouter**: ❌ HTTP 404 — '{"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: openai/gpt-oss-120b","code":404},"user_id":"user_3KfyeosVXBV4zZYAPXu0o0Zpcv6"}'
- **cloudflare (candidate, chat)**: HTTP 200 in 30s, prompt 7397 / answer 1403 tokens, neurons 331.0168151855469, finish stop — ✅ valid trading answer
