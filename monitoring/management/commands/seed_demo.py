"""Fill an empty database with clearly-labelled sample data so new users can explore the app.

    python manage.py seed_demo           # only runs on an empty database
    python manage.py seed_demo --force   # add demo data even if records exist

The minimum sizes created here are made up for demonstration. They are NOT legal limits.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from monitoring.models import Boat, CatchRecord, Fisher, FishSpecies, Inspection, LandingSite

DEMO_REFERENCE = "DEMO VALUE ONLY - not a legal limit. Replace with a verified regulation."

SITES = [
    ("Demo Bay Landing", "Demo District", "Demo Lake"),
    ("Demo Point Landing", "Demo District", "Demo Lake"),
    ("Demo Island Landing", "Other District", "Demo Lake"),
]

# (name, demo minimum in cm or None, typical length range in cm)
SPECIES = [
    ("Nile perch (demo)", Decimal("50.00"), (35, 80)),
    ("Nile tilapia (demo)", Decimal("25.00"), (15, 35)),
    ("Catfish (demo)", None, (30, 70)),
]

FISHERS = ["Demo Fisher A", "Demo Fisher B", "Demo Fisher C", "Demo Fisher D"]


class Command(BaseCommand):
    help = "Create sample landing sites, species, fishers, boats, catches and inspections for practice."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Add demo data even if the database already has records.")
        parser.add_argument("--days", type=int, default=14, help="How many past days of catches to create (default 14).")

    @transaction.atomic
    def handle(self, *args, **options):
        if CatchRecord.objects.exists() and not options["force"]:
            self.stdout.write(self.style.WARNING(
                "The database already has catch records, so nothing was added. Use --force to add demo data anyway."
            ))
            return

        rng = random.Random(42)  # same data every run
        today = timezone.localdate()
        user = get_user_model().objects.filter(is_superuser=True).first()

        sites = [
            LandingSite.objects.get_or_create(name=name, defaults={"district": district, "water_body": water})[0]
            for name, district, water in SITES
        ]
        species = []
        for name, minimum, length_range in SPECIES:
            obj, _ = FishSpecies.objects.get_or_create(
                name=name,
                defaults={"minimum_length_cm": minimum, "legal_reference": DEMO_REFERENCE if minimum else ""},
            )
            species.append((obj, length_range))

        fishers = []
        for i, name in enumerate(FISHERS):
            fisher, _ = Fisher.objects.get_or_create(
                full_name=name,
                defaults={"registration_number": f"DEMO-F{i + 1:03d}", "landing_site": sites[i % len(sites)]},
            )
            fishers.append(fisher)
        boats = []
        for i, fisher in enumerate(fishers):
            boat, _ = Boat.objects.get_or_create(
                name_or_number=f"Demo Boat {i + 1}",
                defaults={"registration_number": f"DEMO-B{i + 1:03d}", "landing_site": fisher.landing_site, "owner": fisher},
            )
            boats.append(boat)

        created = 0
        for day_offset in range(options["days"]):
            day = today - timedelta(days=day_offset)
            for _ in range(rng.randint(1, 5)):
                sp, (low, high) = rng.choice(species)
                idx = rng.randrange(len(fishers))
                measured = None if rng.random() < 0.15 else Decimal(str(round(rng.uniform(low, high), 1)))
                CatchRecord.objects.create(
                    landing_site=fishers[idx].landing_site,
                    species=sp,
                    fisher=fishers[idx],
                    boat=boats[idx],
                    quantity=rng.randint(1, 30),
                    measured_length_cm=measured,
                    catch_date=day,
                    notes="Demo record",
                    recorded_by=user,
                )
                created += 1

        inspections = 0
        for record in CatchRecord.objects.filter(status=CatchRecord.Status.FLAGGED, notes="Demo record")[:5]:
            Inspection.objects.create(
                catch_record=record,
                inspector=user,
                findings="Demo inspection: measured fish below the configured minimum.",
                action_taken="Demo: verbal warning given to the fisher.",
                outcome=rng.choice([Inspection.Outcome.OPEN, Inspection.Outcome.WARNING, Inspection.Outcome.CLOSED]),
            )
            inspections += 1

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {len(sites)} sites, {len(species)} species, {len(fishers)} fishers, "
            f"{len(boats)} boats, {created} catches, {inspections} inspections."
        ))
        self.stdout.write("Demo minimum sizes are NOT legal limits - edit or delete them before real use.")
