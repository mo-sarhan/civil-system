"""Duplicate detection, comparison and merging (admin-only operations).

The schema keeps ``person.national_id`` unique, so a duplicate national ID is
rejected at write time; detection therefore works on names plus birth dates.
"""

from __future__ import annotations

from app.models.audit import AuditLog
from app.models.marriage import Marriage
from app.models.person import Person


def _twin(db, *, name: str, national_id: str | None = None, gender: str = "M", born=None) -> int:
    twin = Person(
        national_id=national_id,
        full_name=name,
        gender=gender,
        birth_date=born,
    )
    db.add(twin)
    db.commit()
    return twin.id


class TestDuplicateDetection:
    def test_fuzzy_name_with_the_same_birth_date(self, client, auth, sample_family, db) -> None:
        original = db.get(Person, sample_family["4"])  # محمود محمد أحمد
        twin_id = _twin(db, name="محمود احمد السيد", born=original.birth_date)

        body = client.get("/api/v1/duplicates?threshold=0.4", headers=auth("admin")).json()
        assert body["total_groups"] >= 1
        group = next(
            g
            for g in body["groups"]
            if {sample_family["4"], twin_id} <= {p["id"] for p in g["persons"]}
        )
        assert len(group["persons"]) == 2
        assert 0.4 <= group["confidence"] <= 1.0
        assert "تشابه في الاسم" in group["reason"]
        assert {p["national_id"] for p in group["persons"]} == {
            original.national_id,
            None,
        }

    def test_identical_name_and_birth_date_scores_highest(
        self, client, auth, sample_family, db
    ) -> None:
        original = db.get(Person, sample_family["7"])  # هدى
        twin_id = _twin(db, name=original.full_name, born=original.birth_date)

        body = client.get("/api/v1/duplicates?threshold=0.4", headers=auth("admin")).json()
        reasons = [
            g["reason"]
            for g in body["groups"]
            if {sample_family["7"], twin_id} <= {p["id"] for p in g["persons"]}
        ]
        assert reasons, body
        assert any("تطابق الاسم" in reason or "نفس الكلمات" in reason for reason in reasons)

    def test_duplicate_national_id_is_rejected_at_write_time(
        self, client, auth, sample_family, db
    ) -> None:
        existing = db.get(Person, sample_family["1"]).national_id
        response = client.post(
            "/api/v1/persons",
            json={
                "national_id": existing,
                "full_name": "محمد آخر السيد",
                "gender": "M",
                "birth_date": "1990-01-01",
            },
            headers=auth("editor"),
        )
        assert response.status_code in {400, 409}

    def test_clean_dataset_has_no_groups(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/duplicates?threshold=0.95", headers=auth("admin")).json()
        assert body["groups"] == []
        assert body["total_groups"] == 0

    def test_merged_rows_are_ignored(self, client, auth, sample_family, db) -> None:
        original = db.get(Person, sample_family["7"])
        twin_id = _twin(db, name=original.full_name, born=original.birth_date)
        client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["7"], "source_id": twin_id},
            headers=auth("admin"),
        )
        body = client.get("/api/v1/duplicates?threshold=0.4", headers=auth("admin")).json()
        assert all(twin_id not in {p["id"] for p in group["persons"]} for group in body["groups"])

    def test_requires_admin(self, client, auth, sample_family) -> None:
        assert client.get("/api/v1/duplicates", headers=auth("viewer")).status_code == 403
        assert client.get("/api/v1/duplicates", headers=auth("editor")).status_code == 403


class TestCompare:
    def test_compare_reports_field_differences(self, client, auth, sample_family, db) -> None:
        original = db.get(Person, sample_family["1"])
        twin_id = _twin(db, name=original.full_name, born=original.birth_date, gender="F")
        body = client.get(
            f"/api/v1/duplicates/compare?a={sample_family['1']}&b={twin_id}",
            headers=auth("admin"),
        ).json()
        fields = {row["field"]: row for row in body["fields"]}
        assert fields["gender"]["same"] is False
        assert fields["full_name"]["same"] is True
        assert fields["birth_date"]["same"] is True
        assert body["differences"] == sum(1 for row in body["fields"] if row["same"] is False)
        assert body["differences"] >= 1
        assert body["name_similarity"] == 1.0
        assert body["recommendation"]["keep"] in {sample_family["1"], twin_id}
        assert body["a"]["children"] == 3  # محمد has three children
        assert body["b"]["children"] == 0

    def test_compare_is_admin_only(self, client, auth, sample_family) -> None:
        response = client.get(
            f"/api/v1/duplicates/compare?a={sample_family['1']}&b={sample_family['2']}",
            headers=auth("editor"),
        )
        assert response.status_code == 403


