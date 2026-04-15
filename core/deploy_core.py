#!/usr/bin/env python3
"""
WSL2 本地大模型自动化部署工具
自动完成: WSL2 启用 → Ubuntu 24.04 安装 → CUDA 12.9.1 → llama.cpp-turboquant 编译运行

Usage: 以管理员身份运行 python autodeploy.py
"""

import os
import sys
import argparse
import json
import time
import getpass
import socket
import codecs
import shlex
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

from model_presets import DEFAULT_MODEL_PRESET_KEY, MODEL_PRESETS, get_model_preset

try:
    if not sys.stdout.isatty() or os.environ.get('AUTODEPLOY_FORCE_UTF8'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
except Exception:
    pass

# ═══════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════

DISTRO = "Ubuntu-24.04"
SCRIPT_DIR = os.environ.get("AUTODEPLOY_BASE_DIR") or os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "deploy_state.json")
CRED_BACKUP = os.path.join(SCRIPT_DIR, "ubuntu_credentials.txt")

# WSL2 更新包
WSL_UPDATE_URL = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
WSL_UPDATE_FILE = os.path.join(SCRIPT_DIR, "wsl_update_x64.msi")

# WSL 离线镜像
OFFLINE_WSL_URL = "https://releases.ubuntu.com/noble/ubuntu-24.04.4-wsl-amd64.wsl"
OFFLINE_WSL_FILE = os.path.join(SCRIPT_DIR, "ubuntu-24.04.4-wsl-amd64.wsl")
OFFLINE_WSL_SOURCES = [
    ("Ubuntu official", OFFLINE_WSL_URL),
    ("Aliyun mirror", "https://mirrors.aliyun.com/ubuntu-releases/24.04.4/ubuntu-24.04.4-wsl-amd64.wsl"),
    ("SYSU mirror", "https://mirror.sysu.edu.cn/ubuntu-releases/24.04/ubuntu-24.04.4-wsl-amd64.wsl"),
]
OFFICIAL_WSL_MIN_SPEED_MBPS = 1.0

# CUDA Toolkit 12.9.1
CUDA_RUN = "cuda_12.9.1_575.57.08_linux.run"
CUDA_URL = r"https://developer.download.nvidia.com/compute/cuda/12.9.1/local_installers/cuda_12.9.1_575.57.08_linux.run"

# llama.cpp turboquant
REPO_URL = "https://github.com/TheTom/llama-cpp-turboquant.git"
REPO_DIR = "llama-cpp-turboquant"

# 模型预设定义在 model_presets.py，部署时按 AUTODEPLOY_MODEL_PRESET / --model-preset 选择。





# 服务
SERVER_PORT = 8888
API_KEY = "sk-your-key"

# 代理 (宿主机 Clash 等代理，WSL2 通过宿主机 IP 访问)
PROXY_PORT = 7890

# 非交互模式 (GUI 启动器集成: 通过环境变量传入参数，跳过所有终端交互)
_ENV_PASSWORD = os.environ.get('AUTODEPLOY_PASSWORD', '')
_ENV_USERNAME = os.environ.get('AUTODEPLOY_USERNAME', '')
_ENV_INSTALL_DIR = os.environ.get('AUTODEPLOY_INSTALL_DIR', '')
_ENV_NON_INTERACTIVE = bool(os.environ.get('AUTODEPLOY_NON_INTERACTIVE', ''))
_ENV_WSL_MIRROR = os.environ.get('AUTODEPLOY_WSL_MIRROR', '')
_ENV_NO_START_SERVER = bool(os.environ.get('AUTODEPLOY_NO_START_SERVER', ''))
_ENV_JSON_EVENTS = bool(os.environ.get('AUTODEPLOY_JSON_EVENTS', ''))
_ENV_RESULT_FILE = os.environ.get('AUTODEPLOY_RESULT_FILE', os.path.join(SCRIPT_DIR, 'deploy_result.json'))
_ENV_MODEL_PRESET = os.environ.get('AUTODEPLOY_MODEL_PRESET', DEFAULT_MODEL_PRESET_KEY)


def _env_enabled(value):
    return str(value).strip().lower() not in ('', '0', 'false', 'no', 'off')


def emit_event(phase, step, status, message, **extra):
    """Emit machine-readable progress for the GUI while keeping normal logs intact."""
    if not _ENV_JSON_EVENTS:
        return
    payload = {
        'phase': phase,
        'step': step,
        'status': status,
        'message': message,
        'time': datetime.now().isoformat(timespec='seconds'),
    }
    payload.update(extra)
    print('::autodeploy-json::' + json.dumps(payload, ensure_ascii=False), flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Deploy WSL2 + Ubuntu 24.04 + CUDA + llama.cpp-turboquant.'
    )
    parser.add_argument('--non-interactive', action='store_true', help='Skip terminal prompts when possible.')
    parser.add_argument('--username', help='WSL user name to create or reuse.')
    parser.add_argument('--password', help='WSL user password for sudo and new-user creation.')
    parser.add_argument('--install-dir', help='Windows directory used for Ubuntu-24.04 import.')
    parser.add_argument('--wsl-mirror', help='Local Ubuntu .wsl image path.')
    parser.add_argument('--no-start-server', action='store_true', help='Prepare llama.cpp and models but do not start llama-server.')
    parser.add_argument('--model-preset', choices=sorted(MODEL_PRESETS.keys()), help='Model preset to download.')
    parser.add_argument('--json-events', action='store_true', help='Emit ::autodeploy-json:: progress records.')
    parser.add_argument('--result-file', help='Write deployment result metadata to this JSON file.')
    return parser.parse_args(argv)


def apply_args(args):
    global _ENV_PASSWORD, _ENV_USERNAME, _ENV_INSTALL_DIR, _ENV_NON_INTERACTIVE
    global _ENV_WSL_MIRROR, _ENV_NO_START_SERVER, _ENV_JSON_EVENTS, _ENV_RESULT_FILE, _ENV_MODEL_PRESET

    if args.password:
        _ENV_PASSWORD = args.password
    if args.username:
        _ENV_USERNAME = args.username
    if args.install_dir:
        _ENV_INSTALL_DIR = args.install_dir
    if args.wsl_mirror:
        _ENV_WSL_MIRROR = args.wsl_mirror
    if args.result_file:
        _ENV_RESULT_FILE = args.result_file
    if args.model_preset:
        _ENV_MODEL_PRESET = args.model_preset

    _ENV_NON_INTERACTIVE = _ENV_NON_INTERACTIVE or args.non_interactive
    _ENV_NO_START_SERVER = _ENV_NO_START_SERVER or args.no_start_server
    _ENV_JSON_EVENTS = _ENV_JSON_EVENTS or args.json_events


# ═══════════════════════════════════════════════════════════════
# 状态管理 — 断点续传
# ═══════════════════════════════════════════════════════════════

