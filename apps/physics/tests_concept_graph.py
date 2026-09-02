"""Step 20 -- the deterministic Physics concept graph (pure, no student data)."""

from django.test import TestCase

from .concept_graph import (
    build_physics_concept_graph,
    find_shortest_concept_path,
    get_adjacent_concepts,
)
from .models import PhysicsConcept

D = PhysicsConcept.Difficulty


class GraphDataMixin:
    def make(self, name, *, prerequisites=None, difficulty=D.FOUNDATIONAL,
             topic="Kinematics", is_active=True):
        return PhysicsConcept.objects.create(
            name=name, description="d", topic=topic, difficulty=difficulty,
            prerequisites=prerequisites or [], is_active=is_active,
        )

    def chain(self):
        """Velocity -> Acceleration -> Force -> Newton's Second Law (+ a branch)."""
        self.velocity = self.make("Velocity", difficulty=D.INTRODUCTORY)
        self.accel = self.make("Acceleration", prerequisites=["Velocity"], difficulty=D.INTERMEDIATE)
        self.force = self.make("Force", prerequisites=["Acceleration"], difficulty=D.INTRODUCTORY, topic="Dynamics")
        self.nsl = self.make(
            "Newton's Second Law", prerequisites=["Force", "Acceleration"],
            difficulty=D.INTERMEDIATE, topic="Dynamics",
        )
        self.n3l = self.make(
            "Newton's Third Law", prerequisites=["Force"],
            difficulty=D.INTERMEDIATE, topic="Dynamics",
        )


class GraphStructureTests(GraphDataMixin, TestCase):
    def test_graph_loads_all_active_concepts(self):
        self.chain()
        self.make("Retired", is_active=False)
        graph = build_physics_concept_graph()
        self.assertEqual(
            set(graph.nodes),
            {"velocity", "acceleration", "force", "newtons-second-law", "newtons-third-law"},
        )
        self.assertNotIn("retired", graph.nodes)

    def test_prerequisite_edges_resolve_by_name(self):
        self.chain()
        graph = build_physics_concept_graph()
        # Ordered by difficulty rank first: Force is INTRODUCTORY, Acceleration
        # INTERMEDIATE.
        self.assertEqual(graph.prerequisites["newtons-second-law"], ["force", "acceleration"])
        # Both dependents are INTERMEDIATE, so ordered by name ("second" < "third").
        self.assertEqual(
            graph.next_concepts["force"], ["newtons-second-law", "newtons-third-law"]
        )

    def test_next_concepts_are_the_reverse_of_prerequisites(self):
        self.chain()
        graph = build_physics_concept_graph()
        self.assertIn("acceleration", graph.next_concepts["velocity"])
        self.assertIn("newtons-second-law", graph.next_concepts["acceleration"])

    def test_duplicate_prerequisites_collapse(self):
        self.make("Velocity")
        self.make("Acceleration", prerequisites=["Velocity", "Velocity", "velocity"])
        graph = build_physics_concept_graph()
        self.assertEqual(graph.prerequisites["acceleration"], ["velocity"])

    def test_unknown_prerequisite_is_safe_and_reported(self):
        self.make("Acceleration", prerequisites=["Nonexistent Concept", "Velocity"])
        self.make("Velocity")
        graph = build_physics_concept_graph()
        self.assertEqual(graph.prerequisites["acceleration"], ["velocity"])
        self.assertEqual(graph.unresolved["acceleration"], ["Nonexistent Concept"])
        self.assertNotIn("nonexistent-concept", graph.nodes)

    def test_self_prerequisite_is_dropped(self):
        self.make("Acceleration", prerequisites=["Acceleration"])
        graph = build_physics_concept_graph()
        self.assertEqual(graph.prerequisites["acceleration"], [])

    def test_inactive_prerequisite_is_not_an_edge(self):
        self.make("Velocity", is_active=False)
        self.make("Acceleration", prerequisites=["Velocity"])
        graph = build_physics_concept_graph()
        self.assertEqual(graph.prerequisites["acceleration"], [])
        self.assertEqual(graph.unresolved["acceleration"], ["Velocity"])

    def test_concept_ordering_is_a_stable_total_order(self):
        self.chain()
        first = list(build_physics_concept_graph().nodes)
        second = list(build_physics_concept_graph().nodes)
        self.assertEqual(first, second)
        # difficulty rank, then name: Force & Velocity are INTRODUCTORY (rank 1),
        # "force" < "velocity"; Acceleration is INTERMEDIATE (rank 2).
        self.assertEqual(first[:2], ["force", "velocity"])
        self.assertLess(first.index("velocity"), first.index("acceleration"))

    def test_edge_ordering_is_stable(self):
        self.chain()
        self.assertEqual(
            build_physics_concept_graph().edges(),
            build_physics_concept_graph().edges(),
        )

    def test_get_adjacent_concepts(self):
        self.chain()
        graph = build_physics_concept_graph()
        adj = get_adjacent_concepts(graph, "force")
        self.assertEqual([n.slug for n in adj["prerequisites"]], ["acceleration"])
        self.assertEqual(
            [n.slug for n in adj["next_concepts"]],
            ["newtons-second-law", "newtons-third-law"],
        )


