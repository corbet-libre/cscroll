# SPDX-License-Identifier: Apache-2.0
import asyncio
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "ipc-compat" / "scroll-swayipc-compat"
LOADER = importlib.machinery.SourceFileLoader("scroll_swayipc_compat", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
compat = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(compat)


class LayoutRewriteTests(unittest.TestCase):
    def test_rewrites_nested_layouts_and_recomputes_frame_length(self):
        payload = (
            b'{"layout":"horizontal","nodes":'
            b'[{"layout" : "vertical"},{"layout":"none"}]}'
        )

        rewritten = compat.rewrite_layouts(payload)
        framed = compat.frame(4, rewritten)
        length, message_type = struct.unpack(
            "<II", framed[len(compat.MAGIC) : compat.HEADER_SIZE]
        )

        self.assertEqual(
            rewritten,
            b'{"layout":"splith","nodes":'
            b'[{"layout":"splitv"},{"layout":"none"}]}',
        )
        self.assertEqual(message_type, 4)
        self.assertEqual(length, len(rewritten))
        self.assertEqual(framed[compat.HEADER_SIZE :], rewritten)

    def test_workspace_data_is_unchanged_without_favourites(self):
        payload = json.dumps(
            [{"id": 77, "num": 1, "name": "1", "layout": "vertical"}]
        ).encode()

        rewritten = json.loads(compat.rewrite_response(compat.GET_WORKSPACES, payload))

        self.assertEqual(len(rewritten), 1)
        self.assertEqual(rewritten[0]["id"], 77)
        self.assertEqual(rewritten[0]["num"], 1)
        self.assertEqual(rewritten[0]["layout"], "splitv")

    def test_workspace_events_are_byte_identical_without_favourites(self):
        payload = b'{"change":"empty","current":{"id":91,"num":5}}'
        self.assertEqual(
            compat.rewrite_response(compat.EVENT_WORKSPACE, payload), payload
        )

    def test_favourites_are_rekeyed_and_synthesized(self):
        payload = json.dumps(
            [
                {
                    "id": 77,
                    "num": 1,
                    "name": "1",
                    "focused": True,
                    "visible": True,
                    "urgent": False,
                    "nodes": [{"id": 88}],
                    "floating_nodes": [{"id": 89}],
                    "representation": "H[]",
                }
            ]
        ).encode()

        rewritten = json.loads(
            compat.rewrite_response(compat.GET_WORKSPACES, payload, (1, 2, 5))
        )

        self.assertEqual([workspace["num"] for workspace in rewritten], [1, 2, 5])
        self.assertEqual([workspace["id"] for workspace in rewritten], [1, 2, 5])
        self.assertTrue(rewritten[0]["focused"])
        self.assertEqual(rewritten[1]["nodes"], [])
        self.assertEqual(rewritten[1]["floating_nodes"], [])
        self.assertIsNone(rewritten[1]["representation"])

    def test_empty_event_for_favourite_is_suppressed(self):
        payload = b'{"change":"empty","current":{"id":91,"num":5}}'
        self.assertIsNone(
            compat.rewrite_response(compat.EVENT_WORKSPACE, payload, (5,))
        )

    def test_other_workspace_events_are_rekeyed(self):
        payload = b'{"change":"focus","current":{"id":91,"num":5}}'
        rewritten = json.loads(
            compat.rewrite_response(compat.EVENT_WORKSPACE, payload, (1,))
        )
        self.assertEqual(rewritten["current"]["id"], 5)

    def test_favourite_arguments_are_positive_and_deduplicated_at_runtime(self):
        args = compat.parse_args(["--favorite", "2", "--favorite", "2"])
        self.assertEqual(args.favorite, [2, 2])
        with self.assertRaises(SystemExit):
            compat.parse_args(["--favorite", "0"])


class SocketSafetyTests(unittest.TestCase):
    def test_refuses_to_replace_a_regular_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "compat.sock"
            path.write_text("not a socket")

            with self.assertRaisesRegex(RuntimeError, "non-socket"):
                compat.remove_stale_socket(str(path))

            self.assertEqual(path.read_text(), "not a socket")

    def test_removes_a_refused_stale_socket(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "compat.sock")
            stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            stale.bind(path)
            stale.close()

            compat.remove_stale_socket(path)

            self.assertFalse(os.path.exists(path))

    def test_candidate_order_excludes_the_proxy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            listen = str(Path(temp_dir) / "compat.sock")
            discovered = str(Path(temp_dir) / "scroll-ipc.1000.42.sock")
            Path(discovered).touch()
            environment = {
                "XDG_RUNTIME_DIR": temp_dir,
                "SCROLL_REAL_SOCK": listen,
                "SCROLLSOCK": "/run/user/1000/scroll-primary.sock",
                "SWAYSOCK": "/run/user/1000/scroll-primary.sock",
            }

            with mock.patch.dict(os.environ, environment, clear=True):
                candidates = compat.upstream_candidates(
                    listen, ("/explicit/scroll.sock", listen)
                )

            self.assertEqual(
                candidates,
                [
                    "/explicit/scroll.sock",
                    "/run/user/1000/scroll-primary.sock",
                    discovered,
                ],
            )


class ProxyRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_upstream_responses_are_rewritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upstream_path = str(Path(temp_dir) / "upstream.sock")
            proxy_path = str(Path(temp_dir) / "proxy.sock")
            request_seen = asyncio.Future()

            async def upstream(reader, writer):
                message_type, payload = await compat.read_frame(reader)
                request_seen.set_result((message_type, payload))
                response = b'{"layout":"horizontal","id":81,"num":2}'
                writer.write(compat.frame(message_type, response))
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            upstream_server = await asyncio.start_unix_server(
                upstream, path=upstream_path
            )
            proxy_server = await asyncio.start_unix_server(
                lambda reader, writer: compat.handle(
                    reader, writer, proxy_path, (upstream_path,)
                ),
                path=proxy_path,
            )
            try:
                reader, writer = await asyncio.open_unix_connection(proxy_path)
                request = b'{"command":"workspace vertical"}'
                writer.write(compat.frame(0, request))
                await writer.drain()

                message_type, response = await asyncio.wait_for(
                    compat.read_frame(reader), timeout=1
                )
                seen_type, seen_payload = await asyncio.wait_for(
                    request_seen, timeout=1
                )

                self.assertEqual((seen_type, seen_payload), (0, request))
                self.assertEqual(message_type, 0)
                self.assertEqual(
                    response, b'{"layout":"splith","id":81,"num":2}'
                )
                writer.close()
                await writer.wait_closed()
            finally:
                proxy_server.close()
                upstream_server.close()
                await proxy_server.wait_closed()
                await upstream_server.wait_closed()


if __name__ == "__main__":
    unittest.main()
