## Let the critic verify API fixes
When asking watoom-critic to diagnose an engine/library error or review an API-level fix, do not instruct it to "reason only" or forbid tools. Ask it to verify the API online (native websearch + webfetch of the official docs for the installed version) and to return the source URLs. Do not adopt an API fix the critic marked UNVERIFIED without a runtime check.
