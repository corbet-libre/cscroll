import time
from test_utils import ScrollCompositorFactory


def test_rapid_switch(scroll_compositor_factory: ScrollCompositorFactory) -> None:
    config = (
        "workspace 1\nanimations enabled yes\nanimations workspace_switch yes 1000\n"
    )
    with scroll_compositor_factory(config) as scroll_compositor:
        scroll_compositor.cmd("workspace 2")
        scroll_compositor.cmd("workspace 1")

        # Check that it IS animating immediately after the switch back
        is_animating: bool = scroll_compositor.execute_lua("return scroll.animating()")
        assert is_animating is True, "Expected animation to be running"

        # Poll for animation completion instead of a fixed sleep: the
        # compositor reports its animating state, so wait on that directly.
        deadline = time.monotonic() + 10
        while scroll_compositor.execute_lua("return scroll.animating()"):
            assert time.monotonic() < deadline, "animation did not finish"
            time.sleep(0.05)

        # Check that it finished
        is_animating = scroll_compositor.execute_lua("return scroll.animating()")
        assert is_animating is False, "Expected animation to have finished"
