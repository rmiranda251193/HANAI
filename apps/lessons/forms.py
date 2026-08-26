from django import forms

from apps.physics.models import PhysicsConcept

from .models import Lesson
from .services import lines_to_list


class LessonForm(forms.ModelForm):
    learning_objectives = forms.CharField(
        label="Learning objectives",
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "Students can calculate acceleration.\nStudents can explain the relationship between force and mass.",
            }
        ),
        help_text="Enter one learning objective per line.",
    )
    common_misconceptions = forms.CharField(
        label="Common misconceptions",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "More mass always means more acceleration.",
            }
        ),
        help_text="Enter one misconception per line.",
    )

    class Meta:
        model = Lesson
        fields = (
            "title",
            "topic",
            "grade_level",
            "duration_minutes",
            "physics_concepts",
            "learning_objectives",
            "common_misconceptions",
        )
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Introduction to Newton's Second Law"}),
            "topic": forms.TextInput(attrs={"placeholder": "Dynamics"}),
            "grade_level": forms.TextInput(attrs={"placeholder": "11"}),
            "duration_minutes": forms.NumberInput(attrs={"min": 1}),
            "physics_concepts": forms.CheckboxSelectMultiple(),
        }
        labels = {
            "grade_level": "Grade level",
            "duration_minutes": "Duration (minutes)",
            "physics_concepts": "Physics concepts",
        }
        help_texts = {
            "physics_concepts": "Select every concept this lesson teaches or applies.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["physics_concepts"].queryset = PhysicsConcept.objects.filter(
            is_active=True
        ).order_by("topic", "name")
        self.fields["physics_concepts"].required = True
        self.fields["physics_concepts"].widget.attrs["class"] = "concept-checkbox-group"

        for field_name in ("learning_objectives", "common_misconceptions"):
            value = self.initial.get(field_name)
            if isinstance(value, list):
                self.initial[field_name] = "\n".join(value)

    def clean_learning_objectives(self) -> list[str]:
        return lines_to_list(self.cleaned_data["learning_objectives"])

    def clean_common_misconceptions(self) -> list[str]:
        return lines_to_list(self.cleaned_data["common_misconceptions"])
