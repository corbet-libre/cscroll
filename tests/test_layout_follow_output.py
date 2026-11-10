from contextlib import ExitStack

import pytest

from test_utils import run_compositor, wayland_client, wait_for_client_map


@pytest.mark.parametrize("primary,pivot,output_count", [
    ("HEADLESS-1", "HEADLESS-2", 3),
    ("HEADLESS-1", "missing-hp", 2),
    ("missing-dell", "HEADLESS-1", 2),
    ("missing-dell", "missing-hp", 2),
])
def test_default_workspaces_respect_output_priorities(
        scroll_compositor_binary, tmp_path, monkeypatch, primary, pivot, output_count):
    monkeypatch.setenv("WLR_HEADLESS_OUTPUTS", str(output_count))
    config = "\n".join([
        "xwayland disable",
        "animations enabled no",
        "default_orientation horizontal",
        "layout_follow_output yes",
        f"output {pivot} layout_type vertical",
        *[f"bindsym Mod4+{n} workspace number {n}" for n in range(8)],
        *[f"workspace {n} output {primary}" for n in range(7)],
        f"workspace 7 output {pivot} {primary}",
    ])
    with run_compositor(scroll_compositor_binary, tmp_path, config) as compositor:
        compositor.wait_for_idle()
        workspaces = compositor.ipc.get_workspaces()
        assert len(workspaces) == output_count
        for ws in workspaces:
            if ws["num"] in range(7) and primary.startswith("HEADLESS-"):
                assert ws["output"] == primary
            if ws["num"] == 7:
                preferred = pivot if pivot.startswith("HEADLESS-") else primary
                if preferred.startswith("HEADLESS-"):
                    assert ws["output"] == preferred
        # With neither preferred display present, numbered slots are open.
        if primary == "missing-dell" and pivot == "missing-hp":
            assert {ws["num"] for ws in workspaces} == {0, 1}


def test_layout_follows_output_hotplug(scroll_compositor_binary, tmp_path):
    config = "\n".join([
        "xwayland disable",
        "animations enabled no",
        "default_orientation horizontal",
        "layout_follow_output yes",
        "output HEADLESS-3 layout_type vertical",
        "output HEADLESS-3 layout_default_width 1.0",
        "output HEADLESS-3 layout_default_height 0.5",
        *[f"workspace {n} output HEADLESS-2" for n in range(7)],
        "workspace 7 output HEADLESS-3 HEADLESS-2",
        "workspace 0",
    ])
    # Own compositor, exact socket, real clients. Never uses CLI socket discovery.
    with run_compositor(scroll_compositor_binary, tmp_path, config) as compositor:
        compositor.ipc.sock.settimeout(10)
        with ExitStack() as clients:
            views = []
            for n in range(8):
                compositor.cmd(f"workspace {n}")
                title = f"workspace-{n}"
                clients.enter_context(wayland_client(compositor, title))
                views.append(wait_for_client_map(compositor, title))
            clients.enter_context(wayland_client(compositor, "second-window"))
            views.append(wait_for_client_map(compositor, "second-window"))

            def verify(primary, secondary, secondary_layout):
                compositor.wait_for_idle()
                workspaces = {w["name"]: w for w in compositor.ipc.get_workspaces()}
                for n in range(8):
                    workspace = workspaces[str(n)]
                    expected = secondary_layout if n == 7 else "horizontal"
                    assert workspace["output"] == (secondary if n == 7 else primary)
                    assert workspace["layout"] == expected
                    ws = workspace["id"]
                    assert compositor.execute_lua(
                        f"return scroll.workspace_get_mode({ws}).mode"
                    ) == expected
                    # Existing tiled columns/rows must change too, not just metadata.
                    children = compositor.execute_lua(
                        f"return scroll.workspace_get_tiling({ws})"
                    )
                    tree_nodes = {}

                    def walk(node):
                        tree_nodes[node["id"]] = node
                        for child in node.get("nodes", []) + node.get("floating_nodes", []):
                            walk(child)

                    walk(compositor.get_tree())
                    for child in children:
                        assert tree_nodes[child]["layout"] == (
                            "horizontal" if expected == "vertical" else "vertical"
                        )
                assert all(compositor.execute_lua(
                    f"return scroll.view_get_container({view})"
                ) is not None for view in views)

            verify("HEADLESS-1", "HEADLESS-1", "horizontal")
            compositor.cmd("create_output")
            verify("HEADLESS-2", "HEADLESS-2", "horizontal")
            compositor.cmd("create_output")
            verify("HEADLESS-2", "HEADLESS-3", "vertical")

            for _ in range(3):
                compositor.cmd("output HEADLESS-3 disable")
                verify("HEADLESS-2", "HEADLESS-2", "horizontal")
                compositor.cmd("output HEADLESS-2 disable")
                verify("HEADLESS-1", "HEADLESS-1", "horizontal")
                compositor.cmd("output HEADLESS-3 enable")
                verify("HEADLESS-1", "HEADLESS-3", "vertical")
                compositor.cmd("output HEADLESS-2 enable")
                verify("HEADLESS-2", "HEADLESS-3", "vertical")

            # Removing the physical output uses the same evacuation path, but also
            # destroys the output object. Previously vertical windows must survive.
            compositor.cmd("output HEADLESS-3 unplug")
            verify("HEADLESS-2", "HEADLESS-2", "horizontal")
            compositor.cmd("output HEADLESS-2 disable")
            compositor.cmd("output HEADLESS-1 disable")
            compositor.cmd("output HEADLESS-1 enable")
            verify("HEADLESS-1", "HEADLESS-1", "horizontal")
            assert compositor.proc.poll() is None


