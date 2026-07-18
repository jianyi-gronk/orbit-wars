FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5

LABEL org.opencontainers.image.title="Orbit Wars Agent Sandbox" \
      org.opencontainers.image.description="Fixed stdlib-only phase-one agent runtime" \
      org.opencontainers.image.version="py311-stdlib-v1"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/orbit-sandbox \
    ORBIT_AGENT_ROOT=/strategy

WORKDIR /opt/orbit-sandbox
COPY orbit_agent_sandbox /opt/orbit-sandbox/orbit_agent_sandbox

USER 65532:65532
ENTRYPOINT ["python", "-m", "orbit_agent_sandbox.runner"]
