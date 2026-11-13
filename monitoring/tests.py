from datetime import date, timedelta
from io import StringIO
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CatchRecord, FishSpecies, Inspection, LandingSite
from .views import csv_safe

User = get_user_model()


class BaseTestCase(TestCase):
    def setUp(self):
        self.site = LandingSite.objects.create(name="Test landing site")
        self.species = FishSpecies.objects.create(
            name="Test fish", minimum_length_cm=Decimal("40.00"), legal_reference="Test regulation"
        )
        self.staff = User.objects.create_user("officer", password="pass-12345", is_staff=True)
        self.clerk = User.objects.create_user("clerk", password="pass-12345")

    def make_catch(self, length="45.00", **kwargs):
        data = {
            "landing_site": self.site,
            "species": self.species,
            "quantity": 1,
            "measured_length_cm": Decimal(length) if length is not None else None,
            "catch_date": date.today(),
        }
        data.update(kwargs)
        return CatchRecord.objects.create(**data)


class CatchAssessmentTests(BaseTestCase):
    def test_undersized_fish_is_flagged(self):
        self.assertEqual(self.make_catch("35.00").status, CatchRecord.Status.FLAGGED)

    def test_fish_at_minimum_is_compliant(self):
        self.assertEqual(self.make_catch("40.00").status, CatchRecord.Status.COMPLIANT)

    def test_missing_measurement_is_pending(self):
        self.assertEqual(self.make_catch(None).status, CatchRecord.Status.PENDING)

    def test_species_without_minimum_is_pending(self):
        species = FishSpecies.objects.create(name="Unregulated fish")
        self.assertEqual(self.make_catch("10.00", species=species).status, CatchRecord.Status.PENDING)

    def test_changing_species_minimum_rechecks_existing_catches(self):
        record = self.make_catch("45.00")
        self.assertEqual(record.status, CatchRecord.Status.COMPLIANT)
        self.species.minimum_length_cm = Decimal("50.00")
        self.species.save()
        record.refresh_from_db()
        self.assertEqual(record.status, CatchRecord.Status.FLAGGED)

    def test_removing_species_minimum_makes_catches_pending(self):
        record = self.make_catch("45.00")
        self.species.minimum_length_cm = None
        self.species.save()
        record.refresh_from_db()
        self.assertEqual(record.status, CatchRecord.Status.PENDING)

    def test_reference_format(self):
        self.assertRegex(self.make_catch().reference, r"^LW-\d{4,}$")


