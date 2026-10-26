# AI provider check (2026-10-26 08:06 UTC)

- **groq** (openai/gpt-oss-120b): ✅ HTTP 200 in 0.4s — "OK | model=openai/gpt-oss-120b usage={'queue_time': 0.227494118, 'prompt_tokens': 78, 'prompt_time': 0.003666995, 'completion_tokens': 53, 'completion_time': 0.110612045, 'total_tokens': 131, 'total_time': 0.11427904, 'completion_tokens_details': {'reasoning_tokens': 43}}"
- **cloudflare** (@cf/openai/gpt-oss-120b): ✅ HTTP 200 in 0.4s — "OK | model=@cf/openai/gpt-oss-120b usage={'prompt_tokens': 74, 'completion_tokens': 29, 'total_tokens': 103, 'prompt_tokens_details': {'cached_tokens': 0}, 'neurons': 4.331804275512695}"

## Full-size test (newest real ai_largemid prompt, every endpoint that answered)
- **cloudflare**: HTTP 200 in 20s, prompt 7611 / answer 2853 tokens, neurons 436.689453125, finish stop — ✅ valid trading answer
- **cloudflare (candidate, chat)**: HTTP 200 in 17s, prompt 7611 / answer 2596 tokens, neurons 419.166748046875, finish stop — ✅ valid trading answer
