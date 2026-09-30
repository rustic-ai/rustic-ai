# LocalSERPAgent

`LocalSERPAgent` is a drop-in replacement for [`SERPAgent`](serp_agent.md) for guilds that run on a user's own machine. It needs no SerpAPI key. Instead, it drives a real browser locally: the user's installed Google Chrome, with a persistent profile. Searches therefore come from the user's own IP address and browser, like ordinary browsing.

> **Local use only.** `LocalSERPAgent` is meant for one user running Rustic AI on their own computer. Use `SERPAgent` on shared or hosted infrastructure.

## Installation

```shell
pip install "rusticai-serpapi[local]"
```

The `local` extra adds `rusticai-playwright` and `beautifulsoup4`. The agent uses the installed Google Chrome. If Chrome isn't installed, the agent downloads Playwright's bundled Chromium the first time it runs.

## Usage

The messages are the same as `SERPAgent`'s, so switching agents only means changing `class_name` in the guild spec:

```json
{
  "name": "SERP Agent",
  "description": "Searches the web from the user's machine",
  "class_name": "rustic_ai.serpapi.local_agent.LocalSERPAgent",
  "properties": {"headless": false}
}
```

- **Input:** `SERPQuery(engine, query, id, num, start)`. The `engine` can be `google`, `bing` or `duckduckgo`.
- **Output:** `SERPResults`. Each result is a `MediaLink` with the same metadata keys as `SERPAgent` (`title`, `snippet`, `date`, `search_position`, `query_id`, `favicon`), plus `engine` and `source: "local_browser"`. A search that finds nothing returns an empty `SERPResults`.
- **Errors:** `SearchError`. The agent searches only the requested engine and never switches to another one on its own.

### Errors

When a search can't be completed, `SearchError.response` is:

```json
{"status": "Error", "engine": "google", "reason": "captcha", "error": "google showed a captcha page"}
```

| `reason` | Meaning |
|---|---|
| `captcha` | The engine showed a bot check. In headed mode, this also means the user didn't solve it within `captcha_wait_s`. |
| `consent` | The engine showed a consent page that couldn't be dismissed. |
| `timeout` | A page load or the whole search took too long. |
| `unsupported_engine` | The requested engine isn't `google`, `bing` or `duckduckgo`. |
| `browser_error` | The browser failed to launch or navigate. |

What to do next is up to the guild. For example, it can retry a `captcha` error with `engine: "bing"`, or pass the error back to the user.

If an engine blocks the agent after one or more pages have already loaded, the agent returns the results collected so far instead of an error.

## Modes

The `headless` property selects one of two modes:

| | `headless: true` (default) | `headless: false` |
|---|---|---|
| Browser | Invisible headless Chrome | Real Chrome window, kept minimized (`hide_window`) |
| Google | Often returns a `captcha` error | Usually answers |
| On a CAPTCHA | Returns a `captcha` error | Brings the window forward and waits up to `captcha_wait_s` for the user to solve it, then minimizes the window again. It asks at most once per search. |
| Needs a display | No | Yes. Without one, the agent falls back to headless mode. |

Use `headless: false` when a person is at the machine and Google results matter. Use `headless: true` for unattended runs, preferably with `bing` or `duckduckgo`.

## One-time profile setup (recommended)

Open the agent's browser profile once to accept consent banners, solve a CAPTCHA and, optionally, sign in to Google. The session is saved in the profile and used in both modes.

```shell
python -m rustic_ai.serpapi.local_setup          # or: rustic-local-serp-setup
```

Close the window when you're done. Stop any running `LocalSERPAgent` first, because a profile can be open in only one browser at a time. If the agent doesn't use the default profile location or browser, pass the same values with `--user-data-dir` and `--channel`.

## Configuration

| Property | Default | Description |
|---|---|---|
| `headless` | `true` | `false` runs a real, minimized Chrome window (see [Modes](#modes)). |
| `hide_window` | `true` | Headed mode: keep the window minimized except while a CAPTCHA needs solving. |
| `captcha_wait_s` | `120` | Headed mode: seconds to wait for the user to solve a CAPTCHA or consent page. `0` turns waiting off. |
| `browser_channel` | `"chrome"` | Playwright browser channel. `null` uses bundled Chromium. |
| `user_data_dir` | `~/.rustic_ai/local_serp/profile` | Root folder of the persistent browser profile. |
| `hl` / `gl` | `"en"` / `"us"` | Language and region. |
| `min_delay_s` / `max_delay_s` | `1.0` / `3.0` | Random pause between result pages. |
| `max_pages` | `5` | Maximum result pages loaded per search. |
| `navigation_timeout_s` | `30` | Timeout for each page load. |
| `search_timeout_s` | `120` | Timeout for a whole search, not counting time spent waiting for the user to solve a CAPTCHA. |
| `close_browser_after_request` | `false` | Close the browser after each search instead of keeping it open. |

## Notes

- Each agent runs one search at a time.
- Google's result links point to encrypted `/goto?url=...` redirects. The agent resolves them to the real URLs using the browser's session, and only for the results it returns.
- Bing and DuckDuckGo are paginated by clicking "Next". A large `start` therefore costs extra page loads and is limited by `max_pages`.
- If another browser already has the shared profile open, the agent uses a separate profile of its own.
