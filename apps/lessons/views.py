from django.shortcuts import get_object_or_404, redirect, render

from .forms import LessonForm
from .models import Lesson


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
