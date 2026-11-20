import base64, contextlib, hashlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "watoom-code"))
from broker import Broker
from store import Store

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"fixture-image"


class Restoration(unittest.TestCase):
    def run_image(
        self, restores=True, ends=True, phase="qwen-ready", negative_prompt=None, generation_error=None, progress=None
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "controller"
            state.mkdir()
            (state / "selected-model.json").write_text(json.dumps({"deployment": "selected-chat"}))
            (state / "managed-models.json").write_text(
                json.dumps({"models": {"image-worker": {"url": "http://fixture"}}})
            )
            auth = root / "auth"
            auth.write_text("fixture")
            run = root / "transactions" / "12345678901234567-aaaaaaaaaaaaaaaa"
            run.mkdir(parents=True)
            store = Store(root / "catalog.sqlite")
            broker = Broker(
                {
                    "state": str(root / "broker"),
                    "controller_state": str(state),
                    "controller_socket": "fixture",
                    "images": {"backend_auth_file": str(auth)},
                    "image_output_root": str(root / "published"),
                },
                store,
            )
            self.calls = []
            self.fenced = False
            self.released = False

            def rpc(sock, req):
                self.calls.append(req)
                if req["action"] == "status":
                    return {"owner": None, "uncertain": False, "active_requests": 0, "phase": phase}
                if req["action"] == "begin-inference":
                    return {"lease": "fixture"}
                if req["action"] == "end-inference":
                    return {"released": ends}
                if req["action"] == "request-model":
                    return {"allowed": restores}
                raise AssertionError(req)

            @contextlib.contextmanager
            def hold(run, clearance):
                clearance()
                self.fenced = True
                try:
                    yield
                finally:
                    clearance()
                    self.fenced = False
                    self.released = True

            original = Path.read_text

            def read(path, *args, **kwargs):
                if str(path) == "/data/ai/helper-scripts/config/gpu-controller.json":
                    return json.dumps(
                        {
                            "primary": "swift",
                            "models": ["swift", "selected-chat"],
                            "mesh": "mesh",
                            "aliases": {"selected-chat": "selected-alias"},
                        }
                    )
                return original(path, *args, **kwargs)

            result = {
                "artifact": "image.png",
                "sha256": hashlib.sha256(PNG).hexdigest(),
                "width": 1,
                "height": 1,
                "model": "image-model",
            }
            try:
                with patch("broker.rpc", rpc), patch("broker.Path.read_text", read), patch(
                    "native_admission.hold", hold
                ), patch.object(broker, "hardware_admission"), patch(
                    "broker.urllib.request.urlopen",
                    side_effect=(
                        [generation_error]
                        if generation_error
                        else [io.BytesIO(json.dumps(result).encode()), io.BytesIO(PNG)]
                    ),
                ), patch(
                    "image_publish.publish", return_value={"path": "/generated/model-manager/fixture/image.png"}
                ) as publish:
                    self.publisher = publish
                    return broker.inference(
                        {"deployment": "image-worker", "kind": "diffusion-pipeline", "settings": {}},
                        {
                            "prompt": "A simple wooden park bench",
                            **({"negative_prompt": negative_prompt} if negative_prompt is not None else {}),
                        },
                        run,
                        progress,
                    )
            finally:
                store.close()

    def test_exact_previous_chat_restored_before_publication(self):
        result = self.run_image()
        self.assertEqual(result["restoration"]["deployment"], "selected-chat")
        self.assertEqual(
            next(x["deployment"] for x in reversed(self.calls) if x["action"] == "request-model"), "selected-chat"
        )
        self.assertTrue(self.released)
        self.publisher.assert_called_once()

    def test_stages_reported_in_transaction_order(self):
        stages = []
        self.run_image(progress=stages.append)
        self.assertEqual(stages, ["loading-model", "generating", "restoring-chat-model", "publishing"])

    def test_failed_render_still_reports_restoration_stage(self):
        stages = []
        with self.assertRaises(OSError):
            self.run_image(progress=stages.append, generation_error=OSError("render failed"))
        self.assertEqual(stages, ["loading-model", "generating", "restoring-chat-model"])

    def test_other_static_chat_ready_phase_restores_selected_model(self):
        result = self.run_image(phase="model-ready")
        self.assertEqual(result["restoration"]["deployment"], "selected-chat")

    def test_failed_restoration_retains_fence_and_does_not_publish(self):
        with self.assertRaisesRegex(ValueError, "restoration"):
            self.run_image(restores=False)
        self.assertTrue(self.fenced)
        self.assertFalse(self.released)
        self.publisher.assert_not_called()

    def test_unreleased_inference_retains_fence(self):
        with self.assertRaisesRegex(ValueError, "restoration failed"):
            self.run_image(ends=False)
        self.assertTrue(self.fenced)
        self.publisher.assert_not_called()

    def test_native_work_waits_before_controller_or_artifact_access(self):
        from admission_errors import AdmissionBusy

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "catalog.sqlite")
            broker = Broker({"state": str(Path(tmp) / "broker")}, store)
            try:
                with patch("broker.os.geteuid", return_value=0), patch(
                    "native_admission.check_native_idle", side_effect=AdmissionBusy("Native busy")
                ), patch("maintenance_guard.Maintenance"), patch("broker.rpc") as rpc, patch.object(
                    broker, "artifacts"
                ) as artifacts:
                    with self.assertRaises(AdmissionBusy):
                        broker._dispatch("generate", {"id": "a" * 64})
                    rpc.assert_not_called()
                    artifacts.assert_not_called()
            finally:
                store.close()

    def test_negative_prompt_recorded_with_verified_restoration(self):
        result = self.run_image(negative_prompt="blur, watermark")
        self.assertEqual(result["generation_settings"]["negative_prompt"], "blur, watermark")
        self.assertTrue(result["restoration"]["verified"])


class TimeoutRestoration(unittest.TestCase):
    run_image = Restoration.run_image

    def test_generation_timeout_restores_chat_and_releases_native_fence(self):
        with self.assertRaises(TimeoutError):
            self.run_image(generation_error=TimeoutError("generation deadline"))
        self.assertTrue(self.released)
        self.assertFalse(self.fenced)
        self.publisher.assert_not_called()
        self.assertEqual(self.calls[-1]["action"], "status")
        self.assertTrue(any(c["action"] == "end-inference" for c in self.calls))
        self.assertTrue(any(c["action"] == "request-model" and c["deployment"] == "selected-chat" for c in self.calls))

    def test_generation_timeout_with_failed_restore_keeps_fence(self):
        with self.assertRaisesRegex(ValueError, "restoration"):
            self.run_image(restores=False, generation_error=TimeoutError("generation deadline"))
        self.assertTrue(self.fenced)
        self.assertFalse(self.released)
        self.publisher.assert_not_called()
