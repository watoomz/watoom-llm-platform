FROM docker.io/nvidia/cuda@sha256:520292dbb4f755fd360766059e62956e9379485d9e073bbd2f6e3c20c270ed66 AS build
ARG SOURCE_COMMIT=e9193f81423a613e19336834c0bb76dd94dd3191
ARG BUILD_JOBS=4
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake git python3 libssl-dev libgomp1 ca-certificates
WORKDIR /src
COPY . /src
RUN cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=86 \
      -DGGML_CUDA=ON -DGGML_NATIVE=OFF -DGGML_BACKEND_DL=OFF -DGGML_CPU_ALL_VARIANTS=OFF \
      -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DGGML_BMI2=ON \
      -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF \
      -DLLAMA_BUILD_COMMIT=${SOURCE_COMMIT} -DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined && \
    cmake --build /build --config Release --parallel ${BUILD_JOBS} --target llama-server llama-perplexity
RUN mkdir -p /stage/bin /stage/lib && cp /build/bin/llama-server /build/bin/llama-perplexity /stage/bin/ && \
    find /build -name '*.so*' -exec cp -P {} /stage/lib/ \;
