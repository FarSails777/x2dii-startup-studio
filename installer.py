#!/usr/bin/env python3
"""Install a post-logo animation on the verified X2D II build."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from x2dii_protocol import (CMD_HBLSHELL, CMD_PRODCONFIG, ProtocolError,
                            exchange, probe_frame, shell_frame)
import bootstrap

HOST = "192.168.42.2"
MAC_IP = "192.168.42.1"
PRODUCT = bootstrap.PRODUCT
RC_SHA = bootstrap.MOD_CAMERA_SHA
BASELINE_SHA = "0402199eda6b3e39e96b51ac71c49b1c740778db6769a620b0074b5c615e89d5"
BASELINE = "/system/usr/share/video/x2dii_boot.mp4"
PREVIOUS = "/blackbox/x2dii_animation_previous"
STAGE = "/blackbox/x2dii_animation.stage"
SCRIPT = "/blackbox/x2dii_animation_apply.sh"
LINK = "/blackbox/" + " " * 200 + ".mp4"
ANIMATION_PREFIX = "/blackbox/x2dii_animation_"


def log(message: str) -> None:
    print(message, flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tool(name: str) -> str:
    result = shutil.which(name)
    if not result:
        raise RuntimeError(f"缺少 {name}。请先在这台 Mac 安装 FFmpeg。")
    return result


def probe_video(source: Path) -> float:
    if not source.is_file():
        raise RuntimeError("找不到所选视频。")
    result = subprocess.run(
        [tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(source)],
        capture_output=True, text=True, timeout=20, check=True,
    )
    info = json.loads(result.stdout)
    if not info.get("streams"):
        raise RuntimeError("所选文件没有视频画面。")
    duration = float(info["format"]["duration"])
    if not 0.2 <= duration <= 2.4:
        raise RuntimeError(f"视频时长 {duration:.2f} 秒；当前启动窗口只支持 0.2–2.4 秒。")
    return duration


def prepare_video(source: Path, destination: Path) -> str:
    duration = probe_video(source)
    log(f"转换视频：{duration:.2f} 秒 → 1024×768、25 fps、H.264；结尾定格到 3.52 秒。")
    filter_graph = (
        "scale=1024:768:force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=1024:768:(ow-iw)/2:(oh-ih)/2:black,"
        "fps=25,format=yuv420p,tpad=stop_mode=clone:stop_duration=4"
    )
    result = subprocess.run(
        [tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
         "-map", "0:v:0", "-an", "-vf", filter_graph, "-t", "3.52",
         "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high",
         "-level:v", "4.0", "-crf", "22", "-maxrate", "3000k", "-bufsize", "3000k",
         "-movflags", "+faststart", str(destination)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"视频转换失败：{result.stderr[-600:]}")
    if not destination.is_file() or destination.stat().st_size > 12 * 1024 * 1024:
        raise RuntimeError("转换后文件超过 12 MB，未安装。")
    info = subprocess.run(
        [tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height,pix_fmt,avg_frame_rate:format=duration",
         "-of", "json", str(destination)], capture_output=True, text=True, timeout=20, check=True,
    )
    output = json.loads(info.stdout)
    stream = output["streams"][0]
    if (stream["codec_name"], stream["width"], stream["height"], stream["pix_fmt"],
            stream["avg_frame_rate"]) != ("h264", 1024, 768, "yuv420p", "25/1"):
        raise RuntimeError("转换结果的格式校验失败，未安装。")
    if not 3.48 <= float(output["format"]["duration"]) <= 3.56:
        raise RuntimeError("转换结果的时长校验失败，未安装。")
    return sha256(destination)


def can_connect() -> bool:
    if not bridge_interface_up():
        return False
    try:
        replies = exchange(HOST, probe_frame(), CMD_PRODCONFIG, 2)
        return any(reply.function == 2 and reply.field == 13 for reply in replies)
    except (OSError, ProtocolError):
        return False


def bridge_interface_up() -> bool:
    result = subprocess.run(["/sbin/ifconfig", "-a"], capture_output=True, text=True,
                            timeout=5, check=False)
    return "192.168.42.1 --> 192.168.42.2" in result.stdout


def bridge_binary() -> Path:
    return Path(__file__).resolve().parent / "rndis-up"


def ensure_connection() -> None:
    if can_connect():
        return
    if bridge_interface_up():
        for _ in range(2):
            time.sleep(1)
            if can_connect():
                return
        raise RuntimeError("Mac 已建立 USB 网络，但相机诊断通道没有有效回应。请重新插 USB 后再检查。")
    binary = bridge_binary()
    if not binary.is_file():
        raise RuntimeError("安装包内缺少 Mac USB 桥接程序。")
    log("正在请求 macOS 管理员授权，以建立相机 USB 诊断连接…")
    command = (
        f"{shlex.quote(str(binary))} --vid 2756 --pid 000b "
        f"--host-ip {MAC_IP} --peer-ip {HOST} --host-mac 02:00:00:00:00:01 "
        ">/dev/null 2>&1"
    )
    apple = 'do shell script "' + command.replace("\\", "\\\\").replace('"', '\\"') + '" with administrator privileges'
    process = subprocess.Popen(["/usr/bin/osascript", "-e", apple],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(25):
        if can_connect():
            return
        if process.poll() is not None:
            raise RuntimeError("Mac USB 桥接未获授权或相机已断开。")
        time.sleep(1)
    process.terminate()
    raise RuntimeError("未找到相机。请保持开机、接 USB，并在相机选择“大容量存储”。")


def camera(command: str, timeout: float = 5) -> str:
    replies = exchange(HOST, shell_frame(command), CMD_HBLSHELL, timeout)
    result = "\n".join(reply.text for reply in replies)
    if not result:
        raise RuntimeError(f"相机命令无有效应答：{command[:80]}")
    return result


def camera_read(command: str, timeout: float = 5) -> str:
    """Retry only read-only shell commands after a transient USB timeout."""
    error = None
    for attempt in range(3):
        try:
            return camera(command, timeout=timeout)
        except (RuntimeError, ProtocolError) as exc:
            error = exc
            if attempt == 2:
                break
            time.sleep(1)
            if not bridge_interface_up():
                ensure_connection()
    raise error


def remote_sha(path: str) -> str:
    output = camera_read(f"sha256sum {shlex.quote(path)}")
    match = re.search(r"\b[0-9a-f]{64}\b", output)
    if not match:
        raise RuntimeError(f"相机文件校验失败：{path}")
    return match.group(0)


def current_target() -> str:
    output = camera_read("S=$(printf '%200s' ''); readlink /blackbox/\"$S\".mp4")
    targets = re.findall(r"/(?:system|blackbox)/[^\s]+", output)
    if not targets:
        raise RuntimeError("未找到现有动画入口；相机启动配置可能已经变化。")
    return targets[-1]


def valid_target(target: str) -> bool:
    return target == BASELINE or bool(re.fullmatch(r"/blackbox/x2dii_animation_[0-9a-f]{16}\.mp4", target))


def marker_present() -> bool:
    return "X2DII_BETA_PRESENT" in camera_read(
        f"test -f {bootstrap.MARKER} && echo X2DII_BETA_PRESENT || echo X2DII_BETA_ABSENT")


def baseline_target() -> str:
    if marker_present():
        output = camera(f"readlink {bootstrap.BASELINE_LINK}")
        paths = re.findall(r"/blackbox/x2dii_animation_[0-9a-f]{{16}}\.mp4", output)
        if not paths or remote_sha(paths[-1])[:16] != paths[-1].split("_")[-1][:16]:
            raise RuntimeError("首次安装基准动画校验失败；安装已停止。")
        return paths[-1]
    if remote_sha(BASELINE) != BASELINE_SHA:
        raise RuntimeError("基准动画校验失败；安装已停止。")
    return BASELINE


def inspect_camera() -> tuple[str, str | None]:
    ensure_connection()
    if not re.search(r"\beagle2_hb722\b", camera("getprop ro.product.device")):
        raise RuntimeError("相机型号不匹配；只支持已验证的 X2D II 100C。")
    camera_sha = remote_sha(bootstrap.CAMERA_RC)
    init_sha = remote_sha(bootstrap.INIT_RC)
    if (camera_sha, init_sha) == (bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA):
        if marker_present():
            raise RuntimeError("发现首次安装记录，但启动配置已恢复原厂；请先检查恢复状态。")
        if remote_sha("/system/bin/camera-gui") != bootstrap.STOCK_GUI_SHA:
            raise RuntimeError("原厂拍照程序与已验证版本不同；首次安装已停止。")
        log("已确认 X2D II 原厂启动配置；可执行首次安装。")
        return "stock", None
    if (camera_sha, init_sha) != (RC_SHA, bootstrap.MOD_INIT_SHA):
        raise RuntimeError("启动配置不是已验证的原厂或改装版本；安装已停止。")
    baseline_target()
    target = current_target()
    if not valid_target(target):
        raise RuntimeError(f"当前动画入口指向未知文件：{target}。安装已停止。")
    log("已确认 X2D II 和已验证的启动配置。")
    log(f"当前动画：{'基准动画' if target == BASELINE else '自定义动画'}")
    return "ready", target


def check_camera() -> str:
    mode, target = inspect_camera()
    if mode != "ready" or target is None:
        raise RuntimeError("这台相机尚未安装动画入口；请先选择视频并执行首次安装。")
    return target


@contextmanager
def file_server(directory: Path):
    # This directory contains only this operation's video and fixed apply script.
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8766", "--bind", MAC_IP,
         "--directory", str(directory)], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.4)
        if process.poll() is not None:
            raise RuntimeError("Mac 本地传输端口 8766 启动失败。")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


def download_to_camera(route: str, destination: str) -> None:
    url = f"http://{MAC_IP}:8766/{route}"
    result = camera(f"/sbin/busybox wget -q -O {destination} {url} && echo X2DII_TRANSFER",
                    timeout=30)
    if "X2DII_TRANSFER" not in result:
        raise RuntimeError("相机下载文件失败；当前动画未更改。")


def apply_script(expected_sha: str, target: str, old: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("invalid digest")
    if not valid_target(target) or not valid_target(old):
        raise ValueError("invalid camera target")
    # All values are fixed paths or checked hex. The long-space filename stays inside this script.
    return f"""#!/system/bin/sh
