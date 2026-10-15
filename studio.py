#!/usr/bin/env python3
"""Apply a verified static boot picture and optional post-logo animation."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import bootstrap
import installer
from x2dii_protocol import ProtocolError

ROOT = Path(__file__).resolve().parent
HEADER = b"width:1024 height:768 offset-x:0 offset-y:0 format:2;"
PAYLOAD_SIZE = 1024 * 768 * 3 // 2
ORIGINAL_LOGO_SHA = "03fe95b65e39db203061b8f9d367a6f184d8c71bd9f5c7dd67b27ce0b1105576"
PHASE_LOGO_SHA = "23b5b2c839c57012a2b64ce646e78c8297cfd484ab2816d2aababedf6a3cdd70"
LOGO = "/factory_data/logo.bin"
LOGO_BACKUP = "/blackbox/x2dii_factory_logo.original"
LOGO_STAGE = "/blackbox/x2dii_studio_logo.stage"
LOGO_MARKER = "/blackbox/x2dii_studio_logo.sha256"
PAUSED = "/blackbox/x2dii_studio_animation_paused"
MOD_CAMERA_BACKUP = "/blackbox/x2dii_studio_camera-gui.rc"
MOD_INIT_BACKUP = "/blackbox/x2dii_studio_init.services.rc"
LEGACY_CAMERA_BACKUP = "/blackbox/x2dii_camera-gui.rc.original"
LEGACY_INIT_BACKUP = "/blackbox/x2dii_init.services.rc.before-serial"


def has_file(path: str) -> bool:
    return "X2DII_YES" in installer.camera_read(
        f"test -f {path} && echo X2DII_YES || echo X2DII_NO", timeout=2)


def sha_if_present(path: str) -> str | None:
    return installer.remote_sha(path) if has_file(path) else None


def quick_sha(path: str) -> str:
    output = installer.camera_read(f"sha256sum {path}", timeout=3)
    match = re.search(r"\b[0-9a-f]{64}\b", output)
    if not match:
        raise RuntimeError(f"相机文件校验失败：{path}")
    return match.group(0)


def inspect() -> tuple[str, str]:
    installer.ensure_connection()
    if not re.search(r"\beagle2_hb722\b", installer.camera_read("getprop ro.product.device", timeout=2)):
        raise RuntimeError("仅支持已核对的 X2D II 100C。")
    if quick_sha("/system/bin/camera-gui") != bootstrap.STOCK_GUI_SHA:
        raise RuntimeError("相机拍照程序与已验证版本不同，已停止。")
    pair = (quick_sha(bootstrap.CAMERA_RC), quick_sha(bootstrap.INIT_RC))
    stock = (bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA)
    modified = (bootstrap.MOD_CAMERA_SHA, bootstrap.MOD_INIT_SHA)
    if pair == modified:
        animation = "on"
        if has_file(PAUSED):
            raise RuntimeError("动画暂停标记与启动配置不一致，请先检查相机。")
    elif pair == stock:
        animation = "paused" if has_file(PAUSED) else "stock"
    else:
        raise RuntimeError("启动配置与已验证的原厂或现有动画版本不一致，已停止。")
    logo = quick_sha(LOGO)
    if logo not in (ORIGINAL_LOGO_SHA, PHASE_LOGO_SHA):
        marker = installer.camera_read(f"cat {LOGO_MARKER} 2>/dev/null")
        if logo not in marker or sha_if_present(LOGO_BACKUP) != ORIGINAL_LOGO_SHA:
            raise RuntimeError("开机图片不是本软件管理的版本，已停止。")
    installer.log(f"相机已连接：开机图 {'原厂' if logo == ORIGINAL_LOGO_SHA else '飞思' if logo == PHASE_LOGO_SHA else '自定义'}；动画 {'开启' if animation == 'on' else '关闭'}。")
    return animation, logo


def prepare_custom_logo(source: Path, destination: Path) -> str:
    if source.suffix.lower() not in (".png", ".jpg", ".jpeg") or not source.is_file():
        raise RuntimeError("自定义开机图仅接受 PNG 或 JPEG。")
    if source.stat().st_size > 30 * 1024 * 1024:
        raise RuntimeError("图片不能超过 30 MB。")
    raw = destination.with_suffix(".nv12")
    graph = ("color=c=black:s=1024x768:r=1[bg];"
             "[0:v]scale=1024:768:force_original_aspect_ratio=decrease,format=rgba[fg];"
             "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=nv12[out]")
    result = subprocess.run(
        [installer.tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(source), "-filter_complex", graph, "-map", "[out]",
         "-frames:v", "1", "-f", "rawvideo", str(raw)],
        capture_output=True, text=True, timeout=45, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"图片转换失败：{result.stderr[-400:]}")
    payload = raw.read_bytes()
    if len(payload) != PAYLOAD_SIZE:
        raise RuntimeError("图片转换后尺寸异常，未写入相机。")
    destination.write_bytes(HEADER + payload)
    raw.unlink()
    return installer.sha256(destination)


def checked_logo(path: Path) -> str:
    data = path.read_bytes()
    if not data.startswith(HEADER) or len(data) != len(HEADER) + PAYLOAD_SIZE:
        raise RuntimeError("开机图格式不符。")
    return hashlib.sha256(data).hexdigest()


def run_script(text: str, expected: str, timeout: float = 40) -> None:
    with tempfile.TemporaryDirectory(prefix="x2dii-studio-script-") as directory:
        script = Path(directory) / "apply.sh"
        script.write_text(text, encoding="ascii")
        subprocess.run(["/bin/sh", "-n", str(script)], check=True)
        installer.run_camera_script(script, expected, timeout=timeout)


def logo_script(old: str, new: str, restore: bool) -> str:
    for digest in (old, new):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid logo digest")
    source = (f"cp {LOGO_BACKUP} {LOGO_STAGE}\n" if restore else "")
    marker = (f"rm -f {LOGO_MARKER}\n" if restore else
              f"printf '%s\\n' {new} > {LOGO_MARKER}.next\n"
              f"mv -f {LOGO_MARKER}.next {LOGO_MARKER}\n")
    return f'''#!/system/bin/sh
set -eu
sha() {{ sha256sum "$1" | cut -c1-64; }}
test "$(getprop ro.product.device)" = {bootstrap.PRODUCT}
test "$(sha {LOGO})" = {old}
if test ! -f {LOGO_BACKUP}; then
    test {old} = {ORIGINAL_LOGO_SHA}
    cp -p {LOGO} {LOGO_BACKUP}.next
    test "$(sha {LOGO_BACKUP}.next)" = {ORIGINAL_LOGO_SHA}
    mv -f {LOGO_BACKUP}.next {LOGO_BACKUP}
fi
test "$(sha {LOGO_BACKUP})" = {ORIGINAL_LOGO_SHA}
{source}test "$(sha {LOGO_STAGE})" = {new}
cp {LOGO_STAGE} {LOGO}.next
chown 0:0 {LOGO}.next
chmod 600 {LOGO}.next
restorecon {LOGO}.next
test "$(sha {LOGO}.next)" = {new}
mv -f {LOGO}.next {LOGO}
sync
if test "$(sha {LOGO})" != {new}; then
    cp {LOGO_BACKUP} {LOGO}.restore
    chmod 600 {LOGO}.restore
    chown 0:0 {LOGO}.restore
    restorecon {LOGO}.restore
    mv -f {LOGO}.restore {LOGO}
    sync
    exit 1
fi
{marker}echo X2DII_LOGO_APPLIED
'''


def apply_logo(mode: str, image: Path | None, old: str) -> None:
    if mode == "original":
        new = ORIGINAL_LOGO_SHA
        if old == new:
            installer.log("开机图已是原厂版本。")
            return
        if sha_if_present(LOGO_BACKUP) != ORIGINAL_LOGO_SHA:
            raise RuntimeError("缺少这台相机的原厂开机图备份，不能恢复。")
        run_script(logo_script(old, new, True), "X2DII_LOGO_APPLIED")
    else:
        with tempfile.TemporaryDirectory(prefix="x2dii-logo-") as directory:
            root = Path(directory)
            payload = root / "logo.bin"
            if mode == "phase":
                payload.write_bytes((ROOT / "assets/phaseone-logo.bin").read_bytes())
                if checked_logo(payload) != PHASE_LOGO_SHA:
                    raise RuntimeError("内置飞思开机图校验失败。")
                new = PHASE_LOGO_SHA
            else:
                if image is None:
                    raise RuntimeError("请先选择自定义图片。")
                new = prepare_custom_logo(image, payload)
            if old == new:
                installer.log("开机图已经是所选版本。")
                return
            with installer.file_server(root):
                installer.download_to_camera("logo.bin", LOGO_STAGE)
            if installer.remote_sha(LOGO_STAGE) != new:
                raise RuntimeError("开机图传输校验失败，未替换。")
            run_script(logo_script(old, new, False), "X2DII_LOGO_APPLIED")
    if installer.remote_sha(LOGO) != new:
        raise RuntimeError("开机图读回校验失败；请先不要重启。")
    installer.log("开机图已安装并读回校验。")


def stock_backups() -> tuple[str, str]:
    choices = (
        (bootstrap.STOCK_CAMERA_BACKUP, bootstrap.STOCK_INIT_BACKUP),
        (LEGACY_CAMERA_BACKUP, LEGACY_INIT_BACKUP),
    )
    for cam, init in choices:
        if (sha_if_present(cam), sha_if_present(init)) == (
                bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA):
            return cam, init
    raise RuntimeError("找不到这台相机经校验的原厂启动配置备份，不能关闭动画。")


def animation_script(enable: bool, sources: tuple[str, str] | None = None) -> str:
    old = ((bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA) if enable else
           (bootstrap.MOD_CAMERA_SHA, bootstrap.MOD_INIT_SHA))
    new = ((bootstrap.MOD_CAMERA_SHA, bootstrap.MOD_INIT_SHA) if enable else
           (bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA))
    if enable:
        first = f'''test -f {PAUSED}
test "$(sha {MOD_CAMERA_BACKUP})" = {new[0]}
test "$(sha {MOD_INIT_BACKUP})" = {new[1]}
S=$(printf '%200s' '')
test -f "/blackbox/$S.mp4"
'''
        src_cam, src_init = MOD_CAMERA_BACKUP, MOD_INIT_BACKUP
        final = f"rm -f {PAUSED}\n"
    else:
        assert sources is not None
        src_cam, src_init = sources
        first = f'''test "$(sha {src_cam})" = {new[0]}
test "$(sha {src_init})" = {new[1]}
cp {bootstrap.CAMERA_RC} {MOD_CAMERA_BACKUP}.next
cp {bootstrap.INIT_RC} {MOD_INIT_BACKUP}.next
test "$(sha {MOD_CAMERA_BACKUP}.next)" = {old[0]}
test "$(sha {MOD_INIT_BACKUP}.next)" = {old[1]}
mv -f {MOD_CAMERA_BACKUP}.next {MOD_CAMERA_BACKUP}
mv -f {MOD_INIT_BACKUP}.next {MOD_INIT_BACKUP}
'''
        final = f"touch {PAUSED}\n"
    return f'''#!/system/bin/sh
set -eu
sha() {{ sha256sum "$1" | cut -c1-64; }}
test "$(getprop ro.product.device)" = {bootstrap.PRODUCT}
test "$(sha {bootstrap.CAMERA_RC})" = {old[0]}
test "$(sha {bootstrap.INIT_RC})" = {old[1]}
{first}mount -o remount,rw /system
trap 'mount -o remount,ro /system' EXIT
cp {src_cam} {bootstrap.CAMERA_RC}.next
cp {src_init} {bootstrap.INIT_RC}.next
chown 0:0 {bootstrap.CAMERA_RC}.next {bootstrap.INIT_RC}.next
chmod 644 {bootstrap.CAMERA_RC}.next {bootstrap.INIT_RC}.next
restorecon {bootstrap.CAMERA_RC}.next {bootstrap.INIT_RC}.next
test "$(sha {bootstrap.CAMERA_RC}.next)" = {new[0]}
test "$(sha {bootstrap.INIT_RC}.next)" = {new[1]}
mv -f {bootstrap.INIT_RC}.next {bootstrap.INIT_RC}
mv -f {bootstrap.CAMERA_RC}.next {bootstrap.CAMERA_RC}
sync
test "$(sha {bootstrap.CAMERA_RC})" = {new[0]}
test "$(sha {bootstrap.INIT_RC})" = {new[1]}
{final}echo X2DII_ANIMATION_SWITCHED
'''


def switch_animation(enable: bool, sources: tuple[str, str] | None = None) -> None:
    expected = ((bootstrap.MOD_CAMERA_SHA, bootstrap.MOD_INIT_SHA) if enable else
                (bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA))
    original = ((bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA) if enable else
                (bootstrap.MOD_CAMERA_SHA, bootstrap.MOD_INIT_SHA))
    script = animation_script(enable, sources)
    for attempt in range(2):
        try:
            run_script(script, "X2DII_ANIMATION_SWITCHED", timeout=15)
        except (RuntimeError, ProtocolError):
            installer.log("相机未返回完成回执，正在读取实际状态…")
            time.sleep(3)
        for read_attempt in range(3):
            try:
                installer.ensure_connection()
                actual = (quick_sha(bootstrap.CAMERA_RC), quick_sha(bootstrap.INIT_RC))
                marker = has_file(PAUSED)
                break
            except (RuntimeError, ProtocolError):
                if read_attempt == 2:
                    raise RuntimeError("USB 诊断连接中断，无法确认写入结果；请重连后先按“检查相机”。")
                time.sleep(2)
        if actual == expected and marker == (not enable):
            installer.log("动画配置已读回校验。")
            return
        if actual == original and marker == enable and attempt == 0:
            installer.log("启动配置未变化，安全重试一次…")
            continue
        raise RuntimeError("动画配置未完整切换；请先按“检查相机”，不要重启。")


def apply_animation(current: str, enabled: bool, video: Path | None) -> None:
    if not enabled:
        if current == "on":
            switch_animation(False, stock_backups())
            installer.log("动画已关闭；下次开机将直接进入拍照界面。")
        else:
            installer.log("动画已经关闭。")
        return
    if current == "stock":
        if video is None:
            raise RuntimeError("首次开启动画需要选择视频。")
        installer.install(video)
        return
    if current == "paused":
        switch_animation(True)
        installer.log("动画已重新开启。")
    if video is not None:
        installer.install(video)
    elif current == "on":
        installer.log("保留相机当前动画。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    apply = sub.add_parser("apply")
    apply.add_argument("--logo", choices=("original", "phase", "custom"), required=True)
    apply.add_argument("--image", type=Path)
    apply.add_argument("--animation", choices=("on", "off"), required=True)
    apply.add_argument("--video", type=Path)
    args = parser.parse_args()
    try:
        current, logo = inspect()
        if args.command == "check":
            return 0
        if args.logo == "custom" and args.image is None:
            raise RuntimeError("请先选择自定义图片。")
        if args.animation == "on" and args.video is not None:
            installer.probe_video(args.video)
        if args.animation == "on" and current == "stock" and args.video is None:
            raise RuntimeError("首次开启动画需要选择视频。")
        apply_animation(current, args.animation == "on", args.video)
        apply_logo(args.logo, args.image, logo)
        installer.log("方案已应用。彻底关机再开机后查看效果。")
        return 0
    except (OSError, ProtocolError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
        installer.log(f"错误：{error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
