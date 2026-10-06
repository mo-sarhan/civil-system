"""CSV import lifecycle: template, upload, mapping, validate, commit."""

from __future__ import annotations

import io
import time
from pathlib import Path

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.person import Person

CSV_HEADER = "national_id,full_name,gender,birth_date,birth_place,father_national_id,mother_national_id,notes"

NEW_ROWS = [
    # Two brand-new people (national ids encode birth date, century and gender).
    "29105045100011,جديد كامل عبد الرحمن,M,1991-05-04,الإسكندرية,,,اختبار",
    "29306055100022,جديدة ثانية عبد الرحمن,F,1993-06-05,الإسكندرية,,,اختبار",
    # One row that already exists in the sample (updates it).
    "24003151200113,محمد أحمد السيد,M,1940-03-15,القاهرة,,,محدث",
    # Invalid rows: unknown gender and an impossible national id.
    "99999999999999,رقم خاطئ,X,1990-01-01,القاهرة,,,خطأ",
]

#: The national id of sample person 1 (``محمد أحمد السيد``), used to prove that
#: a committed row updates the existing record instead of creating a duplicate.
EXISTING_NATIONAL_ID = "24003151200113"


def _upload(client, auth, csv_text: str, filename: str = "people.csv", role: str = "editor"):
    return client.post(
        "/api/v1/imports/upload",
        files={"file": (filename, io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
        headers=auth(role),
    )


def _wait_for_job(client, auth, job_id: int, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/v1/imports/jobs/{job_id}", headers=auth("editor")).json()["job"]
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.2)
    raise AssertionError(f"import job {job_id} did not finish in {timeout}s")


class TestMetadata:
    def test_fields_expose_labels_aliases_and_linking_modes(
        self, client, auth, sample_family
    ) -> None:
        body = client.get("/api/v1/imports/fields", headers=auth("editor")).json()
        keys = {field["key"] for field in body["fields"]}
        assert {"national_id", "full_name", "gender", "birth_date", "birth_place"} <= keys
        required = {field["key"] for field in body["fields"] if field["required"]}
        assert "full_name" in required
        assert all(field["label"] for field in body["fields"])
        assert {mode["key"] for mode in body["linking_modes"]} == {
            "by_national_id",
            "by_name",
            "none",
        }
        assert body["max_rows"] > 0 and body["chunk_size"] > 0

    def test_csv_template_is_downloadable(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/imports/template/csv", headers=auth("editor"))
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        lines = response.text.strip().splitlines()
        assert lines[0] == CSV_HEADER
        assert len(lines) == 3  # header plus two sample rows

    def test_viewers_cannot_import(self, client, auth, sample_family) -> None:
        assert client.get("/api/v1/imports/fields", headers=auth("viewer")).status_code == 403


class TestUpload:
    def test_upload_returns_a_preview(self, client, auth, sample_family) -> None:
        response = _upload(client, auth, CSV_HEADER + "\n" + "\n".join(NEW_ROWS))
        assert response.status_code == 201, response.text
        job = response.json()["job"]
        assert job["status"] == "pending"
        assert job["file_type"] == "csv"
        assert job["total_rows"] == 4
        assert job["progress"] == 0

    def test_upload_suggests_the_columns(self, client, auth, sample_family) -> None:
        body = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()
        suggested = body["preview"]["suggested_mapping"]
        assert suggested["full_name"] == 1
        assert suggested["national_id"] == 0
        assert suggested["gender"] == 2
        assert suggested["birth_date"] == 3
        # The mapping stays unconfirmed until the user posts it.
        assert body["job"]["column_mapping"] is None

    def test_mapping_can_be_saved_explicitly(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        response = client.post(
            f"/api/v1/imports/jobs/{job['id']}/mapping",
            json={
                "mapping": {"national_id": 0, "full_name": 1, "gender": 2, "birth_date": 3},
                "linking_mode": "by_national_id",
            },
            headers=auth("editor"),
        )
        assert response.status_code == 200, response.text
        saved = response.json()["job"]
        assert saved["column_mapping"]["full_name"] == 1
        assert saved["linking_mode"] == "by_national_id"

    def test_mapping_rejects_an_unknown_field(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        response = client.post(
            f"/api/v1/imports/jobs/{job['id']}/mapping",
            json={"mapping": {"full_name": 1, "nope": 4}, "linking_mode": "none"},
            headers=auth("editor"),
        )
        assert response.status_code == 400

    def test_mapping_rejects_an_out_of_range_column(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        response = client.post(
            f"/api/v1/imports/jobs/{job['id']}/mapping",
            json={"mapping": {"full_name": 99}, "linking_mode": "none"},
            headers=auth("editor"),
        )
        assert response.status_code == 400

    def test_mapping_requires_the_full_name(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        response = client.post(
            f"/api/v1/imports/jobs/{job['id']}/mapping",
            json={"mapping": {"gender": 2}, "linking_mode": "none"},
            headers=auth("editor"),
        )
        assert response.status_code == 400

    def test_preview_returns_the_first_rows(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + "\n".join(NEW_ROWS)).json()["job"]
        preview = client.get(
            f"/api/v1/imports/jobs/{job['id']}/preview?rows=2", headers=auth("editor")
        ).json()
        assert preview["total_rows"] == 4
        assert len(preview["rows"]) == 2
        assert preview["headers"][1] == "full_name"
        assert preview["rows"][0][1] == "جديد كامل عبد الرحمن"
        available = {field["key"] for field in preview["fields"] if field["available"]}
        assert {"national_id", "full_name", "gender", "birth_date"} <= available

    def test_rejects_a_non_data_file(self, client, auth, sample_family) -> None:
        response = _upload(client, auth, "irrelevant", filename="payload.exe")
        assert response.status_code == 400

    def test_stored_filename_is_sanitised(self, client, auth, sample_family) -> None:
        """A traversal attempt must not write outside the storage directory."""
        from app.services.import_service import validate_upload

        storage = Path(settings.import_storage_dir).resolve()
        file_type, path = validate_upload("../../../../etc/passwd.csv", 0)
        assert file_type == "csv"
        assert path.parent == storage
        assert ".." not in path.name
        assert path.name.endswith(".csv")

    def test_two_uploads_of_the_same_name_do_not_collide(self, client, auth, sample_family) -> None:
        first = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        second = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[1]).json()["job"]
        assert first["id"] != second["id"]
        assert first["filename"] == second["filename"] == "people.csv"
        # Both stored files exist side by side.
        for job_id in (first["id"], second["id"]):
            assert (
                client.get(f"/api/v1/imports/jobs/{job_id}", headers=auth("editor")).status_code
                == 200
            )

    def test_rejects_an_empty_upload(self, client, auth, sample_family) -> None:
        response = _upload(client, auth, "")
        assert response.status_code in {400, 422}

    def test_jobs_list_and_delete(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        listing = client.get("/api/v1/imports/jobs", headers=auth("editor")).json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == job["id"]

        assert (
            client.delete(f"/api/v1/imports/jobs/{job['id']}", headers=auth("editor")).status_code
            == 200
        )
        assert client.get("/api/v1/imports/jobs", headers=auth("editor")).json()["total"] == 0

    def test_missing_job_is_404(self, client, auth, sample_family) -> None:
        assert client.get("/api/v1/imports/jobs/9999", headers=auth("editor")).status_code == 404


class TestValidate:
    def test_validation_reports_errors_in_arabic(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + "\n".join(NEW_ROWS)).json()["job"]
        report = client.post(
            f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor")
        ).json()
        assert report["total_rows"] == 4
        assert report["valid_rows"] + report["invalid_rows"] == 4
        assert report["errors_count"] >= report["invalid_rows"]
        assert report["errors"], report
        assert all({"row", "field", "message", "severity"} <= set(row) for row in report["errors"])
        # The three well-formed rows pass; only the broken one is reported.
        assert report["valid_rows"] == 3
        assert report["invalid_rows"] == 1
        assert {row["row"] for row in report["errors"]} == {5}
        assert report["can_commit"] is True
        # Validation must not write anything.
        assert (
            client.get("/api/v1/persons?page_size=200", headers=auth("viewer")).json()["total"]
            == 14
        )

    def test_validation_moves_the_job_to_ready(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        client.post(f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor"))
        after = client.get(f"/api/v1/imports/jobs/{job['id']}", headers=auth("editor")).json()[
            "job"
        ]
        assert after["status"] == "ready"

    def test_validate_writes_an_audit_entry(self, client, auth, sample_family, db) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        client.post(f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor"))
        db.expire_all()
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "IMPORT")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert entry is not None
        assert entry.details["stage"] == "validate"
        assert entry.username == "editor"


class TestCommit:
    def test_commit_creates_updates_and_skips(self, client, auth, sample_family, db) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + "\n".join(NEW_ROWS)).json()["job"]
        client.post(f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor"))
        response = client.post(
            f"/api/v1/imports/jobs/{job['id']}/commit",
            json={"skip_invalid": True},
            headers=auth("editor"),
        )
        assert response.status_code == 200, response.text
        final = _wait_for_job(client, auth, job["id"])
        assert final["status"] == "completed"
        assert final["progress"] == 100
        assert final["created_rows"] == 2
        assert final["updated_rows"] == 1
        assert final["failed_rows"] == 1
        assert final["success_rows"] == 3

        db.expire_all()
        listing = client.get("/api/v1/persons?page_size=200", headers=auth("viewer")).json()
        assert listing["total"] == 16
        names = {row["full_name"] for row in listing["items"]}
        assert "جديد كامل عبد الرحمن" in names
        assert "جديدة ثانية عبد الرحمن" in names

    def test_progress_survives_every_chunk_boundary(
        self, client, auth, sample_family, monkeypatch
    ) -> None:
        """`session.refresh` drops local job state, so re-set it after each read."""
        rows = [NEW_ROWS[0]] * 30
        job = _upload(client, auth, CSV_HEADER + "\n" + "\n".join(rows)).json()["job"]
        client.post(f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor"))
        # Force many chunk boundaries instead of one big final write.
        monkeypatch.setattr(settings, "import_chunk_size", 5)
        assert (
            client.post(
                f"/api/v1/imports/jobs/{job['id']}/commit", json={}, headers=auth("editor")
            ).status_code
            == 200
        )
        final = _wait_for_job(client, auth, job["id"])
        assert final["status"] == "completed"
        assert final["processed_rows"] == 30, final
        assert final["created_rows"] == 1
        assert final["updated_rows"] == 29
        assert final["progress"] == 100
        assert final["success_rows"] == 30

    def test_commit_updates_an_existing_record(self, client, auth, sample_family, db) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[2]).json()["job"]
        client.post(f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor"))
        client.post(f"/api/v1/imports/jobs/{job['id']}/commit", json={}, headers=auth("editor"))
        final = _wait_for_job(client, auth, job["id"])
        assert final["updated_rows"] == 1
        assert final["created_rows"] == 0
        db.expire_all()
        assert db.query(Person).filter(Person.national_id == EXISTING_NATIONAL_ID).count() == 1

    def test_commit_without_validation_is_refused(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        response = client.post(
            f"/api/v1/imports/jobs/{job['id']}/commit", json={}, headers=auth("editor")
        )
        assert response.status_code == 400

    def test_commit_writes_an_audit_entry(self, client, auth, sample_family, db) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        client.post(f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor"))
        client.post(f"/api/v1/imports/jobs/{job['id']}/commit", json={}, headers=auth("editor"))
        _wait_for_job(client, auth, job["id"])
        db.expire_all()
        stages = {
            entry.details.get("stage")
            for entry in db.query(AuditLog).filter(AuditLog.action == "IMPORT").all()
        }
        assert {"validate", "commit"} <= stages

    def test_admin_may_import_but_viewers_may_not(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        client.post(f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("admin"))
        assert (
            client.post(
                f"/api/v1/imports/jobs/{job['id']}/commit", json={}, headers=auth("admin")
            ).status_code
            == 200
        )
        _wait_for_job(client, auth, job["id"])


class TestRecovery:
    """Jobs orphaned by a process that died mid-commit must not stay stuck."""

    @staticmethod
    def _stuck_job(db) -> int:
        from app.models.import_job import ImportJob, ImportStatus

        job = ImportJob(
            filename="stuck.csv",
            status=ImportStatus.PROCESSING.value,
            total_rows=100,
            processed_rows=40,
            progress=40,
            message="جارٍ التنفيذ...",
        )
        db.add(job)
        db.commit()
        return job.id

    def test_startup_reaps_an_orphaned_processing_job(self, db) -> None:
        from app.models.import_job import ImportJob, ImportStatus
        from app.services.import_service import ImportService

        job_id = self._stuck_job(db)
        assert ImportService.reap_stale_jobs() == 1

        db.expire_all()
        job = db.get(ImportJob, job_id)
        assert job.status == ImportStatus.FAILED.value
        assert "إعادة تشغيل" in job.message
        assert job.progress == 40

    def test_reaping_leaves_finished_jobs_alone(self, db) -> None:
        from app.models.import_job import ImportJob, ImportStatus
        from app.services.import_service import ImportService

        stuck = self._stuck_job(db)
        finished = ImportJob(filename="done.csv", status=ImportStatus.COMPLETED.value)
        db.add(finished)
        db.commit()

        assert ImportService.reap_stale_jobs() == 1

        db.expire_all()
        assert db.get(ImportJob, stuck).status == ImportStatus.FAILED.value
        assert db.get(ImportJob, finished.id).status == ImportStatus.COMPLETED.value

    def test_a_positive_threshold_spares_a_recent_job(self, db) -> None:
        """Multi-replica deployments keep live jobs by raising the threshold."""
        from app.models.import_job import ImportJob, ImportStatus
        from app.services.import_service import ImportService

        job_id = self._stuck_job(db)
        assert ImportService.reap_stale_jobs(older_than_minutes=30) == 0

        db.expire_all()
        assert db.get(ImportJob, job_id).status == ImportStatus.PROCESSING.value
        # The default (single process) reaps regardless of age.
        assert ImportService.reap_stale_jobs() == 1

    def test_the_commit_pool_is_bounded_by_the_worker_setting(self) -> None:
        """User-triggered commits must not spawn an unbounded number of threads."""
        from concurrent.futures import ThreadPoolExecutor

        from app.services import import_service

        pool = import_service._commit_executor()
        assert isinstance(pool, ThreadPoolExecutor)
        # `_max_workers` is the only way to observe the bound without timing tests.
        assert pool._max_workers == max(1, settings.import_worker_threads)


class TestCancel:
    def test_pending_job_can_be_cancelled(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        response = client.post(f"/api/v1/imports/jobs/{job['id']}/cancel", headers=auth("editor"))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["job"]["status"] == "cancelled"
        assert "أُلغي" in body["message"] or "إلغاء" in body["message"]

        # A cancelled job can no longer be committed.
        assert (
            client.post(
                f"/api/v1/imports/jobs/{job['id']}/commit", json={}, headers=auth("editor")
            ).status_code
            == 400
        )

    def test_cancelling_twice_is_rejected(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        assert (
            client.post(
                f"/api/v1/imports/jobs/{job['id']}/cancel", headers=auth("editor")
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/imports/jobs/{job['id']}/cancel", headers=auth("editor")
            ).status_code
            == 400
        )

    def test_cancel_writes_an_audit_entry(self, client, auth, sample_family, db) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        client.post(f"/api/v1/imports/jobs/{job['id']}/cancel", headers=auth("editor"))
        db.expire_all()
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "IMPORT")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert entry.details["stage"] == "cancel"

    def test_a_cancel_during_commit_stops_the_job(
        self, client, auth, sample_family, users, db, monkeypatch
    ) -> None:
        """A cancel written mid-commit is honoured at the next chunk boundary.

        The cancel is injected from a *second* session, the way the cancel
        endpoint would, while the worker thread is inside its own transaction.
        """
        from app.db.session import SessionLocal
        from app.models.import_job import ImportJob, ImportStatus
        from app.services.import_service import ImportService

        rows = [NEW_ROWS[0]] * 30  # enough rows for several chunks
        job = _upload(client, auth, CSV_HEADER + "\n" + "\n".join(rows)).json()["job"]
        assert (
            client.post(
                f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor")
            ).status_code
            == 200
        )

        monkeypatch.setattr(settings, "import_chunk_size", 5)

        original = ImportService._upsert_chunk
        cancelled = {"done": False}

        def then_cancel(self, records, resolver, *, actor_id):
            result = original(self, records, resolver, actor_id=actor_id)
            if not cancelled["done"]:
                cancelled["done"] = True
                other = SessionLocal()
                try:
                    other.get(ImportJob, job["id"]).status = ImportStatus.CANCELLED.value
                    other.commit()
                finally:
                    other.close()
            return result

        monkeypatch.setattr(ImportService, "_upsert_chunk", then_cancel)

        service = ImportService(db)
        result = service.commit_sync(service.get_job(job["id"]), actor_id=users["editor"].id)

        assert result["status"] == "cancelled", result
        assert cancelled["done"] is True

        final = client.get(f"/api/v1/imports/jobs/{job['id']}", headers=auth("editor")).json()[
            "job"
        ]
        assert final["status"] == "cancelled"
        # It stopped early rather than running the whole file.
        assert final["processed_rows"] < 30
        assert final["progress"] < 100
        # Rows written before the cancel are kept.
        assert final["created_rows"] + final["updated_rows"] > 0

    def test_a_delete_is_refused_while_a_job_is_processing(
        self, client, auth, sample_family, users, db, monkeypatch
    ) -> None:
        """Deleting the row the worker is writing would orphan the thread."""
        from app.services.import_service import ImportService

        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        assert (
            client.post(
                f"/api/v1/imports/jobs/{job['id']}/validate", headers=auth("editor")
            ).status_code
            == 200
        )
        monkeypatch.setattr(settings, "import_chunk_size", 5)

        original = ImportService._upsert_chunk
        probe: dict[str, int] = {}

        def then_probe(self, records, resolver, *, actor_id):
            result = original(self, records, resolver, actor_id=actor_id)
            if not probe:
                probe["status"] = client.get(
                    f"/api/v1/imports/jobs/{job['id']}", headers=auth("editor")
                ).json()["job"]["status"]
                probe["delete"] = client.delete(
                    f"/api/v1/imports/jobs/{job['id']}", headers=auth("editor")
                ).status_code
            return result

        monkeypatch.setattr(ImportService, "_upsert_chunk", then_probe)

        service = ImportService(db)
        service.commit_sync(service.get_job(job["id"]), actor_id=users["editor"].id)

        assert probe["status"] == "processing"
        assert probe["delete"] == 400

    def test_viewers_cannot_cancel(self, client, auth, sample_family) -> None:
        job = _upload(client, auth, CSV_HEADER + "\n" + NEW_ROWS[0]).json()["job"]
        assert (
            client.post(
                f"/api/v1/imports/jobs/{job['id']}/cancel", headers=auth("viewer")
            ).status_code
            == 403
        )


class TestMappingTemplates:
    def test_save_list_and_delete(self, client, auth, sample_family) -> None:
        created = client.post(
            "/api/v1/imports/mapping-templates",
            json={
                "name": "قالب مشترك للاختبار",
                "mapping": {"full_name": 1, "gender": 2, "birth_date": 3},
                "linking_mode": "by_national_id",
                "description": "قالب للاختبار",
                "is_shared": True,
            },
            headers=auth("editor"),
        )
        assert created.status_code == 201, created.text
        template_id = created.json()["id"]

        listing = client.get("/api/v1/imports/mapping-templates", headers=auth("editor")).json()
        assert listing["items"][0]["name"] == "قالب مشترك للاختبار"
        assert listing["items"][0]["linking_mode"] == "by_national_id"

        assert (
            client.delete(
                f"/api/v1/imports/mapping-templates/{template_id}", headers=auth("editor")
            ).status_code
            == 200
        )
        assert (
            client.get("/api/v1/imports/mapping-templates", headers=auth("editor")).json()["items"]
            == []
        )

    def test_name_must_not_be_empty(self, client, auth, sample_family) -> None:
        response = client.post(
            "/api/v1/imports/mapping-templates",
            json={"name": "x", "mapping": {"full_name": 0}},
            headers=auth("editor"),
        )
        assert response.status_code == 422
