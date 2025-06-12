"""Tests for the spawner"""

import pytest
from d4science_hub.spawner import D4ScienceSpawner


@pytest.mark.asyncio
async def test_build_options_role():
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
    # role of user and resource matches
    server_opts, vol_opts = spawner.build_resource_options(roles, resources)
    assert "witoil-authid" in server_opts.keys()
    assert vol_opts == {}

    # role of user and resource does not match
    server_opts, vol_opts = spawner.build_resource_options([], resources)
    assert "witoil-authid" not in server_opts.keys()
    assert vol_opts == {}

    # no role in the resource
    del resources["genericResources"]["Resource"][0]["Profile"]["Body"]["ServerOption"][
        "@role"
    ]
    server_opts, vol_opts = spawner.build_resource_options([], resources)
    assert "witoil-authid" in server_opts.keys()
    assert vol_opts == {}
