# bot/app/services/voice_service/voice_service_factory.py
"""
Factory for creating and configuring voice services.

This factory ensures consistent initialization of voice services
with proper dependency injection.
"""

from typing import Dict, Any
from helpers.logger import get_logger
from .jtc_manager import JoinToCreateManager
from .settings_service import VoiceSettingsService

logger = get_logger(__name__)


class VoiceServiceFactory:
    """
    Factory for creating voice services with proper dependency injection.
    """

    @staticmethod
    def create_voice_services(discord_gateway, app_config) -> Dict[str, Any]:
        """
        Create and initialize all voice services.
        
        Args:
            discord_gateway: The Discord gateway instance
            app_config: The application configuration
            
        Returns:
            Dictionary of initialized voice services
        """
        try:
            # Create JTC Manager
            jtc_manager = JoinToCreateManager(discord_gateway, app_config)
            jtc_manager.load_jtc_channels_from_config()
            
            # Create Settings Service
            settings_service = VoiceSettingsService(discord_gateway, app_config)
            
            services = {
                "jtc_manager": jtc_manager,
                "settings_service": settings_service
            }
            
            logger.info("Voice services initialized successfully")
            return services
            
        except Exception as e:
            logger.exception(f"Error creating voice services: {e}")
            raise