def load_state():
    """加载部署状态，记录已完成的阶段"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"phase1": False, "phase2": False, "phase3": False, "username": None}


def save_state(state):
    """持久化部署状态"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def is_admin():
    """检测是否以管理员身份运行"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _score_decoded_text(text):
    if not text:
        return -1000
    cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    printable = sum(1 for ch in text if ch.isprintable() or ch in '\r\n\t')
    controls = sum(1 for ch in text if not (ch.isprintable() or ch in '\r\n\t'))
    replacement = text.count('\ufffd')
    return cjk * 8 + printable - controls * 8 - replacement * 20


def decode_process_output(raw):
    """Decode mixed Windows/WSL output without letting mojibake leak into the GUI."""
    if not raw:
        return ""
    candidates = []
    for enc in ("utf-8", "utf-16-le", "gb18030", "cp936"):
        try:
            text = raw.decode(enc, errors="strict")
        except Exception:
            text = raw.decode(enc, errors="replace")
        candidates.append((_score_decoded_text(text), text))
    return max(candidates, key=lambda item: item[0])[1]


class ProcessOutputDecoder:
    def __init__(self):
        self._decoder = None
        self._encoding = None

    def decode(self, raw, final=False):
        if not raw and not final:
            return ""
        if self._decoder is None:
            if raw.startswith(b'\xff\xfe') or raw.count(b'\x00') > max(2, len(raw) // 8):
                self._encoding = "utf-16-le"
            else:
                self._encoding = "utf-8"
            self._decoder = codecs.getincrementaldecoder(self._encoding)(errors="strict")
        try:
            return self._decoder.decode(raw, final=final)
        except UnicodeDecodeError:
            self._encoding = "gb18030"
            self._decoder = codecs.getincrementaldecoder(self._encoding)(errors="replace")
            return self._decoder.decode(raw, final=final)


def stream_process_output(proc, prefix=""):
    assert proc.stdout is not None
    decoder = ProcessOutputDecoder()
    line_start = True
    while True:
        raw = proc.stdout.read1(4096)
        if not raw:
            if proc.poll() is not None:
                break
            continue
        text = decoder.decode(raw)
        if not text:
            continue
        if prefix:
            for ch in text:
                if line_start:
                    print(prefix, end="", flush=True)
                    line_start = False
                print(ch, end="", flush=True)
                if ch == "\n":
                    line_start = True
        else:
            print(text, end="", flush=True)
    tail = decoder.decode(b"", final=True)
    if tail:
        print(tail, end="", flush=True)


def run_win(cmd, capture=False):
    """在 Windows 侧执行命令。capture=True 时返回 str, 否则实时输出并返回 exit code。"""
    if capture:
        result = subprocess.run(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        return decode_process_output(result.stdout).strip()

    proc = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    stream_process_output(proc)
    return proc.wait()


def run_wsl(script, user="root", pwd=None, capture=False, timeout=None):
    """
    在 WSL 中执行 shell 脚本。

    通过 stdin (bash -s) 以 bytes 传递脚本内容，避免 Windows 文本模式
    自动把 \\n 转为 \\r\\n 导致 bash 报 $'\\r' 错误。
    """
    # 编码为 bytes 直写管道，绕过 Windows TextIOWrapper 的 \\n→\\r\\n 转换
    script_bytes = script.encode("utf-8")

    cmd = f"wsl -d {DISTRO} -u {user} -- bash -s"
    if capture:
        result = subprocess.run(
            cmd, shell=True, input=script_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
        out = decode_process_output(result.stdout).strip()
        return out, result.returncode

    print(f"  [*] WSL: {script.strip()[:80]}...")
    try:
        proc = subprocess.Popen(
            cmd, shell=True, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert proc.stdin is not None
        proc.stdin.write(script_bytes)
        proc.stdin.close()
        stream_process_output(proc)
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  [!] WSL 命令超时 ({timeout}s)")
        try:
            proc.kill()
        except Exception:
            pass
        return -1


def run_wsl_sudo(script, username, password, capture=False, timeout=None):
    """
    带 sudo 提权的 WSL 命令执行。
    在同一个 shell 内先验证密码 (sudo -v)，再执行脚本。
    """
    # 验证密码 + 执行脚本 放在同一个 bash session
    combined = f"echo '{password}' | sudo -S -v 2>/dev/null && echo '[+] sudo 密码验证成功' || echo '[!] sudo 密码验证失败'; {script}"
    combined_bytes = combined.encode("utf-8")
    cmd = f"wsl -d {DISTRO} -u {username} -- bash -s"

    if capture:
        result = subprocess.run(
            cmd, shell=True, input=combined_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
        out = decode_process_output(result.stdout).strip()
        return out, result.returncode

    print(f"  [*] WSL (sudo): {script.strip()[:80]}...")
    try:
        proc = subprocess.Popen(
            cmd, shell=True, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert proc.stdin is not None
        proc.stdin.write(combined_bytes)
        proc.stdin.close()
        stream_process_output(proc)
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  [!] WSL sudo 命令超时 ({timeout}s)")
        try:
            proc.kill()
        except Exception:
            pass
        return -1


def check_net(url):
    """网络连通性预检"""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        _ = socket.create_connection((host, port), timeout=10)
        return True
    except Exception as e:
        print(f"  [!] 网络不通: {host}:{port} - {e}")
        return False


def download_with_progress(url, dest, min_speed_mbps=None):
    """
    带测速 + ETA 的文件下载器 (Windows 侧)。
    下载满 2MB 时显示网速和预计剩余时间。
    """
    print(f"[*] 获取文件信息: {url}")
    headers = {"User-Agent": "Mozilla/5.0 autodeploy/1.0"}
    total = 0
    try:
        req = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            total = int(resp.headers.get("Content-Length", 0))
    except Exception as e:
        print(f"[!] 无法通过 HEAD 获取文件大小，继续直接下载: {e}")

    if total:
        total_mb = total / (1024 * 1024)
        print(f"[*] 文件大小: {total_mb:.1f} MB")
    else:
        total_mb = 0
        print("[*] 文件大小未知，将在下载时显示已完成体积和速度")

    t0 = time.time()
    done = 0
    chunk_size = 64 * 1024  # 64KB
    speed_shown = False
    tmp_dest = dest + ".part"

    def cleanup_tmp():
        try:
            if os.path.exists(tmp_dest):
                os.remove(tmp_dest)
        except Exception:
            pass

    def curl_download():
        print("[*] Python 下载失败，切换 curl.exe 下载...")
        cmd = [
            "curl.exe",
            "-L",
            "--fail",
            "--retry", "5",
            "--retry-delay", "5",
            "--connect-timeout", "500",
            "--output", tmp_dest,
            url,
        ]
        if min_speed_mbps:
            cmd[1:1] = [
                "--speed-limit", str(int(min_speed_mbps * 1024 * 1024)),
                "--speed-time", "10",
            ]
            print(f"[*] curl.exe 低速保护: 低于 {min_speed_mbps:.1f} MB/s 持续 10 秒则切换源")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            stream_process_output(proc)
            rc = proc.wait()
        except FileNotFoundError:
            print("[!] 找不到 curl.exe")
            return False
        except Exception as e:
            print(f"[!] curl.exe 下载异常: {e}")
            return False
        if rc != 0:
            print(f"[!] curl.exe 下载失败 (rc={rc})")
            return False
        return os.path.exists(tmp_dest) and os.path.getsize(tmp_dest) > 0

    try:
        if os.path.exists(tmp_dest):
            os.remove(tmp_dest)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_dest, "wb") as f:
            if not total:
                try:
                    total = int(resp.headers.get("Content-Length", 0))
                    total_mb = total / (1024 * 1024) if total else 0
                    if total:
                        print(f"[*] GET 响应文件大小: {total_mb:.1f} MB")
                except Exception:
                    total = 0
            while True:
                data = resp.read(chunk_size)
                if not data:
                    break
                f.write(data)
                done += len(data)

                # 下载满 5MB 后测速 + ETA (仅显示一次)
                if not speed_shown and done >= 2 * 1024 * 1024:
                    elapsed = time.time() - t0
                    speed = done / elapsed / (1024 * 1024)  # MB/s
                    if total:
                        remaining = (total - done) / (speed * 1024 * 1024)
                        print(
                            f"[+] 当前速度: {speed:.1f} MB/s | "
                            f"预计剩余: {int(remaining // 60)}分{int(remaining % 60)}秒"
                        )
                    else:
                        print(f"[+] 测速: {speed:.1f} MB/s")
                    speed_shown = True
                    if min_speed_mbps and speed < min_speed_mbps:
                        print(
                            f"[!] 当前源测速 {speed:.1f} MB/s，低于 {min_speed_mbps:.1f} MB/s，切换备用源。"
                        )
                        cleanup_tmp()
                        return False

                # 每 100MB 显示进度
                if speed_shown and done % (100 * 1024 * 1024) < chunk_size:
                    elapsed = time.time() - t0
                    speed = done / elapsed / (1024 * 1024)
                    if total:
                        pct = done / total * 100
                        print(
                            f"  [{pct:.0f}%] "
                            f"{done / (1024*1024):.0f}/{total_mb:.0f} MB "
                            f"@ {speed:.1f} MB/s"
                        )
                    else:
                        print(f"  {done / (1024*1024):.0f} MB @ {speed:.1f} MB/s")
    except Exception as e:
        print(f"[!] 下载失败: {e}")
        cleanup_tmp()
        if not curl_download():
            cleanup_tmp()
            return False
        done = os.path.getsize(tmp_dest)

    if total and done != total:
        print(f"[!] 下载大小不匹配: {done} / {total} bytes")
        cleanup_tmp()
        return False

    os.replace(tmp_dest, dest)
    elapsed = time.time() - t0
    speed = done / elapsed / (1024 * 1024)
    done_mb = done / (1024 * 1024)
    print(f"[+] 下载完成! {done_mb:.0f} MB, 平均 {speed:.1f} MB/s, {int(elapsed)}秒")
    return True


def _parse_size(val):
    """解析 memory/swap 值为 MB 数，如 '20GB' -> 20480, '512MB' -> 512"""
    val = val.strip().upper()
    if val.endswith("GB"):
        return int(val[:-2]) * 1024
    if val.endswith("MB"):
        return int(val[:-2])
    try:
        return int(val)
    except ValueError:
        return 0


def _merge_wslconfig():
    """
    智能合并 .wslconfig:
    - 资源类 (memory/swap/processors): 用户值 >= 最低要求则不改动，否则提升到最低要求
    - 开关类 (guiApplications/localhostForwarding): 缺失则补上 true
    - 保留用户所有其他配置项不变
    """
    wslconfig_path = os.path.join(os.environ["USERPROFILE"], ".wslconfig")

    # 最低要求
    MINIMUM = {
        "memory": "20GB",
        "swap": "30GB",
        "processors": "12",
    }
    # 必须开启的开关
    REQUIRED_FLAGS = {
        "guiApplications": "true",
        "localhostForwarding": "true",
    }

    # 读取已有配置
    existing = {}
    in_wsl2 = False
    other_lines = []  # [wsl2] 段之外的行
    if os.path.exists(wslconfig_path):
        with open(wslconfig_path, "r", encoding="utf-8") as f:
            current_section = None
            for line in f:
                stripped = line.strip()
                if stripped.startswith("["):
                    current_section = stripped
                    if current_section != "[wsl2]":
                        other_lines.append(line.rstrip("\n").rstrip("\r"))
                    continue
                if current_section == "[wsl2]":
                    if "=" in stripped and not stripped.startswith("#"):
                        key, _, value = stripped.partition("=")
                        existing[key.strip()] = value.strip()
                else:
                    other_lines.append(line.rstrip("\n").rstrip("\r"))

    changed = []

    # 处理资源类: 仅在用户值 < 最低要求时提升
    for key, minimum_val in MINIMUM.items():
        if key == "processors":
            # processors 是整数比较
            need = int(minimum_val)
            have = int(existing[key]) if key in existing else 0
            if have < need:
                existing[key] = minimum_val
                changed.append(f"{key}: {have or '未设置'} -> {minimum_val}")
        else:
            # memory/swap 按MB比较
            need_mb = _parse_size(minimum_val)
            have_mb = _parse_size(existing[key]) if key in existing else 0
            if have_mb < need_mb:
                existing[key] = minimum_val
                changed.append(f"{key}: {existing.get(key, '未设置')} -> {minimum_val}")

    # 处理开关类: 缺失则补上
    for key, val in REQUIRED_FLAGS.items():
        if key not in existing or existing[key].lower() != "true":
            existing[key] = val
            changed.append(f"{key}: -> {val}")

    # 写回
    with open(wslconfig_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("[wsl2]\n")
        for key, value in existing.items():
            f.write(f"{key}={value}\n")
        for line in other_lines:
            if line.strip():
                f.write(f"\n{line}\n")

    print(f"[+] .wslconfig -> {wslconfig_path}")
    if changed:
        for c in changed:
            print(f"    {c}")
    else:
        print("    所有配置已满足，无需修改。")

    run_win("wsl --shutdown")
    time.sleep(3)


# ═══════════════════════════════════════════════════════════════
# 阶段 1: Windows 环境检测与 WSL 安装
# ═══════════════════════════════════════════════════════════════


def _wsl2_active():
    """WSL2 核心是否已启用 — wsl --status 返回 0 即为已安装"""
    return subprocess.run(
        "wsl --status", shell=True, capture_output=True,
    ).returncode == 0


def _distro_ready():
    """Ubuntu-24.04 是否已安装且可运行 — 在其中 echo 验证"""
    return subprocess.run(
        f"wsl -d {DISTRO} -- echo OK", shell=True, capture_output=True,
    ).returncode == 0


def _distro_registered():
    """目标发行版是否已经注册。注册存在时绝不能再次 wsl --import。"""
    result = subprocess.run(
        "wsl --list --quiet",
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    text = decode_process_output(result.stdout)
    names = []
    for line in text.splitlines():
        name = line.replace("\x00", "").strip().lstrip("*").strip()
        if name:
            names.append(name)
    return DISTRO in names


def _feature_enabled(name):
    """检查 Windows 功能是否已启用"""
    result = subprocess.run(
        f"dism.exe /online /get-featureinfo /featurename:{name}",
        shell=True, capture_output=True, encoding="utf-8", errors="replace",
    )
    return "启用" in (result.stdout or "") or "Enable" in (result.stdout or "")


def _enable_wsl_fallback():
    """wsl --install 超时: DISM 手动启用 (需重启)"""
    print("\n[*] 启用备用方案 (DISM + 手动更新)...")
    features = [
        "Microsoft-Windows-Subsystem-Linux",
        "VirtualMachinePlatform",
    ]
    need_restart = False
    for feat in features:
        if _feature_enabled(feat):
            print(f"    {feat}: 已启用")
        else:
            print(f"    {feat}: 启用中...")
            run_win(
                f"dism.exe /online /enable-feature "
                f"/featurename:{feat} /all /norestart"
            )
            need_restart = True

    if need_restart:
        print("\n[!] 已启用 Windows 功能，必须重启才能生效。")
        print("    请重启计算机后再次运行此程序 (自动跳过已完成步骤)。")
        sys.exit(0)

    # 功能已启用但 WSL 还不工作 → 安装内核更新
    if not os.path.exists(WSL_UPDATE_FILE):
        print("  [*] 下载 WSL2 内核更新包...")
        download_with_progress(WSL_UPDATE_URL, WSL_UPDATE_FILE)

    print("  [*] 安装 WSL2 内核更新...")
    run_win(f'msiexec /i "{WSL_UPDATE_FILE}" /quiet /norestart')
    run_win("wsl --set-default-version 2")


def _run_with_live_output(cmd, timeout=300):
    """执行 Windows 命令并实时输出 stdout/stderr，带超时。返回 returncode。"""
    proc = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        t0 = time.time()
        decoder = ProcessOutputDecoder()
        line_start = True
        while True:
            if timeout and (time.time() - t0) > timeout:
                proc.kill()
                proc.wait()
                print(f"  [!] 超时 ({timeout}s)")
                return -1
            raw = proc.stdout.read1(4096)
            if not raw and proc.poll() is not None:
                break
            if raw:
                text = decoder.decode(raw)
                if text:
                    for ch in text:
                        if line_start:
                            print("  | ", end="", flush=True)
                            line_start = False
                        print(ch, end="", flush=True)
                        if ch == "\n":
                            line_start = True
        tail = decoder.decode(b"", final=True)
        if tail:
            print(tail, end="", flush=True)
        return proc.returncode
    except Exception:
        proc.kill()
        proc.wait()
        return None






def _pick_wsl_file():
    """弹出文件选择对话框让用户选择 .wsl 镜像文件，返回路径或 None"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        file_path = filedialog.askopenfilename(
            title="选择 Ubuntu WSL 镜像文件",
            filetypes=[("WSL 镜像", "*.wsl"), ("所有文件", "*.*")],
            initialdir=SCRIPT_DIR,
        )
        root.destroy()
        return file_path if file_path else None
    except Exception as e:
        print(f"  [!] 文件选择框不可用: {e}")
        return None


