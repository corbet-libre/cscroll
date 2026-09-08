# SPDX-License-Identifier: Apache-2.0
"""Exercise surface lifetimes across compositor transactions and animations."""

import argparse
import os
from pathlib import Path
import selectors
import socket
import struct
import subprocess
import tempfile
import time

from scrollipc import ScrollIPC


def line(process, expected):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(5):
            raise AssertionError(f"client timed out waiting for {expected}")
        actual = process.stdout.readline().strip()
        assert actual == expected, (actual, expected, process.poll())


def command(client, text):
    client.stdin.write(text + "\n")
    client.stdin.flush()
    line(client, "done")


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def check(binary, client_binary, scenario, phase):
    with tempfile.TemporaryDirectory(prefix="scroll-lifetime-") as directory:
        root = Path(directory)
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        config = root / "config"
        config.write_text(
            "xwayland disable\nworkspace 1\nanimations enabled yes\n"
            "animations layer_shell yes 1000\n"
            "animations fade_out yes 1000\n"
        )
        env = os.environ.copy()
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "SWAYSOCK", "I3SOCK", "SCROLLSOCK"):
            env.pop(name, None)
        env.update(
            XDG_RUNTIME_DIR=str(runtime),
            WLR_BACKENDS="headless",
            WLR_RENDERER="pixman",
            WLR_HEADLESS_OUTPUTS="2",
            ASAN_OPTIONS="detect_leaks=0:abort_on_error=1",
            LSAN_OPTIONS="detect_leaks=0",
        )
        compositor = client = ipc = None
        log_path = root / "compositor.log"
        client_log_path = root / "client.log"
        with log_path.open("w") as log, client_log_path.open("w") as client_log:
            try:
                existing = set(runtime.glob("scroll-ipc.*.sock"))
                compositor = subprocess.Popen(
                    [binary, "-c", str(config), "-d", "-D", "txn-wait",
                     "-D", "txn-timeout=500"],
                    env=env, stdout=log, stderr=subprocess.STDOUT,
                )
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    assert compositor.poll() is None, "compositor exited at startup"
                    sockets = set(runtime.glob("scroll-ipc.*.sock")) - existing
                    if len(sockets) == 1:
                        ipc = ScrollIPC(str(sockets.pop()))
                        ipc.sock.settimeout(5)
                        pid, uid, _ = struct.unpack(
                            "3i", ipc.sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                        )
                        assert (pid, uid) == (compositor.pid, os.getuid())
                        break
                    time.sleep(0.02)
                assert ipc is not None, "no verified test compositor socket"
                assert "Error on line" not in log_path.read_text(), "invalid test configuration"
                response = ipc.lua_eval('return os.getenv("WAYLAND_DISPLAY")')
                wayland = response["results"][0]
                assert (runtime / wayland).is_socket()
                env["WAYLAND_DISPLAY"] = wayland
                time.sleep(0.7)
                client = subprocess.Popen(
                    [client_binary], env=env, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=client_log, text=True, bufsize=1,
                )
                line(client, "ready")
                time.sleep(0.7)
                if scenario == "view":
                    command(client, "view")
                    time.sleep(0.7)
                    for _ in range(3):
                        command(client, "unmap")
                        if phase == "animation":
                            time.sleep(0.6)
                        command(client, "remap")
                    command(client, "destroy-view")
                elif scenario == "layer":
                    command(client, "resize")
                    if phase == "animation":
                        time.sleep(0.6)
                    command(client, "destroy-layer")
                else:
                    command(client, "popup")
                    command(client, "reposition")
                    if phase == "animation":
                        time.sleep(0.6)
                    command(client, "destroy-popup" if scenario == "popup" else "destroy-layer")
                    if scenario == "parent":
                        command(client, "destroy-popup")
                time.sleep(1.5)
                assert compositor.poll() is None, "compositor crashed after destruction"
                assert ipc.command("nop lifetime-survived")[0]["success"]
                if scenario == "popup":
                    # Reuse the same XDG client after its surface list was unlinked.
                    command(client, "popup")
                    command(client, "destroy-popup")
                    time.sleep(0.7)
                    assert compositor.poll() is None, "compositor crashed creating another popup"
                client.stdin.write("quit\n")
                client.stdin.flush()
                assert client.wait(timeout=5) == 0
                time.sleep(0.7)
                assert compositor.poll() is None, "compositor crashed after client disconnect"
                try:
                    ipc.command("exit")
                except EOFError:
                    # Scroll can close IPC before sending the exit reply.
                    pass
                assert compositor.wait(timeout=5) == 0
                print(f"PASS: {scenario} ({phase})", flush=True)
            except Exception:
                print(log_path.read_text())
                print(client_log_path.read_text())
                raise
            finally:
                if ipc is not None:
                    ipc.close()
                stop(client)
                stop(compositor)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scroll", required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--scenario", choices=["layer", "popup", "parent", "view"])
    parser.add_argument("--phase", choices=["pending", "animation"])
    args = parser.parse_args()
    for scenario in ([args.scenario] if args.scenario else ["layer", "popup", "parent", "view"]):
        for phase in ([args.phase] if args.phase else ["pending", "animation"]):
            check(str(Path(args.scroll).resolve()), str(Path(args.client).resolve()), scenario, phase)
