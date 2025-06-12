"""Tests for the spawner"""

import pytest
from d4science_hub.spawner import D4ScienceSpawner


@pytest.mark.asyncio
async def test_build_options_role():
    dummy_user = DummyUser()
    spawner = D4ScienceSpawner(_mock=True)
    roles = ["foo-role"]
    resources = {
        "genericResources": {
            "Resource": [
                {
                    "Profile": {
                        "Name": "ServerOption",
                        "Body": {
                            "ServerOption": {
                                "AuthId": "witoil-authid",
                                "Info": {
                                    "Name": "WITOIL Option",
                                    "Description": "desc",
                                },
                                "@default": "true",
                                "@role": "foo-role",
                            }
                        },
                    }
                }
            ]
        }
    }
    server_opts, vol_opts = spawner.build_resource_options(roles, resources)
    assert "witoil-authid" in server_opts.keys()
    assert vol_opts == {}
