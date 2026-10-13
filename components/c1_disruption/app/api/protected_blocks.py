"""Protected blocks (sleep, meals, prayer, work shift). The engine never places a
task over them (PTVR = 0). A block may cross midnight, e.g. sleep 22:00–06:00."""
from fastapi import APIRouter, Depends, Response

from components.c1_disruption.app.api.deps import get_deps, require_user
from components.c1_disruption.app.api.errors import bad_request
from components.c1_disruption.app.api.models import NewProtectedBlock, ProtectedBlockBody
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.app.services.owned import load_owned

router = APIRouter(prefix="/protected-blocks")


def _check_start_end(start: str, end: str) -> None:
    if start == end:
        raise bad_request("'start' and 'end' must be different")


@router.get("")
def list_blocks(user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> list[dict]:
    return deps.store.list("protectedBlocks", {"userId": user_id})


@router.post("", status_code=201)
def create_block(body: NewProtectedBlock, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    _check_start_end(body.start, body.end)
    block = {"userId": user_id, "label": body.label, "start": body.start, "end": body.end}
    return deps.store.create("protectedBlocks", block)


@router.patch("/{block_id}")
def change_block(
    block_id: str, body: ProtectedBlockBody, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)
) -> dict:
    current = load_owned(deps.store, "protectedBlocks", block_id, user_id, "Protected block")
    patch = {
        "label": body.label if body.label is not None else current["label"],
        "start": body.start if body.start is not None else current["start"],
        "end": body.end if body.end is not None else current["end"],
    }
    _check_start_end(patch["start"], patch["end"])
    return deps.store.update("protectedBlocks", current["id"], patch)


@router.delete("/{block_id}", status_code=204)
def delete_block(block_id: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> Response:
    load_owned(deps.store, "protectedBlocks", block_id, user_id, "Protected block")
    deps.store.remove("protectedBlocks", block_id)
    return Response(status_code=204)
