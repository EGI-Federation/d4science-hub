"""D4Science Authenticator for JupyterHub"""

import base64
import json
import os
from urllib.parse import quote_plus, unquote, urlencode

import jwt
import xmltodict
from jupyterhub.utils import url_path_join
from oauthenticator.generic import GenericOAuthenticator
from oauthenticator.oauth2 import OAuthLoginHandler
from tornado import web
from tornado.httpclient import AsyncHTTPClient, HTTPError, HTTPRequest
from traitlets import Unicode

D4SCIENCE_REGISTRY_BASE_URL = os.environ.get(
    "D4SCIENCE_REGISTRY_BASE_URL",
    "https://registry.d4science.org/icproxy/gcube/service",
)
D4SCIENCE_OIDC_URL = os.environ.get(
    "D4SCIENCE_OIDC_URL", "https://accounts.d4science.org/auth/realms/d4science/"
)
JUPYTERHUB_INFOSYS_URL = os.environ.get(
    "JUPYTERHUB_INFOSYS_URL",
    D4SCIENCE_REGISTRY_BASE_URL + "/GenericResource/JupyterHub",
)
DM_INFOSYS_URL = os.environ.get(
    "DM_INFOSYS_URL",
    D4SCIENCE_REGISTRY_BASE_URL + "/ServiceEndpoint/DataAnalysis/DataMiner",
)
D4SCIENCE_DISCOVER_WPS = os.environ.get(
    "D4SCIENCE_DISCOVER_WPS",
    "false",
)


class D4ScienceContextHandler(OAuthLoginHandler):
    """manages the params for the authenticator"""

    def get(self):
        context = self.get_argument("context", None)
        namespace = self.get_argument("namespace", None)
        label = self.get_argument("label", None)
        self.authenticator.d4science_context = context
        self.authenticator.d4science_namespace = namespace
        self.authenticator.d4science_label = label
        return super().get()


