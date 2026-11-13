from django.contrib import admin

from .models import Boat, CatchRecord, Fisher, FishSpecies, Inspection, LandingSite

admin.site.site_header = "LakeWatch administration"
admin.site.site_title = "LakeWatch admin"
admin.site.index_title = "Manage users, records and settings"


@admin.register(LandingSite)
class LandingSiteAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "water_body", "is_active")
    search_fields = ("name", "district", "water_body")
    list_filter = ("is_active", "district")


@admin.register(FishSpecies)
class FishSpeciesAdmin(admin.ModelAdmin):
    list_display = ("name", "minimum_length_cm", "legal_reference", "is_active")
    search_fields = ("name", "legal_reference")
    list_filter = ("is_active",)


@admin.register(Fisher)
class FisherAdmin(admin.ModelAdmin):
    list_display = ("full_name", "registration_number", "phone", "landing_site")
    search_fields = ("full_name", "registration_number", "phone")
    list_filter = ("landing_site",)


@admin.register(Boat)
class BoatAdmin(admin.ModelAdmin):
    list_display = ("name_or_number", "registration_number", "landing_site", "owner")
    search_fields = ("name_or_number", "registration_number")
    list_filter = ("landing_site",)
    autocomplete_fields = ("owner",)


class InspectionInline(admin.TabularInline):
    model = Inspection
    extra = 0
    fields = ("outcome", "findings", "action_taken", "inspector", "inspected_at")
    readonly_fields = ("inspected_at",)


@admin.register(CatchRecord)
class CatchRecordAdmin(admin.ModelAdmin):
    list_display = ("reference", "catch_date", "landing_site", "species", "quantity", "measured_length_cm", "status")
    list_filter = ("status", "landing_site", "species", "catch_date")
    search_fields = ("species__name", "landing_site__name", "fisher__full_name", "boat__name_or_number")
    date_hierarchy = "catch_date"
    readonly_fields = ("status", "recorded_by", "created_at", "updated_at")
    autocomplete_fields = ("fisher", "boat")
    list_select_related = ("landing_site", "species")
    inlines = [InspectionInline]

    def save_model(self, request, obj, form, change):
        if not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "catch_record", "inspector", "outcome", "inspected_at")
    list_filter = ("outcome", "inspected_at")
    search_fields = ("findings", "action_taken", "catch_record__species__name", "catch_record__landing_site__name")
    list_select_related = ("catch_record__species", "catch_record__landing_site", "inspector")