class TestMerge:
    def test_merge_moves_children(self, client, auth, sample_family, db) -> None:
        target = sample_family["2"]  # فاطمة
        source_id = _twin(db, name="فاطمة عبد الله السيد", gender="F")
        child = db.get(Person, sample_family["3"])
        child.mother_id = source_id
        db.commit()

        response = client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": target, "source_id": source_id},
            headers=auth("admin"),
        )
        assert response.status_code == 200, response.text
        assert response.json()["stats"]["children_moved"] >= 1
        db.expire_all()
        assert db.get(Person, sample_family["3"]).mother_id == target
        assert db.get(Person, source_id).merged_into_id == target

    def test_merge_hides_the_source_from_listings(self, client, auth, sample_family, db) -> None:
        source_id = _twin(db, name="سجل مكرر مخفي", gender="M")
        client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["1"], "source_id": source_id},
            headers=auth("admin"),
        )
        listing = client.get("/api/v1/persons?page_size=200", headers=auth("viewer")).json()
        assert source_id not in {row["id"] for row in listing["items"]}

    def test_merged_record_keeps_a_redirect(self, client, auth, sample_family, db) -> None:
        source_id = _twin(db, name="سجل مكرر بإعادة توجيه", gender="M")
        client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["1"], "source_id": source_id},
            headers=auth("admin"),
        )
        body = client.get(f"/api/v1/persons/{source_id}", headers=auth("viewer")).json()
        assert body["merged_into_id"] == sample_family["1"]

    def test_merge_moves_marriages(self, client, auth, sample_family, db) -> None:
        target = sample_family["2"]
        source_id = _twin(db, name="زوجة أخرى", gender="F")
        db.add(
            Marriage(
                husband_id=sample_family["7"],
                wife_id=source_id,
                start_date="2015-01-01",
                status="married",
            )
        )
        db.commit()

        response = client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": target, "source_id": source_id},
            headers=auth("admin"),
        )
        assert response.status_code == 200, response.text
        db.expire_all()
        assert source_id not in {row[0] for row in db.query(Marriage.wife_id).all()}

    def test_merge_clears_the_source_national_id(self, client, auth, sample_family, db) -> None:
        source_id = _twin(db, name="سجل برقم هوية", national_id="29101011200255", gender="M")
        client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["1"], "source_id": source_id},
            headers=auth("admin"),
        )
        db.expire_all()
        assert db.get(Person, source_id).national_id is None

    def test_merge_writes_an_audit_entry(self, client, auth, sample_family, db) -> None:
        source_id = _twin(db, name="مكرر للتدقيق", gender="M")
        client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["1"], "source_id": source_id},
            headers=auth("admin"),
        )
        db.expire_all()
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "MERGE")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert entry is not None
        assert entry.entity == "person"
        assert entry.entity_id == sample_family["1"]
        assert entry.details["source_id"] == source_id
        assert entry.username == "admin"

    def test_merge_rejects_identical_ids(self, client, auth, sample_family) -> None:
        response = client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["1"], "source_id": sample_family["1"]},
            headers=auth("admin"),
        )
        assert response.status_code == 400

    def test_merge_rejects_a_missing_person(self, client, auth, sample_family) -> None:
        response = client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["1"], "source_id": 9999},
            headers=auth("admin"),
        )
        assert response.status_code in {400, 404}

    def test_merge_rejects_an_already_merged_source(self, client, auth, sample_family, db) -> None:
        first = _twin(db, name="مكرر أول", gender="M")
        client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["1"], "source_id": first},
            headers=auth("admin"),
        )
        response = client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["2"], "source_id": first},
            headers=auth("admin"),
        )
        assert response.status_code in {400, 409}

    def test_merge_is_admin_only(self, client, auth, sample_family) -> None:
        response = client.post(
            "/api/v1/duplicates/merge",
            json={"target_id": sample_family["1"], "source_id": sample_family["2"]},
            headers=auth("editor"),
        )
        assert response.status_code == 403
