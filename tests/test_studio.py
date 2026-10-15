"""Offline checks for the scheme editor's verified camera paths."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bootstrap  # noqa: E402
import studio  # noqa: E402
from x2dii_protocol import ProtocolError  # noqa: E402


class StudioTests(unittest.TestCase):
    def test_read_only_command_retries_transient_usb_timeout(self):
        with mock.patch.object(studio.installer, "camera",
                               side_effect=[ProtocolError("timed out"), "ready"]) as camera, \
             mock.patch.object(studio.installer, "bridge_interface_up", return_value=True), \
             mock.patch.object(studio.installer.time, "sleep"):
            self.assertEqual(studio.installer.camera_read("getprop ro.product.device"), "ready")
            self.assertEqual(camera.call_count, 2)

    def test_existing_modified_camera_and_phase_logo(self):
        digests = {
            "/system/bin/camera-gui": bootstrap.STOCK_GUI_SHA,
            bootstrap.CAMERA_RC: bootstrap.MOD_CAMERA_SHA,
            bootstrap.INIT_RC: bootstrap.MOD_INIT_SHA,
            studio.LOGO: studio.PHASE_LOGO_SHA,
        }
        with mock.patch.object(studio.installer, "ensure_connection"), \
             mock.patch.object(studio.installer, "camera", return_value="eagle2_hb722"), \
             mock.patch.object(studio, "quick_sha", side_effect=digests.__getitem__), \
             mock.patch.object(studio, "has_file", return_value=False):
            self.assertEqual(studio.inspect(), ("on", studio.PHASE_LOGO_SHA))

    def test_unrecognized_boot_config_is_rejected(self):
        digests = {
            "/system/bin/camera-gui": bootstrap.STOCK_GUI_SHA,
            bootstrap.CAMERA_RC: "0" * 64,
            bootstrap.INIT_RC: bootstrap.MOD_INIT_SHA,
        }
        with mock.patch.object(studio.installer, "ensure_connection"), \
             mock.patch.object(studio.installer, "camera", return_value="eagle2_hb722"), \
             mock.patch.object(studio, "quick_sha", side_effect=digests.__getitem__):
            with self.assertRaises(RuntimeError):
                studio.inspect()

    def test_switch_and_logo_scripts_have_valid_shell_syntax(self):
        for script in (
            studio.logo_script(studio.ORIGINAL_LOGO_SHA, studio.PHASE_LOGO_SHA, False),
            studio.logo_script(studio.PHASE_LOGO_SHA, studio.ORIGINAL_LOGO_SHA, True),
            studio.animation_script(False, (studio.LEGACY_CAMERA_BACKUP,
                                            studio.LEGACY_INIT_BACKUP)),
            studio.animation_script(True),
        ):
            subprocess.run(["sh", "-n"], input=script, text=True, check=True)

    def test_bundled_logo_matches_camera_format_and_digest(self):
        path = studio.ROOT / "assets/phaseone-logo.bin"
        self.assertEqual(studio.checked_logo(path), studio.PHASE_LOGO_SHA)
        with tempfile.TemporaryDirectory() as directory:
            converted = Path(directory) / "logo.bin"
            digest = studio.prepare_custom_logo(studio.ROOT / "assets/phaseone-preview.png",
                                                converted)
            self.assertEqual(digest, studio.PHASE_LOGO_SHA)

    def test_lost_switch_reply_uses_readback(self):
        expected = [bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA]
        with mock.patch.object(studio, "run_script", side_effect=RuntimeError("reply lost")), \
             mock.patch.object(studio.installer, "ensure_connection"), \
             mock.patch.object(studio.time, "sleep"), \
             mock.patch.object(studio, "quick_sha", side_effect=expected), \
             mock.patch.object(studio, "has_file", return_value=True):
            studio.switch_animation(False, (studio.LEGACY_CAMERA_BACKUP,
                                            studio.LEGACY_INIT_BACKUP))
        with mock.patch.object(studio, "run_script", side_effect=RuntimeError("reply lost")), \
             mock.patch.object(studio.installer, "ensure_connection"), \
             mock.patch.object(studio.time, "sleep"), \
             mock.patch.object(studio, "quick_sha", side_effect=expected), \
             mock.patch.object(studio, "has_file", return_value=False):
            with self.assertRaises(RuntimeError):
                studio.switch_animation(False, (studio.LEGACY_CAMERA_BACKUP,
                                                studio.LEGACY_INIT_BACKUP))

    def test_switch_retries_only_after_original_state_is_confirmed(self):
        digests = [bootstrap.MOD_CAMERA_SHA, bootstrap.MOD_INIT_SHA,
                   bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA]
        with mock.patch.object(studio, "run_script", side_effect=RuntimeError("reply lost")) as run, \
             mock.patch.object(studio.installer, "ensure_connection"), \
             mock.patch.object(studio.time, "sleep"), \
             mock.patch.object(studio, "quick_sha", side_effect=digests), \
             mock.patch.object(studio, "has_file", side_effect=[False, True]):
            studio.switch_animation(False, (studio.LEGACY_CAMERA_BACKUP,
                                            studio.LEGACY_INIT_BACKUP))
            self.assertEqual(run.call_count, 2)

    def test_logo_install_and_restore_with_local_factory_backup(self):
        original = studio.ROOT.parents[1] / "outputs/device-backup-2026-10-13/logo.bin"
        if not original.is_file():
            self.skipTest("private original logo fixture is not in source distribution")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory = root / "factory_data"
            blackbox = root / "blackbox"
            bins = root / "bin"
            factory.mkdir()
            blackbox.mkdir()
            bins.mkdir()
            (factory / "logo.bin").write_bytes(original.read_bytes())
            (blackbox / "x2dii_studio_logo.stage").write_bytes(
                (studio.ROOT / "assets/phaseone-logo.bin").read_bytes())
            for name, contents in (("getprop", "#!/bin/sh\necho eagle2_hb722\n"),
                                   ("chown", "#!/bin/sh\nexit 0\n"),
                                   ("restorecon", "#!/bin/sh\nexit 0\n"),
                                   ("sync", "#!/bin/sh\nexit 0\n")):
                executable = bins / name
                executable.write_text(contents)
                executable.chmod(0o755)
            env = {**os.environ, "PATH": f"{bins}:/sbin:/bin:/usr/bin"}
            for old, new, restore in (
                (studio.ORIGINAL_LOGO_SHA, studio.PHASE_LOGO_SHA, False),
                (studio.PHASE_LOGO_SHA, studio.ORIGINAL_LOGO_SHA, True),
            ):
                script = studio.logo_script(old, new, restore)
                script = script.replace("/factory_data/", str(factory) + "/")
                script = script.replace("/blackbox/", str(blackbox) + "/")
                subprocess.run(["sh"], input=script, text=True, check=True,
                               env=env, capture_output=True)
                self.assertEqual(studio.checked_logo(factory / "logo.bin"), new)
            self.assertFalse((blackbox / "x2dii_studio_logo.sha256").exists())


if __name__ == "__main__":
    unittest.main()
