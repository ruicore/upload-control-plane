from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.models import DatasetTag, Project, Tag, TagCategory
from upload_control_plane.infrastructure.db.seed import build_dev_seed_result, seed_dev_data

from .support import (
    DatasetFakeObjectStorage,
    _auth_headers,
    _client,
    _create_ready_dataset,
    _db_session_factory_or_skip,
    _delete_upload_artifacts,
    _session_scope,
)


def test_tag_category_and_tag_crud_and_dataset_tag_update() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = "idem-dataset-tags"
    dataset_tag_ids: set[tuple[uuid.UUID, uuid.UUID]] = set()
    tag_ids: set[uuid.UUID] = set()
    category_ids: set[uuid.UUID] = set()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        category = client.post(
            f"/v1/projects/{seed.project_id}/tag-categories",
            headers=_auth_headers("req-tag-category-create"),
            json={"name": "sensor", "color": "#3366ff", "sort_order": 10},
        )
        assert category.status_code == 201
        category_id = category.json()["category_id"]
        category_ids.add(uuid.UUID(category_id))

        tag = client.post(
            f"/v1/projects/{seed.project_id}/tags",
            headers=_auth_headers("req-tag-create"),
            json={"name": "front-camera", "category_id": category_id, "color": "#ff6633"},
        )
        assert tag.status_code == 201
        tag_id = tag.json()["tag_id"]
        tag_uuid = uuid.UUID(tag_id)
        tag_ids.add(tag_uuid)
        dataset_tag_ids.add((uuid.UUID(created["dataset_id"]), tag_uuid))

        updated_dataset = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{created['dataset_id']}",
            headers=_auth_headers("req-dataset-tag-attach"),
            json={"tag_ids": [tag_id]},
        )
        assert updated_dataset.status_code == 200
        assert updated_dataset.json()["tag_ids"] == [tag_id]

        tags = client.get(
            f"/v1/projects/{seed.project_id}/tags",
            headers=_auth_headers("req-tag-list"),
        )
        assert tags.status_code == 200
        assert tag_id in {item["tag_id"] for item in tags.json()["tags"]}

        deleted = client.delete(
            f"/v1/projects/{seed.project_id}/tags/{tag_id}",
            headers=_auth_headers("req-tag-delete"),
        )
        assert deleted.status_code == 204
    finally:
        with _session_scope(session_factory) as session:
            _delete_tag_artifacts(
                session,
                dataset_tag_ids=dataset_tag_ids,
                tag_ids=tag_ids,
                category_ids=category_ids,
            )
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_dataset_update_replaces_tags_and_rejects_invalid_tag_ids() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-dataset-update-tag-replacement"
    foreign_project_id = uuid.uuid4()
    foreign_tag_id = uuid.uuid4()
    dataset_tag_ids: set[tuple[uuid.UUID, uuid.UUID]] = set()
    tag_ids = {foreign_tag_id}
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        tag = client.post(
            f"/v1/projects/{seed.project_id}/tags",
            headers=_auth_headers("req-dataset-update-tag-create"),
            json={"name": "dataset-update-tag"},
        )
        assert tag.status_code == 201
        tag_id = tag.json()["tag_id"]
        tag_uuid = uuid.UUID(tag_id)
        tag_ids.add(tag_uuid)
        dataset_tag_ids.add((dataset_id, tag_uuid))

        attached = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-update-tag-attach"),
            json={"tag_ids": [tag_id]},
        )
        assert attached.status_code == 200
        assert attached.json()["tag_ids"] == [tag_id]

        cleared = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-update-tag-clear"),
            json={"tag_ids": []},
        )
        assert cleared.status_code == 200
        assert cleared.json()["tag_ids"] == []

        duplicate = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-update-tag-duplicate"),
            json={"tag_ids": [tag_id, tag_id]},
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["error"]["code"] == "tag.duplicate_ids"

        missing = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-update-tag-missing"),
            json={"tag_ids": [str(uuid.uuid4())]},
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "tag.not_found"

        now = datetime.now(UTC)
        with _session_scope(session_factory) as session:
            session.add(
                Project(
                    id=foreign_project_id,
                    tenant_id=seed.tenant_id,
                    storage_policy_id=seed.storage_policy_id,
                    slug="dataset-update-foreign-tags",
                    name="Dataset update foreign tags",
                    description=None,
                    status="ACTIVE",
                    metadata_schema={},
                    metadata_={},
                    created_by=seed.api_key_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            session.add(
                Tag(
                    id=foreign_tag_id,
                    tenant_id=seed.tenant_id,
                    project_id=foreign_project_id,
                    category_id=None,
                    name="foreign-dataset-update-tag",
                    color=None,
                    created_at=now,
                    updated_at=now,
                )
            )

        foreign = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-update-tag-foreign"),
            json={"tag_ids": [str(foreign_tag_id)]},
        )
        assert foreign.status_code == 404
        assert foreign.json()["error"]["code"] == "tag.not_found"
    finally:
        with _session_scope(session_factory) as session:
            _delete_tag_artifacts(
                session,
                dataset_tag_ids=dataset_tag_ids,
                tag_ids=tag_ids,
                category_ids=set(),
            )
            session.execute(delete(Project).where(Project.id == foreign_project_id))
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_tag_cleanup_preserves_unrelated_rows() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    owned_category_id = uuid.uuid4()
    owned_tag_id = uuid.uuid4()
    unrelated_category_id = uuid.uuid4()
    unrelated_tag_id = uuid.uuid4()
    owned_dataset_tag_id = (seed.dataset_id, owned_tag_id)
    unrelated_dataset_tag_id = (seed.dataset_id, unrelated_tag_id)

    with session_factory() as session:
        seed_dev_data(session, get_settings())
        session.add_all(
            (
                TagCategory(
                    id=owned_category_id,
                    tenant_id=seed.tenant_id,
                    project_id=seed.project_id,
                    name=f"cleanup-owned-{suffix}",
                    color=None,
                    sort_order=0,
                    created_at=now,
                    updated_at=now,
                ),
                TagCategory(
                    id=unrelated_category_id,
                    tenant_id=seed.tenant_id,
                    project_id=seed.project_id,
                    name=f"cleanup-unrelated-{suffix}",
                    color=None,
                    sort_order=0,
                    created_at=now,
                    updated_at=now,
                ),
            )
        )
        session.flush()
        session.add_all(
            (
                Tag(
                    id=owned_tag_id,
                    tenant_id=seed.tenant_id,
                    project_id=seed.project_id,
                    category_id=owned_category_id,
                    name=f"cleanup-owned-{suffix}",
                    color=None,
                    created_at=now,
                    updated_at=now,
                ),
                Tag(
                    id=unrelated_tag_id,
                    tenant_id=seed.tenant_id,
                    project_id=seed.project_id,
                    category_id=unrelated_category_id,
                    name=f"cleanup-unrelated-{suffix}",
                    color=None,
                    created_at=now,
                    updated_at=now,
                ),
            )
        )
        session.flush()
        session.add_all(
            (
                DatasetTag(dataset_id=owned_dataset_tag_id[0], tag_id=owned_dataset_tag_id[1]),
                DatasetTag(
                    dataset_id=unrelated_dataset_tag_id[0],
                    tag_id=unrelated_dataset_tag_id[1],
                ),
            )
        )
        session.flush()

        _delete_tag_artifacts(
            session,
            dataset_tag_ids={owned_dataset_tag_id},
            tag_ids={owned_tag_id},
            category_ids={owned_category_id},
        )
        session.flush()

        assert session.get(DatasetTag, owned_dataset_tag_id) is None
        assert session.get(Tag, owned_tag_id) is None
        assert session.get(TagCategory, owned_category_id) is None
        assert session.get(DatasetTag, unrelated_dataset_tag_id) is not None
        assert session.get(Tag, unrelated_tag_id) is not None
        assert session.get(TagCategory, unrelated_category_id) is not None
        session.rollback()


def _delete_tag_artifacts(
    session: Session,
    *,
    dataset_tag_ids: set[tuple[uuid.UUID, uuid.UUID]],
    tag_ids: set[uuid.UUID],
    category_ids: set[uuid.UUID],
) -> None:
    for dataset_id, tag_id in dataset_tag_ids:
        session.execute(
            delete(DatasetTag).where(
                (DatasetTag.dataset_id == dataset_id) & (DatasetTag.tag_id == tag_id)
            )
        )
    if tag_ids:
        session.execute(delete(Tag).where(Tag.id.in_(tag_ids)))
    if category_ids:
        session.execute(delete(TagCategory).where(TagCategory.id.in_(category_ids)))
