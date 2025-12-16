"""
Smoke test to verify pytest wiring and basic imports work.
"""


def test_smoke_import():
    """
    Basic smoke test that imports a core module to verify pytest wiring
    and that the basic package structure can be imported without errors.
    """
    # Import a core service module to verify the package structure
    # Import a config module
    from config.config_loader import ConfigLoader

    # Import a helper module - check that the module imports successfully
    from services.config_service import ConfigService
    from services.voice_service import VoiceService

    # Test passes if all imports succeed without exceptions
    assert VoiceService is not None
    assert ConfigService is not None
    assert ConfigLoader is not None
