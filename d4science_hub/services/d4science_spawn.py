"""An helper service to redirect users to the right server option.

It expects that the users is already authenticated.
"""

import os
import os.path
from urllib.parse import urlparse

from jupyterhub.services.auth import HubOAuthCallbackHandler, HubOAuthenticated
from jupyterhub.utils import url_path_join
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application, RequestHandler, authenticated


class D4ScienceHandler(HubOAuthenticated, RequestHandler):
    """Simple handler that redirects to the right spawn page
    for the user depending of the request"""

    @authenticated
    def get(self):
        user = self.get_current_user()
        server_name = self.request.path.split("/")[-1]
        if server_name:
            server_name = f"rname-{server_name}"
        dest_url = url_path_join("/hub/spawn/", user["name"], server_name)
        self.redirect(
            dest_url,
            permanent=False,
        )
        return


def main():
    app = Application(
        [
            (
                url_path_join(
                    os.environ["JUPYTERHUB_SERVICE_PREFIX"], "oauth_callback"
                ),
                HubOAuthCallbackHandler,
            ),
            (
                r"%s/[^/]*" % os.environ["JUPYTERHUB_SERVICE_PREFIX"],
                D4ScienceHandler,
            ),
        ],
        cookie_secret=os.urandom(32),
    )
    http_server = HTTPServer(app)
    url = urlparse(os.environ["JUPYTERHUB_SERVICE_URL"])
    http_server.listen(url.port)
    IOLoop.current().start()


if __name__ == "__main__":
    main()
