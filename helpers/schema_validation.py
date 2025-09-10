#helpers/schema_validation.py

"""
JSON Schema validation utilities for AI agent data consistency.

This module provides validation functions for ensuring data structures
match expected schemas, helping AI agents understand and validate data flows.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import jsonschema
    from jsonschema import Draft7Validator
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    logging.warning("jsonschema not available - schema validation disabled")

logger = logging.getLogger(__name__)

class SchemaValidator:
    """JSON Schema validator for bot data structures."""
    
    def __init__(self, schema_dir: Path | None = None):
        self.schema_dir = schema_dir or Path("prompts/schemas")
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._validators: Dict[str, Draft7Validator] = {}
        
        if JSONSCHEMA_AVAILABLE:
            self._load_schemas()
    
    def _load_schemas(self) -> None:
        """Load all JSON schemas from the schema directory."""
        if not self.schema_dir.exists():
            logger.warning(f"Schema directory not found: {self.schema_dir}")
            return
        
        for schema_file in self.schema_dir.glob("*.json"):
            try:
                with open(schema_file, 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                
                schema_name = schema_file.stem
                self._schemas[schema_name] = schema
                
                if JSONSCHEMA_AVAILABLE:
                    self._validators[schema_name] = Draft7Validator(schema)
                
                logger.debug(f"Loaded schema: {schema_name}")
                
            except Exception as e:
                logger.error(f"Failed to load schema {schema_file}: {e}")
    
    def validate(
        self, 
        data: Any, 
        schema_name: str, 
        definition_path: Optional[str] = None
    ) -> tuple[bool, List[str]]:
        """
        Validate data against a schema.
        
        Args:
            data: Data to validate
            schema_name: Name of the schema file (without .json)
            definition_path: Optional path to specific definition (e.g., "definitions/member")
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        if not JSONSCHEMA_AVAILABLE:
            logger.warning("Schema validation skipped - jsonschema not available")
            return True, []
        
        if schema_name not in self._validators:
            logger.error(f"Schema not found: {schema_name}")
            return False, [f"Schema '{schema_name}' not loaded"]
        
        try:
            validator = self._validators[schema_name]
            
            # If a specific definition is requested, extract it
            if definition_path:
                schema = self._extract_definition(schema_name, definition_path)
                if not schema:
                    return False, [f"Definition '{definition_path}' not found in schema '{schema_name}'"]
                validator = Draft7Validator(schema)
            
            errors = []
            for error in validator.iter_errors(data):
                error_msg = f"Validation error at {'.'.join(str(p) for p in error.path)}: {error.message}"
                errors.append(error_msg)
            
            is_valid = len(errors) == 0
            return is_valid, errors
            
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            return False, [f"Validation error: {str(e)}"]
    
    def _extract_definition(self, schema_name: str, definition_path: str) -> Optional[Dict[str, Any]]:
        """Extract a specific definition from a schema."""
        schema = self._schemas.get(schema_name)
        if not schema:
            return None
        
        # Navigate to the definition
        parts = definition_path.split('/')
        current = schema
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        
        return current
    
    def get_schema_info(self, schema_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a loaded schema."""
        schema = self._schemas.get(schema_name)
        if not schema:
            return None
        
        info = {
            'title': schema.get('title', 'Unknown'),
            'description': schema.get('description', 'No description'),
            'definitions': list(schema.get('definitions', {}).keys()) if 'definitions' in schema else [],
            'schema_id': schema.get('$id', 'No ID')
        }
        
        return info
    
    def list_schemas(self) -> List[str]:
        """List all loaded schema names."""
        return list(self._schemas.keys())

# Global validator instance
validator = SchemaValidator()

def validate_discord_member(member_data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate Discord member data structure."""
    return validator.validate(member_data, "discord_events", "definitions/member")

def validate_rsi_profile(profile_data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate RSI profile data structure."""
    return validator.validate(profile_data, "api_responses", "definitions/rsi_profile")

def validate_verification_record(record_data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate verification record data structure."""
    return validator.validate(record_data, "database_models", "definitions/verification_record")

def validate_changeset(changeset_data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate leadership log changeset data structure."""
    return validator.validate(changeset_data, "database_models", "definitions/changeset")

# Decorator for automatic validation
def validate_input(schema_name: str, definition_path: Optional[str] = None):
    """Decorator to automatically validate function inputs."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Find the first dict argument to validate
            data_to_validate = None
            for arg in args:
                if isinstance(arg, dict):
                    data_to_validate = arg
                    break
            
            if not data_to_validate:
                # Check kwargs for dict data
                for value in kwargs.values():
                    if isinstance(value, dict):
                        data_to_validate = value
                        break
            
            if data_to_validate:
                is_valid, errors = validator.validate(data_to_validate, schema_name, definition_path)
                if not is_valid:
                    logger.warning(f"Input validation failed for {func.__name__}: {errors}")
                    # Don't raise exception - just log for now
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

def validate_output(schema_name: str, definition_path: Optional[str] = None):
    """Decorator to automatically validate function outputs."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            if isinstance(result, dict):
                is_valid, errors = validator.validate(result, schema_name, definition_path)
                if not is_valid:
                    logger.warning(f"Output validation failed for {func.__name__}: {errors}")
            
            return result
        return wrapper
    return decorator

# AI-friendly validation reporting
def generate_validation_report(
    data: Any,
    schema_name: str,
    definition_path: Optional[str] = None
) -> Dict[str, Any]:
    """Generate an AI-friendly validation report."""
    is_valid, errors = validator.validate(data, schema_name, definition_path)
    
    schema_info = validator.get_schema_info(schema_name)
    
    report = {
        'validation_result': {
            'is_valid': is_valid,
            'error_count': len(errors),
            'errors': errors
        },
        'schema_info': schema_info,
        'data_summary': {
            'type': type(data).__name__,
            'size': len(data) if hasattr(data, '__len__') else 'unknown',
            'keys': list(data.keys()) if isinstance(data, dict) else 'not_dict'
        },
        'ai_recommendations': _generate_validation_recommendations(is_valid, errors, data)
    }
    
    return report

def _generate_validation_recommendations(
    is_valid: bool,
    errors: List[str],
    data: Any
) -> List[str]:
    """Generate AI-friendly recommendations based on validation results."""
    recommendations = []
    
    if is_valid:
        recommendations.append("Data structure is valid and follows schema")
        return recommendations
    
    # Analyze common error patterns
    missing_fields = [e for e in errors if "required" in e.lower()]
    type_errors = [e for e in errors if "type" in e.lower()]
    format_errors = [e for e in errors if "format" in e.lower()]
    
    if missing_fields:
        recommendations.append(
            f"Missing required fields detected: {len(missing_fields)} errors. "
            "Check data collection logic to ensure all required fields are populated."
        )
    
    if type_errors:
        recommendations.append(
            f"Type mismatch errors detected: {len(type_errors)} errors. "
            "Verify data conversion and casting logic."
        )
    
    if format_errors:
        recommendations.append(
            f"Format validation errors detected: {len(format_errors)} errors. "
            "Check string formatting and data sanitization."
        )
    
    if isinstance(data, dict):
        actual_keys = set(data.keys())
        recommendations.append(
            f"Actual data keys: {sorted(actual_keys)}. "
            "Compare with schema requirements to identify missing or extra fields."
        )
    
    return recommendations
