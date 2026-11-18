/** Bounded native dungeon options for the existing world.compose operation. */
export const dungeonOutputs=["dungeon.umap","asset.glb","perspective.png","manifest.json","validation.json","dungeon-layout.json","dungeon-assembly.json","provenance.json"]
export function validateDungeon(value:unknown) {
 if (typeof value!=="object" || value===null || Array.isArray(value)) throw Error("Invalid dungeon options")
 const options=value as Record<string,unknown>
 const allowed=["style","rooms","levels","grid","room_size","cell_size","floor_height"]
 if(Object.keys(options).some(key=>!allowed.includes(key))) throw Error("Unknown dungeon option")
 if(!["dungeon-builder","dungeon-forge","mixed"].includes(String(options.style))) throw Error("Invalid dungeon style")
 const defaults:Record<string,number>={rooms:12,levels:1,grid:8,room_size:600,cell_size:800,floor_height:400}
 for(const key of Object.keys(defaults)) if(options[key]!==undefined) {
  if(typeof options[key]!=="number" || !Number.isInteger(options[key])) throw Error("Integer dungeon dimensions required")
  defaults[key]=Number(options[key])
 }
 const {rooms,levels,grid,room_size,cell_size,floor_height}=defaults
 if(levels<1 || levels>4 || rooms<2*levels || rooms>64 || grid<2 || grid>16 || Math.ceil(rooms/levels)>grid*grid) throw Error("Dungeon layout outside bounds")
 if(room_size<200 || room_size>=cell_size || cell_size>2000 || floor_height<300 || floor_height>1200) throw Error("Dungeon dimensions outside bounds")
 return options
}
