# Developer Getting Started

Ready to contribute? Here's how to set up for local development.

1. Fork [the repo](https://github.com/rustic-ai/python-framework) on GitHub.
2. Clone your fork locally

    ```sh
    git clone git@github.com:<your_github_username_name_here>/rustic_ai.git
    ```

3. Ensure Python 3.12 and [poetry](https://python-poetry.org/docs/1.8/) are installed.
4. Create a branch for local development:

    ```sh
    git checkout -b name-of-your-bugfix-or-feature
    ```
5. Install the dependencies:
    ```shell
    poetry self add poetry-plugin-mono-repo-deps@0.3.2
    poetry install --with dev --all-extras --sync
    ```

6. When you're done making changes, check that your changes pass the
   tests, including testing other Python versions, with tox:

    ```sh
    docker compose -f scripts/redis/docker-compose.yml up # Redis instance is required for integration tests
    # before proceeding, ensure env variables OPENAI_API_KEY, HUGGINGFACE_API_KEY, SERP_API_KEY are set
    poetry run tox
    ```

7. Commit your changes and push your branch to GitHub:

    ```sh
    git add .
    git commit -m "Your detailed description of your changes."
    git push origin name-of-your-bugfix-or-feature
    ```

    **Note:** Commit messages must follow the [Conventional Commits Specification](https://www.conventionalcommits.org/en/v1.0.0/). This ensures a standardized and semantic versioning-friendly commit history.

8. You may want to add the remote upstream repository to your local repository to stay in sync with the main repository:

    Run this command to add the upstream repository:
    ```sh
    git remote add upstream git@github.com:rustic-ai/python-framework.git
    ```

    You can verify if you added the upstream repository successfully by running the following command:
    ```sh
    git remote -v
    ```
    Now you can pull the latest changes from the main repository by running the following command:
    ```sh
    git pull --rebase upstream main
    ```
9. Submit a pull request through the GitHub website after ensuring you follow the guidelines.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. The code must follow [PEP 8](https://peps.python.org/pep-0008/) with one exception: lines can be up to 160 characters in length, not 79.
3. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring and add the
   feature to the list in [README.md](README.md).
4. IMPORTANT: Make sure the tests pass. Run the tests locally:

    ```sh
    poetry run tox
    ```

## Tips

* To run a subset of tests, specify the file names

    ```sh
    poetry run pytest core/tests/utils/test_gemstone_id.py
    ```

* To debug the messages with Redis, you can use Redis Insight. Both can be launched using docker compose.

    ```sh
    docker compose -f scripts/redis/docker-compose.yml up
    ```

    The Redis Insight server will be accessible [here](http://localhost:5540/).
    Add the Redis database manually by setting the host as `redis` and the port as `6379`.


## Creating a new module

Use the cookiecutter to create a new module

```shell
  poetry shell
  cookiecutter cookiecutter-rustic/
```

## Building from source
This project is a monorepo of all the different Rustic AI modules. Each module has its own folder and can be built
individually or altogether from the root folder.

**Prerequisites**
* Python 3.12
* [Poetry 1.8](https://python-poetry.org/docs/1.8/)

```shell
./scripts/poetry_install.sh
./scripts/poetry_build.sh
```

## Building Docker Image

The Dockerfile is configured to include all the modules in this repo.

On Linux systems,
```shell
docker build -t rusticai-api .
```

On Mac,
```shell
docker buildx build --platform linux/amd64 -t rusticai-api .
```