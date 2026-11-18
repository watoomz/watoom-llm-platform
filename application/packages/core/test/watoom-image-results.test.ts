import { expect, test } from "bun:test"
import { createHash } from "node:crypto"
import { ImageResults } from "../src/watoom/image-results"
import { Mcp } from "../src/mcp/index"

function fixture(): Mcp.ToolResult {
  const png = Buffer.from("89504e470d0a1a0a0000000d494844520000000100000001", "hex")
  return {
    server: Mcp.ServerName.make("watoom-images"),
    tool: "image_result",
    isError: false,
    structured: {
      sha256: createHash("sha256").update(png).digest("hex"),
      width: 1,
      height: 1,
      restoration: { verified: true },
    },
    content: [{ type: "media", mimeType: "image/png", data: png.toString("base64") }],
  }
}
test("only an intact restored worker result is displayable", () => {
  expect(ImageResults.verified(fixture()).sha256).toHaveLength(64)
  expect(() => ImageResults.verified({ ...fixture(), isError: true })).toThrow()
  expect(() => ImageResults.verified({ ...fixture(), structured: { restoration: { verified: false } } })).toThrow()
  expect(() => ImageResults.verified({ ...fixture(), content: [] })).toThrow()
  expect(() =>
    ImageResults.verified({ ...fixture(), content: [{ type: "media", mimeType: "image/png", data: "invalid" }] }),
  ).toThrow()
  expect(() =>
    ImageResults.verified({
      ...fixture(),
      structured: { sha256: "0".repeat(64), width: 1, height: 1, restoration: { verified: true } },
    }),
  ).toThrow()
})