class AccessTests(BaseTestCase):
    def test_pages_require_login(self):
        for name in ["dashboard", "catch_list", "inspection_list", "reports", "site_list", "export_catches"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("login"), response["Location"])

    def test_all_pages_load_for_logged_in_user(self):
        self.client.force_login(self.staff)
        record = self.make_catch()
        urls = [
            reverse(n) for n in [
                "dashboard", "catch_list", "catch_create", "inspection_list", "inspection_create", "site_list",
                "site_create", "species_list", "species_create", "fisher_list", "fisher_create", "boat_list",
                "boat_create", "reports",
            ]
        ] + [reverse("catch_detail", args=[record.pk]), reverse("catch_edit", args=[record.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_non_staff_cannot_change_species_or_sites(self):
        self.client.force_login(self.clerk)
        self.assertEqual(self.client.get(reverse("species_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("species_edit", args=[self.species.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("site_create")).status_code, 403)

    def test_non_staff_cannot_delete_catch(self):
        record = self.make_catch()
        self.client.force_login(self.clerk)
        self.assertEqual(self.client.post(reverse("catch_delete", args=[record.pk])).status_code, 403)
        self.assertTrue(CatchRecord.objects.filter(pk=record.pk).exists())

    def test_non_staff_can_only_edit_own_catches(self):
        other = self.make_catch(recorded_by=self.staff)
        own = self.make_catch(recorded_by=self.clerk)
        self.client.force_login(self.clerk)
        self.assertEqual(self.client.get(reverse("catch_edit", args=[other.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("catch_edit", args=[own.pk])).status_code, 200)


class CatchFormTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.clerk)

    def post_catch(self, **overrides):
        data = {
            "landing_site": self.site.pk,
            "species": self.species.pk,
            "quantity": 3,
            "measured_length_cm": "38.5",
            "catch_date": timezone.localdate().isoformat(),
            "notes": "",
        }
        data.update(overrides)
        return self.client.post(reverse("catch_create"), data)

    def test_create_catch_records_user_and_flags(self):
        response = self.post_catch()
        record = CatchRecord.objects.get()
        self.assertRedirects(response, reverse("catch_detail", args=[record.pk]))
        self.assertEqual(record.recorded_by, self.clerk)
        self.assertEqual(record.status, CatchRecord.Status.FLAGGED)

    def test_future_date_rejected(self):
        response = self.post_catch(catch_date=(timezone.localdate() + timedelta(days=1)).isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CatchRecord.objects.exists())

    def test_zero_or_negative_length_rejected(self):
        for value in ["0", "-5"]:
            self.post_catch(measured_length_cm=value)
        self.assertFalse(CatchRecord.objects.exists())

    def test_inactive_site_not_offered(self):
        closed = LandingSite.objects.create(name="Closed site", is_active=False)
        response = self.post_catch(landing_site=closed.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CatchRecord.objects.exists())

    def test_save_and_add_another_returns_to_form(self):
        response = self.post_catch(save_another="1")
        self.assertRedirects(response, reverse("catch_create"))


class SpeciesFormTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_minimum_requires_legal_reference(self):
        response = self.client.post(reverse("species_create"), {"name": "New fish", "minimum_length_cm": "30", "is_active": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FishSpecies.objects.filter(name="New fish").exists())

    def test_duplicate_name_ignoring_case_rejected(self):
        self.client.post(reverse("species_create"), {"name": "TEST FISH", "is_active": "on"})
        self.assertEqual(FishSpecies.objects.filter(name__iexact="test fish").count(), 1)


class ListAndExportTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.small = self.make_catch("30.00")
        self.big = self.make_catch("60.00", catch_date=date.today() - timedelta(days=10))

    def test_status_filter(self):
        response = self.client.get(reverse("catch_list"), {"status": "flagged"})
        self.assertEqual(list(response.context["records"]), [self.small])

    def test_search_by_reference(self):
        response = self.client.get(reverse("catch_list"), {"q": self.big.reference})
        self.assertEqual(list(response.context["records"]), [self.big])

    def test_date_filter(self):
        response = self.client.get(reverse("catch_list"), {"date_from": date.today().isoformat()})
        self.assertEqual(list(response.context["records"]), [self.small])

    def test_export_respects_filters(self):
        response = self.client.get(reverse("export_catches"), {"status": "compliant"})
        content = response.content.decode("utf-8-sig")
        self.assertIn(self.big.reference, content)
        self.assertNotIn(self.small.reference, content)

    def test_csv_safe_neutralises_formulas(self):
        self.assertEqual(csv_safe("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(csv_safe("Nile perch"), "Nile perch")
        self.assertEqual(csv_safe(None), "")

    def test_reports_date_range(self):
        response = self.client.get(reverse("reports"), {"date_from": date.today().isoformat()})
        self.assertEqual(response.context["totals"]["records"], 1)

    def test_inspection_prefilled_from_catch(self):
        response = self.client.get(reverse("inspection_create"), {"catch": self.small.pk})
        self.assertEqual(response.context["form"].initial["catch_record"], self.small.pk)

    def test_staff_can_delete_catch_with_inspections(self):
        Inspection.objects.create(catch_record=self.small, findings="x")
        response = self.client.post(reverse("catch_delete", args=[self.small.pk]))
        self.assertRedirects(response, reverse("catch_list"))
        self.assertFalse(Inspection.objects.exists())


class SeedDemoTests(TestCase):
    def test_seed_demo_creates_data_once(self):
        call_command("seed_demo", verbosity=0, stdout=StringIO())
        count = CatchRecord.objects.count()
        self.assertGreater(count, 0)
        call_command("seed_demo", verbosity=0, stdout=StringIO())
        self.assertEqual(CatchRecord.objects.count(), count)
