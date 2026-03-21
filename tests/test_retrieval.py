"""
Integration test for the RAG retrieval engine.

Runs inside the Flask application context (no HTTP server needed).
Finds a user with at least one ready-ingested document and exercises
retrieve_chunks() against a real query.

Run from project root:
  cd backend && python ../test_retrieval.py
"""

import json
import sys
import os

# Make sure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))


def hdr(label):
    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


# ── Bootstrap Flask app ───────────────────────────────────────────────────────
hdr("Bootstrapping Flask app")
# Import create_app FIRST, before any app.db.* imports, to avoid the
# name-shadowing bug where importing app.db subpackage overwrites the
# SQLAlchemy `db` reference in app/__init__.py.
from app import create_app  # noqa: E402

app = create_app()

with app.app_context():
    # Model and service imports must happen inside the app context (or at least
    # after create_app()) so the app.db subpackage doesn't shadow the
    # extensions.db SQLAlchemy instance during app initialisation.
    from app.db.models.document import Document  # noqa: E402
    from app.db.models.user import User  # noqa: E402 (available for future use)
    from app.extensions import db  # noqa: E402
    from app.services.rag.retrieval import retrieve_chunks  # noqa: E402
    from app.services.wrapper.client import WrapperError  # noqa: E402
    # ── Find a user with a ready document ─────────────────────────────────────
    hdr("Finding a user with at least one ready-ingested document")

    doc = (
        Document.query
        .filter(
            Document.is_deleted.is_(False),
            Document.current_ingestion_id.isnot(None),
        )
        .first()
    )

    if doc is None:
        fail(
            "No ingested document found in the database. "
            "Run test_documents.py first to upload and ingest a PDF."
        )

    user_id = doc.user_id
    print(f"Using user_id : {user_id}")
    print(f"Document      : {doc.id!r}  title={doc.title!r}  source_type={doc.source_type!r}")

    # ── Call retrieve_chunks ───────────────────────────────────────────────────
    hdr("retrieve_chunks – basic query")
    query = "What is Python programming language?"
    print(f"Query: {query!r}")

    try:
        results = retrieve_chunks(query_text=query, user_id=user_id, top_k=5)
    except WrapperError as exc:
        fail(f"WrapperError during retrieval: {exc}")

    print(f"\nReturned {len(results)} result(s)")

    if not results:
        fail("No results returned. Expected at least one chunk to match.")

    # ── Validate payload structure ─────────────────────────────────────────────
    hdr("Validating payload structure")
    REQUIRED_KEYS = {"chunk_id", "document_id", "snippet", "score", "document_title", "source_type", "filename"}
    for i, r in enumerate(results):
        missing = REQUIRED_KEYS - r.keys()
        if missing:
            fail(f"Result #{i} missing keys: {missing}")

        if not isinstance(r["chunk_id"], int):
            fail(f"Result #{i}: chunk_id is not int: {type(r['chunk_id'])}")
        if not isinstance(r["document_id"], str):
            fail(f"Result #{i}: document_id is not str")
        if not isinstance(r["snippet"], str) or not r["snippet"].strip():
            fail(f"Result #{i}: snippet is empty or not str")
        if not isinstance(r["score"], float):
            fail(f"Result #{i}: score is not float: {type(r['score'])}")
        if not isinstance(r["document_title"], str):
            fail(f"Result #{i}: document_title is not str")
        if r["source_type"] not in ("upload", "text"):
            fail(f"Result #{i}: source_type invalid: {r['source_type']!r}")
        # filename is None for text docs, str for uploads
        if r["source_type"] == "upload" and r["filename"] is None:
            fail(f"Result #{i}: upload doc has filename=None")

        # Scores must be finite and sensible
        if not (-1.0 <= r["score"] <= 1.0):
            fail(f"Result #{i}: score {r['score']} out of [-1, 1] range")

    print("All result keys and types are valid.")
    print(json.dumps(results, indent=2))

    # ── Verify results are user-scoped ─────────────────────────────────────────
    hdr("User-scope isolation check")
    for r in results:
        if r["document_id"] != doc.user_id:
            # Verify ownership via DB
            from app.db.models.document import Document as Doc
            fetched = db.session.get(Doc, r["document_id"])
            if fetched is None:
                fail(f"Result references unknown document_id {r['document_id']!r}")
            if fetched.user_id != user_id:
                fail(
                    f"Result references document {r['document_id']!r} "
                    f"owned by a different user {fetched.user_id!r}"
                )
    print("All results correctly scoped to user_id:", user_id)

    # ── Empty query short-circuit ──────────────────────────────────────────────
    hdr("Empty query short-circuit")
    empty_results = retrieve_chunks(query_text="   ", user_id=user_id)
    if empty_results != []:
        fail(f"Empty query should return [] but got: {empty_results}")
    print("Empty query correctly returns [].")

    # ── Wrong user returns nothing ─────────────────────────────────────────────
    hdr("Wrong user_id returns 0 results (or well-isolated results)")
    import uuid
    fake_user = str(uuid.uuid4())
    fake_results = retrieve_chunks(query_text=query, user_id=fake_user, top_k=5)
    if fake_results:
        fail(
            f"Expected 0 results for unknown user but got {len(fake_results)}. "
            "Data isolation is broken!"
        )
    print(f"Correctly returned 0 results for unknown user_id {fake_user!r}.")

print("\n" + "=" * 60)
print("ALL RETRIEVAL TESTS PASSED")
print("=" * 60)
