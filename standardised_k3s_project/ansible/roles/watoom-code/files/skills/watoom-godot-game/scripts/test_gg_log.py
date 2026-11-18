import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_log
FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(n):
    return gg_log.classify(open(os.path.join(FX, n + ".log")).read())


class T(unittest.TestCase):
    def test_clean_boot_is_clean(self):
        r = fx("clean_boot")
        self.assertEqual(r["fatal"], [])
        self.assertEqual(r["warnings"], [])  # the root warning is allowlisted noise
        self.assertTrue(r["done"] and r["begun"])
        self.assertEqual(gg_log.exit_code(r, strict_warnings=True), 0)

    def test_real_engine_errors_are_fatal(self):
        for name, cls in (("shader_error", "shader_error"), ("script_error", "script_error"), ("engine_error", "engine_error"), ("missing_scene", "load_error")):
            r = fx(name)
            self.assertIn(cls, {f["cls"] for f in r["fatal"]}, name)
            self.assertEqual(gg_log.exit_code(r), 3, name)

    def test_continuation_lines_attach(self):
        r = fx("engine_error")
        f = [x for x in r["fatal"] if x["cls"] == "engine_error"][0]
        self.assertTrue(f["at"] and f["at"][0].startswith("at:"))

    def test_audio_noise_not_fatal(self):
        t = "ALSA lib pulse.c:242:(pulse_connect) [error.] PulseAudio: Unable to connect\nWARNING: All audio drivers failed, falling back to the dummy driver.\n     at: initialize (servers/audio/audio_server.cpp:258)\n"
        r = gg_log.classify(t)
        self.assertEqual((r["fatal"], r["warnings"]), ([], []))

    def test_unknown_error_is_fatal(self):
        self.assertEqual(gg_log.exit_code(gg_log.classify("ERROR: something new")), 3)

    def test_gpu_and_crash_are_exit_4(self):
        for t in ("ERROR: vkCreateDevice failed VK_ERROR_OUT_OF_DEVICE_MEMORY", "handle_crash: Program crashed with signal 11"):
            self.assertEqual(gg_log.exit_code(gg_log.classify(t)), 4)

    def test_strict_warnings(self):
        r = gg_log.classify("WARNING: something odd\n")
        self.assertEqual(gg_log.exit_code(r), 0)
        self.assertEqual(gg_log.exit_code(r, True), 3)

    def test_ansi_stripped(self):
        self.assertEqual(gg_log.exit_code(gg_log.classify("\x1b[31mERROR: x\x1b[0m")), 3)

    def test_noise_cannot_swallow_real_errors(self):
        for t in ("SCRIPT ERROR: Parse Error: bad PulseAudio token", "ERROR: Cannot open file 'audio_server.cpp'", "SHADER ERROR: x [ DONE ] first_scan_filesystem"):
            self.assertEqual(gg_log.exit_code(gg_log.classify(t)), 3, t)
        self.assertEqual(gg_log.exit_code(gg_log.classify("ERROR: Parameter \"singleton\" is null.")), 3)

    def test_empty_log_not_done(self):
        r = gg_log.classify("")
        self.assertFalse(r["done"])


if __name__ == "__main__":
    unittest.main()
