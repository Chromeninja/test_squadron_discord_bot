"""Debug nested value retrieval.

Developer utility moved into scripts/debug/.
"""

import asyncio

from services.config_service import ConfigService


async def test_nested_value():
    """Test the nested value logic."""
    config_service = ConfigService()

    # Test with flat key
    data = {"test.setting": {"nested": "value"}}

    print("Testing flat key retrieval:")
    print(f"Data: {data}")

    # This should work for flat keys
    result1 = config_service._get_nested_value(data, "test.setting")
    print(f"Result for 'test.setting': {result1}")

    # Test with nested structure
    nested_data = {
        "test": {
            "setting": {"nested": "value"}
        }
    }

    print("\nTesting nested key retrieval:")
    print(f"Data: {nested_data}")

    result2 = config_service._get_nested_value(nested_data, "test.setting")
    print(f"Result for 'test.setting' in nested: {result2}")


if __name__ == "__main__":
    asyncio.run(test_nested_value())
