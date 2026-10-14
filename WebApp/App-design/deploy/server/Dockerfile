ARG UPSTREAM_TAG=latest
FROM spg-registry.us-west-1.cr.aliyuncs.com/spg/openspg-server:${UPSTREAM_TAG}
LABEL org.opencontainers.image.title="kag-legal-server" \
      org.opencontainers.image.source="https://github.com/OpenSPG/openspg"
COPY start.sh /start.sh
USER root
RUN chmod +x /start.sh
CMD ["/start.sh"]
