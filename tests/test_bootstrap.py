"""Offline checks. The full fixture test runs only when local camera backups exist."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path.insert(0, str(PROJECT))
import bootstrap  # noqa: E402
import installer  # noqa: E402
from x2dii_protocol import ProtocolError  # noqa: E402


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sandbox_script(script, root):
    """Redirect file writes into a temp root; preserve generated RC/launcher text."""
    lines = []
    inside_awk = False
    inside_launcher = False
    for line in script.splitlines(keepends=True):
        if line.startswith("awk '"):
            inside_awk = True
        if line.startswith("cat > ") and "<<'X2DII_LAUNCHER'" in line:
            inside_launcher = True
        if inside_awk:
            if line.startswith("}' \"$CAM\"") or line.startswith("{ print }' \"$INIT\""):
                inside_awk = False
                line = line.replace("/blackbox/", str(root / "blackbox") + "/")
        elif inside_launcher and line != "X2DII_LAUNCHER\n":
            if line.startswith("cat > "):
                line = line.replace("/blackbox/", str(root / "blackbox") + "/")
        else:
            line = line.replace("/blackbox/", str(root / "blackbox") + "/")
            line = line.replace("/system/", str(root / "system") + "/")
        if line == "X2DII_LAUNCHER\n":
            inside_launcher = False
        lines.append(line)
    return "".join(lines)


class BootstrapTests(unittest.TestCase):
    def test_existing_camera_is_still_recognized(self):
        digests = {
            bootstrap.CAMERA_RC: bootstrap.MOD_CAMERA_SHA,
            bootstrap.INIT_RC: bootstrap.MOD_INIT_SHA,
        }
        with mock.patch.object(installer, "ensure_connection"), \
             mock.patch.object(installer, "camera", return_value="eagle2_hb722"), \
             mock.patch.object(installer, "remote_sha", side_effect=digests.__getitem__), \
             mock.patch.object(installer, "baseline_target", return_value=installer.BASELINE), \
             mock.patch.object(installer, "current_target", return_value=installer.BASELINE):
            self.assertEqual(installer.inspect_camera(), ("ready", installer.BASELINE))

    def test_only_exact_stock_build_is_accepted(self):
        digests = {
            bootstrap.CAMERA_RC: bootstrap.STOCK_CAMERA_SHA,
            bootstrap.INIT_RC: bootstrap.STOCK_INIT_SHA,
            "/system/bin/camera-gui": bootstrap.STOCK_GUI_SHA,
        }
        with mock.patch.object(installer, "ensure_connection"), \
             mock.patch.object(installer, "camera", return_value="eagle2_hb722"), \
             mock.patch.object(installer, "remote_sha", side_effect=digests.__getitem__), \
             mock.patch.object(installer, "marker_present", return_value=False):
            self.assertEqual(installer.inspect_camera(), ("stock", None))
            digests[bootstrap.CAMERA_RC] = "0" * 64
            with self.assertRaises(RuntimeError):
                installer.inspect_camera()

    def test_disconnected_camera_reports_error_without_traceback(self):
        with mock.patch.object(sys, "argv", ["installer.py", "check"]), \
             mock.patch.object(installer, "ensure_connection",
                               side_effect=ProtocolError("camera disconnected")):
            self.assertEqual(installer.main(), 1)

    def test_generated_shell_syntax(self):
        for script in (bootstrap.install_script("a" * 64,
                        "/blackbox/x2dii_animation_" + "a" * 16 + ".mp4"),
                       bootstrap.uninstall_script()):
            subprocess.run(["sh", "-n"], input=script, text=True, check=True)

    def test_rejects_unchecked_video_path(self):
        with self.assertRaises(ValueError):
            bootstrap.install_script("a" * 64, "/system/etc/init/camera-gui.rc")

    def test_stock_to_modified_and_back_with_local_fixtures(self):
        camera_source = ROOT / "outputs/x2dii_boot_change/camera-gui.rc.original"
        init_source = ROOT / "work/etc_init_init.services.rc"
        gui_source = ROOT / "work/camera-gui"
        if not all(p.is_file() for p in (camera_source, init_source, gui_source)):
            self.skipTest("private device fixtures are not in this source distribution")
        self.assertEqual(digest(bootstrap.transformed(camera_source, bootstrap.CAMERA_AWK)),
                         bootstrap.MOD_CAMERA_SHA)
        self.assertEqual(digest(bootstrap.transformed(init_source, bootstrap.INIT_AWK)),
                         bootstrap.MOD_INIT_SHA)
        with tempfile.TemporaryDirectory(prefix="x2dii-bootstrap-test-") as directory:
            root = Path(directory)
            camera = root / "system/etc/init/camera-gui.rc"
            init = root / "system/etc/init/init.services.rc"
            gui = root / "system/bin/camera-gui"
            blackbox = root / "blackbox"
            bins = root / "bin"
            for path in (camera, init, gui):
                path.parent.mkdir(parents=True, exist_ok=True)
            blackbox.mkdir()
            bins.mkdir()
            camera.write_bytes(camera_source.read_bytes())
            init.write_bytes(init_source.read_bytes())
            gui.symlink_to(gui_source)
            for name in ("mount", "restorecon", "chown", "sync"):
                (bins / name).write_text("#!/bin/sh\nexit 0\n")
                (bins / name).chmod(0o755)
            (bins / "getprop").write_text("#!/bin/sh\necho eagle2_hb722\n")
            (bins / "getprop").chmod(0o755)
            video = b"test-video-payload"
            video_sha = digest(video)
            target = "/blackbox/x2dii_animation_" + video_sha[:16] + ".mp4"
            (blackbox / "x2dii_animation.stage").write_bytes(video)
            env = {**os.environ, "PATH": str(bins) + ":" + os.environ["PATH"]}
            for text in (bootstrap.install_script(video_sha, target),
                         bootstrap.uninstall_script()):
                script = root / "run.sh"
                script.write_text(sandbox_script(text, root))
                subprocess.run(["sh", str(script)], env=env, check=True,
                               capture_output=True, text=True)
                if "BOOTSTRAP_INSTALLED" in text:
                    self.assertEqual(digest(camera.read_bytes()), bootstrap.MOD_CAMERA_SHA)
                    self.assertEqual(digest(init.read_bytes()), bootstrap.MOD_INIT_SHA)
                    self.assertTrue((blackbox / (" " * 200 + ".mp4")).is_symlink())
            self.assertEqual(digest(camera.read_bytes()), bootstrap.STOCK_CAMERA_SHA)
            self.assertEqual(digest(init.read_bytes()), bootstrap.STOCK_INIT_SHA)
            self.assertFalse((blackbox / (" " * 200 + ".mp4")).exists())


if __name__ == "__main__":
    unittest.main()
