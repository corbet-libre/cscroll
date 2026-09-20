# SPDX-License-Identifier: MIT AND Apache-2.0
from pathlib import Path

import pytest

from check_lifetime import check


@pytest.mark.parametrize("scenario", ["layer", "popup", "parent", "view"])
@pytest.mark.parametrize("phase", ["pending", "animation"])
def test_surface_lifetime(scroll_compositor_binary, scenario, phase):
    build = Path(scroll_compositor_binary).parent.parent
    check(scroll_compositor_binary, str(build / "tests/lifetime-client"), scenario, phase)
