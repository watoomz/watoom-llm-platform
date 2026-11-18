import { strict as assert } from "node:assert";
const root = process.env.EPIC_FAB_SOURCE;
if (!root) throw new Error("EPIC_FAB_SOURCE must identify the existing source checkout");
const {parseManifest} = await import(root + "/src/manifestParser.ts");
const expected = "9dda50a0c8bc12a5149b3983b019d8d9560c3e3a";
const blob = [...Buffer.from(expected, "hex")].map(x => x.toString().padStart(3,"0")).join("");
const original = globalThis.fetch;
globalThis.fetch = async () => new Response(JSON.stringify({ManifestFileVersion:"013000000000",FileManifestList:[{Filename:"fixture.uasset",FileHash:blob,FileChunkParts:[]}]}));
try {
 const value = await parseManifest("https://fixture.invalid/manifest");
 assert.equal(value.fileManifestList[0].fileHash, expected, "JSON SHA1 bytes must retain canonical order");
 console.log("PASS canonical JSON SHA1 parsing; no external network");
} finally { globalThis.fetch = original; }
