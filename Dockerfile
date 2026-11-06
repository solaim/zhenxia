FROM public.ecr.aws/docker/library/node:22-bookworm-slim AS node_runtime
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
RUN node --version && ffmpeg -version >/dev/null
COPY pyproject.toml ./
RUN python -c "import subprocess,tomllib; subprocess.check_call(['pip','install','--no-cache-dir',*tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']])" \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY README.md LICENSE ./
COPY zhenxia ./zhenxia
RUN pip install --no-cache-dir --no-deps .
COPY config.web.example.yml docker-entrypoint.sh ./
ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["--config", "/data/config.yml", "--host", "0.0.0.0", "--port", "8000"]
