FROM 127.0.0.1:5000/watoom-llamampere@sha256:93e4b8bb081469a614817844c4890f27368723945f080d061149084d15ae5d64
ARG SOURCE_COMMIT=e9193f81423a613e19336834c0bb76dd94dd3191
LABEL org.opencontainers.image.source="https://github.com/JakeATX/llamAmpere" \
      org.opencontainers.image.revision=${SOURCE_COMMIT} \
      org.opencontainers.image.version="v0.6.2-watoom-async-disk.1" \
      org.opencontainers.image.licenses="MIT"
# Remove inherited backend libraries only inside the derived image, avoiding mixed ABIs.
RUN find /app/lib -maxdepth 1 -name '*.so*' -delete
COPY stage/bin/ /app/
COPY stage/lib/ /app/lib/
# New dynamic backend discovery searches beside the executable, not LD_LIBRARY_PATH.
# Keep the existing /app/lib staging layout and expose only backend symlinks there.
RUN for library in /app/lib/libggml*.so; do ln -sfn "$library" "/app/$(basename "$library")"; done
COPY LICENSE /usr/share/doc/llamampere/LICENSE
ENV LD_LIBRARY_PATH=/app/lib
WORKDIR /app
ENTRYPOINT ["/app/llama-server"]
