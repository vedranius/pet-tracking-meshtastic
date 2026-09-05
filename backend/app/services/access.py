from sqlmodel import select

from ..models import Tracker, TrackerCaretaker


def accessible_tracker_ids(session, user_id: int) -> set[int]:
    """Trackers this user can read: their own, plus any they're an added
    caretaker on."""
    owned = session.exec(select(Tracker.id).where(Tracker.owner_id == user_id)).all()
    cared = session.exec(select(TrackerCaretaker.tracker_id).where(TrackerCaretaker.user_id == user_id)).all()
    return set(owned) | set(cared)


def tracker_recipient_ids(session, tracker: Tracker) -> set[int]:
    """Who should receive live updates (WebSocket/Telegram-adjacent events)
    for this tracker: its owner plus every caretaker added to it."""
    caretakers = session.exec(
        select(TrackerCaretaker.user_id).where(TrackerCaretaker.tracker_id == tracker.id)
    ).all()
    return {tracker.owner_id, *caretakers}
