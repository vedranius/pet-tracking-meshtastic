from fastapi import APIRouter, Depends
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import PetPhoto, Tracker, User

router = APIRouter(prefix="/api/community", tags=["community"])


@router.get("/pets")
def list_community_pets(_: User = Depends(require_login)):
    """A directory of every pet on the server (name, species, photos, owner)
    visible to any signed-in user — deliberately excludes live location,
    battery, or any tracking data, which stay owner/admin-only. This exists
    purely so a photo can help someone recognize a pet that's turned up
    somewhere, not to let users watch each other's trackers."""
    with get_session() as session:
        trackers = session.exec(select(Tracker)).all()
        owners = {u.id: u.username for u in session.exec(select(User)).all()}
        photos_by_tracker: dict[int, list[PetPhoto]] = {}
        for photo in session.exec(select(PetPhoto).order_by(PetPhoto.created_at)).all():
            photos_by_tracker.setdefault(photo.tracker_id, []).append(photo)

        return [
            {
                "id": t.id,
                "name": t.name,
                "species": t.species,
                "color": t.color,
                "owner_username": owners.get(t.owner_id, "?"),
                "photos": [{"id": p.id} for p in photos_by_tracker.get(t.id, [])],
            }
            for t in trackers
        ]
