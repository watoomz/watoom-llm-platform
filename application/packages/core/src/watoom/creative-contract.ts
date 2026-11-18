import {validateDungeon,dungeonOutputs} from "./dungeon-contract"
/** Additive typed contracts for the existing native Toolkit specialist. */
export const operations: Record<string, string> = {
 "asset.index":"asset-index", "asset.search":"asset-search",
 "asset.inspect":"inspect", "asset.optimize":"optimize", "world.compose":"world",
 "character.prepare":"character", "material.derive":"material",
}
const bounds: Record<string, readonly [number,number]> = {size:[2,32],resolution:[4,48],height:[0,3],instances:[1,64],density:[0,1],lod_ratio:[.1,1],roughness:[0,1],metallic:[0,1],texture_resolution:[32,512]}
export function validate(input: Record<string,unknown>, capability: string) {
 const operation = operations[capability]
 if (!operation) throw Error("Unknown creative capability")
 const catalog = operation.startsWith("asset-")
 if (input.task !== (catalog ? operation : "3d-creative") || (!catalog && input.operation !== operation)) throw Error("Creative capability/task mismatch")
 const allowed = ["task","timeout", ...(operation === "asset-index" ? ["limit"] : operation === "asset-search" ? ["query","category","format","limit"] : ["operation","asset_id","asset_ids","seed","parameters","dungeon"])]
 if (Object.keys(input).some(key=>!allowed.includes(key))) throw Error("Unsupported creative input")
 if (input.timeout !== undefined && (!Number.isInteger(input.timeout) || Number(input.timeout)<1 || Number(input.timeout)>(operation==="world" && input.dungeon!==undefined ? 840 : 180))) throw Error("Invalid creative timeout")
 if (operation === "asset-index") {
  if (input.limit !== undefined && (!Number.isInteger(input.limit) || Number(input.limit)<1 || Number(input.limit)>1024)) throw Error("Invalid index batch")
  return
 }
 if (operation === "asset-search") {
  if (input.query !== undefined && (typeof input.query!=="string" || input.query.length>256)) throw Error("Invalid search query")
  if (input.limit !== undefined && (!Number.isInteger(input.limit) || Number(input.limit)<1 || Number(input.limit)>16)) throw Error("Invalid search limit")
  for (const field of ["category","format"]) if (input[field] !== undefined && (typeof input[field]!=="string" || String(input[field]).length>48)) throw Error("Invalid search filter")
  return
 }
 const ids = [input.asset_id,...(Array.isArray(input.asset_ids) ? input.asset_ids : [])]
 if (input.asset_ids !== undefined && !Array.isArray(input.asset_ids)) throw Error("Asset references must be an array")
 if (ids.length>4 || ids.some(id=>typeof id!=="string" || !/^ast_[a-f0-9]{24}$/.test(id))) throw Error("Select indexed library references")
 if (input.seed !== undefined && (!Number.isInteger(input.seed) || Number(input.seed)<0 || Number(input.seed)>2147483647)) throw Error("Invalid seed")
 if(input.dungeon!==undefined) {
  if(operation!=="world" || (input.parameters!==undefined && (typeof input.parameters!=="object" || input.parameters===null || Array.isArray(input.parameters) || Object.keys(input.parameters).length>0))) throw Error("Dungeon options apply only to native world mode")
  const options=validateDungeon(input.dungeon)
  if(ids.length!==(options.style==="mixed"?2:1) || new Set(ids).size!==ids.length) throw Error("Select one pack anchor or two compatible mixed anchors")
  return
 }
 const params = input.parameters ?? {}
 if (typeof params!=="object" || params===null || Array.isArray(params)) throw Error("Invalid parameters")
 for (const [name,value] of Object.entries(params)) {
  const range = bounds[name]
  if (!range || typeof value!=="number" || !Number.isFinite(value) || value<range[0] || value>range[1] || (["resolution","instances","texture_resolution"].includes(name) && !Number.isInteger(value))) throw Error("Creative parameter outside bounds")
 }
}
export function outputs(input: Record<string,unknown>) {
 if (input.task === "asset-index" || input.task === "asset-search") return ["result.json","manifest.json"]
 if(input.dungeon!==undefined) return dungeonOutputs
 return ["asset.blend","asset.glb","manifest.json","validation.json","front.png","back.png","left.png","right.png","top.png","perspective.png","creative.json","godot-validation.json","project.godot","scene.tscn","verify.gd",
 ...(input.operation === "world" ? ["world-layout.json"] : input.operation === "material" ? ["albedo.png","normal.png","roughness.png","metallic.png","orm.png"] : input.operation === "character" ? ["Idle-a.png","Idle-b.png","Walk-a.png","Walk-b.png","Run-a.png","Run-b.png"] : [])]
}
