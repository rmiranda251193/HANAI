from django.apps import AppConfig


class PhysicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.physics"

    def ready(self):
        # Populate the simulation registry (apps.physics.simulation_registry) --
        # each module registers itself as a side effect of being imported, the
        # same way apps.teachers.apps wires up its signal receivers.
        from . import simulations  # noqa: F401
        from . import simulations_kinematics  # noqa: F401
        from . import simulations_projectile  # noqa: F401
        from . import simulations_circular_motion  # noqa: F401
        from . import simulations_shm  # noqa: F401
        from . import simulations_collision  # noqa: F401
        from . import simulations_energy_incline  # noqa: F401
        from . import simulations_orbital_motion  # noqa: F401
        from . import simulations_circuits  # noqa: F401
        from . import simulations_coulombs_law  # noqa: F401
        from . import simulations_radioactive_decay  # noqa: F401
        from . import simulations_buoyancy  # noqa: F401
        from . import simulations_refraction  # noqa: F401
        from . import simulations_calorimetry  # noqa: F401
        from . import simulations_ideal_gas_law  # noqa: F401
        from . import simulations_doppler_effect  # noqa: F401
        from . import simulations_magnetic_force  # noqa: F401
        from . import simulations_time_dilation  # noqa: F401
        from . import simulations_photoelectric_effect  # noqa: F401
        from . import simulations_electromagnetic_induction  # noqa: F401
        from . import simulations_bohr_model  # noqa: F401
        from . import simulations_hubbles_law  # noqa: F401
        from . import simulations_particle_physics  # noqa: F401

        # Populate the visualization registry (2D/3D renderer definitions), the
        # code-defined Physics Lab scenario challenges, and the Physics domain /
        # equation catalogs (data only -- no models, no migrations).
        from . import visualization_registry  # noqa: F401
        from . import lab_scenarios  # noqa: F401
        from . import domain_catalog  # noqa: F401
        from . import equation_catalog  # noqa: F401
