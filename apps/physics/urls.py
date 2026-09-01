from django.urls import path

from . import views

app_name = "physics_lab"

urlpatterns = [
    path("", views.physics_lab_index, name="index"),
    path("<slug:slug>/", views.physics_lab_detail, name="detail"),
]
