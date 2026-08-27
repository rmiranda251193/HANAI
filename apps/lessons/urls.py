from django.urls import path

from . import views

app_name = "lessons"

urlpatterns = [
    path("", views.lesson_list, name="list"),
    path("create/", views.lesson_create, name="create"),
    path("<slug:slug>/generate/", views.lesson_generate, name="generate"),
    path(
        "<slug:slug>/drafts/<uuid:draft_id>/review/",
        views.lesson_review,
        name="review",
    ),
    path(
        "<slug:slug>/drafts/<uuid:draft_id>/issues/<uuid:issue_id>/decision/",
        views.lesson_review_issue_decision,
        name="review_issue_decision",
    ),
    path(
        "<slug:slug>/drafts/<uuid:draft_id>/reviews/<uuid:review_id>/finalize/",
        views.lesson_finalize,
        name="finalize",
    ),
    path("<slug:slug>/", views.lesson_detail, name="detail"),
]
