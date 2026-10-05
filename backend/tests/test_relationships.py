r"""Relationship engine tests: parents, siblings, generations, tree, finder.

The ``sample_family`` fixture maps the sample-file ids (1-14) to the database
ids it actually inserts. The sample structure is::

    1 محمد (M)  x  2 فاطمة (F)          generation 1
      |- 3 أحمد (M)  x  6 منى (F)        generation 2
      |    |- 9 عمر (M)   x  14 دعاء (F)  generation 3
      |    |    \- 13 آدم (M)
      |    \- 10 ياسمين (F)
      |- 4 محمود (M) x  7 هدى (F)
      |    \- 11 يوسف (M)
      \- 5 سعاد (F)  x  8 حسن (M)
           \- 12 نور (F)
"""

from __future__ import annotations


class TestParentsAndChildren:
    def test_parents_of_a_child(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['3']}/parents", headers=auth("viewer")
        ).json()
        assert body["father"]["id"] == sample_family["1"]
        assert body["mother"]["id"] == sample_family["2"]
        assert body["missing"] == []

    def test_missing_parents_are_reported(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/parents", headers=auth("viewer")
        ).json()
        assert body["father"] is None and body["mother"] is None
        assert len(body["missing"]) == 2

    def test_children_split_by_link_type(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/children", headers=auth("viewer")
        ).json()
        assert body["total"] == 3
        assert [child["id"] for child in body["as_father"]] == [
            sample_family["3"],
            sample_family["4"],
            sample_family["5"],
        ]
        assert body["as_mother"] == []

    def test_mother_link_only(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['6']}/children", headers=auth("viewer")
        ).json()
        assert [child["id"] for child in body["as_mother"]] == [
            sample_family["9"],
            sample_family["10"],
        ]


class TestSiblings:
    def test_full_siblings(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['5']}/siblings", headers=auth("viewer")
        ).json()
        assert {item["id"] for item in body["full"]} == {
            sample_family["3"],
            sample_family["4"],
        }
        assert body["half_paternal"] == [] and body["half_maternal"] == []

    def test_paternal_half_siblings(self, client, auth, sample_family, db) -> None:
        from app.models.person import Person

        father = db.get(Person, sample_family["4"])
        half = Person(
            national_id="29102151200771",
            full_name="ولد محمود محمد أحمد",
            gender="M",
            birth_date=None,
            father_id=father.id,
        )
        db.add(half)
        db.commit()
        body = client.get(
            f"/api/v1/persons/{sample_family['4']}/children", headers=auth("viewer")
        ).json()
        assert half.id in {child["id"] for child in body["as_father"]}

        # يوسف shares father محمود but not mother هدى -> paternal half sibling
        siblings = client.get(
            f"/api/v1/persons/{sample_family['11']}/siblings", headers=auth("viewer")
        ).json()
        assert half.id in {item["id"] for item in siblings["half_paternal"]}
        assert siblings["full"] == []

    def test_sibling_labels_follow_gender(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['5']}/siblings", headers=auth("viewer")
        ).json()
        labels = {item["id"]: item["relation"] for item in body["full"]}
        assert labels[sample_family["3"]] == "أخ"
        assert labels[sample_family["4"]] == "أخ"


class TestGenerations:
    def test_ancestors_are_ordered_and_labelled(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['12']}/ancestors?depth=3",
            headers=auth("viewer"),
        ).json()
        labels = {item["id"]: item["relation"] for item in body["ancestors"]}
        assert labels[sample_family["8"]] == "أب"  # حسن
        assert labels[sample_family["5"]] == "أم"  # سعاد
        assert labels[sample_family["1"]] == "جد"  # محمد
        assert labels[sample_family["2"]] == "جدة"  # فاطمة
        generations = {item["id"]: item["generation"] for item in body["ancestors"]}
        assert generations[sample_family["8"]] == 1
        assert generations[sample_family["1"]] == 2

    def test_ancestor_depth_limit(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['12']}/ancestors?depth=1", headers=auth("viewer")
        ).json()
        assert {item["id"] for item in body["ancestors"]} == {
            sample_family["8"],
            sample_family["5"],
        }

    def test_ancestors_are_grouped_by_generation_label(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['12']}/ancestors?depth=3",
            headers=auth("viewer"),
        ).json()
        labels_by_id = {item["id"]: item["generation_label"] for item in body["ancestors"]}
        assert labels_by_id[sample_family["1"]] == "جد"
        assert labels_by_id[sample_family["2"]] == "جدة"
        assert body["total"] == 4

    def test_descendants_by_generation(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/descendants?depth=3",
            headers=auth("viewer"),
        ).json()
        by_generation: dict[int, set[int]] = {}
        for item in body["descendants"]:
            by_generation.setdefault(item["generation"], set()).add(item["id"])
        assert by_generation[1] == {
            sample_family["3"],
            sample_family["4"],
            sample_family["5"],
        }
        assert by_generation[2] == {
            sample_family["9"],
            sample_family["10"],
            sample_family["11"],
            sample_family["12"],
        }
        assert by_generation[3] == {sample_family["13"]}

    def test_descendant_labels_follow_gender(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/descendants?depth=1",
            headers=auth("viewer"),
        ).json()
        labels = {item["id"]: item["relation"] for item in body["descendants"]}
        assert labels[sample_family["3"]] == "ابن"
        assert labels[sample_family["5"]] == "ابنة"