class GraphTraversalTests(GraphDataMixin, TestCase):
    def test_shortest_path_forward(self):
        self.chain()
        graph = build_physics_concept_graph()
        self.assertEqual(
            find_shortest_concept_path(graph, "velocity", "newtons-second-law"),
            ["velocity", "acceleration", "newtons-second-law"],
        )

    def test_shortest_path_backward(self):
        self.chain()
        graph = build_physics_concept_graph()
        self.assertEqual(
            find_shortest_concept_path(
                graph, "newtons-second-law", "velocity", forward=False
            ),
            ["newtons-second-law", "acceleration", "velocity"],
        )

    def test_unreachable_returns_empty(self):
        self.chain()
        graph = build_physics_concept_graph()
        self.assertEqual(
            find_shortest_concept_path(graph, "newtons-second-law", "velocity"), []
        )
        self.assertEqual(find_shortest_concept_path(graph, "velocity", "nope"), [])

    def test_same_node_path(self):
        self.chain()
        graph = build_physics_concept_graph()
        self.assertEqual(find_shortest_concept_path(graph, "force", "force"), ["force"])

    def test_traversal_is_deterministic(self):
        self.chain()
        graph = build_physics_concept_graph()
        runs = {
            tuple(find_shortest_concept_path(graph, "velocity", "newtons-third-law"))
            for _ in range(5)
        }
        self.assertEqual(len(runs), 1)

    def test_self_cycle_does_not_hang(self):
        a = self.make("A")
        a.prerequisites = ["A"]
        a.save(update_fields=["prerequisites"])
        self.make("B", prerequisites=["A"])
        graph = build_physics_concept_graph()
        self.assertEqual(find_shortest_concept_path(graph, "a", "b"), ["a", "b"])
        self.assertEqual(find_shortest_concept_path(graph, "a", "a"), ["a"])

    def test_multi_node_cycle_does_not_hang(self):
        # A -> B -> C -> A  (bad data)
        self.make("A", prerequisites=["C"])
        self.make("B", prerequisites=["A"])
        self.make("C", prerequisites=["B"])
        self.make("D", prerequisites=["C"])
        graph = build_physics_concept_graph()
        # forward from A eventually reaches D without looping forever
        self.assertEqual(find_shortest_concept_path(graph, "a", "d"), ["a", "b", "c", "d"])
        # a target genuinely unreachable forward still terminates
        self.make("Island")
        graph = build_physics_concept_graph()
        self.assertEqual(find_shortest_concept_path(graph, "a", "island"), [])


class GraphQueryBudgetTests(GraphDataMixin, TestCase):
    def test_build_graph_is_one_query(self):
        self.chain()
        for i in range(20):
            self.make(f"Extra {i}", prerequisites=["Force"])
        with self.assertNumQueries(1):
            build_physics_concept_graph()