def _find_local_wsl():
    """
    在脚本目录及相邻目录查找 .wsl 镜像文件。
    返回路径或 None。
    """
    search_dirs = [SCRIPT_DIR, os.path.dirname(SCRIPT_DIR), os.getcwd()]
    for d in search_dirs:
        if not d:
            continue
        try:
            for f in os.listdir(d):
                if f.endswith(".wsl"):
                    full = os.path.join(d, f)
                    if os.path.getsize(full) > 100 * 1024 * 1024:  # > 100MB
                        return full
        except Exception:
            pass
    return None


def _pick_install_dir():
    """弹出文件夹选择对话框让用户选择 WSL 安装位置"""
    if _ENV_INSTALL_DIR:
        os.makedirs(_ENV_INSTALL_DIR, exist_ok=True)
        print(f"[+] 使用指定安装位置: {_ENV_INSTALL_DIR}")
        return _ENV_INSTALL_DIR
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        folder = filedialog.askdirectory(
            title="选择 Ubuntu-24.04 的安装位置",
            initialdir=os.environ.get("USERPROFILE", "~"),
        )
        root.destroy()
        if folder:
            install_dir = os.path.join(folder, DISTRO)
            os.makedirs(install_dir, exist_ok=True)
            return install_dir
    except Exception:
        pass
    return None


