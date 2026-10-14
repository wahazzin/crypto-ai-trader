# AI provider check (2026-10-14 07:53 UTC)

- **groq** (openai/gpt-oss-120b): ✅ HTTP 200 in 0.3s — "OK | model=openai/gpt-oss-120b usage={'queue_time': 0.11410347, 'prompt_tokens': 78, 'prompt_time': 0.003000598, 'completion_tokens': 33, 'completion_time': 0.067876286, 'total_tokens': 111, 'total_time': 0.070876884, 'completion_tokens_details': {'reasoning_tokens': 23}}"
- **openrouter** (openai/gpt-oss-120b:free): ❌ HTTP 404 in 0.2s — '{"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: openai/gpt-oss-120b","code":404},"user_id":"user_3KfyeosVXBV4zZYAPXu0o0Zpcv6"}'
- **cloudflare (candidate, chat)** (@cf/openai/gpt-oss-120b): ✅ HTTP 200 in 1.2s — "OK | model=@cf/openai/gpt-oss-120b usage={'prompt_tokens': 74, 'completion_tokens': 50, 'total_tokens': 124, 'prompt_tokens_details': {'cached_tokens': 0}, 'neurons': 5.763621807098389}"
