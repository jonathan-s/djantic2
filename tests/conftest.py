import pytest
from packaging import version


@pytest.fixture(scope="session")
def pydantic_version() -> version.Version:
    import pydantic

    return version.parse(pydantic.VERSION)
