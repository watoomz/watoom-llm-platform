import copy, json, pathlib, tempfile, unittest, sys
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import creative_release as creative
from release_guard import UnsafeRelease

OLD = "127.0.0.1:5000/watoom-toolkit@sha256:" + "a" * 64
NEW = "127.0.0.1:5000/watoom-toolkit@sha256:" + "b" * 64


def baseline():
    return {
        "metadata": {"name": "watoom-toolkit"},
        "spec": {
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "toolkit",
                            "image": OLD,
                            "env": [{"name": "WATOOM_WORKER_IMAGE", "value": OLD}],
                            "volumeMounts": [{"name": "assets", "mountPath": "/assets", "readOnly": True}],
                        }
                    ],
                    "volumes": [{"name": "assets", "hostPath": {"path": "/data/ai/assets"}}],
                }
            },
        },
    }


class CreativeReleaseTests(unittest.TestCase):
    def test_only_image_and_worker_change(self):
        old = baseline()
        new = creative.desired_deployment(old, NEW)
        container = new["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], NEW)
        self.assertEqual(container["env"][0]["value"], NEW)
        container["image"] = OLD
        container["env"][0]["value"] = OLD
        self.assertEqual(new, old)

    def test_native_profile_requires_all_gates_and_updates_only_owned_engine_fields(self):
        accepted = {key: "PASS" for key in creative.NATIVE_GATES}
        accepted.update(
            native_engine_root="/data/ai/builds/unreal-recovery-20261016T213935Z/source", native_editor_sha256="e" * 64
        )
        profile = creative.native_profile(accepted)
        old = baseline()
        pod = old["spec"]["template"]["spec"]
        container = pod["containers"][0]
        container["volumeMounts"].append({"name": "unreal", "mountPath": "/unreal-engine", "readOnly": True})
        pod["volumes"].append(
            {"name": "unreal", "hostPath": {"path": "/data/ai/assets/unreal-engine", "type": "Directory"}}
        )
        new = creative.desired_deployment(old, NEW, native=profile)
        pod = new["spec"]["template"]["spec"]
        self.assertEqual(pod["volumes"][1]["hostPath"]["path"], profile["root"])
        env = {e["name"]: e["value"] for e in pod["containers"][0]["env"]}
        self.assertEqual(env["WATOOM_DUNGEON_ENABLED"], "1")
        self.assertEqual(env["WATOOM_UNREAL_EDITOR_SHA256"], "e" * 64)
        accepted["dungeon_rollback"] = "NOT TESTED"
        with self.assertRaises(UnsafeRelease):
            creative.native_profile(accepted)
        old["spec"]["template"]["spec"]["containers"][0]["volumeMounts"][1]["readOnly"] = False
        with self.assertRaises(UnsafeRelease):
            creative.desired_deployment(old, NEW, native=profile)

    def test_normal_versioned_runtime_requires_matching_hash_prefix(self):
        accepted = {key: "PASS" for key in creative.NATIVE_GATES}
        accepted.update(
            native_engine_root="/data/ai/toolchains/unreal/5.8.3/runtime-" + "e" * 12, native_editor_sha256="e" * 64
        )
        self.assertEqual(creative.native_profile(accepted)["root"], accepted["native_engine_root"])
        accepted["native_engine_root"] = "/data/ai/toolchains/unreal/5.8.3/runtime-" + "f" * 12
        with self.assertRaises(UnsafeRelease):
            creative.native_profile(accepted)

    def test_refuses_writable_library_mutable_image_or_worker_drift(self):
        for mutate in [
            lambda d: d["spec"]["template"]["spec"]["containers"][0]["volumeMounts"][0].update(readOnly=False),
            lambda d: d["spec"].update(replicas=2),
            lambda d: d["spec"]["template"]["spec"]["containers"][0]["env"][0].update(value=NEW),
        ]:
            old = baseline()
            mutate(old)
            with self.assertRaises(UnsafeRelease):
                creative.desired_deployment(old, NEW)
        with self.assertRaises(UnsafeRelease):
            creative.desired_deployment(baseline(), "latest")

    def test_existing_registration_preserved_and_bound(self):
        before = {
            "preserve": {"user": True},
            "watoom_specialists": {
                "entries": [
                    {
                        "backend": "toolkit-3d",
                        "artifactRoot": "/generated",
                        "url": "http://fixture.svc.cluster.local:8879",
                        "descriptor": {
                            "id": "local-toolkit",
                            "capabilities": ["3d.inspect"],
                            "resources": {"cpuCores": 1},
                            "model": {"model": "Blender"},
                            "sourceCommit": "a" * 40,
                        },
                    }
                ]
            },
        }
        after = creative.bind(before, NEW, "owned-uid", "b" * 40)
        self.assertEqual(after["preserve"], before["preserve"])
        self.assertEqual(len(after["watoom_specialists"]["entries"]), 1)
        descriptor = after["watoom_specialists"]["entries"][0]["descriptor"]
        self.assertEqual(descriptor["model"]["modelSha256"], "b" * 64)
        self.assertEqual(descriptor["model"]["deploymentUID"], "owned-uid")
        self.assertEqual(descriptor["capabilities"], ["3d.inspect"] + creative.CAPABILITIES)
        self.assertNotEqual(after, before)

    def test_native_world_has_bounded_fourteen_minute_backend_budget(self):
        before = {
            "watoom_specialists": {
                "entries": [
                    {
                        "backend": "toolkit-3d",
                        "artifactRoot": "/generated",
                        "url": "http://fixture.svc.cluster.local:8879",
                        "descriptor": {"id": "local-toolkit", "capabilities": [], "resources": {}, "model": {}},
                    }
                ]
            }
        }
        self.assertEqual(
            creative.bind(before, NEW, "uid", "b" * 40, dungeon=True)["watoom_specialists"]["entries"][0]["descriptor"][
                "timeoutMs"
            ],
            900000,
        )
        self.assertEqual(
            creative.bind(before, NEW, "uid", "b" * 40, dungeon=True)["watoom_specialists"]["entries"][0]["descriptor"][
                "resources"
            ],
            before["watoom_specialists"]["entries"][0]["descriptor"]["resources"],
        )
        self.assertEqual(before["watoom_specialists"]["entries"][0]["descriptor"]["resources"], {})
        self.assertEqual(
            creative.bind(before, NEW, "uid", "b" * 40)["watoom_specialists"]["entries"][0]["descriptor"]["timeoutMs"],
            210000,
        )

    def test_catalog_change_after_candidate_preparation_is_rejected(self):
        raw = b"owned-global-catalog"
        pin = __import__("hashlib").sha256(raw).hexdigest()
        creative.verify_catalog_snapshot({"catalog_base_sha256": pin}, raw)
        with self.assertRaises(UnsafeRelease):
            creative.verify_catalog_snapshot({"catalog_base_sha256": pin}, raw + b"changed")
        with self.assertRaises(UnsafeRelease):
            creative.verify_catalog_snapshot({}, raw)

    def test_partial_apply_restores_exact_images_and_all_six_agent_files(self):
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory)
            release = creative.Release.__new__(creative.Release)
            release.before = baseline()
            release.desired = creative.desired_deployment(release.before, NEW)
            release.old = OLD
            release.image = NEW
            release.changed = False
            release.out = out
            release.agents = []
            for i in range(6):
                path = out / ("agent" + str(i) + ".md")
                path.write_bytes(b"original")
                release.agents.append((path, b"original", b"updated"))
            state = copy.deepcopy(release.before)
            verified = []
            events = []

            class Fence:
                def acquire(self):
                    events.append("acquire")

                def ensure_closed(self):
                    events.append("close-for-rollback")

            release.fence = Fence()
            release.kub = lambda *args: state

            def cmd(args, **kwargs):
                if "apply" in args:
                    events.append("apply")
                    state.clear()
                    state.update(json.loads(kwargs["input"]))
                return b""

            release.cmd = cmd
            release.verify = verified.append
            count = 0

            def atomic(path, data):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError("injected partial agent write")
                path.write_bytes(data)

            with self.assertRaises(OSError):
                release.apply(atomic)
            release.rollback()
            self.assertEqual(state, release.before)
            self.assertEqual(verified, [NEW, OLD])
            self.assertEqual(events, ["acquire", "apply", "close-for-rollback", "apply"])
            self.assertTrue(all(path.read_bytes() == old for path, old, new in release.agents))

    def test_catalog_install_and_exact_rollback_for_new_and_existing_state(self):
        for previous in [None, b"old verified catalog"]:
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as directory:
                release = creative.Release.__new__(creative.Release)
                release.catalog_path = pathlib.Path(directory) / "asset-catalog/catalog.json"
                release.catalog_before = previous
                release.catalog_seed = b"new completed catalog"
                release.catalog_parent_before = previous is not None
                release.catalog_installed = False
                if previous is not None:
                    release.catalog_path.parent.mkdir()
                    release.catalog_path.write_bytes(previous)
                release.atomic = lambda path, data: path.write_bytes(data)
                with patch.object(creative.os, "chown"), patch.object(creative.os, "fchown"):
                    release.install_catalog()
                    self.assertEqual(release.catalog_path.read_bytes(), release.catalog_seed)
                    release.restore_catalog()
                if previous is None:
                    self.assertFalse(release.catalog_path.parent.exists())
                else:
                    self.assertEqual(release.catalog_path.read_bytes(), previous)

    def test_catalog_concurrent_change_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            release = creative.Release.__new__(creative.Release)
            release.catalog_path = pathlib.Path(directory) / "catalog.json"
            release.catalog_path.write_bytes(b"concurrent data")
            release.catalog_before = b"old"
            release.catalog_seed = b"new"
            release.catalog_installed = False
            with self.assertRaises(UnsafeRelease):
                release.install_catalog()
            self.assertEqual(release.catalog_path.read_bytes(), b"concurrent data")

    def test_application_to_toolkit_route_requires_authenticated_creative_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            release = creative.Release.__new__(creative.Release)
            release.out = pathlib.Path(directory)
            release.config = {
                "watoom_specialists": {
                    "entries": [
                        {
                            "url": "http://owned.svc.cluster.local:8879",
                            "tokenEnv": "OWNED_TOKEN_REFERENCE",
                            "descriptor": {"id": "local-toolkit"},
                        }
                    ]
                }
            }
            release.kub = lambda *args: {"items": [{"metadata": {"name": "owned-app"}, "status": {"phase": "Running"}}]}
            commands = []

            def cmd(args):
                commands.append(args)
                return json.dumps(creative.CAPABILITIES).encode()

            release.cmd = cmd
            release.verify_route()
            target = json.loads(commands[0][-1])
            self.assertEqual(
                target, {"url": "http://owned.svc.cluster.local:8879", "tokenEnv": "OWNED_TOKEN_REFERENCE"}
            )
            self.assertEqual(commands[0][4], "owned-app")
            release.cmd = lambda args: b"[]"
            with self.assertRaises(UnsafeRelease):
                release.verify_route()
            release.verify_route(False)


if __name__ == "__main__":
    unittest.main()
