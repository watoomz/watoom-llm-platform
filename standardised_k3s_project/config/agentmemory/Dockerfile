FROM iiidev/iii@sha256:15f8d4ed16c0bec350b98f4e18ed04498b1fc5ccc50585e087b736717300cf26 AS iii-image
FROM node@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c
ARG AGENTMEMORY_VERSION=0.9.29
ARG III_SDK_VERSION=0.11.2
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl tini \
 && rm -rf /var/lib/apt/lists/*
COPY --from=iii-image /app/iii /usr/local/bin/iii
WORKDIR /opt/agentmemory
RUN printf '{"name":"watoom-agentmemory","version":"1.0.0","private":true,"overrides":{"iii-sdk":"%s"}}\n' "${III_SDK_VERSION}" > package.json \
 && npm install "@agentmemory/agentmemory@${AGENTMEMORY_VERSION}" --omit=optional --no-fund --no-audit \
 && ln -s /opt/agentmemory/node_modules/.bin/agentmemory /usr/local/bin/agentmemory
COPY iii-config.yaml /opt/agentmemory/node_modules/@agentmemory/agentmemory/dist/iii-config.yaml
RUN test "$(id -u node)" = "1000" \
 && test "$(id -g node)" = "1000" \
 && chown -R node:node /opt/agentmemory \
 && mkdir -p /data \
 && chown node:node /data
ENV AGENTMEMORY_III_VERSION=0.11.2 \
    AGENTMEMORY_DATA_DIR=/data \
    AGENTMEMORY_INJECT_CONTEXT=false \
    AGENTMEMORY_AUTO_COMPRESS=false \
    TOKEN_BUDGET=2000 \
    TINI_SUBREAPER=1
USER node:node
EXPOSE 3111
ENTRYPOINT ["/usr/bin/tini", "--", "agentmemory"]
