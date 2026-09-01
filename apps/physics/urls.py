from django.urls import path

from . import views

app_name = "physics_lab"

urlpatterns = [
    path("", views.physics_lab_index, name="index"),
    path("<slug:slug>/", views.physics_lab_detail, name="detail"),
    path(
        "<slug:slug>/experiment/predict/",
        views.experiment_predict,
        name="experiment_predict",
    ),
    path(
        "<slug:slug>/experiment/observe/",
        views.experiment_observe,
        name="experiment_observe",
    ),
    path(
        "<slug:slug>/experiment/explain/",
        views.experiment_explain,
        name="experiment_explain",
    ),
]
