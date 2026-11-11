# NEKO AI Online

Vietnamese AI chat app. The browser communicates only with this server. The OpenAI API key is stored only in Render Environment and is never sent to the browser.

## Deploy
1. Never place API keys, passwords, or .env files in GitHub.
2. Create a Render Blueprint from this repository and review the plan.
3. Set OPENAI_API_KEY and NEKO_ACCESS_PASSWORD in Render Environment. The password must be at least 16 characters and unique. NEKO_ACCESS_USER defaults to neko.
4. Default model: gpt-6.1-sol. Other allowed models: gpt-6.1-terra and gpt-6-luna. Availability depends on the OpenAI API account.
5. Render Free services are for testing and may sleep when idle. API usage can cost money; the account owner should configure spending limits and monitor usage before enabling chat.

All site and chat endpoints require browser HTTP Basic Authentication. /healthz is public for Render health checks. Chat is not stored in a server-side database.
