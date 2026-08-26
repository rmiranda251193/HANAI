import django.db.models.deletion

from django.db import migrations, models
from django.utils.text import slugify


def populate_lesson_slugs(apps, schema_editor):
    Lesson = apps.get_model("lessons", "Lesson")
    used_slugs = set(
        Lesson.objects.exclude(slug__isnull=True).values_list("slug", flat=True)
    )

    for lesson in Lesson.objects.order_by("created_at", "pk"):
        base_slug = slugify(lesson.title) or f"lesson-{lesson.pk.hex}"
        candidate_slug = base_slug
        suffix = 2

        while candidate_slug in used_slugs:
            candidate_slug = f"{base_slug}-{suffix}"
            suffix += 1

        used_slugs.add(candidate_slug)
        Lesson.objects.filter(pk=lesson.pk).update(slug=candidate_slug)


class Migration(migrations.Migration):
    dependencies = [
        ("physics", "0001_initial"),
        ("lessons", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="lesson",
            name="duration_minutes",
            field=models.PositiveSmallIntegerField(
                default=60,
                help_text="Planned lesson duration in minutes.",
            ),
        ),
        migrations.AddField(
            model_name="lesson",
            name="physics_concepts",
            field=models.ManyToManyField(
                blank=True,
                help_text="Physics concepts taught or applied by this lesson.",
                related_name="lessons",
                to="physics.physicsconcept",
            ),
        ),
        migrations.AddField(
            model_name="lesson",
            name="slug",
            field=models.SlugField(blank=True, max_length=280, null=True, unique=True),
        ),
        migrations.RenameField(
            model_name="lesson",
            old_name="misconceptions",
            new_name="common_misconceptions",
        ),
        migrations.RenameField(
            model_name="lesson",
            old_name="objectives",
            new_name="learning_objectives",
        ),
        migrations.RemoveField(
            model_name="lesson",
            name="approved_by",
        ),
        migrations.RemoveField(
            model_name="lesson",
            name="prerequisites",
        ),
        migrations.RemoveField(
            model_name="lesson",
            name="approved_at",
        ),
        migrations.AlterField(
            model_name="lesson",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lessons",
                to="auth.user",
            ),
        ),
        migrations.AlterField(
            model_name="lesson",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("review", "Under review"),
                    ("published", "Published"),
                    ("archived", "Archived"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.RunPython(populate_lesson_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="lesson",
            name="slug",
            field=models.SlugField(blank=True, max_length=280, unique=True),
        ),
    ]
