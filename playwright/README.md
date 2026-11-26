# Rustic AI Playwright

This module employs [Playwright](https://playwright.dev/python/docs/intro) to facilitate web scraping tasks.

## Installing

```shell
pip install rusticai-playwright
```
**Note:** It depends on [rusticai-core](https://pypi.org/project/rusticai-core/)

## Building from Source

```shell
poetry install --with dev
poetry build
```

## Cancellation and idle cleanup

An outer scrape timeout cancels the coroutine owned by that request and waits for cooperative context cleanup. Other requests on the shared browser event loop continue. Idle browser retention runs as a separate cleanup task after the result returns; its delay does not consume the successful request's result timeout. Shutdown cancels pending idle cleanup and closes owned browser resources.
