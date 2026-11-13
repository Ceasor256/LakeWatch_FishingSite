from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Catches
    path("catches/", views.catch_list, name="catch_list"),
    path("catches/new/", views.catch_create, name="catch_create"),
    path("catches/<int:pk>/", views.catch_detail, name="catch_detail"),
    path("catches/<int:pk>/edit/", views.catch_edit, name="catch_edit"),
    path("catches/<int:pk>/delete/", views.catch_delete, name="catch_delete"),
    # Inspections
    path("inspections/", views.inspection_list, name="inspection_list"),
    path("inspections/new/", views.inspection_create, name="inspection_create"),
    path("inspections/<int:pk>/edit/", views.inspection_edit, name="inspection_edit"),
    # Registry
    path("sites/", views.site_list, name="site_list"),
    path("sites/new/", views.site_create, name="site_create"),
    path("sites/<int:pk>/edit/", views.site_edit, name="site_edit"),
    path("species/", views.species_list, name="species_list"),
    path("species/new/", views.species_create, name="species_create"),
    path("species/<int:pk>/edit/", views.species_edit, name="species_edit"),
    path("fishers/", views.fisher_list, name="fisher_list"),
    path("fishers/new/", views.fisher_create, name="fisher_create"),
    path("fishers/<int:pk>/edit/", views.fisher_edit, name="fisher_edit"),
    path("boats/", views.boat_list, name="boat_list"),
    path("boats/new/", views.boat_create, name="boat_create"),
    path("boats/<int:pk>/edit/", views.boat_edit, name="boat_edit"),
    # Reports
    path("reports/", views.reports, name="reports"),
    path("reports/export/catches.csv", views.export_catches, name="export_catches"),
]