class TestSpouses:
    def test_spouses_include_marriage_meta(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/spouses", headers=auth("viewer")
        ).json()
        assert body["total"] == 1
        assert body["spouses"][0]["id"] == sample_family["2"]
        assert body["spouses"][0]["relation"] == "زوجة"


class TestTree:
    def test_tree_covers_the_subtree_and_completes_the_couple(
        self, client, auth, sample_family
    ) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['9']}/tree?up=2&down=1", headers=auth("viewer")
        ).json()
        ids = {node["id"] for node in body["nodes"]}
        # عمر + both parents + grandparents + the wife of each included parent
        assert {
            sample_family["9"],
            sample_family["3"],
            sample_family["6"],
            sample_family["1"],
            sample_family["2"],
            sample_family["13"],
        } <= ids
        assert body["person_id"] == sample_family["9"]
        assert body["total_nodes"] == len(body["nodes"])
        assert body["truncated"] is False

    def test_every_link_points_at_existing_nodes(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/tree?up=3&down=3", headers=auth("viewer")
        ).json()
        ids = {node["id"] for node in body["nodes"]}
        assert body["links"], "a tree must contain at least one edge"
        for link in body["links"]:
            assert link["source"] in ids
            assert link["target"] in ids

    def test_root_has_depth_zero_and_descendants_are_positive(
        self, client, auth, sample_family
    ) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['9']}/tree?up=2&down=2", headers=auth("viewer")
        ).json()
        depths = {node["id"]: node["depth"] for node in body["nodes"]}
        assert depths[sample_family["9"]] == 0
        assert depths[sample_family["13"]] == 1
        assert depths[sample_family["3"]] == -1

    def test_depth_limits_are_respected(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/tree?up=0&down=1", headers=auth("viewer")
        ).json()
        depths = [node["depth"] for node in body["nodes"]]
        assert min(depths) == 0
        assert max(depths) == 1

    def test_spouse_links_and_marriages_are_included(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['9']}/tree?up=1&down=1", headers=auth("viewer")
        ).json()
        assert {link["kind"] for link in body["links"]} == {"parent", "spouse"}
        assert body["marriages"]
        marriage = body["marriages"][0]
        assert isinstance(marriage["start_date"], str)

    def test_marriage_dates_survive_serialization(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/tree", headers=auth("viewer")
        ).json()
        for marriage in body["marriages"]:
            assert marriage["start_date"] is None or isinstance(marriage["start_date"], str)


