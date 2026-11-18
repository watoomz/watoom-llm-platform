# Native llama.cpp router candidate

Source for an alternative native router, not production. `llama-cpp-native-router-candidate` is at zero replicas on 5 October 2026. Production uses the Python `llm-router` ConfigMap and one selected managed backend. See [AI platform](../../../docs/09_LLM_AI_PLATFORM.md).

Candidate launch design: models directory `/data/ai/models/gguf`, INI presets `config/llm/router/models.ini`, `--models-max 1`, metrics, host `0.0.0.0`, port `8080`. One resident model does not implement a global chat queue.

Compatibility probes and reviewed normalizers are required before candidate activation. This refresh did not activate or qualify it.
