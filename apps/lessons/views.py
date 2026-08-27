import logging

from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.ai.exceptions import AIError
from apps.ai.requests import LessonGenerationRequest
from apps.ai.services import generate_lesson_draft

from .forms import LessonForm
from .models import Lesson


logger = logging.getLogger(__name__)


GENERATION_ERROR_MESSAGE = (
    "AI generation could not be completed. Please check the AI configuration and try again."
)


def lesson_list(request):
    lessons = Lesson.objects.prefetch_related("physics_concepts")
    return render(request, "lessons/list.html", {"lessons": lessons})


def lesson_create(request):
    form = LessonForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        lesson = form.save()
        return redirect("lessons:detail", slug=lesson.slug)

    return render(request, "lessons/form.html", {"form": form})


def lesson_detail(request, slug):
    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"),
        slug=slug,
    )
    return render(request, "lessons/detail.html", {"lesson": lesson})


@require_POST
def lesson_generate(request, slug):
    """Generate a review-only lesson draft without changing the Lesson."""

    lesson = get_object_or_404(
        Lesson.objects.prefetch_related("physics_concepts"),
        slug=slug,
    )

    try:
        generation_request = LessonGenerationRequest.from_lesson(lesson)
        generation_result = generate_lesson_draft(generation_request)
    except (AIError, ValueError) as exc:
        logger.warning(
            "AI lesson generation failed for lesson %s (%s).",
            lesson.pk,
            exc.__class__.__name__,
        )
        return render(
            request,
            "lessons/detail.html",
            {"lesson": lesson, "generation_error": GENERATION_ERROR_MESSAGE},
        )
    except Exception:
        logger.exception("Unexpected AI lesson generation failure for lesson %s.", lesson.pk)
        return render(
            request,
            "lessons/detail.html",
            {"lesson": lesson, "generation_error": GENERATION_ERROR_MESSAGE},
        )

    return render(
        request,
        "lessons/detail.html",
        {
            "lesson": lesson,
            "generated_draft": generation_result.draft,
            "generation_result": generation_result,
        },
    )
