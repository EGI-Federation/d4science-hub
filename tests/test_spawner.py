"""Tests for the spawner"""

from unittest import mock

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
    assert "witoil-authid" in [s.get("AuthId", "") for s in server_opts]
    assert vol_opts == {}

    # role of user and resource does not match
    server_opts, vol_opts = spawner.build_resource_options([], resources)
    assert "witoil-authid" not in [s.get("AuthId", "") for s in server_opts]
    assert vol_opts == {}

    # no role in the resource
    del resources["genericResources"]["Resource"][0]["Profile"]["Body"]["ServerOption"][
        "@role"
    ]
    server_opts, vol_opts = spawner.build_resource_options([], resources)
    assert "witoil-authid" in [s.get("AuthId", "") for s in server_opts]
    assert vol_opts == {}


@pytest.mark.asyncio
async def test_custom_user_options():
    spawner = D4ScienceSpawner(_mock=True)
    user_options = mock.MagicMock()
    spawner.custom_user_options = user_options
    await spawner.load_user_options()
    user_options.assert_called_once_with(spawner)


@pytest.mark.asyncio
async def test_profile_annotations():
    spawner = D4ScienceSpawner(_mock=True)
    spawner.allowed_profiles = ["foo"]
    spawner.server_options = [
        {
            "AuthId": "foo",
            "server_option_name": "ServerOption",
        }
    ]
    p = spawner.profile_list(spawner)
    assert p.pop()["kubespawner_override"]["extra_annotations"] == {
        "hub.jupyter.org/profile": "foo"
    }


@pytest.mark.asyncio
async def test_get_args():
    spawner = D4ScienceSpawner(_mock=True)
    spawner.default_url = "/foo"

    # if not RStudio
    args = spawner.get_args()
    assert set(
        ["--SingleUserNotebookApp.default_url=/foo", "--ServerApp.default_url=/foo"]
    ).issubset(args)

    # if RStudio
    with mock.patch("d4science_hub.spawner.D4ScienceSpawner.orm_spawner") as m_orm:
        m_orm.name = "RStudio"
        spawner.default_url = "/foo"
        args = spawner.get_args()
        assert set(
            [
                "--SingleUserNotebookApp.default_url=/rstudio",
                "--ServerApp.default_url=/rstudio",
            ]
        ).issubset(args)
