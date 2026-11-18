import { NativeMemory } from "@opencode/core/watoom/native-memory"
import { OwnershipStatus } from "@opencode/core/watoom/ownership-status"
import { Effect } from "effect"
import { HttpApiBuilder } from "effect/http-api"
import { Api } from "../api"
import { response } from "../location"
export const MemoryHandler = HttpApiBuilder.group(Api, "server.memory", (handlers) =>
  handlers.handle("memory.status", () =>
    response(
      Effect.gen(function* () {
        const memory = yield* NativeMemory.Service
        const status = yield* memory.status
        const ownership = yield* Effect.promise(() => OwnershipStatus.read(process.env.WATOOM_GPU_OBSERVATION_FILE))
        return { memory: status, ownership }
      }),
    ),
  ),
)