class TestRelationshipFinder:
    def test_explanation_agrees_with_the_senior_gender(self, client, auth, sample_family) -> None:
        """The sentence introduces the senior person, with a matching pronoun."""
        grandfather = sample_family["1"]  # محمد
        granddaughter = sample_family["12"]  # نور

        # Both query orders describe the same pair, the same way round.
        for a, b in ((grandfather, granddaughter), (granddaughter, grandfather)):
            body = client.get(
                f"/api/v1/relationship?a={a}&b={b}", headers=auth("viewer")
            ).json()
            assert body["explanation"] == "محمد أحمد السيد هو جد نور حسن عبد الله"
            assert body["relation"] == "جد"

        # A female senior gets the feminine pronoun and label.
        mother = sample_family["6"]  # منى
        son = sample_family["9"]  # عمر
        body = client.get(
            f"/api/v1/relationship?a={mother}&b={son}", headers=auth("viewer")
        ).json()
        assert body["explanation"] == "منى إبراهيم يوسف هي أم عمر أحمد محمد"
        assert body["relation"] == "أم"
        assert body["relation_from_b"] == "ابن"

    def test_in_law_explanations_avoid_slash_forms(
        self, client, auth, sample_family
    ) -> None:
        """No "X/Y" placeholders: the label follows the person's gender."""
        husband = sample_family["3"]  # أحمد, married to منى
        brother_in_law = sample_family["4"]  # محمود, brother of أحمد
        body = client.get(
            f"/api/v1/relationship?a={husband}&b={brother_in_law}&direction=ancestor",
            headers=auth("viewer"),
        ).json()
        assert "/" not in body["explanation"]
        assert body["explanation"]
    def test_grandparent_to_grandson(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/relationship?a={sample_family['1']}&b={sample_family['9']}",
            headers=auth("viewer"),
        ).json()
        # `relation` names the senior's role; `relation_from_*` disambiguate.
        assert body["relation"] == "جد"
        assert body["relation_from_a"] == "جد"
        assert body["relation_from_b"] == "حفيد"
        assert body["generations"] == 2

    def test_grandparent_to_granddaughter(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/relationship?a={sample_family['1']}&b={sample_family['10']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "جد"
        assert body["relation_from_b"] == "حفيدة"
        assert body["generations"] == 2

    def test_child_of_the_subject(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/relationship?a={sample_family['1']}&b={sample_family['5']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "أب"
        assert body["relation_from_b"] == "ابنة"
        # A positive generation count means A is that many steps above B.
        assert body["generations"] == 1

    def test_sibling_pair(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/relationship?a={sample_family['3']}&b={sample_family['4']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "أخ"

    def test_parent_child(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/relationship?a={sample_family['8']}&b={sample_family['12']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "أب"
        assert body["relation_from_b"] == "ابنة"
        assert body["generations"] == 1

    def test_paternal_uncle(self, client, auth, sample_family) -> None:
        # أحمد and محمود are brothers, so Ahmad is Yusuf's paternal uncle.
        body = client.get(
            f"/api/v1/relationship?a={sample_family['3']}&b={sample_family['11']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "عم"
        assert body["relation_from_b"] == "ابن العم"
        assert body["common_ancestor_id"] == sample_family["1"]

    def test_paternal_uncle_of_a_niece(self, client, auth, sample_family) -> None:
        # سعاد is محمود's full sister, so نور is his paternal niece.
        body = client.get(
            f"/api/v1/relationship?a={sample_family['4']}&b={sample_family['12']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "عم"
        assert body["relation_from_b"] == "بنت العم"

    def test_grand_aunt(self, client, auth, sample_family) -> None:
        # سعاد is the paternal grand-aunt of آدم through her brother أحمد.
        body = client.get(
            f"/api/v1/relationship?a={sample_family['5']}&b={sample_family['13']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "عة من الدرجة الثانية"
        assert body["common_ancestor_id"] == sample_family["1"]

    def test_maternal_uncle(self, client, auth, sample_family, db) -> None:
        # Give دعاء (Adam's mother) a brother to get a maternal uncle.
        from app.models.person import Person

        grandmother = Person(
            national_id="29102151200783",
            full_name="أم دعاء إبراهيم الصالح",
            gender="F",
        )
        db.add(grandmother)
        db.flush()
        maternal_uncle = Person(
            national_id="29102151200795",
            full_name="فهد إبراهيم الصالح",
            gender="M",
            mother_id=grandmother.id,
        )
        db.add(maternal_uncle)
        mother = db.get(Person, sample_family["14"])  # دعاء
        mother.mother_id = grandmother.id
        db.commit()

        body = client.get(
            f"/api/v1/relationship?a={maternal_uncle.id}&b={sample_family['13']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "خال"
        assert body["relation_from_b"] == "ابن الخال"

    def test_first_cousins(self, client, auth, sample_family) -> None:
        # يوسف and ياسمين are the children of two brothers.
        body = client.get(
            f"/api/v1/relationship?a={sample_family['11']}&b={sample_family['10']}",
            headers=auth("viewer"),
        ).json()
        assert body["relation"] == "بنت عم"
        assert body["common_ancestor_id"] == sample_family["1"]

    def test_same_person_is_handled(self, client, auth, sample_family) -> None:
        response = client.get(
            f"/api/v1/relationship?a={sample_family['3']}&b={sample_family['3']}",
            headers=auth("viewer"),
        )
        assert response.status_code == 200
        assert response.json()["relation"] == "نفسه"

    def test_missing_person_is_404(self, client, auth, sample_family) -> None:
        response = client.get(
            f"/api/v1/relationship?a={sample_family['3']}&b=9999", headers=auth("viewer")
        )
        assert response.status_code == 404


class TestRelatives:
    def test_nephews_and_nieces(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['5']}/relatives", headers=auth("viewer")
        ).json()
        ids = {item["id"] for item in body["nephews_nieces"]}
        assert ids == {
            sample_family["9"],
            sample_family["10"],
            sample_family["11"],
            sample_family["13"],
        }

    def test_own_children_are_not_reported_as_in_laws(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/relatives", headers=auth("viewer")
        ).json()
        own = {sample_family["3"], sample_family["4"], sample_family["5"]}
        assert own.isdisjoint({item["id"] for item in body["in_laws"]})

    def test_summary_counts_match_the_lists(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['5']}/relatives", headers=auth("viewer")
        ).json()
        buckets = [
            "uncles_aunts",
            "cousins",
            "nephews_nieces",
            "in_laws",
            "grand_uncles",
            "grand_aunts",
        ]
        for bucket in buckets:
            assert body["summary"][bucket] == len(body[bucket])


class TestFamilySummary:
    def test_counts(self, client, auth, sample_family) -> None:
        body = client.get(
            f"/api/v1/persons/{sample_family['1']}/family-summary", headers=auth("viewer")
        ).json()
        assert body["children"] == 3
        assert body["spouses"] == 1
        assert body["descendants"] == 8
