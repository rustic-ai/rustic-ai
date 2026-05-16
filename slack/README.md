# Rustic AI Slack Integration Module

**Bidirectional** Slack integration for Rustic AI guilds with real-time Socket Mode support.

## Features

✅ **Socket Mode (Real-time)** - Receive Slack events via WebSocket (no public endpoint needed!)  
✅ **Natural Language Interface** - Send messages and manage channels using conversational requests  
✅ **Direct API Access** - Send messages, list channels, create channels programmatically  
✅ **Bidirectional Communication** - Bot responds to @mentions and DMs automatically  
✅ **Thread Support** - Replies stay in threads for organized conversations  
✅ **Simple Token Management** - Environment variable token storage  
✅ **LLM Tool Calling** - Automatic conversion of natural language to Slack API calls  
✅ **Multi-workspace Support** - Manage multiple Slack workspaces

## Installation

```bash
cd slack
poetry install --with dev --all-extras
```

## Quick Start

### 1. Create Slack App with Socket Mode

1. Visit https://api.slack.com/apps
2. Create new app → "From scratch"
3. **Socket Mode** → Enable Socket Mode
4. **Generate App-Level Token**:
   - Token Name: "Socket Mode Token"
   - Scopes: `connections:write`
   - Copy token (starts with `xapp-`)
5. **Event Subscriptions** → Enable Events
   - Subscribe to bot events:
     - `app_mention` - Bot is @mentioned
     - `message.channels` - Messages in channels
     - `message.im` - Direct messages
6. **OAuth & Permissions** → Add bot token scopes:
   - `app_mentions:read`
   - `chat:write`
   - `channels:read`
   - `channels:history`
   - `im:history`
   - `users:read`
7. **Install to workspace**
8. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### 2. Set Environment Variables

```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token-here"
export SLACK_APP_TOKEN="xapp-your-app-token-here"  # NEW - For Socket Mode
export OPENAI_API_KEY="sk-your-key-here"  # For LLM agent
```

### 3. Load the Guild

```python
from rustic_ai.core.guild.builders import GuildBuilder

# Build guild from JSON spec - Socket Mode connects automatically!
guild = GuildBuilder.from_json_file("slack/slack_guild.json").launch("my_org")

# Check logs for:
# INFO - SlackSocketModeAgent ready, starting Socket Mode listener...
# INFO - Connecting to Slack via Socket Mode...
# INFO - Socket Mode connected and listening for events!
```

### 4. Interact with Bot

#### In Slack (Socket Mode - Inbound)

```
# In any Slack channel where bot is a member:
@mybot what's the weather?

# Bot automatically:
# 1. Receives event via Socket Mode
# 2. Processes with LLM
# 3. Responds in thread
```

#### From Web App or Code (Outbound)

Send messages via guild:

#### Option A: Natural Language (via LLM)

```python
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    UserMessage
)

# Send to guild
request = ChatCompletionRequest(
    messages=[
        UserMessage(content="Send 'Hello team!' to #general")
    ]
)
# Publish request to guild...
```

#### Option B: Direct API Call

```python
from rustic_ai.slack.models.messages import SlackSendMessageRequest

request = SlackSendMessageRequest(
    workspace_id="default_workspace",
    channel="#general",
    text="Hello from Rustic AI!"
)
# Publish request to guild...
```

## Architecture

