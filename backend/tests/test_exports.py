"""CSV/XLSX exports, including national-ID masking and audit trails."""

from __future__ import annotations

import csv
import io

from app.models.audit import AuditLog


def _csv_rows(response) -> list[dict[str, str]]:
    text = response.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


class TestPersonExport:
    def test_csv_has_an_utf8_bom_and_headers(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/export/persons?format=csv", headers=auth("viewer"))
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert response.content.startswith(b"\xef\xbb\xbf")
        assert "attachment" in response.headers["content-disposition"]

        rows = _csv_rows(response)
        assert len(rows) == 14
        assert set(rows[0]) == {
            "المعرف",
            "رقم القومى",
            "الاسم الكامل",
            "الاسم الأول",
            "اسم الأب",
            "اسم الجد",
            "اسم العائلة",
            "النوع",
            "تاريخ الميلاد",
            "تاريخ الوفاة",
            "مكان الميلاد",
            "معرف الأب",
            "معرف الأم",
            "ملاحظات",
            "تاريخ الإنشاء",
        }

    def test_csv_keeps_arabic_intact_and_splits_the_name(self, client, auth, sample_family) -> None:
        rows = _csv_rows(client.get("/api/v1/export/persons", headers=auth("viewer")))
        first = next(row for row in rows if row["المعرف"] == "1")
        assert first["الاسم الكامل"] == "محمد أحمد السيد"
        assert first["الاسم الأول"] == "محمد"
        assert first["اسم الأب"] == "أحمد"
        assert first["اسم العائلة"] == "السيد"

    def test_xlsx_is_a_real_workbook(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/export/persons?format=xlsx", headers=auth("viewer"))
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml"
        )
        assert response.content[:2] == b"PK"  # zip container
        assert b"xl/worksheets" in response.content[:2048] or response.content[:2] == b"PK"

    def test_masks_the_national_id_for_viewers(self, client, auth, sample_family, db) -> None:
        from app.models.person import Person

        rows = _csv_rows(client.get("/api/v1/export/persons", headers=auth("viewer")))
        first = next(row for row in rows if row["المعرف"] == "1")
        raw = db.get(Person, 1)
        assert first["رقم القومى"] != raw.national_id
        assert first["رقم القومى"].endswith(raw.national_id[-4:])
        assert "*" in first["رقم القومى"]

    def test_editor_sees_the_full_national_id(self, client, auth, sample_family, db) -> None:
        from app.models.person import Person

        rows = _csv_rows(client.get("/api/v1/export/persons", headers=auth("editor")))
        raw = db.get(Person, 1)
        first = next(row for row in rows if row["المعرف"] == "1")
        assert first["رقم القومى"] == raw.national_id

    def test_filters_apply(self, client, auth, sample_family) -> None:
        rows = _csv_rows(client.get("/api/v1/export/persons?gender=M", headers=auth("viewer")))
        assert len(rows) == 7
        assert all(row["النوع"] == "ذكر" for row in rows)

    def test_search_filter_applies(self, client, auth, sample_family) -> None:
        rows = _csv_rows(client.get("/api/v1/export/persons?q=يوسف", headers=auth("viewer")))
        # يوسف appears both as a given name and as a father's name.
        assert len(rows) == 2
        assert all("يوسف" in row["الاسم الكامل"] for row in rows)

    def test_birth_place_filter_applies(self, client, auth, sample_family) -> None:
        rows = _csv_rows(
            client.get("/api/v1/export/persons?birth_place=الجيزة", headers=auth("viewer"))
        )
        assert all(row["مكان الميلاد"] == "الجيزة" for row in rows)
        assert 0 < len(rows) < 14

    def test_limit_caps_the_rows(self, client, auth, sample_family) -> None:
        rows = _csv_rows(client.get("/api/v1/export/persons?limit=5", headers=auth("viewer")))
        assert len(rows) == 5

    def test_rejects_an_unknown_format(self, client, auth, sample_family) -> None:
        assert (
            client.get("/api/v1/export/persons?format=pdf", headers=auth("viewer")).status_code
            == 422
        )

    def test_requires_authentication(self, client) -> None:
        assert client.get("/api/v1/export/persons").status_code == 401


class TestTreeExport:
    def test_tree_csv(self, client, auth, sample_family) -> None:
        response = client.get(
            f"/api/v1/export/tree-csv?person_id={sample_family['1']}", headers=auth("viewer")
        )
        assert response.status_code == 200
        rows = _csv_rows(response)
        assert len(rows) == 14
        assert set(rows[0]) == {"المعرف", "الاسم", "الجيل", "رقم الأب", "رقم الأم", "تاريخ الميلاد"}
        assert any(row["الجيل"] == "الأنفس" for row in rows)
        assert next(row for row in rows if row["المعرف"] == str(sample_family["1"]))["الاسم"] == (
            "محمد أحمد السيد"
        )

    def test_tree_csv_requires_a_person(self, client, auth, sample_family) -> None:
        assert client.get("/api/v1/export/tree-csv", headers=auth("viewer")).status_code == 422


class TestExportAudit:
    def test_every_export_is_recorded(self, client, auth, sample_family, db) -> None:
        before = db.query(AuditLog).filter(AuditLog.action == "EXPORT").count()
        client.get("/api/v1/export/persons?format=csv", headers=auth("editor"))
        client.get("/api/v1/export/persons?format=xlsx", headers=auth("editor"))
        db.expire_all()
        after = db.query(AuditLog).filter(AuditLog.action == "EXPORT").count()
        assert after - before == 2

    def test_audit_records_the_format_and_filters(self, client, auth, sample_family, db) -> None:
        client.get("/api/v1/export/persons?format=xlsx&gender=F", headers=auth("editor"))
        db.expire_all()
        entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "EXPORT")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert entry is not None
        assert entry.entity == "person"
        assert entry.details["format"] == "xlsx"
        assert entry.details["filters"]["gender"] == "F"
        assert entry.details["rows"] == 7
        assert entry.username == "editor"

    def test_tree_export_is_recorded(self, client, auth, sample_family, db) -> None:
        before = db.query(AuditLog).filter(AuditLog.action == "EXPORT").count()
        client.get(
            f"/api/v1/export/tree-csv?person_id={sample_family['1']}", headers=auth("viewer")
        )
        db.expire_all()
        after = db.query(AuditLog).filter(AuditLog.action == "EXPORT").count()
        assert after - before == 1
