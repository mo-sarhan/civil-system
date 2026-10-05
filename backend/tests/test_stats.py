"""Dashboard statistics endpoints."""

from __future__ import annotations


class TestOverview:
    def test_counts_match_the_fixture(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/stats", headers=auth("viewer")).json()
        assert body["total_persons"] == 14
        assert body["active_persons"] == 14
        assert body["merged_persons"] == 0
        assert body["marriages"] == 5
        assert body["active_marriages"] == 4
        assert body["by_gender"]["M"] + body["by_gender"]["F"] == 14
        assert body["alive"] + body["deceased"] == 14
        assert body["with_national_id"] == 14

    def test_requires_authentication(self, client) -> None:
        assert client.get("/api/v1/stats").status_code == 401


class TestGenerations:
    def test_max_generation_covers_the_deepest_chain(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/stats/generations", headers=auth("viewer")).json()
        # محمد -> أحمد -> عمر -> آدم is four generations.
        assert body["max_generation"] == 4
        assert body["persons_with_lineage"] == 14
        assert body["persons_without_lineage"] == 0


class TestLargestFamilies:
    def test_families_are_sorted_descending(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/stats/largest-families?limit=3", headers=auth("viewer")).json()
        items = body["items"]
        assert 0 < len(items) <= 3
        assert body["total"] >= len(items)
        sizes = [item["members"] for item in items]
        assert sizes == sorted(sizes, reverse=True)
        assert items[0]["family_name"] == "أحمد"
        assert items[0]["members"] == 4
        assert all(item["with_father_link"] <= item["members"] for item in items)


class TestBirthDistribution:
    def test_birth_years_are_grouped_by_decade(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/stats/birth-years", headers=auth("viewer")).json()
        decades = [row["decade"] for row in body["items"]]
        assert decades == sorted(decades)
        assert all(row["decade"] % 10 == 0 for row in body["items"])
        assert body["total"] == 14
        assert sum(row["total"] for row in body["items"]) == 14
        for row in body["items"]:
            assert row["male"] + row["female"] == row["total"]

    def test_birth_places_are_ranked(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/stats/birth-places?limit=5", headers=auth("viewer")).json()
        counts = [row["count"] for row in body["items"]]
        assert counts == sorted(counts, reverse=True)
        assert all(row["birth_place"] for row in body["items"])


class TestDataQuality:
    def test_missing_links_are_reported(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/stats/missing-links", headers=auth("viewer")).json()
        assert body["total"] == 6  # the six roots have no father
        assert len(body["items"]) == body["total"]
        assert all("id" in row and "full_name" in row for row in body["items"])
        assert all(row["has_mother_link"] is False for row in body["items"])

    def test_data_quality_percentages(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/stats/data-quality", headers=auth("viewer")).json()
        assert body["total"] == 14
        fields = body["fields"]
        assert set(fields) >= {"national_id", "birth_date", "gender", "father_link", "mother_link"}
        assert fields["national_id"]["percent"] == 100.0
        # 8 of the 14 people have a recorded father.
        assert fields["father_link"]["count"] == 8
        assert fields["father_link"]["percent"] == round(8 / 14 * 100, 1)
        for values in fields.values():
            assert 0.0 <= values["percent"] <= 100.0

    def test_search_suggestions(self, client, auth, sample_family) -> None:
        body = client.get("/api/v1/stats/search-suggestions", headers=auth("viewer")).json()
        assert body["family_names"][0]["value"] == "أحمد"
        assert body["family_names"][0]["count"] == 4
        counts = [row["count"] for row in body["family_names"]]
        assert counts == sorted(counts, reverse=True)
        assert all(isinstance(place, str) for place in body["birth_places"])
