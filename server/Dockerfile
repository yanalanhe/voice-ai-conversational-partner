# Deploy target is 3.12 (see pyproject.toml's requires-python comment) --
# 3.10 is only the local dev-machine floor.
FROM python:3.12-slim

WORKDIR /build

# jieba (the [zh] extra) is a RUNTIME dependency, not a dev-only tool: it
# backs the zh_hsk vocabulary-ceiling check (app/pedagogy/ceiling.py), which
# runs in production whenever that pack is loaded, not just in tests.
COPY pyproject.toml ./
COPY server ./server

RUN pip install --no-cache-dir ".[zh]"

EXPOSE 8000

# --app-dir is required because the "app" package lives under server/app,
# not at the build context root (see pyproject.toml's packages.find "where").
CMD ["uvicorn", "app.main:app", "--app-dir", "server", "--host", "0.0.0.0", "--port", "8000"]
