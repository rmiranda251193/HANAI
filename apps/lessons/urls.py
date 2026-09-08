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
    # --- teacher lesson builder (Step 26) ---
    path("<slug:slug>/build/", views.lesson_build, name="build"),
    path("<slug:slug>/build/basics/", views.lesson_update_basics, name="update_basics"),
    path(
        "<slug:slug>/build/objectives/",
        views.lesson_update_objectives,
        name="update_objectives",
    ),
    path(
        "<slug:slug>/build/concepts/",
        views.lesson_update_concepts,
        name="update_concepts",
    ),
    path(
        "<slug:slug>/build/activities/add/",
        views.lesson_activity_add,
        name="activity_add",
    ),
    path(
        "<slug:slug>/build/activities/<uuid:activity_id>/edit/",
        views.lesson_activity_edit,
        name="activity_edit",
    ),
    path(
        "<slug:slug>/build/activities/<uuid:activity_id>/delete/",
        views.lesson_activity_delete,
        name="activity_delete",
    ),
    path(
        "<slug:slug>/build/activities/<uuid:activity_id>/move/",
        views.lesson_activity_move,
        name="activity_move",
    ),
    path("<slug:slug>/preview/", views.lesson_preview, name="preview"),
    path("<slug:slug>/publish/", views.lesson_publish, name="publish"),
    path(
        "<slug:slug>/activities/<uuid:activity_id>/practice/",
        views.student_activity_practice,
        name="student_activity_practice",
    ),
    path("<slug:slug>/", views.lesson_detail, name="detail"),
]
