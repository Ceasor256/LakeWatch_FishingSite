from django import forms
from django.utils import timezone

from .models import Boat, CatchRecord, Fisher, FishSpecies, Inspection, LandingSite


class StyledModelForm(forms.ModelForm):
    """Adds the site's CSS class to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " form-control").strip()

    def limit_to_active(self, field_name, queryset):
        """Only offer active items, but keep the currently selected one when editing."""
        current_id = getattr(self.instance, f"{field_name}_id", None)
        active = queryset.filter(is_active=True)
        if current_id:
            active = queryset.filter(is_active=True) | queryset.filter(pk=current_id)
        self.fields[field_name].queryset = active.distinct()

    def clean_unique_name(self, field_name):
        """Reject names that only differ by upper/lower case from an existing one."""
        value = self.cleaned_data[field_name].strip()
        model = self._meta.model
        clash = model.objects.filter(**{f"{field_name}__iexact": value}).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(f"“{value}” already exists.")
        return value


class CatchRecordForm(StyledModelForm):
    class Meta:
        model = CatchRecord
        fields = ["landing_site", "species", "fisher", "boat", "quantity", "measured_length_cm", "catch_date", "notes"]
        labels = {"measured_length_cm": "Measured length (cm)"}
        widgets = {
            "catch_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional notes from the attendant"}),
            "measured_length_cm": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "placeholder": "e.g. 45.5"}),
            "quantity": forms.NumberInput(attrs={"min": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit_to_active("landing_site", LandingSite.objects.all())
        self.limit_to_active("species", FishSpecies.objects.all())
        self.fields["fisher"].queryset = Fisher.objects.select_related("landing_site")
        self.fields["boat"].queryset = Boat.objects.select_related("landing_site")
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault("catch_date", timezone.localdate())
        self.fields["catch_date"].widget.attrs["max"] = timezone.localdate().isoformat()

    def clean_catch_date(self):
        catch_date = self.cleaned_data["catch_date"]
        if catch_date > timezone.localdate():
            raise forms.ValidationError("The catch date can't be in the future.")
        return catch_date


class InspectionForm(StyledModelForm):
    class Meta:
        model = Inspection
        fields = ["catch_record", "findings", "action_taken", "outcome"]
        labels = {"catch_record": "Catch record"}
        widgets = {
            "findings": forms.Textarea(attrs={"rows": 4, "placeholder": "What did the inspection find?"}),
            "action_taken": forms.Textarea(attrs={"rows": 3, "placeholder": "Warning, follow-up, or other action"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["catch_record"].queryset = CatchRecord.objects.select_related("species", "landing_site")


class LandingSiteForm(StyledModelForm):
    class Meta:
        model = LandingSite
        fields = ["name", "district", "water_body", "is_active"]
        labels = {"is_active": "Active (available for new catch records)"}

    def clean_name(self):
        return self.clean_unique_name("name")


class FishSpeciesForm(StyledModelForm):
    class Meta:
        model = FishSpecies
        fields = ["name", "minimum_length_cm", "legal_reference", "is_active"]
        labels = {"minimum_length_cm": "Minimum legal length (cm)", "is_active": "Active (available for new catch records)"}
        widgets = {"minimum_length_cm": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"})}

    def clean_name(self):
        return self.clean_unique_name("name")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("minimum_length_cm") is not None and not (cleaned.get("legal_reference") or "").strip():
            self.add_error("legal_reference", "Please say where this minimum size comes from (law, regulation or official guidance).")
        return cleaned


class FisherForm(StyledModelForm):
    class Meta:
        model = Fisher
        fields = ["full_name", "registration_number", "phone", "landing_site"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit_to_active("landing_site", LandingSite.objects.all())


class BoatForm(StyledModelForm):
    class Meta:
        model = Boat
        fields = ["name_or_number", "registration_number", "landing_site", "owner"]
        labels = {"name_or_number": "Boat name or number"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit_to_active("landing_site", LandingSite.objects.all())
