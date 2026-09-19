from test_utils import wayland_client, wait_for_client_map, ScrollInstance


def workspace_of(tree: dict, title: str) -> str | None:
    found: dict = {}

    def walk(node: dict, ws: str | None) -> None:
        if node.get("type") == "workspace":
            ws = node.get("name")
        if node.get("type") == "con" and node.get("name") == title:
            found["ws"] = ws
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            walk(child, ws)

    walk(tree, None)
    return found.get("ws")


def test_move_up_or_to_workspace_prev_hops(scroll_compositor: ScrollInstance) -> None:
    inst = scroll_compositor
    with wayland_client(inst, "HopUp W1"):
        wait_for_client_map(inst, "HopUp W1")
        inst.cmd("workspace 2")
        with wayland_client(inst, "HopUp W2"):
            wait_for_client_map(inst, "HopUp W2")

            # W2 is alone on workspace 2: no intra-workspace move is
            # possible, so it must hop to the previous workspace.
            res = inst.cmd("move up-or-to-workspace-prev")
            assert res and res[0]["success"], f"Command failed: {res}"
            inst.wait_for_idle()

            tree = inst.get_tree()
            assert workspace_of(tree, "HopUp W2") == "1"
            assert workspace_of(tree, "HopUp W1") == "1"
            assert inst.proc.poll() is None, "Compositor crashed"


def test_move_down_or_to_workspace_next_hops(scroll_compositor: ScrollInstance) -> None:
    inst = scroll_compositor
    with wayland_client(inst, "HopDown W1"):
        wait_for_client_map(inst, "HopDown W1")
        inst.cmd("workspace 2")
        with wayland_client(inst, "HopDown W2"):
            wait_for_client_map(inst, "HopDown W2")
            inst.cmd("workspace 1")

            # W1 is alone on workspace 1: it must hop to workspace 2.
            res = inst.cmd("move down-or-to-workspace-next")
            assert res and res[0]["success"], f"Command failed: {res}"
            inst.wait_for_idle()

            tree = inst.get_tree()
            assert workspace_of(tree, "HopDown W1") == "2"
            assert workspace_of(tree, "HopDown W2") == "2"
            assert inst.proc.poll() is None, "Compositor crashed"


def test_move_left_or_to_workspace_prev_stays_when_possible(
    scroll_compositor: ScrollInstance,
) -> None:
    inst = scroll_compositor
    with wayland_client(inst, "Stay W1"):
        wait_for_client_map(inst, "Stay W1")
        inst.cmd("workspace 2")
        with wayland_client(inst, "Stay W2"):
            wait_for_client_map(inst, "Stay W2")
            with wayland_client(inst, "Stay W3"):
                wait_for_client_map(inst, "Stay W3")

                # Two windows share workspace 2, so a left move always
                # succeeds intra-workspace (swap, expel or reorder) and
                # must never hop.
                res = inst.cmd("move left-or-to-workspace-prev")
                assert res and res[0]["success"], f"Command failed: {res}"
                inst.wait_for_idle()

                tree = inst.get_tree()
                assert workspace_of(tree, "Stay W3") == "2"
                assert workspace_of(tree, "Stay W2") == "2"
                assert inst.proc.poll() is None, "Compositor crashed"


def test_move_right_or_to_workspace_next_stays_when_possible(
    scroll_compositor: ScrollInstance,
) -> None:
    inst = scroll_compositor
    with wayland_client(inst, "StayR W1"):
        wait_for_client_map(inst, "StayR W1")
        inst.cmd("workspace 2")
        with wayland_client(inst, "StayR W2"):
            wait_for_client_map(inst, "StayR W2")
            # Force a side-by-side pair so the focused window always has
            # a right-hand neighbour to move into.
            inst.cmd("splith")
            with wayland_client(inst, "StayR W3"):
                wait_for_client_map(inst, "StayR W3")
                inst.cmd("focus left")

                # W2 now moves right into W3's column: succeeds
                # intra-workspace and must never hop.
                res = inst.cmd("move right-or-to-workspace-next")
                assert res and res[0]["success"], f"Command failed: {res}"
                inst.wait_for_idle()

                tree = inst.get_tree()
                assert workspace_of(tree, "StayR W2") == "2"
                assert workspace_of(tree, "StayR W3") == "2"
                assert inst.proc.poll() is None, "Compositor crashed"
