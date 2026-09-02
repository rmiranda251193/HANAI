from django.urls import path

from . import views

app_name = "students"

urlpatterns = [
    path("", views.student_home, name="home"),
    path("lessons/", views.student_lessons, name="lessons"),
    path("progress/", views.student_progress, name="progress"),
    path("tutor/<slug:slug>/", views.tutor_view, name="tutor"),
    path("insights/<slug:slug>/", views.lesson_insights, name="insights"),
    path(
        "insights/<slug:slug>/observations/<int:observation_id>/decision/",
        views.misconception_decision,
        name="misconception_decision",
    ),
]
