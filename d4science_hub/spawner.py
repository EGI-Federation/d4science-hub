"""D4Science Authenticator for JupyterHub
"""

from kubespawner import KubeSpawner
from traitlets import Bool, Dict, List, Unicode


class D4ScienceSpawner(KubeSpawner):
    frame_ancestors = Unicode(
        "https://*.d4science.org 'self'",
        config=True,
        help="""Frame ancestors for embedding the hub in d4science""",
    )
    use_ophidia = Bool(
        True,
        config=True,
        help="""Whether to enable or not the ophidia setup""",
    )
    ophidia_image = Unicode(
        "ophidiabigdata/ophidia-backend-hub:v1.1",
        config=True,
        help="""Ophidia image""",
    )
    ophidia_user = Unicode(
        "oph-test",
        config=True,
        help="""Ophidia user""",
    )
    ophidia_passwd = Unicode(
        "abcd",
        config=True,
        help="""Ophidia password""",
    )
    workspace_security_context = Dict(
        {
            "capabilities": {"add": ["SYS_ADMIN"]},
            "privileged": True,
            "runAsUser": 1000,
        },
        config=True,
        help="""Container security context for mounting the workspace""",
    )
    use_sidecar = Bool(
        True,
        config=True,
        help="""Whether to use or not a sidecar for the workspace""",
    )
    sidecar_image = Unicode(
        "eginotebooks/d4science-storage",
        config=True,
        help="""the D4science storage image to use""",
    )
    volume_mappings = Dict(
        {},
        config=True,
        help="""Mapping of extra volumes from the information system to k8s volumes
                Dicts should have an entry for each of the extra volumes as follows:
                {
                    'name-of-extra-volume': {
                        'mount_path': '/home/jovyan/dataspace',
                        'volume': { k8s object defining the volume},
                    }
                }
            """,
    )
    extra_profiles = List(
        [],
        config=True,
        help="""Extra profiles to add to user options independently of the configuration
                from the D4Science Information System. The profiles should be a list of
                dictionaries as defined in the Kubespanwer
                https://jupyterhub-kubespawner.readthedocs.io/en/latest/spawner.html#kubespawner.KubeSpawner.profile_list
            """,
    )
    server_options_names = List(
        ["ServerOption", "RStudioServerOption"],
        config=True,
        help="""Name of ServerOptions to consider from the D4Science Information
                System. These can be then used for filtering with named servers""",
    )
    default_server_option_name = Unicode(
        "ServerOption",
        config=True,
        help="""Name of default ServerOption (to be used
                if no named server is spawned)""",
    )
    server_name_prefix = Unicode(
        "rname-",
        config=True,
        help="""Prefix for naming the servers""",
    )
    data_manager_role = Unicode(
        "Data-Manager",
        config=True,
        help="""Name of the data manager role in D4Science""",
    )
    context_namespaces = Bool(
        False,
        config=True,
        help="""Whether context-specific namespaces will be used or not""",
    )
    image_repo_override = Unicode(
        "",
        config=True,
        help="""If provided, override image repository with this value""",
    )
    gpu_override = Dict(
        {
            "node_selector": {
                "cloud.google.com/gke-nodepool": "d4science-prod-vre-gke-nodepool2"
            },
            "extra_resource_guarantees": {"nvidia.com/gpu": 1},
            "extra_resource_limits": {"nvidia.com/gpu": 1},
        },
        config=True,
        help="""Configuration to add for GPU servers""",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_profiles = []
        self.server_options = []
        self._orig_volumes = self.volumes
        self._orig_volume_mounts = self.volume_mounts
        if self.image_repo_override:
            # pylint: disable-next=access-member-before-definition
            image = self.image.rsplit("/", 1)[-1]
            self.image = f"{self.image_repo_override}/{image}"

    async def _ensure_namespace(self):
        if not self.context_namespaces:
            super()._ensure_namespace()

    def get_args(self):
        args = super().get_args()
        # TODO: check if this keeps making sense
        return [
            "--FileCheckpoints.checkpoint_dir='/home/jovyan/.notebookCheckpoints'",
            "--FileContentsManager.use_atomic_writing=False",
            "--ResourceUseDisplay.track_cpu_percent=True",
            "--NotebookApp.iopub_data_rate_limit=100000000",
        ] + args

    def get_volume_name(self, name):
        return name.strip().lower().replace(" ", "-")

    async def auth_state_hook(self, spawner, auth_state):
        if not auth_state:
            return
        # just get from the authenticator
        permissions = auth_state.get("permissions", [])
        roles = auth_state.get("roles", [])
        self.log.debug("Roles at hook: %s", roles)
        self.allowed_profiles = [claim["rsname"] for claim in permissions]
        resources = auth_state.get("resources", {})
        self.server_options = {}
        volume_options = {}
        try:
            resource_list = resources["genericResources"]["Resource"]
            if not isinstance(resource_list, list):
                resource_list = [resource_list]
            for opt in resource_list:
                p = opt.get("Profile", {}).get("Body", {})
                if p.get("ServerOption", None):
                    name = opt.get("Profile", {}).get("Name", "")
                    if name in self.server_options_names:
                        self.server_options[p["ServerOption"]["AuthId"]] = p[
                            "ServerOption"
                        ]
                        self.server_options[p["ServerOption"]["AuthId"]].update(
                            {"server_option_name": name}
                        )
                elif p.get("VolumeOption", None):
                    volume_options[p["VolumeOption"]["Name"]] = p["VolumeOption"][
                        "Permission"
                    ]
        except KeyError:
            self.log.debug("Unexpected resource response from D4Science")

        self.volumes = self._orig_volumes.copy()
        self.volume_mounts = self._orig_volume_mounts.copy()
        for name, permission in volume_options.items():
            if name in self.volume_mappings:
                vol_name = self.get_volume_name(name)
                vol = {"name": (vol_name)}
                vol.update(self.volume_mappings[name]["volume"])
                self.volumes.append(vol)
                read_write = (permission == "Read-Write") or (
                    self.data_manager_role in roles
                )
                self.log.debug(
                    "permission: %s, data-manager: %s",
                    permission,
                    self.data_manager_role in roles,
                )
                self.volume_mounts.append(
                    {
                        "name": vol_name,
                        "mountPath": self.volume_mappings[name]["mount_path"],
                        "readOnly": not read_write,
                    },
                )
        self.log.debug("allowed: %s", self.allowed_profiles)
        self.log.debug("opts: %s", self.server_options)
        self.log.debug("volume_options %s", volume_options)
        self.log.debug("volumes: %s", self.volumes)
        self.log.debug("volume_mounts: %s", self.volume_mounts)
        self.log.debug("volume_mappings: %s", self.volume_mappings)

    def profile_list(self, spawner):
        # returns the list of profiles built according to the permissions
        # and resource definition that the authenticator obtained initially
        profiles = []

        # Requires python 3.9!
        server_option_name = (
            spawner.name.removeprefix(self.server_name_prefix)
            if spawner.name
            else self.default_server_option_name
        )

        if self.allowed_profiles and self.server_options:
            for allowed in self.allowed_profiles:
                p = self.server_options.get(allowed, None)
                if not p:
                    continue
                override = {}
                name = p.get("Info", {}).get("Name", "")
                if p.get("server_option_name", "") != server_option_name:
                    self.log.debug(
                        "Discarding %s as it uses %s",
                        name,
                        p.get("server_option_name", ""),
                    )
                    continue
                if "ImageId" in p:
                    image = p.get("ImageId", "")
                    if self.image_repo_override:
                        image = image.rsplit("/", 1)[-1]
                        image = f"{self.image_repo_override}/{image}"
                    override["image"] = image
                if "Cut" in p:
                    cut_info = []
                    if "Cores" in p["Cut"]:
                        override["cpu_limit"] = float(p["Cut"]["Cores"])
                        override["cpu_guarantee"] = (
                            1 if override["cpu_limit"] <= 4 else 2
                        )
                        cut_info.append(f"{p['Cut']['Cores']} Cores")
                    if "Memory" in p["Cut"]:
                        override["mem_limit"] = (
                            "%(#text)s%(@unit)s" % p["Cut"]["Memory"]
                        )
                        cut_info.append(f"{override['mem_limit']} RAM")
                    name += " - %s" % " / ".join(cut_info)
                if p.get("@gpu", {}) == "true":
                    override.update(self.gpu_override)
                profile = {
                    "display_name": name,
                    "description": p.get("Info", {}).get("Description", ""),
                    "slug": p.get("AuthId", ""),
                    "kubespawner_override": override,
                    "default": p.get("@default", {}) == "true",
                }
                if profile["default"]:
                    profiles.insert(0, profile)
                else:
                    profiles.append(profile)
        if self.extra_profiles:
            profiles.extend(self.extra_profiles)
        sorted_profiles = sorted(profiles, key=lambda x: x["display_name"])
        self.log.debug("Profiles: %s", sorted_profiles)
        return sorted_profiles

    def _configure_ophidia(self, spawner):
        if not self.use_ophidia:
            return
        chosen_profile = spawner.user_options.get("profile", "")
        if "ophidia" in chosen_profile:
            ophidia_mounts = [
                m for m in spawner.volume_mounts if m["name"] != "workspace"
            ]
            ophidia = {
                "name": "ophidia",
                "image": self.ophidia_image,
                "volumeMounts": ophidia_mounts,
            }
            spawner.extra_containers.append(ophidia)
            spawner.environment["OPH_USER"] = self.ophidia_user
            spawner.environment["OPH_PASSWD"] = self.ophidia_passwd
            spawner.environment["OPH_SERVER_HOST"] = "127.0.0.1"
            spawner.environment["HDF5_USE_FILE_LOCKING"] = "FALSE"

    def _configure_workspace(self, spawner):
        token = spawner.environment.get("D4SCIENCE_TOKEN", "")
        if not token:
            self.log.debug("Not configuring workspace access, there is no token")
            return
        if self.use_sidecar:
            sidecar = {
                "name": "workspace-sidecar",
                "image": self.sidecar_image,
                "securityContext": self.workspace_security_context,
                "env": [
                    {"name": "MNTPATH", "value": "/workspace"},
                    {"name": "D4SCIENCE_TOKEN", "value": token},
                ],
                "volumeMounts": [
                    {"mountPath": "/workspace:shared", "name": "workspace"},
                ],
                "lifecycle": {
                    "preStop": {
                        "exec": {"command": ["fusermount", "-uz", "/workspace"]}
                    },
                },
            }
            spawner.extra_containers.append(sidecar)
        else:
            spawner.container_security_context = self.workspace_security_context

    async def pre_spawn_hook(self, spawner):
        context = spawner.environment.get("D4SCIENCE_CONTEXT", "")
        if context:
            # set the whole context as annotation (needed for accounting)
            spawner.extra_annotations["d4science_context"] = context
            # set only the VRE name in the environment (needed for NFS subpath)
            vre = context[context.rindex("/") + 1 :]
            spawner.log.debug("VRE: %s", vre)
            spawner.environment["VRE"] = vre
        # TODO(enolfc): check whether assigning to [] is safe
        spawner.extra_containers = []
        self._configure_workspace(spawner)
        self._configure_ophidia(spawner)
