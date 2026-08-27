from django.urls import path

from . import views

app_name = "lessons"

urlpatterns = [
    path("", views.lesson_list, name="list"),
    path("create/", views.lesson_create, name="create"),
    path("<slug:slug>/generate/", views.lesson_generate, name="generate"),
    path("<slug:slug>/", views.lesson_detail, name="detail"),
]
