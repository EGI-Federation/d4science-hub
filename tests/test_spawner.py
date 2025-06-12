import pytest
from d4science_hub.spawner import D4ScienceSpawner


class DummyUser:
    name = "testuser"
    id = "testuser-id"


class DummySpawner:
    name = "rname-test"


@pytest.mark.asyncio
async def test_witoil_server_option_role():
    dummy_user = DummyUser()
    spawner = D4ScienceSpawner(user=dummy_user)  # Pass user at construction
    dummy_spawner = DummySpawner()

    # Simulate auth_state with WITOIL-User role
    auth_state_with_role = {
        "permissions": [{"rsname": "witoil-authid"}],
        "roles": ["WITOIL-User"],
        "resources": {
            "genericResources": {
                "Resource": [
                    {
                        "Profile": {
                            "Name": "WITOILServerOption",
                            "Body": {
                                "ServerOption": {
                                    "AuthId": "witoil-authid",
                                    "Info": {
                                        "Name": "WITOIL Option",
                                        "Description": "desc",
                                    },
                                    "@default": "true",
                                }
                            },
                        }
                    }
                ]
            }
        },
    }
    await spawner.auth_state_hook(dummy_spawner, auth_state_with_role)
    assert "witoil-authid" in spawner.server_options

    # Simulate auth_state without WITOIL-User role
    auth_state_without_role = {
        "permissions": [{"rsname": "witoil-authid"}],
        "roles": [],
        "resources": auth_state_with_role["resources"],
    }
    await spawner.auth_state_hook(dummy_spawner, auth_state_without_role)
    assert "witoil-authid" not in spawner.server_options
