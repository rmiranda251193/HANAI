"""URL fragments for the question bank and structured assessments.

These pattern lists are spliced into ``apps.teachers.urls`` and
``apps.students.urls`` (not included at the project root) so the resulting
paths stay under the existing ``/teacher/`` and ``/student/`` prefixes and
resolve in the existing ``teachers`` / ``students`` namespaces, exactly like
every other teacher- or student-facing route in the project.
"""

from django.urls import path

from . import views

teacher_patterns = [
    path("questions/", views.question_bank, name="question_bank"),
    path("questions/create/", views.question_create, name="question_create"),
    path("questions/<int:question_id>/edit/", views.question_edit, name="question_edit"),
    path(
        "questions/<int:question_id>/deactivate/",
        views.question_deactivate,
        name="question_deactivate",
    ),
    path("assessments/", views.assessment_list_teacher, name="assessment_list_teacher"),
    path("assessments/create/", views.assessment_create, name="assessment_create"),
    path(
        "assessments/<int:assessment_id>/",
        views.assessment_detail_teacher,
        name="assessment_detail_teacher",
    ),
    path(
        "assessments/<int:assessment_id>/questions/add/",
        views.assessment_add_question,
        name="assessment_add_question",
    ),
    path(
        "assessments/<int:assessment_id>/questions/<int:question_id>/remove/",
        views.assessment_remove_question,
        name="assessment_remove_question",
    ),
    path(
        "assessments/<int:assessment_id>/publish/",
        views.assessment_publish,
        name="assessment_publish",
    ),
    path(
        "assessments/<int:assessment_id>/archive/",
        views.assessment_archive,
        name="assessment_archive",
    ),
]

student_patterns = [
    path("assessments/", views.student_assessment_list, name="assessment_list"),
    path(
        "assessments/<int:assessment_id>/",
        views.student_assessment_detail,
        name="assessment_detail",
    ),
]
