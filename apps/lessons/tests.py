from django.test import TestCase
from django.urls import reverse

from apps.physics.models import PhysicsConcept

from .models import Lesson


class LessonPhysicsConceptTests(TestCase):
    def setUp(self):
        self.force = PhysicsConcept.objects.create(
            name="Force",
            description="An interaction that can change an object's motion.",
            topic="Dynamics",
            equations=["F_net = ma"],
            si_units=["newton (N)"],
            prerequisites=["Acceleration"],
        )
        self.newtons_second_law = PhysicsConcept.objects.create(
            name="Newton's Second Law",
            description="Net force, mass, and acceleration are related.",
            topic="Dynamics",
        )

    def create_lesson(self, title="Introduction to Newton's Second Law"):
        return Lesson.objects.create(
            title=title,
            topic="Dynamics",
            grade_level="11",
            duration_minutes=60,
            learning_objectives=["Relate net force, mass, and acceleration."],
        )

    def test_lesson_can_be_created_with_draft_status_and_slug(self):
        lesson = self.create_lesson()

        self.assertEqual(lesson.status, Lesson.Status.DRAFT)
        self.assertEqual(lesson.slug, "introduction-to-newtons-second-law")

    def test_lesson_can_reference_multiple_physics_concepts(self):
        lesson = self.create_lesson()

        lesson.physics_concepts.add(self.force, self.newtons_second_law)

        self.assertCountEqual(
            lesson.physics_concepts.values_list("name", flat=True),
            ["Force", "Newton's Second Law"],
        )

    def test_physics_concept_can_belong_to_multiple_lessons(self):
        first_lesson = self.create_lesson()
        second_lesson = self.create_lesson("Using Force and Mass")

        self.force.lessons.add(first_lesson, second_lesson)

        self.assertCountEqual(
            self.force.lessons.values_list("title", flat=True),
            [first_lesson.title, second_lesson.title],
        )

    def test_lesson_does_not_duplicate_physics_concept_reference_fields(self):
        lesson = self.create_lesson()
        lesson.physics_concepts.add(self.force)
        lesson_fields = {field.name for field in Lesson._meta.get_fields()}

        self.assertNotIn("equations", lesson_fields)
        self.assertNotIn("si_units", lesson_fields)
        self.assertNotIn("prerequisites", lesson_fields)
        self.assertEqual(lesson.physics_concepts.get().equations, ["F_net = ma"])


class LessonBuilderViewTests(TestCase):
    def setUp(self):
        self.force = PhysicsConcept.objects.create(
            name="Force",
            description="An interaction that can change an object's motion.",
            topic="Dynamics",
        )
        self.newtons_second_law = PhysicsConcept.objects.create(
            name="Newton's Second Law",
            description="Net force, mass, and acceleration are related.",
            topic="Dynamics",
        )

    def valid_lesson_data(self):
        return {
            "title": "Introduction to Newton's Second Law",
            "topic": "Dynamics",
            "grade_level": "11",
            "duration_minutes": "60",
            "physics_concepts": [self.force.pk, self.newtons_second_law.pk],
            "learning_objectives": (
                "Calculate acceleration from net force and mass.\n\n"
                "Explain the relationship between force and mass."
            ),
            "common_misconceptions": "More mass always means more acceleration.\n\n",
        }

    def test_lesson_list_url_works(self):
        response = self.client.get(reverse("lessons:list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lessons/list.html")

    def test_lesson_create_page_works(self):
        response = self.client.get(reverse("lessons:create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lessons/form.html")

    def test_valid_post_creates_draft_with_concepts_and_json_lists(self):
        response = self.client.post(reverse("lessons:create"), self.valid_lesson_data())

        lesson = Lesson.objects.get()
        self.assertRedirects(response, reverse("lessons:detail", args=[lesson.slug]))
        self.assertEqual(lesson.status, Lesson.Status.DRAFT)
        self.assertCountEqual(
            lesson.physics_concepts.values_list("name", flat=True),
            ["Force", "Newton's Second Law"],
        )
        self.assertEqual(
            lesson.learning_objectives,
            [
                "Calculate acceleration from net force and mass.",
                "Explain the relationship between force and mass.",
            ],
        )
        self.assertEqual(
            lesson.common_misconceptions,
            ["More mass always means more acceleration."],
        )

    def test_lesson_detail_page_works(self):
        lesson = Lesson.objects.create(
            title="Understanding Force",
            topic="Dynamics",
            grade_level="11",
            learning_objectives=["Describe force."],
            common_misconceptions=["Force keeps motion going."],
        )
        lesson.physics_concepts.add(self.force)

        response = self.client.get(reverse("lessons:detail", args=[lesson.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lessons/detail.html")
        self.assertContains(response, "Understanding Force")
        self.assertContains(response, "Force")

    def test_invalid_form_data_does_not_create_a_lesson(self):
        data = self.valid_lesson_data()
        data["title"] = ""

        response = self.client.post(reverse("lessons:create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Lesson.objects.count(), 0)
        self.assertFormError(response.context["form"], "title", "This field is required.")
