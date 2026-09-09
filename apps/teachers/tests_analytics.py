"""Step 28 -- teacher cohort analytics.

These pin the deterministic aggregation, the honest denominators, the
authorization surface (GET-only, teacher-only, read-only), the bounded query
count, and the CSV export. Nothing here mutates authoritative records; the
tests assert that explicitly.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.assessments.models import (
    Assessment,
    AssessmentAnswer,
    AssessmentAttempt,
    AssessmentQuestion,
    QuestionBankItem,
)
from apps.lessons.models import Lesson, LessonActivity
from apps.physics.models import (
    MisconceptionRecoveryActivity,
    MisconceptionRecoveryPath,
    PhysicsConcept,
    PhysicsMisconception,
    PhysicsSimulation,
)
from apps.students.models import (
    ExperimentAttempt,
    LearningEvidence,
    MisconceptionEvidence,
    PracticeAttempt,
    StudentMisconception,
    StudentMisconceptionRecovery,
    StudentProfile,
    StudentRecoveryActivityCompletion,
    TutorMessage,
    TutorSession,
)

from .analytics_services import (
    AnalyticsSnapshot,
    get_cohort_analytics,
    resolve_analytics_filters,
)

User = get_user_model()
Kind = LearningEvidence.Kind


class AnalyticsDataMixin:
    def make_teacher(self, username="teach"):
        return User.objects.create_user(username, password="pw", is_staff=True)

    def make_student_user(self, username="stud"):
        return User.objects.create_user(username, password="pw")

    def make_student(self, name="Alex", user=None):
        return StudentProfile.objects.create(display_name=name, user=user)

    def make_concept(self, name="Force", topic="Dynamics"):
        return PhysicsConcept.objects.create(name=name, description="d", topic=topic)

    def make_misconception(self, concept, code="FORCE_VS_ACCELERATION"):
        return PhysicsMisconception.objects.create(
            code=code, title="Force is acceleration", description="d", physics_concept=concept
        )

    def make_lesson(self, *concepts, title="Forces and Motion"):
        lesson = Lesson.objects.create(
            title=title, topic="Dynamics", grade_level="11",
            duration_minutes=45, learning_objectives=["x"],
        )
        for concept in concepts:
            lesson.physics_concepts.add(concept)
        return lesson

    def make_simulation(self, concept, title="NSL Lab"):
        return PhysicsSimulation.objects.create(
            concept=concept, title=title,
            simulation_type=PhysicsSimulation.SimulationType.NEWTONS_SECOND_LAW,
        )

    def add_evidence(self, student, kind, *, lesson=None, when=None):
        ev = LearningEvidence.objects.create(student=student, lesson=lesson, kind=kind)
        if when is not None:
            LearningEvidence.objects.filter(pk=ev.pk).update(created_at=when)
        return ev

    def add_practice(self, student, lesson, concept, *, is_correct, key="q1", when=None):
        row = PracticeAttempt.objects.create(
            student=student, lesson=lesson, concept=concept, question_key=key,
            question_type="numeric", question_prompt="p", answer_text="1",
            is_correct=is_correct, attempt_number=1,
        )
        if when is not None:
            PracticeAttempt.objects.filter(pk=row.pk).update(created_at=when)
        return row

    def add_experiment(self, student, simulation, *, lesson=None, completed=False,
                       prediction="", observation="", explanation="", when=None):
        row = ExperimentAttempt.objects.create(
            student=student, simulation=simulation, lesson=lesson,
            prediction=prediction, observation=observation, explanation=explanation,
            completed_at=timezone.now() if completed else None,
        )
        if when is not None:
            ExperimentAttempt.objects.filter(pk=row.pk).update(started_at=when)
        return row

    def add_assessment(self, concept, *, title="A1"):
        q = QuestionBankItem.objects.create(
            key=f"{title}-q", question_type="numeric", prompt="p",
            expected_value=1, concept=concept,
        )
        a = Assessment.objects.create(title=title, concept=concept, status="published")
        aq = AssessmentQuestion.objects.create(assessment=a, question=q, position=0)
        return a, aq

    def add_assessment_attempt(self, student, assessment, aq, *, is_correct, completed):
        att = AssessmentAttempt.objects.create(
            student=student, assessment=assessment,
            completed_at=timezone.now() if completed else None,
        )
        AssessmentAnswer.objects.create(
            attempt=att, assessment_question=aq, answer_text="1", is_correct=is_correct
        )
        return att

    def add_recovery(self, student, misconception, *, completed_activities=0, total_activities=1,
                     path_completed=False):
        obs = StudentMisconception.objects.create(
            student=student, misconception=misconception, status="candidate",
            observation_count=max(completed_activities, 1),
        )
        path = MisconceptionRecoveryPath.objects.create(
            misconception=misconception, title="P", student_summary="s"
        )
        acts = [
            MisconceptionRecoveryActivity.objects.create(
                path=path, order=i + 1, activity_type="concept_check", label=f"c{i}"
            )
            for i in range(total_activities)
        ]
        rec = StudentMisconceptionRecovery.objects.create(
            student=student, observation=obs, path=path,
            completed_at=timezone.now() if path_completed else None,
        )
        for act in acts[:completed_activities]:
            StudentRecoveryActivityCompletion.objects.create(
                recovery=rec, activity=act, result="done"
            )
        return rec, obs

    def full_fixture(self):
        """Every authoritative table non-empty, 3 students, 2 concepts."""

        self.c_force = self.make_concept("Force", "Dynamics")
        self.c_kin = self.make_concept("Displacement", "Kinematics")
        self.misc = self.make_misconception(self.c_force)
        self.sim = self.make_simulation(self.c_force)
        self.lesson = self.make_lesson(self.c_force)
        LessonActivity.objects.create(
            lesson=self.lesson, position=1, activity_type="explanation", title="e"
        )
        self.s1 = self.make_student("Alice")
        self.s2 = self.make_student("Bob")
        self.s3 = self.make_student("Cara")

        for i in range(3):
            self.add_evidence(self.s1, Kind.QUESTION_ASKED, lesson=self.lesson)
        self.add_evidence(self.s2, Kind.PRACTICE_ATTEMPTED, lesson=self.lesson)
        for i in range(4):
            self.add_practice(self.s1, self.lesson, self.c_force,
                              is_correct=(i == 0), key=f"q{i}")
        self.add_practice(self.s2, self.lesson, self.c_force, is_correct=True, key="qb")
        self.add_experiment(self.s1, self.sim, lesson=self.lesson, completed=True,
                            prediction="p", observation="o", explanation="x")
        self.add_experiment(self.s2, self.sim, lesson=self.lesson)  # attempted only
        a, aq = self.add_assessment(self.c_force)
        self.assessment = a
        self.add_assessment_attempt(self.s1, a, aq, is_correct=True, completed=True)
        self.add_assessment_attempt(self.s2, a, aq, is_correct=False, completed=False)
        self.add_recovery(self.s1, self.misc, completed_activities=1, total_activities=2,
                          path_completed=False)
        ts = TutorSession.objects.create(student=self.s1, lesson=self.lesson)
        TutorMessage.objects.create(session=ts, role="student", content="hello")
        TutorMessage.objects.create(session=ts, role="tutor", content="hi")


class ResolveFiltersTests(AnalyticsDataMixin, TestCase):
    def test_default_is_thirty_days_all_students(self):
        f = resolve_analytics_filters({})
        self.assertEqual(f.range_key, "30")
        self.assertIsNone(f.student)
        self.assertIsNotNone(f.start)
        self.assertEqual(f.notices, ())

    def test_named_ranges(self):
        for key in ("7", "30", "90"):
            f = resolve_analytics_filters({"range": key})
            self.assertEqual(f.range_key, key)
            self.assertIsNotNone(f.start)
        f_all = resolve_analytics_filters({"range": "all"})
        self.assertEqual(f_all.range_key, "all")
        self.assertIsNone(f_all.start)

    def test_unknown_range_key_falls_back_with_a_notice(self):
        f = resolve_analytics_filters({"range": "nonsense"})
        self.assertEqual(f.range_key, "30")
        self.assertTrue(f.notices)

    def test_start_after_end_is_rejected_with_a_notice(self):
        f = resolve_analytics_filters({"start": "2026-06-01", "end": "2026-01-01"})
        self.assertEqual(f.range_key, "30")
        self.assertTrue(any("after the end date" in n for n in f.notices))

    def test_oversized_range_is_clamped_with_a_notice(self):
        f = resolve_analytics_filters({"start": "2000-01-01", "end": "2026-01-01"})
        self.assertTrue(any("cannot be longer than" in n for n in f.notices))
        self.assertLessEqual((f.end - f.start).days, 365)

    def test_invalid_date_string_falls_back(self):
        f = resolve_analytics_filters({"start": "not-a-date", "end": "2026-01-01"})
        self.assertEqual(f.range_key, "30")
        self.assertTrue(f.notices)

    def test_boundary_same_day_range_is_accepted(self):
        f = resolve_analytics_filters({"start": "2026-02-01", "end": "2026-02-01"})
        self.assertEqual(f.range_key, "custom")
        self.assertEqual(f.notices, ())
        self.assertLess(f.start, f.end)

    def test_unknown_ids_become_notices_not_errors(self):
        f = resolve_analytics_filters(
            {"student": "999999", "lesson": "888888", "concept": "777777"}
        )
        self.assertIsNone(f.student)
        self.assertIsNone(f.lesson)
        self.assertIsNone(f.concept)
        self.assertEqual(len(f.notices), 3)

    def test_valid_ids_resolve(self):
        concept = self.make_concept()
        lesson = self.make_lesson(concept)
        student = self.make_student()
        f = resolve_analytics_filters(
            {"student": str(student.pk), "lesson": str(lesson.pk), "concept": str(concept.pk)}
        )
        self.assertEqual(f.student, student)
        self.assertEqual(f.lesson, lesson)
        self.assertEqual(f.concept, concept)
        self.assertEqual(f.notices, ())


class CohortServiceTests(AnalyticsDataMixin, TestCase):
    def test_empty_cohort_is_all_zeros_no_crash(self):
        snap = get_cohort_analytics(resolve_analytics_filters({}))
        self.assertIsInstance(snap, AnalyticsSnapshot)
        self.assertEqual(snap.student_count, 0)
        self.assertEqual(snap.active_student_count, 0)
        self.assertEqual(snap.concept_summary, ())
        self.assertEqual(snap.attention_signals, ())
        # zero-denominator labels never divide by zero
        for row in snap.practice_summary + snap.recovery_summary:
            self.assertNotIn("ZeroDivision", row.note)

    def test_single_student_counts(self):
        c = self.make_concept()
        lesson = self.make_lesson(c)
        s = self.make_student("Solo")
        self.add_evidence(s, Kind.QUESTION_ASKED, lesson=lesson)
        self.add_practice(s, lesson, c, is_correct=True)
        snap = get_cohort_analytics(resolve_analytics_filters({}))
        self.assertEqual(snap.student_count, 1)
        self.assertEqual(snap.active_student_count, 1)
        activity = {r.label: r.value for r in snap.activity_summary}
        self.assertEqual(activity["Questions asked"], 1)
        practice = {r.label: (r.value, r.note) for r in snap.practice_summary}
        self.assertEqual(practice["Attempts"][0], 1)
        self.assertEqual(practice["Correct"][0], 1)

    def test_multiple_students_aggregate(self):
        self.full_fixture()
        snap = get_cohort_analytics(resolve_analytics_filters({}))
        self.assertEqual(snap.student_count, 3)
        self.assertEqual(snap.active_student_count, 2)  # Cara has no evidence
        practice = {r.label: r.value for r in snap.practice_summary}
        self.assertEqual(practice["Attempts"], 5)
        self.assertEqual(practice["Correct"], 2)
        self.assertEqual(practice["Incorrect"], 3)

    def test_assessment_denominator_is_completed_attempts_only(self):
        self.full_fixture()
        snap = get_cohort_analytics(resolve_analytics_filters({}))
        row = next(r for r in snap.assessment_summary if r.title == "A1")
        self.assertEqual(row.attempts, 2)
        self.assertEqual(row.completed, 1)
        # the in-progress incorrect attempt must not drag the average down
        self.assertIn("1.0 correct of 1.0 answered", row.avg_correct_label)
        self.assertIn("1 completed", row.avg_correct_label)

    def test_physics_lab_distinguishes_attempted_from_completed(self):
        self.full_fixture()
        snap = get_cohort_analytics(resolve_analytics_filters({}))
        lab = {r.label: r.value for r in snap.physics_lab_summary}
        self.assertEqual(lab["Experiments started"], 2)
        self.assertEqual(lab["Experiments completed"], 1)
        completion = next(r for r in snap.physics_lab_summary if r.label == "Completion rate")
        self.assertIn("1 of 2", completion.note)

    def test_recovery_started_and_completed_are_separate_from_resolution(self):
        self.full_fixture()
        # add a completed recovery whose misconception the teacher has NOT resolved
        rec, obs = self.add_recovery(self.s2, self.misc, completed_activities=1,
                                     total_activities=1, path_completed=True)
        snap = get_cohort_analytics(resolve_analytics_filters({}))
        rec_summary = {r.label: r.value for r in snap.recovery_summary}
        self.assertEqual(rec_summary["Recovery paths completed"], 1)
        self.assertEqual(rec_summary["Misconceptions with a completed recovery"], 1)
        self.assertEqual(rec_summary["Misconceptions resolved by a teacher decision"], 0)

    def test_misconception_aggregation(self):
        self.full_fixture()
        self.add_recovery(self.s2, self.misc, completed_activities=0, total_activities=1)
        snap = get_cohort_analytics(resolve_analytics_filters({}))
        row = next(r for r in snap.misconception_summary if r.code == "FORCE_VS_ACCELERATION")
        self.assertEqual(row.students_affected, 2)
        self.assertGreaterEqual(row.candidates, 2)
        self.assertEqual(row.recoveries_started, 2)

    def test_date_filter_changes_counts(self):
        c = self.make_concept()
        lesson = self.make_lesson(c)
        s = self.make_student()
        self.add_evidence(s, Kind.QUESTION_ASKED, lesson=lesson,
                          when=timezone.now() - timedelta(days=2))
        self.add_evidence(s, Kind.QUESTION_ASKED, lesson=lesson,
                          when=timezone.now() - timedelta(days=45))
        recent = get_cohort_analytics(resolve_analytics_filters({"range": "7"}))
        all_time = get_cohort_analytics(resolve_analytics_filters({"range": "all"}))
        r_recent = {x.label: x.value for x in recent.activity_summary}["Questions asked"]
        r_all = {x.label: x.value for x in all_time.activity_summary}["Questions asked"]
        self.assertEqual(r_recent, 1)
        self.assertEqual(r_all, 2)

    def test_concept_filter_scopes_the_snapshot(self):
        self.full_fixture()
        snap = get_cohort_analytics(
            resolve_analytics_filters({"concept": str(self.c_force.pk)})
        )
        self.assertTrue(all(r.concept == "Force" for r in snap.concept_summary))

    def test_student_filter_scopes_the_snapshot(self):
        self.full_fixture()
        snap = get_cohort_analytics(
            resolve_analytics_filters({"student": str(self.s2.pk)})
        )
        self.assertEqual(snap.student_count, 1)
        practice = {r.label: r.value for r in snap.practice_summary}
        self.assertEqual(practice["Attempts"], 1)  # only Bob's one attempt

    def test_attention_signals_are_deterministic_review_prompts(self):
        self.full_fixture()
        # Alice: 3 incorrect on Force + a 4-observation misconception
        StudentMisconception.objects.filter(student=self.s1).update(observation_count=4)
        snap1 = get_cohort_analytics(resolve_analytics_filters({}))
        snap2 = get_cohort_analytics(resolve_analytics_filters({}))
        self.assertEqual(
            [(r.student, r.band, r.signals) for r in snap1.attention_signals],
            [(r.student, r.band, r.signals) for r in snap2.attention_signals],
        )
        alice = next(r for r in snap1.attention_signals if r.student == "Alice")
        self.assertEqual(alice.band, "Needs attention")
        self.assertTrue(any("Repeated incorrect practice" in s for s in alice.signals))
        for row in snap1.attention_signals:
            for text in row.signals:
                self.assertNotIn("at risk", text.lower())
                self.assertNotIn("will fail", text.lower())

    def test_no_unsupported_mastery_or_risk_language_anywhere(self):
        self.full_fixture()
        snap = get_cohort_analytics(resolve_analytics_filters({}))
        banned = ("mastery", "at risk", "ability", "proficiency", "grade level score", "iq")
        haystacks = []
        for group in (
            snap.activity_summary, snap.recovery_summary, snap.practice_summary,
            snap.physics_lab_summary, snap.tutor_summary, snap.activity_type_summary,
        ):
            for row in group:
                haystacks.append((row.label + " " + row.note).lower())
        for row in snap.assessment_summary:
            haystacks.append(row.avg_correct_label.lower())
        for row in snap.attention_signals:
            haystacks.append((row.band + " " + " ".join(row.signals)).lower())
        for text in haystacks:
            for word in banned:
                self.assertNotIn(word, text)


class AuthorizationTests(AnalyticsDataMixin, TestCase):
    def setUp(self):
        self.url = reverse("teachers:analytics")
        self.export_url = reverse("teachers:analytics_export")

    def test_teacher_can_open_dashboard(self):
        self.client.force_login(self.make_teacher())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_signed_in_student_is_refused(self):
        self.client.force_login(self.make_student_user())
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.export_url).status_code, 403)

    def test_anonymous_is_refused(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.export_url).status_code, 403)

    def test_post_is_rejected_get_only(self):
        self.client.force_login(self.make_teacher())
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.export_url).status_code, 405)

    def test_forged_filter_ids_are_safe(self):
        self.client.force_login(self.make_teacher())
        response = self.client.get(
            self.url, {"student": "999999", "lesson": "abc", "concept": "-1"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be found")

    def test_dashboard_and_export_never_write(self):
        self.full_fixture()
        self.client.force_login(self.make_teacher())
        before = {
            "evidence": LearningEvidence.objects.count(),
            "practice": PracticeAttempt.objects.count(),
            "misc": StudentMisconception.objects.count(),
            "misc_evidence": MisconceptionEvidence.objects.count(),
            "recovery": StudentMisconceptionRecovery.objects.count(),
            "recovery_done": StudentRecoveryActivityCompletion.objects.count(),
            "assess_attempt": AssessmentAttempt.objects.count(),
            "assess_answer": AssessmentAnswer.objects.count(),
            "experiments": ExperimentAttempt.objects.count(),
        }
        self.client.get(self.url, {"range": "7"})
        self.client.get(self.url, {"student": str(self.s1.pk)})
        self.client.get(self.export_url)
        after = {
            "evidence": LearningEvidence.objects.count(),
            "practice": PracticeAttempt.objects.count(),
            "misc": StudentMisconception.objects.count(),
            "misc_evidence": MisconceptionEvidence.objects.count(),
            "recovery": StudentMisconceptionRecovery.objects.count(),
            "recovery_done": StudentRecoveryActivityCompletion.objects.count(),
            "assess_attempt": AssessmentAttempt.objects.count(),
            "assess_answer": AssessmentAnswer.objects.count(),
            "experiments": ExperimentAttempt.objects.count(),
        }
        self.assertEqual(before, after)

    def test_display_names_are_escaped_not_injected(self):
        concept = self.make_concept("<script>alert('c')</script>", "Dynamics")
        lesson = self.make_lesson(concept)
        student = self.make_student("<img src=x onerror=alert(1)>")
        self.add_practice(student, lesson, concept, is_correct=False, key="q0")
        self.add_practice(student, lesson, concept, is_correct=False, key="q1")
        self.add_practice(student, lesson, concept, is_correct=False, key="q2")
        self.client.force_login(self.make_teacher())
        body = self.client.get(self.url).content.decode()
        self.assertNotIn("<script>alert('c')</script>", body)
        self.assertNotIn("<img src=x onerror=alert(1)>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_accessibility_landmarks(self):
        self.client.force_login(self.make_teacher())
        body = self.client.get(self.url).content.decode()
        self.assertEqual(body.count("<h1"), 1)
        self.assertIn('scope="col"', body)
        self.assertIn('scope="row"', body)
        self.assertIn("<caption", body)
        for name in ("range", "student", "lesson", "concept"):
            self.assertIn(f'for="af-{name}"', body)


class QueryBudgetTests(AnalyticsDataMixin, TestCase):
    # One bounded set of grouped aggregate queries. No query runs per student,
    # per concept, or per misconception, so the count does not grow with cohort
    # size or history length -- test_budget_does_not_grow_with_cohort pins that.
    def test_cohort_analytics_query_budget(self):
        self.full_fixture()
        filters = resolve_analytics_filters({})
        with self.assertNumQueries(27):
            get_cohort_analytics(filters)

    def test_budget_does_not_grow_with_cohort_size(self):
        self.full_fixture()
        base_concept = self.c_force
        base_lesson = self.lesson
        for i in range(6):
            extra = self.make_student(f"Extra{i}")
            self.add_evidence(extra, Kind.QUESTION_ASKED, lesson=base_lesson)
            self.add_practice(extra, base_lesson, base_concept, is_correct=bool(i % 2),
                              key=f"ex{i}")
            self.add_experiment(extra, self.sim, lesson=base_lesson, completed=bool(i % 2))
        filters = resolve_analytics_filters({})
        with self.assertNumQueries(27):
            get_cohort_analytics(filters)

    def test_empty_cohort_query_budget(self):
        with self.assertNumQueries(3):
            get_cohort_analytics(resolve_analytics_filters({}))


class CsvExportTests(AnalyticsDataMixin, TestCase):
    def setUp(self):
        self.export_url = reverse("teachers:analytics_export")
        self.client.force_login(self.make_teacher())

    def test_headers_and_content_type(self):
        self.full_fixture()
        response = self.client.get(self.export_url)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])
        text = response.content.decode()
        self.assertIn("cohort analytics", text)
        self.assertIn("Students in view,3", text)
        self.assertIn("Concept,Topic,Students engaged", text)

    def test_empty_cohort_exports_without_error(self):
        response = self.client.get(self.export_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Students in view,0", response.content.decode())

    def test_no_tutor_text_or_teacher_notes_in_export(self):
        self.full_fixture()
        TutorMessage.objects.create(
            session=TutorSession.objects.create(student=self.s1, lesson=self.lesson),
            role="student", content="SECRET_TUTOR_SENTENCE",
        )
        response = self.client.get(self.export_url)
        self.assertNotIn("SECRET_TUTOR_SENTENCE", response.content.decode())

    def test_formula_injection_is_neutralised(self):
        evil = self.make_concept('=HYPERLINK("http://evil")', "Dynamics")
        lesson = self.make_lesson(evil)
        s = self.make_student()
        self.add_practice(s, lesson, evil, is_correct=False)
        response = self.client.get(self.export_url)
        text = response.content.decode()
        self.assertNotIn(",=HYPERLINK", text)
        self.assertIn("'=HYPERLINK", text)
