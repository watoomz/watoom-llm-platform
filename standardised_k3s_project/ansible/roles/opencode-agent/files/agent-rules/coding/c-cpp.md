# C / C++ rules
- Detect/preserve the current build system and compiler configuration.
- Do not replace build systems or warning policies for preference; treat existing warnings/tests/sanitizers as meaningful.
- Run the smallest relevant build/test first and preserve memory/resource/error-handling conventions.
- Avoid dependency additions unless required.
