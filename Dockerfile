# Starting with the image used in helm jupyterhub
FROM quay.io/jupyterhub/k8s-hub:4.4.0

USER root

# Do installation in 2 phases to cache dependendencies
COPY requirements.txt /d4science-hub/
RUN pip3 install --no-cache-dir -r /d4science-hub/requirements.txt

# Now install the code itself
COPY . /d4science-hub/
# hadolint ignore=DL3013
RUN pip3 install --no-cache-dir /d4science-hub

# Copy images to the right place so they are found
RUN cp -r /d4science-hub/static/* /usr/local/share/jupyterhub/static/

HEALTHCHECK --interval=5m --timeout=3s \
  CMD curl -f http://localhost:8000/hub/health || exit 1

ARG NB_USER=jovyan
USER ${NB_USER}
