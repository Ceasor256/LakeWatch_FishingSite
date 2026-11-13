from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

POSITIVE_LENGTH = [MinValueValidator(Decimal("0.01"), message="Length must be greater than 0 cm.")]


class LandingSite(models.Model):
    name = models.CharField(max_length=120, unique=True)
    district = models.CharField(max_length=100, blank=True)
    water_body = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True, help_text="Inactive sites stay in old records but can't be picked for new catches.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class FishSpecies(models.Model):
    name = models.CharField(max_length=120, unique=True)
    minimum_length_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=POSITIVE_LENGTH,
        help_text="Leave empty until the legal minimum has been verified. Catches of this species will stay 'Pending review'.",
    )
    legal_reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Official law, regulation, or fisheries guidance used to verify this limit.",
    )
    is_active = models.BooleanField(default=True, help_text="Inactive species can't be picked for new catches.")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Fish species"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep existing catch statuses in line with the (possibly changed) size rule.
        self.reassess_catches()

    def reassess_catches(self):
        """Recalculate the size status of every catch of this species. Returns the number of catches checked."""
        catches = CatchRecord.objects.filter(species=self)
        if self.minimum_length_cm is None:
            catches.update(status=CatchRecord.Status.PENDING)
        else:
            catches.filter(measured_length_cm__isnull=True).update(status=CatchRecord.Status.PENDING)
            catches.filter(measured_length_cm__lt=self.minimum_length_cm).update(status=CatchRecord.Status.FLAGGED)
            catches.filter(measured_length_cm__gte=self.minimum_length_cm).update(status=CatchRecord.Status.COMPLIANT)
        return catches.count()


class Fisher(models.Model):
    full_name = models.CharField(max_length=160)
    registration_number = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    landing_site = models.ForeignKey(LandingSite, on_delete=models.PROTECT, related_name="fishers", help_text="The site this fisher usually lands at.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        if self.registration_number:
            return f"{self.full_name} ({self.registration_number})"
        return self.full_name


class Boat(models.Model):
    name_or_number = models.CharField(max_length=100)
    registration_number = models.CharField(max_length=80, blank=True)
    landing_site = models.ForeignKey(LandingSite, on_delete=models.PROTECT, related_name="boats", help_text="The site this boat usually lands at.")
    owner = models.ForeignKey(Fisher, on_delete=models.SET_NULL, null=True, blank=True, related_name="boats")

    class Meta:
        ordering = ["name_or_number"]

    def __str__(self):
        return self.name_or_number


class CatchRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        COMPLIANT = "compliant", "Meets configured size"
        FLAGGED = "flagged", "Flagged for review"

    landing_site = models.ForeignKey(LandingSite, on_delete=models.PROTECT, related_name="catches")
    species = models.ForeignKey(FishSpecies, on_delete=models.PROTECT, related_name="catches")
    fisher = models.ForeignKey(Fisher, on_delete=models.SET_NULL, null=True, blank=True, related_name="catches")
    boat = models.ForeignKey(Boat, on_delete=models.SET_NULL, null=True, blank=True, related_name="catches")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)], help_text="Number of fish in this record.")
    measured_length_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=POSITIVE_LENGTH,
        help_text="Total length of the measured fish in centimetres. Leave empty if not measured.",
    )
    catch_date = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, editable=False)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-catch_date", "-created_at"]
        indexes = [
            models.Index(fields=["catch_date"]),
            models.Index(fields=["status"]),
        ]

    @property
    def reference(self):
        return f"LW-{self.pk:04d}" if self.pk else "LW-new"

    def assess_size(self):
        minimum = self.species.minimum_length_cm
        if self.measured_length_cm is None or minimum is None:
            self.status = self.Status.PENDING
        elif self.measured_length_cm < minimum:
            self.status = self.Status.FLAGGED
        else:
            self.status = self.Status.COMPLIANT
        return self.status

    def save(self, *args, **kwargs):
        self.assess_size()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} · {self.species} at {self.landing_site} ({self.catch_date:%d %b %Y})"


class Inspection(models.Model):
    class Outcome(models.TextChoices):
        OPEN = "open", "Open"
        WARNING = "warning", "Warning issued"
        REFERRED = "referred", "Referred for follow-up"
        CLOSED = "closed", "Closed"

    catch_record = models.ForeignKey(CatchRecord, on_delete=models.CASCADE, related_name="inspections")
    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    findings = models.TextField()
    action_taken = models.TextField(blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.OPEN)
    inspected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-inspected_at"]

    def __str__(self):
        return f"Inspection #{self.pk} - {self.get_outcome_display()}"
