import tempfile, unittest
from pathlib import Path
from sdxl_backend import pretrained_variant


class Variant(unittest.TestCase):
    def test_fp16_closure_uses_explicit_variant(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "text_encoder"
            p.mkdir()
            (p / "model.fp16.safetensors").touch()
            self.assertEqual(pretrained_variant(d), {"variant": "fp16"})

    def test_default_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "model.safetensors").touch()
            self.assertEqual(pretrained_variant(d), {})

    def test_mixed_precision_closure_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ["model.safetensors", "model.fp16.safetensors"]:
                (Path(d) / n).touch()
            with self.assertRaises(ValueError):
                pretrained_variant(d)


class Conditioning(unittest.TestCase):
    def test_negative_conditioning_reaches_diffusers_separately(self):
        import sys, types
        from unittest.mock import Mock, patch
        from sdxl_backend import Engine

        with tempfile.TemporaryDirectory() as d:
            engine = Engine(d)
            pipeline = Mock()
            engine.pipeline = pipeline
            image = Mock(width=512, height=512)
            image.save.side_effect = lambda p: Path(p).write_bytes(b"fixture")
            pipeline.return_value.images = [image]
            torch = types.SimpleNamespace(Generator=lambda device: types.SimpleNamespace(manual_seed=lambda seed: None))
            sched = Mock()
            diffusers = types.SimpleNamespace(EulerDiscreteScheduler=sched, DPMSolverMultistepScheduler=sched)
            with patch.dict(sys.modules, {"torch": torch, "diffusers": diffusers}):
                engine.generate(
                    {"prompt": "A wooden bench", "negative_prompt": "blur, watermark", "width": 512, "height": 512},
                    Path(d) / "fixture.png",
                )
            self.assertEqual(pipeline.call_args.kwargs["negative_prompt"], "blur, watermark")
            self.assertEqual(pipeline.call_args.kwargs["prompt"], "A wooden bench")
