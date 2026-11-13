import csv
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from .forms import BoatForm, CatchRecordForm, FisherForm, FishSpeciesForm, InspectionForm, LandingSiteForm
from .models import Boat, CatchRecord, Fisher, FishSpecies, Inspection, LandingSite

PAGE_SIZE = 25


# --------------------------------------------------------------------------- helpers

def staff_required(view):
    """Logged-in users with 'Staff status' only (set in the admin). Others get a 403 page."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff users can do this.")
        return view(request, *args, **kwargs)

    return wrapper


def paginate(request, queryset, per_page=PAGE_SIZE):
    page = Paginator(queryset, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def form_view(request, form, *, title, eyebrow, back_url, submit_label, success_message, on_save, extra=None):
    """Shared create/edit flow: validate, save, flash a message and redirect."""
    if request.method == "POST" and form.is_valid():
        response = on_save(form)
        messages.success(request, success_message)
        return response
    context = {
        "form": form,
        "page_title": title,
        "eyebrow": eyebrow,
        "back_url": back_url,
        "submit_label": submit_label,
    }
    context.update(extra or {})
    return render(request, "monitoring/form_page.html", context)


def save_then_redirect(url_name):
    def on_save(form):
        form.save()
        return redirect(url_name)

    return on_save


def parse_date_range(request):
    date_from = parse_date(request.GET.get("date_from", "") or "")
    date_to = parse_date(request.GET.get("date_to", "") or "")
    return date_from, date_to


def filter_catches(request):
    """Apply the search/filter options from the catch list (also used by the CSV export)."""
    records = CatchRecord.objects.select_related("landing_site", "species", "fisher", "boat", "recorded_by")
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    site = request.GET.get("site", "").strip()
    species = request.GET.get("species", "").strip()
    date_from, date_to = parse_date_range(request)

    if search:
        lookup = (
            Q(species__name__icontains=search)
            | Q(landing_site__name__icontains=search)
            | Q(fisher__full_name__icontains=search)
            | Q(boat__name_or_number__icontains=search)
            | Q(notes__icontains=search)
        )
        reference = search.upper().removeprefix("LW-")
        if reference.isdigit():
            lookup |= Q(pk=int(reference))
        records = records.filter(lookup)
    if status in CatchRecord.Status.values:
        records = records.filter(status=status)
    if site.isdigit():
        records = records.filter(landing_site_id=int(site))
    if species.isdigit():
        records = records.filter(species_id=int(species))
    if date_from:
        records = records.filter(catch_date__gte=date_from)
    if date_to:
        records = records.filter(catch_date__lte=date_to)

    filters = {
        "q": search,
        "status": status,
        "site": site,
        "species": species,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
    }
    return records, filters


def can_edit_catch(user, record):
    return user.is_staff or record.recorded_by_id == user.id


def csv_safe(value):
    """Stop spreadsheet apps from treating a cell as a formula (CSV injection)."""
    text = "" if value is None else str(value)
    if text and text[0] in "=+-@\t\r":
        return "'" + text
    return text


# --------------------------------------------------------------------------- dashboard

@login_required
def dashboard(request):
    today = timezone.localdate()
    first_day = today - timedelta(days=6)
    catches = CatchRecord.objects.select_related("landing_site", "species", "fisher")

    per_day = dict(
        catches.filter(catch_date__range=(first_day, today))
        .values_list("catch_date")
        .annotate(total=Count("id"))
    )
    days = [first_day + timedelta(days=i) for i in range(7)]

    counts = catches.aggregate(
        total=Count("id"),
        today=Count("id", filter=Q(catch_date=today)),
        flagged=Count("id", filter=Q(status=CatchRecord.Status.FLAGGED)),
        pending=Count("id", filter=Q(status=CatchRecord.Status.PENDING)),
    )
    context = {
        "total_catches": counts["total"],
        "today_catches": counts["today"],
        "flagged_count": counts["flagged"],
        "pending_count": counts["pending"],
        "site_count": LandingSite.objects.filter(is_active=True).count(),
        "species_count": FishSpecies.objects.filter(is_active=True).count(),
        "recent_catches": catches[:7],
        "attention_catches": catches.exclude(status=CatchRecord.Status.COMPLIANT)[:6],
        "chart_labels": [d.strftime("%a") for d in days],
        "chart_values": [per_day.get(d, 0) for d in days],
        "needs_setup": not LandingSite.objects.exists() or not FishSpecies.objects.exists(),
    }
    return render(request, "monitoring/dashboard.html", context)


# --------------------------------------------------------------------------- catches

@login_required
def catch_list(request):
    records, filters = filter_catches(request)
    page, query_string = paginate(request, records)
    context = {
        "page": page,
        "records": page.object_list,
        "filters": filters,
        "query_string": query_string,
        "status_choices": CatchRecord.Status.choices,
        "sites": LandingSite.objects.all(),
        "species_options": FishSpecies.objects.all(),
        "has_filters": any(filters.values()),
    }
    return render(request, "monitoring/catch_list.html", context)


@login_required
def catch_create(request):
    form = CatchRecordForm(request.POST or None)

    def on_save(form):
        record = form.save(commit=False)
        record.recorded_by = request.user
        record.save()
        if record.status == CatchRecord.Status.FLAGGED:
            messages.warning(request, f"{record.reference} is below the configured minimum size and has been flagged for review.")
        if "save_another" in request.POST:
            return redirect("catch_create")
        return redirect("catch_detail", pk=record.pk)

    return form_view(
        request, form,
        title="Register a fish catch", eyebrow="Catch management", back_url="catch_list",
        submit_label="Save catch record", success_message="Catch record saved and size status checked.",
        on_save=on_save, extra={"allow_save_another": True},
    )


@login_required
def catch_edit(request, pk):
    record = get_object_or_404(CatchRecord, pk=pk)
    if not can_edit_catch(request.user, record):
        raise PermissionDenied("Only staff or the person who recorded this catch can edit it.")
    form = CatchRecordForm(request.POST or None, instance=record)
    return form_view(
        request, form,
        title=f"Edit {record.reference}", eyebrow="Catch management", back_url="catch_list",
        submit_label="Save changes", success_message="Catch record updated and size status re-checked.",
        on_save=lambda f: redirect("catch_detail", pk=f.save().pk),
    )


@login_required
def catch_detail(request, pk):
    record = get_object_or_404(
        CatchRecord.objects.select_related("species", "landing_site", "fisher", "boat", "recorded_by"), pk=pk
    )
    context = {
        "record": record,
        "inspections": record.inspections.select_related("inspector"),
        "can_edit": can_edit_catch(request.user, record),
    }
    return render(request, "monitoring/catch_detail.html", context)


@staff_required
def catch_delete(request, pk):
    record = get_object_or_404(CatchRecord.objects.select_related("species", "landing_site"), pk=pk)
    if request.method == "POST":
        reference = record.reference
        record.delete()
        messages.success(request, f"{reference} and its inspections were deleted.")
        return redirect("catch_list")
    return render(request, "monitoring/confirm_delete.html", {
        "object_label": str(record),
        "warning": f"This also deletes {record.inspections.count()} inspection record(s) linked to it.",
        "cancel_url": reverse("catch_detail", args=[record.pk]),
    })


@login_required
def export_catches(request):
    records, _ = filter_catches(request)
    stamp = timezone.localdate().isoformat()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="lakewatch-catches-{stamp}.csv"'
    response.write("﻿")  # BOM so Excel opens the file as UTF-8
    writer = csv.writer(response)
    writer.writerow([
        "Reference", "Date", "Landing site", "Species", "Quantity", "Measured length (cm)",
        "Configured minimum (cm)", "Status", "Fisher", "Boat", "Recorded by", "Notes",
    ])
    for r in records.iterator():
        writer.writerow([csv_safe(v) for v in (
            r.reference, r.catch_date, r.landing_site.name, r.species.name, r.quantity,
            r.measured_length_cm, r.species.minimum_length_cm, r.get_status_display(),
            r.fisher, r.boat, r.recorded_by, r.notes,
        )])
    return response


# --------------------------------------------------------------------------- inspections

@login_required
def inspection_list(request):
    inspections = Inspection.objects.select_related(
        "catch_record", "catch_record__landing_site", "catch_record__species", "inspector"
    )
    outcome = request.GET.get("outcome", "")
    if outcome in Inspection.Outcome.values:
        inspections = inspections.filter(outcome=outcome)
    page, query_string = paginate(request, inspections)
    context = {
        "page": page,
        "inspections": page.object_list,
        "query_string": query_string,
        "outcome": outcome,
        "outcome_choices": Inspection.Outcome.choices,
    }
    return render(request, "monitoring/inspection_list.html", context)


@login_required
def inspection_create(request):
    initial = {}
    catch_id = request.GET.get("catch", "")
    if catch_id.isdigit():
        initial["catch_record"] = int(catch_id)
    form = InspectionForm(request.POST or None, initial=initial)

    def on_save(form):
        inspection = form.save(commit=False)
        inspection.inspector = request.user
        inspection.save()
        return redirect("catch_detail", pk=inspection.catch_record_id)

    return form_view(
        request, form,
        title="Record an inspection", eyebrow="Enforcement", back_url="inspection_list",
        submit_label="Save inspection", success_message="Inspection recorded.", on_save=on_save,
    )


@login_required
def inspection_edit(request, pk):
    inspection = get_object_or_404(Inspection, pk=pk)
    if not (request.user.is_staff or inspection.inspector_id == request.user.id):
        raise PermissionDenied("Only staff or the original inspector can edit this inspection.")
    form = InspectionForm(request.POST or None, instance=inspection)
    return form_view(
        request, form,
        title=f"Edit inspection #{inspection.pk}", eyebrow="Enforcement", back_url="inspection_list",
        submit_label="Save changes", success_message="Inspection updated.",
        on_save=lambda f: redirect("catch_detail", pk=f.save().catch_record_id),
    )


# --------------------------------------------------------------------------- registry: sites, species, fishers, boats

@login_required
def site_list(request):
    sites = LandingSite.objects.annotate(catch_count=Count("catches")).order_by("-is_active", "name")
    return render(request, "monitoring/site_list.html", {"sites": sites})


@staff_required
def site_create(request):
    return _site_form(request, LandingSiteForm(request.POST or None), "Add landing site", "Landing site added.")


@staff_required
def site_edit(request, pk):
    site = get_object_or_404(LandingSite, pk=pk)
    return _site_form(request, LandingSiteForm(request.POST or None, instance=site), f"Edit {site.name}", "Landing site updated.")


def _site_form(request, form, title, message):
    return form_view(
        request, form, title=title, eyebrow="Site management", back_url="site_list",
        submit_label="Save landing site", success_message=message,
        on_save=save_then_redirect("site_list"),
    )


@login_required
def species_list(request):
    species = FishSpecies.objects.annotate(
        catch_count=Count("catches"),
        flagged_count=Count("catches", filter=Q(catches__status=CatchRecord.Status.FLAGGED)),
    ).order_by("-is_active", "name")
    return render(request, "monitoring/species_list.html", {"species_list": species})


@staff_required
def species_create(request):
    return _species_form(request, FishSpeciesForm(request.POST or None), "Add fish species", "Fish species saved.")


@staff_required
def species_edit(request, pk):
    species = get_object_or_404(FishSpecies, pk=pk)
    return _species_form(
        request, FishSpeciesForm(request.POST or None, instance=species), f"Edit {species.name}",
        "Species updated. Existing catches of this species were re-checked against the new size rule.",
    )


def _species_form(request, form, title, message):
    return form_view(
        request, form, title=title, eyebrow="Species & legal limits", back_url="species_list",
        submit_label="Save species", success_message=message,
        on_save=save_then_redirect("species_list"),
        extra={"show_legal_note": True},
    )


@login_required
def fisher_list(request):
    fishers = Fisher.objects.select_related("landing_site").annotate(catch_count=Count("catches")).order_by("full_name")
    search = request.GET.get("q", "").strip()
    if search:
        fishers = fishers.filter(
            Q(full_name__icontains=search) | Q(registration_number__icontains=search) | Q(phone__icontains=search)
        )
    page, query_string = paginate(request, fishers)
    return render(request, "monitoring/fisher_list.html", {
        "page": page, "fishers": page.object_list, "query_string": query_string, "q": search,
    })


@login_required
def fisher_create(request):
    return _fisher_form(request, FisherForm(request.POST or None), "Register a fisher", "Fisher registered.")


@login_required
def fisher_edit(request, pk):
    fisher = get_object_or_404(Fisher, pk=pk)
    return _fisher_form(request, FisherForm(request.POST or None, instance=fisher), f"Edit {fisher.full_name}", "Fisher updated.")


def _fisher_form(request, form, title, message):
    return form_view(
        request, form, title=title, eyebrow="People & boats", back_url="fisher_list",
        submit_label="Save fisher", success_message=message,
        on_save=save_then_redirect("fisher_list"),
    )


@login_required
def boat_list(request):
    boats = Boat.objects.select_related("landing_site", "owner").annotate(catch_count=Count("catches")).order_by("name_or_number")
    page, query_string = paginate(request, boats)
    return render(request, "monitoring/boat_list.html", {"page": page, "boats": page.object_list, "query_string": query_string})


@login_required
def boat_create(request):
    return _boat_form(request, BoatForm(request.POST or None), "Register a boat", "Boat registered.")


@login_required
def boat_edit(request, pk):
    boat = get_object_or_404(Boat, pk=pk)
    return _boat_form(request, BoatForm(request.POST or None, instance=boat), f"Edit {boat.name_or_number}", "Boat updated.")


def _boat_form(request, form, title, message):
    return form_view(
        request, form, title=title, eyebrow="People & boats", back_url="boat_list",
        submit_label="Save boat", success_message=message,
        on_save=save_then_redirect("boat_list"),
    )


# --------------------------------------------------------------------------- reports

@login_required
def reports(request):
    date_from, date_to = parse_date_range(request)
    records = CatchRecord.objects.all()
    if date_from:
        records = records.filter(catch_date__gte=date_from)
    if date_to:
        records = records.filter(catch_date__lte=date_to)

    flagged = Q(status=CatchRecord.Status.FLAGGED)
    totals = records.aggregate(
        records=Count("id"),
        quantity=Sum("quantity"),
        flagged=Count("id", filter=flagged),
        compliant=Count("id", filter=Q(status=CatchRecord.Status.COMPLIANT)),
        pending=Count("id", filter=Q(status=CatchRecord.Status.PENDING)),
    )
    species_summary = (
        records.values("species__name")
        .annotate(records=Count("id"), quantity=Sum("quantity"), flagged=Count("id", filter=flagged))
        .order_by("-quantity")
    )
    site_summary = (
        records.values("landing_site__name")
        .annotate(records=Count("id"), quantity=Sum("quantity"), flagged=Count("id", filter=flagged))
        .order_by("-records")
    )
    flagged_rate = round(100 * totals["flagged"] / totals["records"], 1) if totals["records"] else 0

    export_params = {k: v for k, v in (("date_from", date_from), ("date_to", date_to)) if v}
    context = {
        "totals": totals,
        "total_quantity": totals["quantity"] or 0,
        "flagged_rate": flagged_rate,
        "species_summary": species_summary,
        "site_summary": site_summary,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "export_query": "&".join(f"{k}={v.isoformat()}" for k, v in export_params.items()),
    }
    return render(request, "monitoring/reports.html", context)
