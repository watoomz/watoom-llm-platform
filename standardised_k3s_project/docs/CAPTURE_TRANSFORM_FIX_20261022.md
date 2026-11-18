# Capture transform correction

The runner assigned cam.position, then replaced the entire transform with Transform3D().looking_at(cam.position, view[2]). The identity transform has origin zero; looking_at arguments are target and up, not position and target. Thus position was discarded and target coordinates became the up vector, explaining why coordinate-only changes did not correctly frame the scene. Corrected to Transform3D(Basis.IDENTITY, view[1]).looking_at(view[2], Vector3.UP).

Source correction only; fresh approved-worker captures and independent visual/criteria acceptance remain REQUIRED. Prior PASS receipts describe their old hashes and do not prove camera correction or current framing. A changed image hash alone proves neither execution provenance nor success.