### Bidirectional Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    OUTBOUND (Guild → Slack)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Request (Web App)                                         │
│    │                                                             │
│    ▼                                                             │
│  ChatCompletionRequest ("send hello to #general")              │
│    │                                                             │
│    ▼                                                             │
│  SlackLLM Agent (LLMAgent with tools)                          │
│    │ (converts to API call)                                     │
│    ▼                                                             │
│  SlackSendMessageRequest                                        │
│    │                                                             │
│    ▼                                                             │
│  SlackConnector Agent                                           │
│    │ (uses SLACK_BOT_TOKEN)                                     │
│    ▼                                                             │
│  POST https://slack.com/api/chat.postMessage                   │
│    │                                                             │
│    ▼                                                             │
│  ✅ Message appears in Slack                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    INBOUND (Slack → Guild)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User in Slack: "@mybot hello"                                 │
│    │                                                             │
│    ▼                                                             │
│  Slack sends event via Socket Mode WebSocket                   │
│    │                                                             │
│    ▼                                                             │
│  SlackSocketModeAgent (WebSocket listener)                     │
│    │ (receives app_mention event)                              │
│    ▼                                                             │
│  Publishes SlackEventMessage to SLACK_INBOUND topic            │
│    │                                                             │
│    ▼                                                             │
│  SlackEventHandlerAgent                                         │
│    │ (cleans @mention, adds context)                           │
│    ▼                                                             │
│  ChatCompletionRequest("hello")                                │
│    │                                                             │
│    ▼                                                             │
│  SlackLLM Agent (processes request)                            │
│    │                                                             │
│    ▼                                                             │
│  SlackSendMessageRequest (with thread_ts for threading)        │
│    │                                                             │
│    ▼                                                             │
│  SlackConnectorAgent                                            │
│    │                                                             │
│    ▼                                                             │
│  POST https://slack.com/api/chat.postMessage                   │
│    │                                                             │
│    ▼                                                             │
│  ✅ Bot replies in Slack thread                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Agents

**SlackSocketMode** (`slack_socket_mode`) - NEW!
- Connects to Slack via Socket Mode WebSocket
- Receives real-time events (mentions, messages, reactions)
- Publishes events to guild message bus
- No public endpoint required

**SlackEventHandler** (`slack_event_handler`) - NEW!
- Processes incoming Slack events
- Cleans up @mentions and formats messages
- Routes events to appropriate handlers (LLM, custom agents)
- Maintains context for threaded replies

**SlackConnector** (`slack_connector`)
- Handles all Slack API operations (outbound)
- Reads token from `SLACK_BOT_TOKEN` env var
- Supports messages, channels, users, files, reactions
- Uses thread context from session state for replies

**SlackLLM** (`slack_llm`)
- Natural language interface using LLMAgent
- Configured with Slack tools (send_message, list_channels, create_channel)
- Converts user requests to API calls
- Processes both web app requests and Slack events

## API Reference

### Message Operations

```python
# Send message
SlackSendMessageRequest(
    workspace_id="default_workspace",
    channel="#general",  # or channel ID "C123ABC"
    text="Hello Slack!",
)

# Update message
SlackUpdateMessageRequest(
    workspace_id="default_workspace",
    channel="C123ABC",
    ts="1234567890.123456",
    text="Updated message",
)

# Delete message
SlackDeleteMessageRequest(
    workspace_id="default_workspace",
    channel="C123ABC",
    ts="1234567890.123456",
)

# Get message history
SlackGetMessagesRequest(
    workspace_id="default_workspace",
    channel="C123ABC",
    limit=100,
)
```

### Channel Operations

```python
# List channels
SlackListChannelsRequest(
    workspace_id="default_workspace",
    types="public_channel,private_channel",  # comma-separated
    exclude_archived=True,
    limit=100,
)

# Create channel
SlackCreateChannelRequest(
    workspace_id="default_workspace",
    name="new-channel",  # lowercase, hyphens only
    is_private=False,
)

# Join channel
SlackJoinChannelRequest(
    workspace_id="default_workspace",
    channel="C123ABC",
)

# Invite to channel
SlackInviteToChannelRequest(
    workspace_id="default_workspace",
    channel="C123ABC",
    users=["U123ABC"],
)
```

## Guild Specification

The guild is defined in `slack_guild.json` with:

- **2 agents**: SlackConnector + SlackLLM
- **3 tools** for LLM:
  - `send_message` → SlackSendMessageRequest
  - `list_channels` → SlackListChannelsRequest
  - `create_channel` → SlackCreateChannelRequest
- **Topic-based routing**:
  - `SLACK_CHAT` - LLM conversations
  - `SLACK_API` - Direct API operations
  - `user_message_broadcast` - Responses to user