set -eu
S=$(printf '%200s' '')
LINK="/blackbox/$S.mp4"
OLD={old}
NEW={target}
test "$(getprop ro.product.device)" = {PRODUCT}
test "$(sha256sum /system/etc/init/camera-gui.rc | cut -c1-64)" = {RC_SHA}
test "$(readlink "$LINK")" = "$OLD"
test "$(sha256sum {STAGE} | cut -c1-64)" = {expected_sha}
mv {STAGE} "$NEW"
chmod 644 "$NEW"
test "$(sha256sum "$NEW" | cut -c1-64)" = {expected_sha}
rm -f {PREVIOUS}.next "$LINK.next"
ln -s "$OLD" {PREVIOUS}.next
mv -f {PREVIOUS}.next {PREVIOUS}
ln -s "$NEW" "$LINK.next"
mv -f "$LINK.next" "$LINK"
sync
test "$(readlink "$LINK")" = "$NEW"
echo X2DII_INSTALLED
"""


def restore_script(target: str, old: str) -> str:
    if not valid_target(target) or not valid_target(old):
        raise ValueError("invalid camera target")
    expected = BASELINE_SHA if target == BASELINE else None
    check = (f'test "$(sha256sum "$NEW" | cut -c1-64)" = {expected}' if expected
             else 'test -s "$NEW"')
    return f"""#!/system/bin/sh
