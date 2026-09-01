from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path("", views.student_home, name="home"),
    path("lessons/", views.student_lessons, name="lessons"),
    path("tutor/<slug:slug>/", views.tutor_view, name="tutor"),
]
