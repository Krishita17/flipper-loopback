"""Load and validate fixture YAML files from ``fixtures/<subsystem>/*.yaml``."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from flci.errors import FlciError
from flci.schema import Fixture

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "fixtures"


class FixtureError(FlciError):
    pass


def load_fixture(path: Path) -> Fixture:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise FixtureError(f"{path}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise FixtureError(f"{path}: expected a mapping at top level")
    try:
        fx = Fixture.model_validate({**data, "source": path})
    except ValidationError as e:
        raise FixtureError(f"{path}: {e}") from e
    if fx.expected.subsystem != fx.subsystem:
        raise FixtureError(
            f"{path}: subsystem {fx.subsystem!r} != expected.subsystem {fx.expected.subsystem!r}"
        )
    if fx.stimulus_path is not None:
        resolved = (path.parent / fx.stimulus_path).resolve()
        if not resolved.is_file():
            raise FixtureError(f"{path}: stimulus_path {fx.stimulus_path} does not exist")
        fx = fx.model_copy(update={"stimulus_path": resolved})
    return fx


def load_fixtures(
    subsystem: str, root: Path = DEFAULT_ROOT, tags: set[str] | None = None
) -> list[Fixture]:
    files = sorted((root / subsystem).glob("*.yaml"))
    fixtures = [load_fixture(f) for f in files]
    ids = [f.id for f in fixtures]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise FixtureError(f"duplicate fixture ids in {root / subsystem}: {sorted(dupes)}")
    if tags:
        fixtures = [f for f in fixtures if tags & set(f.tags)]
    return fixtures
