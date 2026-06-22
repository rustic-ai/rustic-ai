import uniko

# Synchronous (for scripts/notebooks)
uni = uniko.Uniko.in_memory_sync()
agent = uni.agent("memory-assistant")
session = agent.session("user-session-1")

# Add observations
session.observe_sync(uniko.Turn("user", "I prefer working in Python"))
session.observe_sync(uniko.Turn("user", "My name is Nihal"))

# Recall memory
result = agent.recall_sync("user preferences")
for item in result.items:
    print(item.content)

# Async (for async applications)
import asyncio

async def main():
    uni = await uniko.Uniko.in_memory()
    agent = uni.agent("memory-assistant")
    session = agent.session("user-session-1")
    await session.observe(uniko.Turn("user", "I prefer working in Python"))
    bundle = await agent.recall("user preferences")
    for item in bundle.items:
        print(item.content)

asyncio.run(main())
