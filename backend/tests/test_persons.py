"""Person CRUD, validation, masking, and search tests."""

from __future__ import annotations

from app.utils.messages import Messages

NEW_PERSON = {
    "national_id": "29005151200564",
    "full_name": "مي أحمد محمد",
    "gender": "أنثى",
    "birth_date": "1990-05-15",
    "birth_place": "القاهرة",
}


class TestCreate:
    def test_create_returns_the_new_person(self, client, auth) -> None:
        response = client.post("/api/v1/persons", headers=auth("editor"), json=NEW_PERSON)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["full_name"] == "مي أحمد محمد"
        assert body["gender"] == "F"
        assert body["id"] > 0
        assert body["first_name"] == "مي"

    def test_name_parts_are_derived_automatically(self, client, auth) -> None:
        response = client.post(
            "/api/v1/persons",
            headers=auth("editor"),
            json={"full_name": "محمد أحمد عبد الله السيد", "gender": "M"},
        )
        body = response.json()
        assert body["first_name"] == "محمد"
        assert body["father_name"] == "أحمد"
        assert body["grandfather_name"] == "عبد الله"
        assert body["family_name"] == "السيد"

    def test_national_id_must_match_the_birth_date(self, client, auth) -> None:
        payload = {**NEW_PERSON, "birth_date": "1999-01-01"}
        response = client.post("/api/v1/persons", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_national_id_must_match_the_gender(self, client, auth) -> None:
        payload = {**NEW_PERSON, "gender": "ذكر"}
        response = client.post("/api/v1/persons", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_malformed_national_id_is_rejected(self, client, auth) -> None:
        payload = {**NEW_PERSON, "national_id": "12345"}
        response = client.post("/api/v1/persons", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_duplicate_national_id_conflicts(self, client, auth) -> None:
        client.post("/api/v1/persons", headers=auth("editor"), json=NEW_PERSON)
        response = client.post("/api/v1/persons", headers=auth("editor"), json=NEW_PERSON)
        assert response.status_code == 409

    def test_death_before_birth_is_rejected(self, client, auth) -> None:
        payload = {**NEW_PERSON, "death_date": "1980-01-01"}
        response = client.post("/api/v1/persons", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)

    def test_future_birth_date_is_rejected(self, client, auth) -> None:
        payload = {"full_name": "مستقبل", "gender": "M", "birth_date": "2099-01-01"}
        response = client.post("/api/v1/persons", headers=auth("editor"), json=payload)
        assert response.status_code in (400, 422)


class TestRead:
    def test_masking_hides_the_id_for_viewers(self, client, auth, sample_family) -> None:
        response = client.get(f"/api/v1/persons/{sample_family['1']}", headers=auth("viewer"))
        assert response.status_code == 200
        assert "*" in response.json()["national_id"]
        assert "400315" not in response.json()["national_id"]

    def test_editors_see_the_full_id(self, client, auth, sample_family) -> None:
        response = client.get(f"/api/v1/persons/{sample_family['1']}", headers=auth("editor"))
        assert response.json()["national_id"] == "24003151200113"

    def test_unknown_person_is_404(self, client, auth) -> None:
        assert client.get("/api/v1/persons/9999", headers=auth("viewer")).status_code == 404

    def test_list_is_paginated(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/persons?page=1&page_size=5", headers=auth("viewer"))
        body = response.json()
        assert body["total"] == 14
        assert len(body["items"]) == 5
        assert body["page_size"] == 5

    def test_page_size_cap_is_enforced(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/persons?page_size=100000", headers=auth("viewer"))
        assert response.status_code in (400, 422)

    def test_merged_people_are_hidden(self, client, auth, db, sample_family) -> None:
        from app.models.person import Person

        source = db.get(Person, sample_family["14"])
        target = db.get(Person, sample_family["10"])
        source.merged_into_id = target.id
        db.commit()
        response = client.get("/api/v1/persons?page_size=100", headers=auth("viewer"))
        ids = {item["id"] for item in response.json()["items"]}
        assert source.id not in ids


class TestSearch:
    def test_exact_name_search(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/persons?q=محمد أحمد السيد", headers=auth("viewer"))
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == sample_family["1"]

    def test_search_ignores_tashkeel_and_alef_forms(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/persons?q=محمد احمد السيد", headers=auth("viewer"))
        assert sample_family["1"] in {item["id"] for item in response.json()["items"]}

    def test_search_by_family_name(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/persons?q=السيد", headers=auth("viewer"))
        assert response.json()["total"] >= 1

    def test_search_with_no_hits_returns_an_empty_page(self, client, auth, sample_family) -> None:
        response = client.get(
            "/api/v1/persons", params={"q": "زائر غير موجود"}, headers=auth("viewer")
        )
        assert response.json()["total"] == 0
        assert response.json()["items"] == []

    def test_gender_filter(self, client, auth, sample_family) -> None:
        response = client.get("/api/v1/persons?gender=F&page_size=100", headers=auth("viewer"))
        assert response.json()["total"] == 7
        assert {item["gender"] for item in response.json()["items"]} == {"F"}

    def test_birth_year_range_filter(self, client, auth, sample_family) -> None:
        response = client.get(
            "/api/v1/persons?birth_year_from=1960&birth_year_to=1970&page_size=100",
            headers=auth("viewer"),
        )
        years = {item["birth_date"][:4] for item in response.json()["items"]}
        assert all(1960 <= int(year) <= 1970 for year in years)

    def test_birth_place_filter(self, client, auth, sample_family) -> None:
        response = client.get(
            "/api/v1/persons?birth_place=القاهرة&page_size=100", headers=auth("viewer")
        )
        assert response.json()["total"] == 12


class TestUpdate:
    def test_partial_update_keeps_other_fields(self, client, auth) -> None:
        created = client.post("/api/v1/persons", headers=auth("editor"), json=NEW_PERSON).json()
        response = client.patch(
            f"/api/v1/persons/{created['id']}",
            headers=auth("editor"),
            json={"birth_place": "الجيزة"},
        )
        assert response.status_code == 200
        assert response.json()["birth_place"] == "الجيزة"
        assert response.json()["full_name"] == NEW_PERSON["full_name"]

    def test_clearing_an_optional_field(self, client, auth) -> None:
        created = client.post("/api/v1/persons", headers=auth("editor"), json=NEW_PERSON).json()
        response = client.patch(
            f"/api/v1/persons/{created['id']}", headers=auth("editor"), json={"notes": None}
        )
        assert response.json()["notes"] is None

    def test_viewer_cannot_update(self, client, auth, sample_family) -> None:
        response = client.patch(
            f"/api/v1/persons/{sample_family['1']}",
            headers=auth("viewer"),
            json={"birth_place": " elsewhere"},
        )
        assert response.status_code == 403

    def test_admin_deletes(self, client, auth, sample_family) -> None:
        response = client.delete(f"/api/v1/persons/{sample_family['13']}", headers=auth("admin"))
        assert response.status_code == 200
        assert (
            client.get(f"/api/v1/persons/{sample_family['13']}", headers=auth("admin")).status_code
            == 404
        )

    def test_descendant_cannot_become_an_ancestor(self, client, auth, sample_family) -> None:
        """The cycle guard itself must reject a parent link that closes a loop.

        The gender and age guards run first, so a direct loop (``1`` <- ``13``)
        is caught by them and never reaches the cycle check.  The only way to
        reach it is a parent whose birth date is unknown, because that skips the
        age comparison entirely -- which is exactly the registry case of someone
        born before civil registration.
        """

        def _new_son(parent_id: int | None) -> int:
            response = client.post(
                "/api/v1/persons",
                headers=auth("editor"),
                json={"full_name": "ابن مجهول", "gender": "M", "father_id": parent_id},
            )
            assert response.status_code == 201, response.text
            return response.json()["id"]

        # A two-generation male line below sample 13, both with no birth date
        # so the parent-age check is skipped.
        grandson = _new_son(sample_family["13"])
        great_grandson = _new_son(grandson)

        # Close the loop: the great-grandson is already a descendant of 13.
        response = client.patch(
            f"/api/v1/persons/{sample_family['13']}",
            headers=auth("admin"),
            json={"father_id": great_grandson},
        )
        assert response.status_code == 400, response.text
        assert Messages.PARENT_CYCLE in response.json()["detail"]

    def test_parent_gender_and_age_guards_precede_the_cycle_check(
        self, client, auth, sample_family
    ) -> None:
        """A loop built from dated relatives is reported by the cheaper guard."""
        response = client.patch(
            f"/api/v1/persons/{sample_family['1']}",
            headers=auth("admin"),
            json={"father_id": sample_family["13"]},
        )
        assert response.status_code == 400, response.text
        assert "دورة" not in response.json()["detail"]
