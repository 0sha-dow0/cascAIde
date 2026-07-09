from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

from backend.adapters.mirror_record_store import MirroringRecordStore
from backend.domain.errors import Err, Ok, RecordStoreError
from backend.domain.models import Repo
from backend.ports.record_store import RecordStore

_DT = datetime(2026, 1, 1, tzinfo=UTC)


def _repo() -> Repo:
    return Repo(id="r1", url="https://example/r", owner="o", registered_at=_DT)


def _store(primary: MagicMock, mirror: MagicMock) -> MirroringRecordStore:
    return MirroringRecordStore(cast(RecordStore, primary), cast(RecordStore, mirror))


def test_successful_write_is_mirrored() -> None:
    repo = _repo()
    primary, mirror = MagicMock(), MagicMock()
    primary.create_repo.return_value = Ok(repo)

    result = _store(primary, mirror).create_repo(repo)

    assert result == Ok(repo)
    primary.create_repo.assert_called_once_with(repo)
    mirror.create_repo.assert_called_once_with(repo)


def test_failed_primary_write_is_not_mirrored() -> None:
    repo = _repo()
    primary, mirror = MagicMock(), MagicMock()
    primary.create_repo.return_value = Err(RecordStoreError("boom", {}))

    result = _store(primary, mirror).create_repo(repo)

    assert isinstance(result, Err)
    mirror.create_repo.assert_not_called()


def test_mirror_failure_is_swallowed() -> None:
    repo = _repo()
    primary, mirror = MagicMock(), MagicMock()
    primary.create_repo.return_value = Ok(repo)
    mirror.create_repo.side_effect = RuntimeError("db down")

    result = _store(primary, mirror).create_repo(repo)  # must not raise

    assert result == Ok(repo)


def test_reads_do_not_touch_the_mirror() -> None:
    primary, mirror = MagicMock(), MagicMock()
    primary.get_repo.return_value = Ok(_repo())

    _store(primary, mirror).get_repo("r1")

    primary.get_repo.assert_called_once_with("r1")
    mirror.get_repo.assert_not_called()
