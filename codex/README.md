# Codex Setup

1. Copy `config.toml.example`'s `[mcp_servers.credit-box-rag]` block into
   your Codex config, with the correct absolute path to this repo.
2. Copy `AGENTS.md.snippet`'s content into your project's `AGENTS.md`.
3. Run `pip install openpyxl pydantic pyyaml mcp` in this directory.
4. Start Codex. The first time you ask it a lending question, if it reports
   "Corpus DB not found," give it the path to your Master Credit Box Excel
   file — it will call `ingest_excel` to build `corpus.db` locally.
