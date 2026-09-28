import pytest

from test_utils import DEFAULT_CONFIG, wayland_client, wait_for_client_map, ScrollInstance


DIRECTIONS = [
    ("left-or-to-workspace-prev", -1),
    ("up-or-to-workspace-prev", -1),
    ("right-or-to-workspace-next", 1),
    ("down-or-to-workspace-next", 1),
]


def declare_slots(inst: ScrollInstance, names: list[str], extra: str = "") -> None:
    inst.reload_config(DEFAULT_CONFIG + "".join(
        f'workspace "{name}" output HEADLESS-1\n' for name in names
    ) + extra)


def move(inst: ScrollInstance, command: str) -> None:
    result = inst.cmd(command)
    assert result and all(item["success"] for item in result), result
    inst.wait_for_idle()


@pytest.mark.parametrize("command,step", DIRECTIONS)
@pytest.mark.parametrize("names", [
    ["2", "9", "23", "105"],
    ["0: inbox", "12: work", "57: review", "300: archive"],
    ["inbox", "work bench", "review", "archive"],
])
def test_fallthrough_reaches_empty_declared_slot(
    fresh_compositor: ScrollInstance, names: list[str], command: str, step: int,
) -> None:
    inst = fresh_compositor
    # Numeric order must not depend on declaration order. Named slots use it.
    declared = list(reversed(names)) if names[0][0].isdigit() else names
    declare_slots(inst, declared)
    source = 0 if step > 0 else len(names) - 1
    distant = len(names) - 1 - source
    move(inst, f'workspace "{names[distant]}"')
    with wayland_client(inst, "Distant anchor"):
        wait_for_client_map(inst, "Distant anchor")
        move(inst, f'workspace "{names[source]}"')
        with wayland_client(inst, "Moving window"):
            wait_for_client_map(inst, "Moving window")
            target = names[source + step]
            assert target not in [ws["name"] for ws in inst.ipc.get_workspaces()]
            move(inst, f"move {command}")
            tree = inst.get_tree()
            assert workspace_of(tree, "Moving window") == target
            assert workspace_of(tree, "Distant anchor") == names[distant]
            # Traversal creates only the selected slot, not every empty workspace.
            other_empty = names[source + 2 * step]
            assert other_empty not in [ws["name"] for ws in inst.ipc.get_workspaces()]


@pytest.mark.parametrize("command,step", DIRECTIONS)
def test_fallthrough_wraps_declared_slots(
    fresh_compositor: ScrollInstance, command: str, step: int,
) -> None:
    inst = fresh_compositor
    names = ["4", "16", "81"]
    declare_slots(inst, names)
    source = -1 if step > 0 else 0
    target = 0 if step > 0 else -1
    move(inst, f"workspace {names[source]}")
    with wayland_client(inst, "Wrapping window"):
        wait_for_client_map(inst, "Wrapping window")
        move(inst, f"move {command}")
        assert workspace_of(inst.get_tree(), "Wrapping window") == names[target]


@pytest.mark.parametrize("command,step", DIRECTIONS)
@pytest.mark.parametrize("preferred_available", [False, True])
def test_fallthrough_respects_output_priorities(
    fresh_compositor: ScrollInstance, command: str, step: int,
    preferred_available: bool,
) -> None:
    inst = fresh_compositor
    if preferred_available:
        move(inst, "create_output")
    # The middle slot belongs elsewhere only while its preferred output exists.
    declare_slots(inst, ["8", "72"],
        "workspace 34 output HEADLESS-2 HEADLESS-1\n")
    source, other = ("8", "72") if step > 0 else ("72", "8")
    move(inst, f"workspace {source}")
    with wayland_client(inst, "Output-bound window"):
        wait_for_client_map(inst, "Output-bound window")
        move(inst, f"move {command}")
        target = other if preferred_available else "34"
        assert workspace_of(inst.get_tree(), "Output-bound window") == target
        ws = next(ws for ws in inst.ipc.get_workspaces() if ws["name"] == target)
        assert ws["output"] == "HEADLESS-1"


@pytest.mark.parametrize("command,step", DIRECTIONS)
def test_single_declared_slot_does_not_create_or_move_elsewhere(
    fresh_compositor: ScrollInstance, command: str, step: int,
) -> None:
    inst = fresh_compositor
    declare_slots(inst, ["19"], "workspace_auto_back_and_forth yes\n")
    move(inst, "workspace 19")
    with wayland_client(inst, "Only window"):
        wait_for_client_map(inst, "Only window")
        before = [ws["name"] for ws in inst.ipc.get_workspaces()]
        move(inst, f"move {command}")
        assert workspace_of(inst.get_tree(), "Only window") == "19"
        assert [ws["name"] for ws in inst.ipc.get_workspaces()] == before


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
    declare_slots(inst, ["1", "2", "3"])
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
    declare_slots(inst, ["1", "2", "3"])
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