## Token Management

### Environment Variable (Primary)

```bash
export SLACK_BOT_TOKEN="xoxb-your-token"
```

SlackConnector checks `SLACK_BOT_TOKEN` first.

### Guild State (Fallback)

```python
# Set in guild state
await guild.set_state("slack_bot_token", "xoxb-new-token")

# Clear cache to reload
slack_connector = guild._agents_by_name["SlackConnector"]
slack_connector._clients.clear()
slack_connector._token = None
```

## Socket Mode vs HTTP Webhooks

This module uses **Socket Mode** instead of HTTP webhooks for receiving events:

| Feature | Socket Mode ✅ | HTTP Webhooks |
|---------|--------------|---------------|
| **Public endpoint** | Not needed | Required (HTTPS) |
| **Firewall** | Works behind firewall | Requires inbound access |
| **Development** | Local testing easy | Need ngrok/public URL |
| **Connection** | WebSocket (persistent) | HTTP POST (per event) |
| **Setup complexity** | Simple (2 tokens) | Complex (webhook verification) |
| **Security** | WSS connection | Signature verification |
| **Best for** | Internal tools, dev | Public apps, production |

**Why Socket Mode?**
- ✅ No public server needed
- ✅ Works on localhost
- ✅ Simpler setup
- ✅ Faster development
- ✅ Consistent with WebSocket architecture

## Configuration

### Required Scopes

```
# Socket Mode
connections:write    # Socket Mode connection (app-level token)

# Bot Token Scopes
app_mentions:read    # Receive @bot mentions
chat:write           # Post messages
channels:read        # View channel info
channels:history     # View channel messages
im:history           # View DM messages
users:read           # View user info
```

### Environment Variables

```bash
SLACK_BOT_TOKEN=xoxb-your-token        # Required
SLACK_APP_TOKEN=xapp-your-token        # Required (Socket Mode)
OPENAI_API_KEY=sk-your-key             # Required for LLM agent
```

## Testing

```bash
# Run tests
cd slack
poetry run pytest

# Run specific test
poetry run pytest tests/test_connector_agent.py
```

## Examples

### Example 1: Send Notification

```python
from rustic_ai.slack.models.messages import SlackSendMessageRequest

request = SlackSendMessageRequest(
    workspace_id="default_workspace",
    channel="#notifications",
    text="Deployment completed successfully!"
)
```

### Example 2: List Channels

```python
from rustic_ai.slack.models.channels import SlackListChannelsRequest

request = SlackListChannelsRequest(
    workspace_id="default_workspace",
    types="public_channel",
    limit=50
)
```

### Example 3: Natural Language

```python
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    ChatCompletionRequest,
    UserMessage
)

request = ChatCompletionRequest(
    messages=[
        UserMessage(content="Create a new channel called project-alpha")
    ]
)
```

## Troubleshooting

### "No Slack bot token found"

```bash
# Check if set
echo $SLACK_BOT_TOKEN

# Set it
export SLACK_BOT_TOKEN="xoxb-your-token"
```

### "Channel not found"

Invite the bot to the channel first:
```
# In Slack:
/invite @YourBot
```

### "Missing scope"

1. Go to https://api.slack.com/apps
2. Your App → OAuth & Permissions
3. Add missing scope under "Bot Token Scopes"
4. Reinstall to workspace
5. Update `SLACK_BOT_TOKEN`

## Module Structure

```
slack/
├── src/rustic_ai/slack/
│   ├── agents/
│   │   └── connector_agent.py    # SlackConnectorAgent
│   ├── client/
│   │   └── slack_client.py       # SlackAPIClient
│   ├── models/
│   │   ├── messages.py           # Message models
│   │   ├── channels.py           # Channel models
│   │   └── users.py             # User models
│   └── __init__.py
├── tests/
│   ├── test_connector_agent.py
│   └── ...
├── slack_guild.json              # Guild specification
├── pyproject.toml
└── README.md
```

## License

Apache-2.0

---

**Built with ❤️ for Rustic AI**
