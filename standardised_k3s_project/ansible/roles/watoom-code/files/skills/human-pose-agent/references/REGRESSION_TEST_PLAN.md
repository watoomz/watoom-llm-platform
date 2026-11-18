# Runtime acceptance tests — REQUIRED BEFORE PRODUCTION

Status: NOT TESTED (Blender unavailable in packaging environment).

Run with exact installed Blender binary, using disposable new `.blend` files:

1. Synthetic disconnected FK rig: must BLOCK before editing.
2. Synthetic three-bone arm with non-aligned edit-bone rest rolls and rotated armature object: solve reachable endpoint and compare evaluated world bone axes (both world rotation and endpoint); tolerance 0.03.
3. Two simultaneous limb chains with shared torso or pelvis: 5 sweeps must preserve both endpoints; if unable, FAIL and do not save.
4. Missing calibrated joint limits: MUST WARN; invalid limit MUST FAIL.
5. End-effector quaternion of [1,0,0,0]: final evaluated world orientation angular error below tolerance; unreachable MUST FAIL.
6. Character's forearm triangles crossing torso triangles within ONE mesh: self_mesh collision warning; adjacent triangles sharing vertices must NOT count.
7. Mesh penetrating ground plane: environment hit must FAIL; environment fully enclosing character remains NOT TESTED (known limitation).
8. Mesh evaluated under armature modifier plus transformed mesh object: collision coordinates must match evaluated world geometry.
9. Missing ground or foot contact data: MUST WARN or NOT TESTED; must never claim physical balance proven.
10. Failure case: no output blend; report includes failure reasons; original blend hash unchanged.
11. A Rigify/control-rig asset: BLOCK until tested with rig-specific adapter.
12. Export to FBX/glTF and import in chosen game engine: NOT TESTED until explicit engine pipeline integration.

Collision checking is a conservative warning detector, not proof of no clipping.
Do not treat center-of-mass projection as proof of believable motion.
