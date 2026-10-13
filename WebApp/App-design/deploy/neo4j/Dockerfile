ARG UPSTREAM_TAG=latest
FROM spg-registry.us-west-1.cr.aliyuncs.com/spg/openspg-neo4j:${UPSTREAM_TAG}
LABEL org.opencontainers.image.title="kag-legal-neo4j" \
      org.opencontainers.image.source="https://github.com/OpenSPG/openspg"
COPY restore-entrypoint.sh /restore-entrypoint.sh
RUN chmod +x /restore-entrypoint.sh
ENTRYPOINT ["/restore-entrypoint.sh"]
CMD ["neo4j"]
