# Codex Setup

- Use `apps.web.app:app` as the only public ASGI entrypoint.
- Treat `production_data_processing/` outside this repo as the private data workspace.
- Treat `RUNTIME_ROOT/current` as the active runtime bundle pointer.
