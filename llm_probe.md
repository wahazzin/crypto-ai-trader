# AI provider check (2026-10-14 07:58 UTC)

- **groq** (openai/gpt-oss-120b): ✅ HTTP 200 in 0.4s — "OK | model=openai/gpt-oss-120b usage={'queue_time': 0.17103136, 'prompt_tokens': 78, 'prompt_time': 0.003221393, 'completion_tokens': 38, 'completion_time': 0.07989752, 'total_tokens': 116, 'total_time': 0.083118913, 'completion_tokens_details': {'reasoning_tokens': 28}}"
- **openrouter** (openai/gpt-oss-120b:free): ❌ HTTP 404 in 0.2s — '{"error":{"message":"This model is unavailable for free. The paid version is available now - use this slug instead: openai/gpt-oss-120b","code":404},"user_id":"user_3KfyeosVXBV4zZYAPXu0o0Zpcv6"}'
- **cloudflare (candidate, chat)** (@cf/openai/gpt-oss-120b): ✅ HTTP 200 in 0.7s — "OK | model=@cf/openai/gpt-oss-120b usage={'prompt_tokens': 74, 'completion_tokens': 28, 'total_tokens': 102, 'prompt_tokens_details': {'cached_tokens': 0}, 'neurons': 4.263622283935547}"

## Full-size test (newest real ai_largemid prompt, every endpoint that answered)
- ❌ full-size test failed to run: KeyError: 'universe'