@pytest.mark.parametrize("follow", ["yes", "no"])
def test_manual_move_layout_is_opt_in(scroll_compositor_binary, tmp_path, follow):
    config = f"""xwayland disable
animations enabled no
default_orientation horizontal
layout_follow_output {follow}
output HEADLESS-2 layout_type vertical
workspace 0
"""
    with run_compositor(scroll_compositor_binary, tmp_path, config) as compositor:
        compositor.ipc.sock.settimeout(10)
        with wayland_client(compositor, "moving-window"):
            view = wait_for_client_map(compositor, "moving-window")
            compositor.cmd("create_output")
            compositor.cmd("workspace 0; move workspace to output HEADLESS-2")
            compositor.wait_for_idle()
            ws = compositor.execute_lua("return scroll.focused_workspace()")
            expected = "vertical" if follow == "yes" else "horizontal"
            assert compositor.execute_lua(
                f"return scroll.workspace_get_layout_type({ws})"
            ) == expected
            assert compositor.execute_lua(
                f"return scroll.workspace_get_mode({ws}).mode"
            ) == expected
            compositor.cmd("move workspace to output HEADLESS-1")
            compositor.wait_for_idle()
            assert compositor.execute_lua(
                f"return scroll.workspace_get_layout_type({ws})"
            ) == "horizontal"
            assert compositor.execute_lua(f"return scroll.view_get_container({view})")


def _container_and_window(compositor, title):
    """The tiled window called `title` and the container that holds it, from the live tree."""
    found = []

    def walk(node, parent):
        if node.get("name") == title and node.get("pid") is not None:
            found.append((parent, node))
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            walk(child, node)

    walk(compositor.get_tree(), None)
    assert len(found) == 1, f"expected exactly one window titled {title!r}, found {len(found)}"
    return found[0]


def _fractions(compositor, title):
    parent, window = _container_and_window(compositor, title)
    return (
        (parent["width_fraction"], parent["height_fraction"]),
        (window["width_fraction"], window["height_fraction"]),
    )


def test_follow_output_transposes_sizes(scroll_compositor_binary, tmp_path):
    """A workspace that moves onto a portrait output reflows like one that lives there natively.

    layout_follow_output used to flip the axis and the containers' layout but leave every size
    fraction alone: a column made on a landscape output (0.5 wide, 1.0 high) stayed 0.5 by 1.0 as a
    row of the portrait output, where its own windows are 1.0 by 0.5 -- half the width of the
    screen and one window per screen height (the Elitebook's messengers on the pivoted HP).
    """
    config = """xwayland disable
animations enabled no
default_orientation horizontal
layout_follow_output yes
output HEADLESS-2 layout_type vertical
output HEADLESS-2 layout_default_width 1.0
output HEADLESS-2 layout_default_height 0.5
workspace 1 output HEADLESS-2
workspace 0
"""
    with run_compositor(scroll_compositor_binary, tmp_path, config) as compositor:
        compositor.ipc.sock.settimeout(10)
        compositor.cmd("create_output")
        compositor.wait_for_idle()
        with ExitStack() as clients:
            # Made on the landscape output: the horizontal defaults (0.5 by 1.0).
            compositor.cmd("workspace 0")
            clients.enter_context(wayland_client(compositor, "landscape-made"))
            wait_for_client_map(compositor, "landscape-made")
            made_on_landscape = _fractions(compositor, "landscape-made")
            assert made_on_landscape == ((0.5, 1.0), (0.5, 1.0))

            # Made natively on the portrait output: the vertical defaults (1.0 by 0.5).
            compositor.cmd("workspace 1")
            clients.enter_context(wayland_client(compositor, "portrait-made"))
            wait_for_client_map(compositor, "portrait-made")
            native = _fractions(compositor, "portrait-made")
            assert native == ((1.0, 0.5), (1.0, 0.5))

            # Workspace 0 moves onto the portrait output: its window must look like the native one.
            compositor.cmd("workspace 0; move workspace to output HEADLESS-2")
            compositor.wait_for_idle()
            assert _fractions(compositor, "landscape-made") == native

            # ...and back: the transposition is its own inverse, so nothing drifts.
            compositor.cmd("move workspace to output HEADLESS-1")
            compositor.wait_for_idle()
            assert _fractions(compositor, "landscape-made") == made_on_landscape
            assert compositor.proc.poll() is None


def test_same_axis_move_keeps_sizes(scroll_compositor_binary, tmp_path):
    """Moving between two outputs of the same axis changes no size."""
    config = """xwayland disable
animations enabled no
default_orientation horizontal
layout_follow_output yes
workspace 0
"""
    with run_compositor(scroll_compositor_binary, tmp_path, config) as compositor:
        compositor.ipc.sock.settimeout(10)
        compositor.cmd("create_output")
        compositor.wait_for_idle()
        with wayland_client(compositor, "stays-put"):
            wait_for_client_map(compositor, "stays-put")
            before = _fractions(compositor, "stays-put")
            compositor.cmd("workspace 0; move workspace to output HEADLESS-2")
            compositor.wait_for_idle()
            assert _fractions(compositor, "stays-put") == before
