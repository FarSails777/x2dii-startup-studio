"""First-install and stock-restore scripts for the verified X2D II build.

Only transformation rules are shipped; no vendor init files are bundled.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

PRODUCT = "eagle2_hb722"
STOCK_CAMERA_SHA = "b237e080a60bda4765c1834592d410956931e7d453f33cfa55bc01c5f5d58f1d"
STOCK_INIT_SHA = "2b2e00a7ee342aa478d18bfac08db6ed849de7354f34ff0a93a104ff049699b7"
STOCK_GUI_SHA = "b1b643cb36176cd5a49129dd9bb2be480aa045a96ed1c35c30a779ab5af0801b"
MOD_CAMERA_SHA = "42252ab326d94e253c474a1289da7d17268cef172f1370e7c662c595141a72c3"
MOD_INIT_SHA = "a52a8ba773e4a7a13eedbf84bc526d7bdb0991cc1d922c174f97f799d77811f5"
CAMERA_RC = "/system/etc/init/camera-gui.rc"
INIT_RC = "/system/etc/init/init.services.rc"
STOCK_CAMERA_BACKUP = "/blackbox/x2dii_stock_camera-gui.rc"
STOCK_INIT_BACKUP = "/blackbox/x2dii_stock_init.services.rc"
MARKER = "/blackbox/x2dii_animation_bootstrap_v1"
BASELINE_LINK = "/blackbox/x2dii_animation_baseline"
LAUNCHER = "/blackbox/x2dii_launch_camera.sh"
LAUNCHER_TEXT = "#!/system/bin/sh\n/system/bin/sleep 3\n/system/bin/setprop ctl.start camera-gui\n"
LAUNCHER_SHA = hashlib.sha256(LAUNCHER_TEXT.encode("ascii")).hexdigest()

CAMERA_AWK = r'''
/^service camera-gui / { in_camera=1 }
in_camera && $0 == "    class core" && !inserted { print; print "    disabled"; inserted=1; next }
in_camera && /^$/ { in_camera=0 }
$0 == "on property:persist.hbl.touchtest=0" {
    print "on property:persist.hbl.touchtest=0 && property:init.svc.x2dii-boot-video=stopped"
    next
}
{ print }
END {
    print ""
    print "# Show the custom main-screen video during early boot."
    print "service x2dii-boot-video /system/bin/camera-gui -platform wayland-egl --imagetest --url \"/blackbox/" sprintf("%200s", "") ".mp4\" --fullscreen --timeout 3"
    print "    disabled"
    print "    oneshot"
    print "    setenv XDG_RUNTIME_DIR /tmp"
    print "    setenv XDG_CACHE_HOME /data"
    print "    setenv QT_QPA_FONTDIR /system/lib64/qt/lib/fonts"
    print "    user root"
    print "    group root"
    print ""
    print "on early-init-normal"
    print "    start x2dii-boot-video"
    print "    exec_background u:r:shell:s0 -- /system/bin/sh /blackbox/x2dii_launch_camera.sh"
    print ""
    print "on property:init.svc.x2dii-boot-video=stopped"
    print "    start camera-gui"
}
'''.strip()

INIT_AWK = r'''
!done && $0 == "    write /dev/kmsg \"<3>start camera-gui\"" {
    print "    # Camera GUI starts after x2dii-boot-video stops."
    done=1
    skip=1
    next
}
skip { skip=0; next }
{ print }
'''.strip()


def transformed(source: Path, program: str) -> bytes:
    """Used in offline verification; the camera executes the same awk program."""
    result = subprocess.run(["awk", program, str(source)], capture_output=True, check=True)
    return result.stdout


def _checked_digest(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("invalid SHA-256")
    return value


def _checked_video(target: str) -> str:
    if not re.fullmatch(r"/blackbox/x2dii_animation_[0-9a-f]{16}\.mp4", target):
        raise ValueError("invalid animation path")
    return target


def install_script(video_sha: str, video_target: str) -> str:
    video_sha = _checked_digest(video_sha)
    video_target = _checked_video(video_target)
    return f'''#!/system/bin/sh
set -eu
sha() {{ sha256sum "$1" | cut -c1-64; }}
CAM={CAMERA_RC}
INIT={INIT_RC}
VIDEO={video_target}
STAGE=/blackbox/x2dii_animation.stage
S=$(printf '%200s' '')
LINK="/blackbox/$S.mp4"
test "$(getprop ro.product.device)" = {PRODUCT}
test "$(sha "$CAM")" = {STOCK_CAMERA_SHA}
test "$(sha "$INIT")" = {STOCK_INIT_SHA}
test "$(sha /system/bin/camera-gui)" = {STOCK_GUI_SHA}
test "$(sha "$STAGE")" = {video_sha}
test ! -e {MARKER}
test ! -e "$LINK"
test ! -L "$LINK"
if test ! -e {STOCK_CAMERA_BACKUP}; then
    cp "$CAM" {STOCK_CAMERA_BACKUP}.next
    test "$(sha {STOCK_CAMERA_BACKUP}.next)" = {STOCK_CAMERA_SHA}
    mv {STOCK_CAMERA_BACKUP}.next {STOCK_CAMERA_BACKUP}
fi
if test ! -e {STOCK_INIT_BACKUP}; then
    cp "$INIT" {STOCK_INIT_BACKUP}.next
    test "$(sha {STOCK_INIT_BACKUP}.next)" = {STOCK_INIT_SHA}
    mv {STOCK_INIT_BACKUP}.next {STOCK_INIT_BACKUP}
fi
test "$(sha {STOCK_CAMERA_BACKUP})" = {STOCK_CAMERA_SHA}
test "$(sha {STOCK_INIT_BACKUP})" = {STOCK_INIT_SHA}
awk '{CAMERA_AWK}' "$CAM" > /blackbox/x2dii_camera-gui.rc.new
awk '{INIT_AWK}' "$INIT" > /blackbox/x2dii_init.services.rc.new
test "$(sha /blackbox/x2dii_camera-gui.rc.new)" = {MOD_CAMERA_SHA}
test "$(sha /blackbox/x2dii_init.services.rc.new)" = {MOD_INIT_SHA}
cat > {LAUNCHER}.next <<'X2DII_LAUNCHER'
{LAUNCHER_TEXT.rstrip()}
X2DII_LAUNCHER
test "$(sha {LAUNCHER}.next)" = {LAUNCHER_SHA}
chmod 755 {LAUNCHER}.next
mv {LAUNCHER}.next {LAUNCHER}
mv "$STAGE" "$VIDEO"
chmod 644 "$VIDEO"
test "$(sha "$VIDEO")" = {video_sha}
ln -s "$VIDEO" {BASELINE_LINK}
ln -s "$VIDEO" "$LINK"
printf '%s\\n' {STOCK_CAMERA_SHA} {STOCK_INIT_SHA} > {MARKER}
mount -o remount,rw /system
trap 'mount -o remount,ro /system' EXIT
cp /blackbox/x2dii_camera-gui.rc.new "$CAM.next"
cp /blackbox/x2dii_init.services.rc.new "$INIT.next"
chown 0:0 "$CAM.next" "$INIT.next"
chmod 644 "$CAM.next" "$INIT.next"
restorecon "$CAM.next" "$INIT.next"
test "$(sha "$CAM.next")" = {MOD_CAMERA_SHA}
test "$(sha "$INIT.next")" = {MOD_INIT_SHA}
mv "$CAM.next" "$CAM"
mv "$INIT.next" "$INIT"
sync
test "$(sha "$CAM")" = {MOD_CAMERA_SHA}
test "$(sha "$INIT")" = {MOD_INIT_SHA}
echo X2DII_BOOTSTRAP_INSTALLED
'''


def uninstall_script() -> str:
    return f'''#!/system/bin/sh
set -eu
sha() {{ sha256sum "$1" | cut -c1-64; }}
CAM={CAMERA_RC}
INIT={INIT_RC}
test "$(getprop ro.product.device)" = {PRODUCT}
test -f {MARKER}
test "$(sha {STOCK_CAMERA_BACKUP})" = {STOCK_CAMERA_SHA}
test "$(sha {STOCK_INIT_BACKUP})" = {STOCK_INIT_SHA}
case "$(sha "$CAM")" in {STOCK_CAMERA_SHA}|{MOD_CAMERA_SHA}) ;; *) exit 21;; esac
case "$(sha "$INIT")" in {STOCK_INIT_SHA}|{MOD_INIT_SHA}) ;; *) exit 22;; esac
mount -o remount,rw /system
trap 'mount -o remount,ro /system' EXIT
cp {STOCK_CAMERA_BACKUP} "$CAM.next"
cp {STOCK_INIT_BACKUP} "$INIT.next"
chown 0:0 "$CAM.next" "$INIT.next"
chmod 644 "$CAM.next" "$INIT.next"
restorecon "$CAM.next" "$INIT.next"
test "$(sha "$CAM.next")" = {STOCK_CAMERA_SHA}
test "$(sha "$INIT.next")" = {STOCK_INIT_SHA}
mv "$INIT.next" "$INIT"
mv "$CAM.next" "$CAM"
sync
test "$(sha "$CAM")" = {STOCK_CAMERA_SHA}
test "$(sha "$INIT")" = {STOCK_INIT_SHA}
S=$(printf '%200s' '')
rm -f "/blackbox/$S.mp4" {BASELINE_LINK}
rm -f {MARKER}
echo X2DII_STOCK_RESTORED
'''