set -eu
S=$(printf '%200s' '')
LINK="/blackbox/$S.mp4"
OLD={old}
NEW={target}
test "$(getprop ro.product.device)" = {PRODUCT}
test "$(sha256sum /system/etc/init/camera-gui.rc | cut -c1-64)" = {RC_SHA}
test "$(readlink "$LINK")" = "$OLD"
{check}
rm -f {PREVIOUS}.next "$LINK.next"
ln -s "$OLD" {PREVIOUS}.next
mv -f {PREVIOUS}.next {PREVIOUS}
ln -s "$NEW" "$LINK.next"
mv -f "$LINK.next" "$LINK"
sync
test "$(readlink "$LINK")" = "$NEW"
echo X2DII_RESTORED
"""


def run_camera_script(path: Path, expected: str, timeout: float = 15) -> None:
    with file_server(path.parent):
        download_to_camera("apply.sh", SCRIPT)
        if remote_sha(SCRIPT) != sha256(path):
            raise RuntimeError("相机脚本传输校验失败，未改动动画入口。")
        result = camera(f"sh {SCRIPT}", timeout=timeout)
        if expected not in result:
            raise RuntimeError("相机没有确认切换完成，请检查状态；不要直接重启。")


def install(source: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="x2dii-animation-") as directory:
        root = Path(directory)
        payload = root / "video.mp4"
        digest = prepare_video(source, payload)
        mode, old = inspect_camera()
        new = f"{ANIMATION_PREFIX}{digest[:16]}.mp4"
        if mode == "stock":
            with file_server(root):
                log("首次安装：正在传输并校验动画…")
                download_to_camera("video.mp4", STAGE)
                if remote_sha(STAGE) != digest:
                    raise RuntimeError("相机视频传输校验失败；未修改启动配置。")
            script = root / "apply.sh"
            script.write_text(bootstrap.install_script(digest, new), encoding="ascii")
            log("正在备份原厂文件并安装启动播放入口…")
            run_camera_script(script, "X2DII_BOOTSTRAP_INSTALLED", timeout=60)
            if (remote_sha(bootstrap.CAMERA_RC), remote_sha(bootstrap.INIT_RC)) != (
                    RC_SHA, bootstrap.MOD_INIT_SHA):
                raise RuntimeError("首次安装后配置校验失败；请勿重启，先执行恢复原厂启动配置。")
            if current_target() != new or remote_sha(new) != digest:
                raise RuntimeError("首次安装后视频校验失败；请勿重启，先执行恢复原厂启动配置。")
            log("首次安装完成。彻底关机再开机后观察白 H、动画和拍照界面。")
            return
        assert old is not None
        if old == new:
            log("这段动画已经安装，无需重复写入。")
            return
        with file_server(root):
            log("正在传输并校验动画…")
            download_to_camera("video.mp4", STAGE)
            if remote_sha(STAGE) != digest:
                raise RuntimeError("相机视频传输校验失败；当前动画未更改。")
        script = root / "apply.sh"
        script.write_text(apply_script(digest, new, old), encoding="ascii")
        log("正在原子切换动画入口…")
        run_camera_script(script, "X2DII_INSTALLED")
        if current_target() != new or remote_sha(new) != digest:
            raise RuntimeError("写入后校验失败；请先不要重启相机。")
        log("安装完成。下次彻底关机再开机即可看到新动画。")


def restore(which: str) -> None:
    old = check_camera()
    if which == "baseline":
        target = baseline_target()
    else:
        result = camera(f"readlink {PREVIOUS}")
        paths = re.findall(r"/(?:system|blackbox)/[^\s]+", result)
        target = paths[-1] if paths else ""
        if not valid_target(target):
            raise RuntimeError("没有可恢复的上一段动画。")
    if old == target:
        log("目标动画已在使用。")
        return
    with tempfile.TemporaryDirectory(prefix="x2dii-restore-") as directory:
        script = Path(directory) / "apply.sh"
        script.write_text(restore_script(target, old), encoding="ascii")
        run_camera_script(script, "X2DII_RESTORED")
    if current_target() != target:
        raise RuntimeError("恢复后校验失败；请先不要重启相机。")
    log("恢复完成。下次彻底关机再开机生效。")


def restore_stock() -> None:
    ensure_connection()
    if not re.search(r"\beagle2_hb722\b", camera("getprop ro.product.device")):
        raise RuntimeError("相机型号不匹配；未执行原厂恢复。")
    if not marker_present():
        raise RuntimeError("没有本安装器的首次安装记录；未改动原厂配置。")
    if (remote_sha(bootstrap.STOCK_CAMERA_BACKUP),
            remote_sha(bootstrap.STOCK_INIT_BACKUP)) != (
            bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA):
        raise RuntimeError("原厂备份校验失败；未执行恢复。")
    if remote_sha(bootstrap.CAMERA_RC) not in (
            bootstrap.STOCK_CAMERA_SHA, RC_SHA):
        raise RuntimeError("相机启动配置未知；未执行恢复。")
    if remote_sha(bootstrap.INIT_RC) not in (
            bootstrap.STOCK_INIT_SHA, bootstrap.MOD_INIT_SHA):
        raise RuntimeError("系统启动配置未知；未执行恢复。")
    with tempfile.TemporaryDirectory(prefix="x2dii-stock-restore-") as directory:
        script = Path(directory) / "apply.sh"
        script.write_text(bootstrap.uninstall_script(), encoding="ascii")
        run_camera_script(script, "X2DII_STOCK_RESTORED", timeout=30)
    if (remote_sha(bootstrap.CAMERA_RC), remote_sha(bootstrap.INIT_RC)) != (
            bootstrap.STOCK_CAMERA_SHA, bootstrap.STOCK_INIT_SHA):
        raise RuntimeError("原厂恢复后校验失败；请勿重启相机。")
    log("原厂启动配置已恢复。重启确认正常拍照后，可保留备份文件以备核查。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="只读检查原厂或已配置的相机")
    install_parser = sub.add_parser("install", help="转换并安装短视频")
    install_parser.add_argument("video", type=Path)
    restore_parser = sub.add_parser("restore", help="恢复基准或上一段动画")
    restore_parser.add_argument("which", choices=("baseline", "previous"))
    sub.add_parser("restore-stock", help="恢复本安装器首次安装前的原厂启动配置")
    args = parser.parse_args()
    try:
        if args.command == "check":
            inspect_camera()
        elif args.command == "install":
            install(args.video)
        elif args.command == "restore":
            restore(args.which)
        else:
            restore_stock()
        return 0
    except (OSError, ProtocolError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
        log(f"错误：{error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
