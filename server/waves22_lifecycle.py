"""Wave 22 cleanup inside PRIMARY's existing private-data transaction."""
import json


def cleanup_db(db, sid, owner=None):
    """Remove an owner's private state and their unfinished coedit drafts.

    Caller holds store.LOCK and an active transaction. Session cleanup already
    deletes all session objects. An adopted Studio version remains under the
    creator's ordinary editorial lifecycle; it is not an unfinished draft.
    """
    if not db.in_transaction:
        raise ValueError('cleanup requires caller transaction')
    if owner is None:
        return
    kinds = ('w22claim', 'w22claimreceipt', 'w22model', 'w22modelreceipt',
             'w22modelshare', 'w22coeditreceipt', 'w22descriptionreceipt')
    marks = ','.join('?' for _ in kinds)
    db.execute(f'DELETE FROM objects WHERE session_id=? AND owner_id=? AND kind IN ({marks})',
               (sid, owner, *kinds))
    drafts = []
    for row in db.execute("SELECT id,data FROM objects WHERE session_id=? AND kind IN ('w22coedit','w22coeditgrant')", (sid,)).fetchall():
        value = json.loads(row['data'])
        if owner in (value.get('creatorId'), value.get('collaboratorId')):
            drafts.append(row['id'])
    for draft_id in set(drafts):
        db.execute("DELETE FROM objects WHERE session_id=? AND id=? AND kind IN ('w22coedit','w22coeditgrant')", (sid, draft_id))
    for row in db.execute("SELECT id,data FROM objects WHERE session_id=? AND kind='w22adoption'", (sid,)).fetchall():
        if json.loads(row['data']).get('draftId') in drafts:
            db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE session_id=? AND kind='w22adoption' AND id=?",
                       (json.dumps({'forgotten': True}), sid, row['id']))