def _get_wsl_install_dir():
    """获取 WSL 发行版安装目录 (用户选择 or 默认)"""
    print("[*] 请选择 Ubuntu 安装位置...")
    chosen = _pick_install_dir()
    if chosen:
        print(f"[+] 安装位置: {chosen}")
        return chosen
    # 用户取消或对话框不可用 → 使用默认
    default = os.path.join(
        os.environ.get("USERPROFILE", "~"), "WSL", DISTRO
    )
    os.makedirs(default, exist_ok=True)
    print(f"[+] 使用默认位置: {default}")
    return default


def _import_wsl(wsl_file):
    """
    使用 wsl --import 导入镜像。
    - 不自动启动 (不中断脚本)
    - 不交互式创建用户 (留给 phase_2)
    - 自定义安装位置
    返回 True/False
    """
    if _distro_registered():
        print(f"[+] {DISTRO} 已经注册，跳过 wsl --import。")
        return True

    install_dir = _get_wsl_install_dir()
    print(f"    安装位置: {install_dir}")
    ret = run_win(f'wsl --import {DISTRO} "{install_dir}" "{wsl_file}"')
    if ret == 0:
        print("[+] 导入成功!")
        return True
    if _distro_registered():
        print(f"[+] {DISTRO} 已经注册，按已有发行版继续。")
        return True
    print(f"[!] wsl --import 失败 (rc={ret})")
    return False


def _download_offline_wsl_image():
    """Download Ubuntu .wsl image with official-first mirror fallback."""
    target = OFFLINE_WSL_FILE
    if os.path.exists(target):
        print(f"[+] 本地已有 Ubuntu 离线包: {target}")
        return target

    for idx, (name, url) in enumerate(OFFLINE_WSL_SOURCES):
        print(f"\n[*] 尝试下载 Ubuntu WSL 镜像: {name}")
        print(f"    {url}")
        if not check_net(url):
            print(f"[!] {name} 连接失败，切换下一个源。")
            continue

        min_speed = OFFICIAL_WSL_MIN_SPEED_MBPS if idx == 0 else None
        if min_speed:
            print(f"[*] 官方源测速低于 {min_speed:.1f} MB/s 时自动切换备用源。")

        if download_with_progress(url, target, min_speed_mbps=min_speed):
            return target

    return None


def _install_ubuntu():
    """Ubuntu-24.04 安装: 指定镜像 → 本地镜像搜索 → 官方 .wsl 下载 → WSL 在线兜底"""

    # 最高优先级: GUI 传入的镜像路径
    if _ENV_WSL_MIRROR and os.path.isfile(_ENV_WSL_MIRROR):
        print(f"\n[+] 使用指定镜像: {_ENV_WSL_MIRROR}")
        if _import_wsl(_ENV_WSL_MIRROR):
            return
        print("[!] 指定镜像导入失败，继续尝试其他方案。")

    # 搜索本地已有的 .wsl 镜像
    local_wsl = _find_local_wsl()

    if local_wsl:
        print(f"\n[+] 发现本地镜像: {local_wsl}")
        if _import_wsl(local_wsl):
            return
        print("[!] 本地镜像导入失败，继续尝试官方 .wsl 镜像下载。")

    # 询问用户是否有本地镜像
    if _ENV_NON_INTERACTIVE:
        pass
    else:
        choice = input(
            "\n[?] 是否手动选择本地 .wsl 镜像文件？(直接回车跳过，输入 y 打开文件选择): "
        ).strip().lower()
        if choice.startswith("y"):
            picked = _pick_wsl_file()
            if picked:
                print(f"[*] 使用用户选择: {picked}")
                if _import_wsl(picked):
                    return
                print("[!] 用户选择的镜像导入也失败。")

    # 优先官方 .wsl 离线包: 下载到项目目录后通过 wsl --import 导入，绕开微软商店下载链路
    print(f"\n[*] 下载 Ubuntu WSL 镜像并本地导入 ({DISTRO})...")
    target = _download_offline_wsl_image()
    if target:
        print("[*] 从 .wsl 镜像导入安装...")
        if _import_wsl(target):
            return
        print("[!] .wsl 镜像导入失败。")
    else:
        print("[!] 所有 .wsl 镜像源下载失败。")

    # 最后兜底: WSL 内置在线安装
    print(f"\n[*] 官方 .wsl 导入未成功，最后尝试 WSL 在线安装 {DISTRO} (--web-download)...")
    print(f"    (最长等待 5 分钟，实时输出如下:)")
    rc = _run_with_live_output(
        f"wsl --install -d {DISTRO} --web-download",
        timeout=300,
    )
    if rc == 0:
        print(f"[+] {DISTRO} 在线安装成功!")
        return
    if rc is None:
        print("[!] WSL 在线安装超时 (5分钟)。")
    else:
        print(f"[!] WSL 在线安装失败 (rc={rc})。")

    print("[!] 所有安装方式均失败，请手动安装后重试。")
    sys.exit(1)


def _selected_model_preset():
    key = _ENV_MODEL_PRESET if _ENV_MODEL_PRESET in MODEL_PRESETS else DEFAULT_MODEL_PRESET_KEY
    if key != _ENV_MODEL_PRESET:
        print(f"[!] 未知模型预设 {_ENV_MODEL_PRESET!r}，使用默认预设 {DEFAULT_MODEL_PRESET_KEY}")
    return key, get_model_preset(key)


def _model_paths(username):
    key, preset = _selected_model_preset()
    home = f"/home/{username}"
    model_dir = f"{home}/gguf_models/{preset['directory']}"
    llm_file = preset['artifacts']['llm']['filename']
    mm_file = preset['artifacts']['mm']['filename']
    return {
        'key': key,
        'preset': preset,
        'model_dir': model_dir,
        'llm_path': f"{model_dir}/{llm_file}",
        'mm_path': f"{model_dir}/{mm_file}",
        'llm_file': llm_file,
        'mm_file': mm_file,
    }


def _validate_downloaded_gguf(username, path):
    out, rc = run_wsl(
        f"""
python3 - {shlex.quote(path)} <<'PY'
import struct
import sys

path = sys.argv[1]
try:
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise SystemExit(2)
        f.seek(12)
        data = f.read(4)
        if len(data) != 4:
            raise SystemExit(3)
        if struct.unpack("<I", data)[0] == 0:
            raise SystemExit(4)
except Exception:
    raise SystemExit(5)
PY
""",
        user=username,
        capture=True,
    )
    return rc == 0


