# syntax=docker/dockerfile:1.4
FROM python:3.13.0-slim AS base

ARG RAY_UID=1000
ARG RAY_GID=1000

RUN <<EOF
#!/bin/bash

groupadd -g $RAY_GID ray
useradd -ms /bin/bash -d /home/ray ray --uid $RAY_UID --gid $RAY_GID
usermod -aG sudo ray
echo 'ray ALL=NOPASSWD: ALL' >> /etc/sudoers

EOF

ENV HOME=/home/ray
SHELL ["/bin/bash", "-c"]

ENV APPDIR=$HOME/app
ENV VIRTUAL_ENV="${APPDIR}/.venv"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

RUN mkdir -p $APPDIR

WORKDIR $APPDIR

# Pull base image
FROM base AS builder

# Set environment varibles
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev

RUN pip install poetry==2.1.3

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

COPY . .

ENV SKIP_MODULE=testing

RUN scripts/poetry_install.sh

RUN scripts/poetry_build.sh


# The runtime image, used to just run the code provided its virtual environment
FROM base AS final

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY --from=builder ${APPDIR}/dist/*.whl ${APPDIR}/dist/
COPY conf ${APPDIR}/conf

RUN ${VIRTUAL_ENV}/bin/pip install ${APPDIR}/dist/*.whl

RUN rm -rf ${APPDIR}/dist

# System dependencies required for playwright
RUN playwright install --with-deps chromium

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev wget grep

# Expose port
EXPOSE 8880

RUN echo 'source $VIRTUAL_ENV/bin/activate' >> $HOME/.profile

RUN chown -R ray:ray $HOME

USER $RAY_UID
