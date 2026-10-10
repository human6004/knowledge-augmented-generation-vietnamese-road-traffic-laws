# Build only after separate capacity/cache approval; every RUN is offline.
ARG KAG_RUNTIME_IMAGE
FROM ${KAG_RUNTIME_IMAGE}
USER 0
WORKDIR /workspace
COPY requirements.txt requirements-http-api.txt .python-version ./
RUN --network=none --mount=type=bind,from=http_wheels,target=/wheels,ro \
    python -m pip install --no-index --no-deps --require-hashes --find-links=/wheels -r requirements-http-api.txt \
    && python -m pip check \
    && python -c "import platform,sys; assert sys.version_info[:3]==(3,10,16) and platform.system()=='Linux' and platform.machine()=='x86_64'" \
    && python -c "from importlib.metadata import version; from pathlib import Path; rows=[s.split('==') for s in Path('requirements.txt').read_text().splitlines() if s and not s.startswith('#')]; assert all(version(n)==v for n,v in rows)"
COPY --chown=10001:10001 kag/ ./kag/
COPY --chown=10001:10001 vendor/KAG/ ./vendor/KAG/
# Keep actual pinned objects/index for bootstrap without baking host Git config/remotes or credentials.
USER 10001:10001
RUN --network=none --mount=type=bind,from=vendor_objects,target=/vendor-objects,ro \
    git init -q vendor/KAG \
    && cp -R /vendor-objects/. vendor/KAG/.git/objects/ \
    && printf '%s\n' fdab15b3929d2ee40dfcdd388f90233096a6afc9 > vendor/KAG/.git/HEAD \
    && git -C vendor/KAG config core.autocrlf true \
    && git -C vendor/KAG config core.filemode false \
    && git -C vendor/KAG read-tree HEAD \
    && test -z "$(git -C vendor/KAG status --porcelain --untracked-files=all)"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KAG_DEBUG_DUMP_CONFIG=0 \
    MPLCONFIGDIR=/tmp/matplotlib HOME=/tmp \
    KAG_OPERATIONAL_PROOF=DENY KAG_PRODUCTION_WRITE=BLOCKED KAG_PROVIDER_EGRESS=DENY
EXPOSE 8000
ENTRYPOINT ["python", "-B", "-m", "kag.http_api.server"]