def _download_model_artifact(username, model_dir, label, filename, sources):
    target = f"{model_dir}/{filename}"
    run_wsl(f"mkdir -p {shlex.quote(model_dir)}", user=username)
    for source_name, url in sources:
        print(f"[*] 下载 {label}: {filename}")
        print(f"    源: {source_name}")
        rc = run_wsl(
            (
                f"cd {shlex.quote(model_dir)}\n"
                f"wget -c --progress=bar:force:noscroll --timeout=30 --tries=3 "
                f"{shlex.quote(url)} -O {shlex.quote(filename)}"
            ),
            user=username,
            timeout=7200,
        )
        if rc == 0:
            if _validate_downloaded_gguf(username, target):
                return True
            print(f"[!] {filename} 下载结果不是有效 GGUF 文件，删除后尝试下一个源。")
        else:
            print(f"[!] {source_name} 下载失败 (rc={rc})，尝试下一个源。")
        run_wsl(f"rm -f {shlex.quote(target)}", user=username)
    return False


def _write_failure_log(filename, content):
    path = os.path.join(SCRIPT_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.write(content.rstrip() + "\n")
        print(f"[!] 错误详情已写入: {path}")
    except Exception as e:
        print(f"[!] 写入错误日志失败: {e}")
    return path


def _verify_llama_build(username, repo_path, log_on_fail=False):
    print("[*] 验证编译结果...")
    out, rc = run_wsl(
        f"""
source ~/.bashrc
cd {shlex.quote(repo_path)}
if [ ! -x ./build/bin/llama-server ]; then
    echo '[!] ./build/bin/llama-server 不存在或不可执行'
    exit 2
fi
set -o pipefail
./build/bin/llama-server --help 2>&1 | grep -E 'turbo[0-9]'
""",
        user=username,
        capture=True,
        timeout=120,
    )
    if out:
        print(out)
    ok = rc == 0 and "turbo" in out
    if ok:
        print("[+] 编译完成并验证通过")
        return True

    print(f"[!] 编译验证失败 (rc={rc})。")
    if log_on_fail:
        _write_failure_log(
            "compile_verify_error.log",
            (
                "llama.cpp-turboquant build verification failed\n"
                f"time: {datetime.now().isoformat(timespec='seconds')}\n"
                f"distro: {DISTRO}\n"
                f"user: {username}\n"
                f"repo: {repo_path}\n"
                f"return_code: {rc}\n\n"
                f"{out or '<no output>'}"
            ),
        )
    return False


def phase_1():
    print("\n" + "=" * 60)
    print("  阶段 1: Windows 环境检测与 WSL 安装")
    print("=" * 60)

    # ── [1/3] 检查 WSL2 核心 + 目标分发版 ──
    print("\n[1/3] 检查 WSL 状态...")
    wsl_ok = _wsl2_active()
    distro_registered = _distro_registered() if wsl_ok else False
    distro_ok = _distro_ready()

    if wsl_ok and distro_ok:
        print(f"[+] WSL2 + {DISTRO} 均已就绪，跳过安装。")
    else:
        if not wsl_ok:
            print("[!] WSL2 未启用，执行 wsl --install --no-distribution...")
            install_ok = False
            try:
                ret = subprocess.run(
                    "wsl --install --no-distribution",
                    shell=True, capture_output=True,
                    encoding="utf-8", errors="replace",
                    timeout=300,
                )
                install_ok = ret.returncode == 0
            except subprocess.TimeoutExpired:
                print("[!] wsl --install 超时 (5分钟)，切换备用方案...")
            except Exception as e:
                print(f"[!] wsl --install 异常: {e}")

            if not install_ok:
                _enable_wsl_fallback()

            wsl_ok = _wsl2_active()
            if not wsl_ok:
                print("[!] WSL2 仍未就绪，可能需要重启。")
                print("    请重启计算机后再次运行此程序 (自动跳过已完成步骤)。")
                sys.exit(0)
            print("[+] WSL2 核心组件已经安装，准备安装 Ubuntu 发行版。")
            distro_registered = _distro_registered()

        if distro_registered and not distro_ok:
            print(f"[+] {DISTRO} 已注册，跳过导入安装，稍后进行运行验证。")
        elif not distro_ok:
            _install_ubuntu()

    # ── [2/3] 配置 .wslconfig (智能合并，不降低用户已有配置) ──
    print(f"\n[2/3] 配置 .wslconfig...")
    _merge_wslconfig()

    # ── [3/3] 最终验证 ──
    print(f"\n[3/3] 验证 {DISTRO} 运行...")
    for retry in range(1, 4):
        if _distro_ready():
            print(f"[+] {DISTRO} 运行正常。")
            return
        print(f"  [*] 验证重试 {retry}/3...")
        time.sleep(3)
    print("[!] WSL 验证失败，可能需要重启后重试。")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# 用户凭据输入
# ═══════════════════════════════════════════════════════════════

def _detect_wsl_users():
    """扫描 WSL 中已有的普通用户 (UID >= 1000)，返回列表"""
    out, rc = run_wsl(
        "awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd",
        user="root",
        capture=True,
    )
    if rc != 0 or not out.strip():
        return []
    return [u for u in out.strip().splitlines() if u]


def _ask_password(username, verify=False, max_retry=3):
    """
    请求用户输入密码，带重试。
    verify=True 时通过 WSL sudo -S -v 验证密码是否正确。
    """
    if _ENV_PASSWORD:
        print("[+] 使用预设密码")
        return _ENV_PASSWORD
    for attempt in range(1, max_retry + 1):
        pwd = getpass.getpass(f"请输入 {username} 的密码 (第 {attempt}/{max_retry} 次): ")
        if not pwd:
            print("[!] 密码不能为空。")
            continue

        if verify:
            # 通过 WSL 验证密码是否正确
            check_script = f"echo '{pwd}' | sudo -S -v 2>/dev/null && echo PWD_OK || echo PWD_FAIL"
            check_bytes = check_script.encode("utf-8")
            cmd = f"wsl -d {DISTRO} -u {username} -- bash -s"
            try:
                result = subprocess.run(
                    cmd, shell=True, input=check_bytes,
                    capture_output=True, timeout=10,
                )
                out = result.stdout.decode("utf-8", errors="replace")
                if "PWD_OK" in out:
                    return pwd
                else:
                    print("[!] 密码错误，请重试。")
                    continue
            except Exception:
                # WSL 不可用时跳过验证
                pass

        return pwd

    print(f"[!] {max_retry} 次密码输入均失败。")
    sys.exit(1)


def resolve_user():
    """
    确定 WSL 中要使用的用户:
    1. 自动检测已有普通用户
    2. 只有 1 个 → 直接复用
    3. 有多个 → 让用户选
    4. 没有 → 提示创建新用户
    返回 (username, password, is_new_user)
    """
    existing = _detect_wsl_users()
    preferred = _ENV_USERNAME.strip()

    if preferred:
        if preferred in existing:
            print(f"\n[+] 使用指定用户: {preferred}")
            password = _ask_password(preferred, verify=True)
            return preferred, password, False
        print(f"\n[*] WSL 中没有指定用户 {preferred}，将创建该用户。")
        password = _ask_password(preferred, verify=False)
        return preferred, password, True

    if len(existing) == 1:
        username = existing[0]
        print(f"\n[+] 检测到已有用户: {username}，直接使用。")
        password = _ask_password(username, verify=True)
        return username, password, False

    if len(existing) > 1:
        print(f"\n[*] 检测到多个用户: {', '.join(existing)}")
        if _ENV_NON_INTERACTIVE:
            username = existing[0]
            print(f"[+] 非交互模式，自动选择: {username}")
        else:
            for i, u in enumerate(existing, 1):
                print(f"  {i}. {u}")
            while True:
                choice = input(f"请选择 (1-{len(existing)}): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(existing):
                    username = existing[int(choice) - 1]
                    break
        password = _ask_password(username, verify=True)
        return username, password, False

    # 没有普通用户 → 创建新用户
    print("\n[*] WSL 中暂无普通用户，需要创建一个。")
    print("=" * 40)
    if _ENV_NON_INTERACTIVE:
        username = preferred or "llama"
        print(f"[+] 非交互模式，使用默认用户名: {username}")
    else:
        while True:
            username = input("请输入新用户名 (小写字母开头): ").strip()
            if (
                username
                and username[0].isalpha()
                and username.replace("_", "").isalnum()
                and username.lower() == username
            ):
                break
            print("[!] 用户名需小写字母开头，仅含小写字母/数字/下划线。")

    if _ENV_PASSWORD:
        pwd = _ENV_PASSWORD
        print("[+] 使用预设密码")
    else:
        while True:
            pwd = getpass.getpass("请设置密码 (输入时不显示): ")
            pwd_confirm = getpass.getpass("确认密码: ")
            if pwd and pwd == pwd_confirm:
                break
            if not pwd:
                print("[!] 密码不能为空。")
            else:
                print("[!] 两次密码不一致。")

    # 明文备份
    with open(CRED_BACKUP, "w", encoding="utf-8") as f:
        f.write(f"Ubuntu-24.04 凭据备份\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"用户名: {username}\n")
        f.write(f"密码: {pwd}\n")
    print(f"[+] 凭据已备份: {CRED_BACKUP}")

    return username, pwd, True


# ═══════════════════════════════════════════════════════════════
# 阶段 2: Ubuntu 环境静默配置
# ═══════════════════════════════════════════════════════════════

def phase_2(username, password, is_new=False):
    print("\n" + "=" * 60)
    print(f"  阶段 2: Ubuntu 环境配置 (用户: {username})")
    print("=" * 60)

    home = f"/home/{username}"

    # ── [0] 配置代理 (通过宿主机 Clash 等代理加速) ──
    print("\n[*] 配置网络代理 (通过宿主机)...")
    run_wsl(
        f"""
HOST_IP=$(ip route show default 2>/dev/null | awk '{{print $3}}')
if [ -z "$HOST_IP" ]; then
    HOST_IP=$(cat /etc/resolv.conf 2>/dev/null | grep nameserver | awk '{{print $2}}')
fi
if [ -n "$HOST_IP" ]; then
    export http_proxy="http://${{HOST_IP}}:{PROXY_PORT}"
    export https_proxy="http://${{HOST_IP}}:{PROXY_PORT}"
    export HTTP_PROXY="$http_proxy"
    export HTTPS_PROXY="$https_proxy"
    # 验证代理是否可用
    if curl -x "$http_proxy" -s --connect-timeout 5 https://www.google.com -o /dev/null 2>/dev/null; then
        echo "[+] 代理可用: $http_proxy (宿主机 $HOST_IP)"
    else
        echo "[!] 代理不可达 (${{HOST_IP}}:{PROXY_PORT})，将使用直连"
        unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    fi
else
    echo "[!] 无法获取宿主机 IP，将使用直连"
fi
""",
        user="root",
        pwd=password,
    )

    # ── [1/5] 创建用户 (仅新用户时执行) ──
    if is_new:
        print(f"\n[1/5] 创建用户 {username}...")
        run_wsl(
            f"""
useradd -m -s /bin/bash -G sudo '{username}'
echo '{username}:{password}' | chpasswd
echo '[+] 用户创建成功'
""",
            user="root",
        )
    else:
        print(f"\n[1/5] 用户 {username} 已存在，跳过创建。")

    # ── [2/5] 配置 /etc/wsl.conf (追加合并，不覆盖已有配置) ──
    print("\n[2/5] 配置 /etc/wsl.conf...")
    run_wsl(
        f"""
# 确保 [user] 段有 default={username}
if ! grep -q '\\[user\\]' /etc/wsl.conf 2>/dev/null; then
    echo '[user]' >> /etc/wsl.conf
    echo 'default={username}' >> /etc/wsl.conf
elif ! grep -q 'default={username}' /etc/wsl.conf 2>/dev/null; then
    sed -i '/\\[user\\]/a default={username}' /etc/wsl.conf
fi

# 确保 [boot] 段有 systemd=true
if ! grep -q '\\[boot\\]' /etc/wsl.conf 2>/dev/null; then
    echo '' >> /etc/wsl.conf
    echo '[boot]' >> /etc/wsl.conf
    echo 'systemd=true' >> /etc/wsl.conf
elif ! grep -q 'systemd=true' /etc/wsl.conf 2>/dev/null; then
    sed -i '/\\[boot\\]/a systemd=true' /etc/wsl.conf
fi

# 确保 [interop] 段有 enabled=true 和 appendWindowsPath=false
if ! grep -q '\\[interop\\]' /etc/wsl.conf 2>/dev/null; then
    echo '' >> /etc/wsl.conf
    echo '[interop]' >> /etc/wsl.conf
    echo 'enabled=true' >> /etc/wsl.conf
    echo 'appendWindowsPath=false' >> /etc/wsl.conf
else
    if ! grep -q 'enabled=true' /etc/wsl.conf 2>/dev/null; then
        sed -i '/\\[interop\\]/a enabled=true' /etc/wsl.conf
    fi
    if ! grep -q 'appendWindowsPath=false' /etc/wsl.conf 2>/dev/null; then
        sed -i '/\\[interop\\]/a appendWindowsPath=false' /etc/wsl.conf
    fi
fi

# 确保 [automount] 段有 enabled=false 和 mountFsTab=false (禁止访问 Windows 磁盘)
if ! grep -q '\\[automount\\]' /etc/wsl.conf 2>/dev/null; then
    echo '' >> /etc/wsl.conf
    echo '[automount]' >> /etc/wsl.conf
    echo 'enabled=false' >> /etc/wsl.conf
    echo 'mountFsTab=false' >> /etc/wsl.conf
else
    if ! grep -q 'enabled=false' /etc/wsl.conf 2>/dev/null; then
        sed -i '/\\[automount\\]/a enabled=false' /etc/wsl.conf
    fi
    if ! grep -q 'mountFsTab=false' /etc/wsl.conf 2>/dev/null; then
        sed -i '/\\[automount\\]/a mountFsTab=false' /etc/wsl.conf
    fi
fi

echo '[+] /etc/wsl.conf 配置完成'
cat /etc/wsl.conf
""",
        user="root",
        pwd=password,
    )

    # ── [3/5] APT 依赖安装 ──
    print("\n[3/5] 安装系统依赖...")
    run_wsl(
        """
# 配置清华镜像源 (DEB822 格式，写入独立文件，不覆盖原有配置)
if [ ! -f /etc/apt/sources.list.d/tsinghua.sources ]; then
    echo '[*] 配置清华镜像源...'
    cat > /etc/apt/sources.list.d/tsinghua.sources << 'TSINGHUA'
Types: deb
URIs: https://mirrors.tuna.tsinghua.edu.cn/ubuntu
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

# 默认注释了源码镜像以提高 apt update 速度，如有需要可自行取消注释
# Types: deb-src
# URIs: https://mirrors.tuna.tsinghua.edu.cn/ubuntu
# Suites: noble noble-updates noble-backports
# Components: main restricted universe multiverse
# Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

# 以下安全更新软件源包含了官方源与镜像站配置，如有需要可自行修改注释切换
Types: deb
URIs: http://security.ubuntu.com/ubuntu/
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
TSINGHUA
    echo '[+] 清华源配置完成'
else
    echo '[+] 清华源已配置'
fi

# 检查编译工具是否已安装
if command -v cmake >/dev/null 2>&1 && command -v gcc >/dev/null 2>&1; then
    echo '[+] 编译工具已安装，跳过'
else
    echo '[*] apt-get update...'
    apt-get update -qq

    echo '[*] 安装编译工具链...'
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential gcc g++ make cmake ccache

    echo '[*] 安装网络与开发库...'
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        git wget openssh-server libssl-dev dkms \
        pciutils curl libcurl4-openssl-dev

    echo '[+] 系统依赖安装完成'
fi
""",
        user="root",
        pwd=password,
    )

    # ── [4/5] CUDA Toolkit 12.9.1 ──
    print("\n[4/5] 安装 CUDA Toolkit 12.9.1...")
    out, _ = run_wsl(
        "test -d /usr/local/cuda-12.9 && echo YES || echo NO",
        user=username,
        capture=True,
    )
    if "YES" in out:
        print("[+] CUDA 已安装，跳过。")
    else:
        if not check_net(CUDA_URL):
            print("[!] 无法连接 NVIDIA 下载服务器，请检查网络。")
            sys.exit(1)

        print("[*] 下载 CUDA 安装包 (约 4GB，需要一些时间)...")
        run_wsl_sudo(
            f"""
cd {home}
wget -nc {CUDA_URL}
chmod +x {CUDA_RUN}
sudo ./{CUDA_RUN} --silent --toolkit --override --nox11
rm -f {CUDA_RUN}
""",
            username=username,
            password=password,
            timeout=1800,
        )
        print("[+] CUDA Toolkit 安装完成。")

    # ── [5/5] CUDA 环境变量 ──
    print("\n[5/5] 配置 CUDA 环境变量...")
    run_wsl(
        """
grep -q 'cuda-12.9/bin' ~/.bashrc 2>/dev/null
if [ $? -ne 0 ]; then
    cat >> ~/.bashrc << 'CUDAEOF'
export PATH=/usr/local/cuda-12.9/bin${PATH:+:${PATH}}
export LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}
CUDAEOF
    echo '[+] CUDA 环境变量已写入 .bashrc'
else
    echo '[+] CUDA 环境变量已存在'
fi
""",
        user=username,
    )


# ═══════════════════════════════════════════════════════════════
# 阶段 3: llama.cpp 编译与服务启动
# ═══════════════════════════════════════════════════════════════

def phase_3(username, start_server=True):
    print("\n" + "=" * 60)
    print("  阶段 3: llama.cpp 编译与服务启动")
    print("=" * 60)

    home = f"/home/{username}"
    model_info = _model_paths(username)
    preset = model_info['preset']
    model_dir = model_info['model_dir']
    llm_path = model_info['llm_path']
    mm_path = model_info['mm_path']
    llm_file = model_info['llm_file']
    mm_file = model_info['mm_file']
    print(f"[*] 模型预设: {preset['display_name']}")
    emit_event('model', 'preset', 'running', f"模型预设: {preset['display_name']}", preset=model_info['key'])

    # 重启 WSL 确保 wsl.conf 生效
    print("\n[*] 重启 WSL 以应用环境隔离配置...")
    run_win("wsl --shutdown")
    time.sleep(3)

    # ── [1/4] 克隆仓库 + 切换分支 ──
    print(f"\n[1/4] 克隆 {REPO_DIR} 仓库...")
    clone_success = False
    repo_path = f"{home}/{REPO_DIR}"

    # 先静默检查目录是否已存在
    out, _ = run_wsl(
        f"""
if [ -d {shlex.quote(repo_path)}/.git ]; then
    echo GIT_REPO
elif [ -e {shlex.quote(repo_path)} ]; then
    echo NON_GIT
else
    echo MISS
fi
""",
        user=username,
        capture=True,
    )
    if "GIT_REPO" in out:
        clone_success = True
        print("[+] 仓库已存在，跳过克隆，准备更新目标分支。")
    elif "NON_GIT" in out:
        print(f"[!] {repo_path} 已存在但不是 git 仓库，将删除后重新克隆。")
        run_wsl(f"rm -rf {shlex.quote(repo_path)}", user=username)

    # 克隆 (带代理 + 输出直接流到控制台 + 重试)
    for attempt in range(1, 4):
        if clone_success:
            break
        print(f"[*] git clone (第 {attempt}/3 次)...")
        print("    (下载中，git 进度会直接显示在下方...)")
        # run_wsl 不设 stdout=PIPE，git 输出直接流到终端，无缓冲问题
        rc = run_wsl(
            f"""# 配置代理 (通过宿主机 Clash 等)
HOST_IP=$(ip route show default 2>/dev/null | awk '{{print $3}}')
if [ -z "$HOST_IP" ]; then
    HOST_IP=$(cat /etc/resolv.conf 2>/dev/null | grep nameserver | awk '{{print $2}}')
fi
if [ -n "$HOST_IP" ]; then
    export http_proxy="http://$HOST_IP:{PROXY_PORT}"
    export https_proxy="http://$HOST_IP:{PROXY_PORT}"
fi
# 低速检测: 速度 < 1KB/s 持续 30 秒就中断 (快速触发重试)
export GIT_HTTP_LOW_SPEED_LIMIT=1000
export GIT_HTTP_LOW_SPEED_TIME=30
cd {shlex.quote(home)} && git clone --progress {shlex.quote(REPO_URL)}""",
            user=username,
            timeout=1200,
        )
        if rc == 0:
            clone_success = True
            break
        run_wsl(f"rm -rf {shlex.quote(repo_path)}", user=username)
        print(f"  [!] 克隆失败 (第 {attempt}/3 次)，重试中...")
        time.sleep(3)

    if not clone_success:
        print("[!] git clone 3 次均失败，请检查网络或代理设置。")
        sys.exit(1)

    # 切换到 turboquant-kv-cache 分支
    rc = run_wsl(
        f"""
cd {shlex.quote(repo_path)}
git fetch origin feature/turboquant-kv-cache
CURRENT=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT" != "feature/turboquant-kv-cache" ]; then
    git checkout -B feature/turboquant-kv-cache origin/feature/turboquant-kv-cache
    echo '[+] 已切换到 feature/turboquant-kv-cache 分支'
else
    echo '[+] 已在 feature/turboquant-kv-cache 分支'
fi
git pull --ff-only origin feature/turboquant-kv-cache
""",
        user=username,
    )
    if rc != 0:
        print(f"[!] 更新/切换 feature/turboquant-kv-cache 分支失败 (rc={rc})。")
        sys.exit(1)

    # ── [2/4] CUDA 编译 ──
    print("\n[2/4] 编译 llama.cpp (CUDA 加速，需要几分钟)...")
    if _verify_llama_build(username, repo_path):
        print("[+] 已存在可用的 llama-server，跳过编译。")
    else:
        build_script = f"""set -e
source ~/.bashrc
cd {shlex.quote(repo_path)}
echo '[*] 执行 cmake 配置...'
export CUDACXX=/usr/local/cuda-12.9/bin/nvcc
cmake -B build -DGGML_CUDA=ON -DGGML_CUDA_FLA=ON \\
    -DGGML_CUDA_FA_ALL_QUANTS=ON -DLLAMA_OPENSSL=ON \\
    -DCMAKE_BUILD_TYPE=Release
echo '[*] cmake 配置完成，开始编译 (使用 $(nproc) 核中的 $(($(nproc)-2)) 个)...'
cmake --build build --config Release -j $(($(nproc)-2))
"""
        rc = run_wsl(build_script, user=username, timeout=1800)
        if rc != 0:
            print(f"[!] 编译失败 (rc={rc})，请检查错误信息。")
            sys.exit(1)
        if not _verify_llama_build(username, repo_path, log_on_fail=True):
            print("[!] 编译完成但验证未通过，已终止部署。")
            sys.exit(1)

    # ── [3/4] 检查并下载模型 ──
    print("\n[3/4] 检查模型文件...")
    out, _ = run_wsl(
        f"""
mkdir -p {shlex.quote(model_dir)}
# 校验 GGUF 文件: 魔数 + header 中的 n_tensors 字段
# GGUF v3 header: magic(4) + version(4) + n_tensors(4) + n_kv_head(8)
# 如果文件被截断，读取 header 字段会失败
validate_gguf() {{
    local file="$1"
    local size=$(stat -c%s "$file" 2>/dev/null)
    if [ -z "$size" ]; then
        echo "MISS"
        return
    fi
    # 文件太小 (GGUF header 至少 32 字节)
    if [ "$size" -lt 32 ]; then
        echo "CORRUPT"
        return
    fi
    # 检查魔数
    local magic=$(head -c 4 "$file" 2>/dev/null)
    if [ "$magic" != "GGUF" ]; then
        echo "CORRUPT"
        return
    fi
    # 用 python 读取 n_tensors，如果文件截断会报错
    python3 -c "
import struct, sys
try:
    with open(sys.argv[1], 'rb') as f:
        f.seek(12)
        n_tensors = struct.unpack('<I', f.read(4))[0]
        if n_tensors == 0:
            sys.exit(1)
        sys.exit(0)
except Exception:
    sys.exit(1)
" "$file" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "OK"
    else
        echo "CORRUPT"
    fi
}}

result=$(validate_gguf {shlex.quote(llm_path)})
echo "MODEL_$result"
result=$(validate_gguf {shlex.quote(mm_path)})
echo "MMPROJ_$result"
""",
        user=username,
        capture=True,
    )

    model_ok = "MODEL_OK" in out
    mmproj_ok = "MMPROJ_OK" in out
    model_corrupt = "MODEL_CORRUPT" in out
    mmproj_corrupt = "MMPROJ_CORRUPT" in out

    if model_ok and mmproj_ok:
        print(f"[+] 模型文件已存在且完整 ({llm_file}, {mm_file})，跳过下载。")
    else:
        # 清除损坏的文件
        if model_corrupt:
            print(f"[!] {llm_file} 文件损坏，将删除重新下载。")
            run_wsl(f"rm -f {shlex.quote(llm_path)}", user=username)
        if mmproj_corrupt:
            print(f"[!] {mm_file} 文件损坏，将删除重新下载。")
            run_wsl(f"rm -f {shlex.quote(mm_path)}", user=username)

        if not model_ok or model_corrupt:
            ok = _download_model_artifact(
                username, model_dir, "大语言模型", llm_file, preset['artifacts']['llm']['sources']
            )
            if not ok:
                print(f"[!] {llm_file} 所有下载源均失败。")
                sys.exit(1)
        if not mmproj_ok or mmproj_corrupt:
            ok = _download_model_artifact(
                username, model_dir, "多模态投影器", mm_file, preset['artifacts']['mm']['sources']
            )
            if not ok:
                print(f"[!] {mm_file} 所有下载源均失败。")
                sys.exit(1)
        print("[+] 模型下载完成。")
        run_wsl(f"ls -lh {shlex.quote(model_dir)}/*.gguf", user=username)

    # ── [4/4] 启动 llama-server ──
    print("\n[4/4] 启动 llama-server...")
    if not start_server:
        print("[+] GUI 模式已跳过自动启动服务，后续由启动器负责启动/停止。")
        emit_event('service', 'start', 'skipped', '已跳过自动启动服务')
        return

    server_script = (
        "#!/bin/bash\n"
        "source ~/.bashrc\n"
        f"exec {home}/{REPO_DIR}/build/bin/llama-server \\\n"
        f"  -m {llm_path} \\\n"
        f"  --mmproj {mm_path} \\\n"
        f"  --image-min-tokens 1024 \\\n"
        f"  --host 0.0.0.0 --port {SERVER_PORT} \\\n"
        f"  --batch-size 4096 \\\n"
        f'  --alias "model-turbo" \\\n'
        f"  --jinja -ngl 99 -c 262144 -fa on \\\n"
        f"  --cache-type-k turbo3 --cache-type-v turbo3 \\\n"
        f"  -np 3 --metrics \\\n"
        f'  --api-key "{API_KEY}" \\\n'
        f"  --verbose\n"
    )

    proc = subprocess.Popen(
        f"wsl -d {DISTRO} -u {username} -- bash -s",
        shell=True,
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    proc.stdin.write(server_script.encode("utf-8"))
    proc.stdin.flush()
    proc.stdin.close()

    # 等待服务启动
    time.sleep(3)

    # 检查进程是否还在运行 (立即退出说明启动失败)
    poll = proc.poll()
    if poll is not None:
        print(f"\n[!] 服务进程意外退出 (code={poll})，请检查 GPU 驱动和模型文件。")
        print("[!] 阶段 3 未完成，下次运行将重新尝试。")
        sys.exit(1)
    else:
        print(
            f"\n{'=' * 60}\n"
            f"  ✓ 部署完成!\n"
            f"  API 地址: http://127.0.0.1:{SERVER_PORT}\n"
            f"  API Key:  {API_KEY}\n"
            f"  兼容 OpenAI API 格式\n"
            f"{'=' * 60}"
        )


def write_deploy_result(username):
    home = f"/home/{username}"
    model_info = _model_paths(username)
    preset = model_info['preset']
    result = {
        'distro': DISTRO,
        'username': username,
        'repo_dir': f"{home}/{REPO_DIR}",
        'exec_path': f"{home}/{REPO_DIR}/build/bin/llama-server",
        'model_preset': model_info['key'],
        'model_dir': model_info['model_dir'],
        'model_search_path': [
            f"{home}/model",
            f"{home}/models",
            f"{home}/gguf_models",
            f"{home}/{REPO_DIR}",
            model_info['model_dir'],
        ],
        'llm_model_name': preset['llm_name'],
        'llm_model_path': model_info['llm_path'],
        'mm_model_name': preset['mm_name'],
        'mm_model_path': model_info['mm_path'],
        'host': '0.0.0.0',
        'port': SERVER_PORT,
        'api_key': API_KEY,
        'cache_type_k': 'turbo3',
        'cache_type_v': 'turbo3',
        'batch_size': 4096,
        'parallel': 3,
        'ctx_length_k': 256,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(_ENV_RESULT_FILE)), exist_ok=True)
        with open(_ENV_RESULT_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[+] 部署结果已写入: {_ENV_RESULT_FILE}")
    except Exception as e:
        print(f"[!] 部署结果写入失败: {e}")
    emit_event('complete', 'result', 'success', '部署结果已生成', **result)
    return result


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main():
    apply_args(parse_args())
    print("=" * 60)
    print("  WSL2 本地大模型自动化部署工具")
    print("  Ubuntu 24.04 | CUDA 12.9.1 | llama.cpp-turboquant")
    print("=" * 60)

    # 管理员权限检查
    if not is_admin():
        print("\n[!] 请以管理员身份运行此程序!")
        print("    右键 -> 以管理员身份运行")
        emit_event('preflight', 'admin', 'failed', '请以管理员身份运行此程序')
        sys.exit(1)

    state = load_state()

    # deploy_state.json 只做记录，不作为跳过依据；真实状态必须每次由命令探测。
    emit_event('phase1', 'start', 'running', '开始检查 Windows 与 WSL2')
    phase_1()
    state["phase1"] = True
    save_state(state)
    print("\n[+] 阶段 1 完成!")
    emit_event('phase1', 'finish', 'success', 'Windows 与 WSL2 检查完成')

    emit_event('user', 'resolve', 'running', '正在确定 WSL 用户')
    username, password, is_new = resolve_user()
    state["username"] = username
    save_state(state)
    emit_event('user', 'resolve', 'success', f'已确定 WSL 用户: {username}', username=username)

    emit_event('phase2', 'start', 'running', '开始配置 Ubuntu 环境')
    phase_2(username, password, is_new)
    state["phase2"] = True
    save_state(state)
    print("\n[+] 阶段 2 完成!")
    emit_event('phase2', 'finish', 'success', 'Ubuntu 环境配置完成')

    emit_event('phase3', 'start', 'running', '开始部署 llama.cpp 与模型')
    phase_3(username, start_server=not _ENV_NO_START_SERVER)
    state["phase3"] = True
    save_state(state)
    print("\n[+] 阶段 3 完成!")
    emit_event('phase3', 'finish', 'success', 'llama.cpp 与模型部署完成')

    write_deploy_result(username)

    if not _ENV_NON_INTERACTIVE:
        print("\n按任意键退出...")
        os.system("pause >nul")


if __name__ == "__main__":
    main()