class D4ScienceOauthenticator(GenericOAuthenticator):
    login_handler = D4ScienceContextHandler
    # some options that will come from the context handler
    d4science_context = None
    d4science_namespace = None
    d4science_label = None

    d4science_oidc_url = Unicode(
        D4SCIENCE_OIDC_URL,
        config=True,
        help="""The OIDC URL for D4science""",
    )
    jupyterhub_infosys_url = Unicode(
        JUPYTERHUB_INFOSYS_URL,
        config=True,
        help="""The URL for getting JupyterHub profiles from the
                Information System of D4science""",
    )
    dm_infosys_url = Unicode(
        DM_INFOSYS_URL,
        config=True,
        help="""The URL for getting DataMiner resources from the
                Information System of D4science""",
    )
    d4science_label_name = Unicode(
        "d4science-namespace",
        config=True,
        help="""The name of the label to use when setting extra labels
                coming from the authentication (i.e. label="blue-cloud"
                as param)""",
    )

    _pubkeys = None

    async def get_iam_public_keys(self):
        if self._pubkeys:
            return self._pubkeys
        discovery_url = url_path_join(
            self.d4science_oidc_url, ".well-known/openid-configuration"
        )
        self.log.debug("Getting OIDC discovery info at %s", discovery_url)
        http_client = AsyncHTTPClient()
        req = HTTPRequest(discovery_url, method="GET")
        try:
            resp = await http_client.fetch(req)
        except HTTPError as e:
            # whatever, get out
            self.log.warning("Discovery endpoint not working? %s", e)
            raise web.HTTPError(403)
        jwks_uri = json.loads(resp.body.decode("utf8", "replace"))["jwks_uri"]
        self.log.debug("Getting JWKS info at %s", jwks_uri)
        req = HTTPRequest(jwks_uri, method="GET")
        try:
            resp = await http_client.fetch(req)
        except HTTPError as e:
            # whatever, get out
            self.log.warning("Unable to get jwks info: %s", e)
            raise web.HTTPError(403)
        self._pubkeys = {}
        jwks_keys = json.loads(resp.body.decode("utf8", "replace"))["keys"]
        for jwk in jwks_keys:
            kid = jwk["kid"]
            self._pubkeys[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        return self._pubkeys

    async def get_uma_token(self, context, audience, access_token, extra_params={}):
        body = {
            "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
            "claim_token_format": "urn:ietf:params:oauth:token-type:jwt",
            "audience": audience,
        }
        body.update(extra_params)
        http_client = AsyncHTTPClient()
        req = HTTPRequest(
            self.token_url,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "Authorization": f"Bearer {access_token}",
            },
            body=urlencode(body),
        )
        try:
            resp = await http_client.fetch(req)
        except HTTPError as e:
            # whatever, get out
            self.log.warning("Unable to get the permission for user: %s", e)
            raise web.HTTPError(403)
        self.log.debug("Got UMA ticket from server...")
        token = json.loads(resp.body.decode("utf8", "replace"))["access_token"]
        kid = jwt.get_unverified_header(token)["kid"]
        key = (await self.get_iam_public_keys())[kid]
        decoded_token = jwt.decode(
            token,
            key=key,
            audience=audience,
            algorithms=["RS256"],
        )
        self.log.debug("Decoded token: %s", decoded_token)
        return token, decoded_token

    async def get_wps(self, access_token):
        # discover WPS if enabled
        wps_endpoint = {}
        if D4SCIENCE_DISCOVER_WPS.lower() in ["true", "1"]:
            http_client = AsyncHTTPClient()
            req = HTTPRequest(
                self.dm_infosys_url,
                method="GET",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )
            try:
                resp = await http_client.fetch(req)
            except HTTPError as e:
                self.log.warning("Unable to get the resources for user: %s", e)
                self.log.debug(req)
                # no need to fail here
                return wps_endpoint
            dm = xmltodict.parse(resp.body)
            try:
                for ap in dm["serviceEndpoints"]["Resource"]["Profile"]["AccessPoint"]:
                    if ap["Interface"]["Endpoint"]["@EntryName"] == "Cluster":
                        wps_endpoint = {
                            "D4SCIENCE_WPS_URL": ap["Interface"]["Endpoint"]["#text"]
                        }
            except KeyError as e:
                # unexpected xml, just keep going
                self.log.warning("Unexpected XML: %s", e)
                self.log.debug(dm)
        return wps_endpoint

    async def get_resources(self, access_token):
        http_client = AsyncHTTPClient()
        req = HTTPRequest(
            self.jupyterhub_infosys_url,
            method="GET",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        try:
            resp = await http_client.fetch(req)
        except HTTPError as e:
            # whatever, get out
            self.log.warning("Unable to get the resources for user: %s", e)
            self.log.debug(req)
            raise web.HTTPError(403)
        self.log.debug("Got resources description...")
        # Assume that this will fly
        return xmltodict.parse(resp.body)

    def _get_d4science_attr(self, attr_name):
        v = getattr(self, attr_name, None)
        if v:
            return quote_plus(v)
        return None

    async def authenticate(self, handler, data=None):
        # first get authorized upstream
        user_data = await super().authenticate(handler, data)
        context = self._get_d4science_attr("d4science_context")
        self.log.debug("Context is %s", context)
        if not context:
            self.log.error("Unable to get the user context")
            raise web.HTTPError(403)
        access_token = user_data["auth_state"]["access_token"]
        extra_params = {
            "claim_token": base64.b64encode(
                json.dumps({"context": [f"{context}"]}).encode("utf-8")
            )
        }
        token, decoded_token = await self.get_uma_token(
            context, self.client_id, access_token, extra_params
        )
        ws_token, decoded_ws_token = await self.get_uma_token(
            context, context, access_token
        )
        permissions = decoded_token["authorization"]["permissions"]
        self.log.debug("Permissions: %s", permissions)
        roles = (
            decoded_ws_token.get("resource_access", {})
            .get(context, {})
            .get("roles", [])
        )
        self.log.debug("Roles: %s", roles)
        resources = await self.get_resources(ws_token)
        self.log.debug("Resources: %s", resources)
        user_data["auth_state"].update(
            {
                "context_token": ws_token,
                "permissions": permissions,
                "context": context,
                "namespace": self._get_d4science_attr("d4science_namespace"),
                "label": self._get_d4science_attr("d4science_label"),
                "resources": resources,
                "roles": roles,
            }
        )
        # get WPS endpoint in also
        user_data["auth_state"].update(await self.get_wps(ws_token))
        return user_data

    async def pre_spawn_start(self, user, spawner):
        """Pass relevant variables to spawner via environment variable"""
        auth_state = await user.get_auth_state()
        if not auth_state:
            # auth_state not enabled
            return
        namespace = auth_state.get("namespace", None)
        if namespace:
            spawner.namespace = namespace
        label = auth_state.get("label", None)
        if label:
            spawner.extra_labels[self.d4science_label_name] = label
        # GCUBE_TOKEN should be removed in the future
        spawner.environment["GCUBE_TOKEN"] = auth_state["context_token"]
        spawner.environment["D4SCIENCE_TOKEN"] = auth_state["context_token"]
        # GCUBE_CONTEXT should be removed in the future
        spawner.environment["GCUBE_CONTEXT"] = unquote(auth_state["context"])
        spawner.environment["D4SCIENCE_CONTEXT"] = unquote(auth_state["context"])
        if "D4SCIENCE_WPS_URL" in auth_state:
            spawner.environment["DATAMINER_URL"] = auth_state["D4SCIENCE_WPS_URL"]
