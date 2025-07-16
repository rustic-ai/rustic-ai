# Multiprocess Execution Engine

The Multiprocess Execution Engine provides true parallel execution by running agents in separate processes, completely escaping Python's Global Interpreter Lock (GIL). This enables CPU-intensive tasks to run with genuine parallelism while providing process isolation for enhanced robustness.

## Overview

The multiprocess execution engine consists of three main components:

1. **MultiProcessExecutionEngine**: The main execution engine that manages agent processes
2. **MultiProcessAgentWrapper**: Wraps agents and runs them in separate processes
3. **MultiProcessAgentTracker**: Tracks and manages agent processes using shared memory

## Key Features

### Core Execution Features
- **True Parallelism**: Completely escapes Python's GIL for genuine concurrent execution
- **Process Isolation**: Each agent runs in its own process, providing fault tolerance
- **Shared Memory Tracking**: Cross-process agent management using multiprocessing.Manager
- **Graceful Shutdown**: Proper process termination with timeout handling
- **Process Limits**: Configurable maximum number of concurrent processes
- **Automatic Cleanup**: Dead process detection and cleanup

### Process Management Features
- **Process Health Monitoring**: Real-time monitoring of agent process status
- **Resource Management**: Proper cleanup of processes and shared memory
- **Fault Tolerance**: Automatic detection and handling of crashed processes
- **Process Information**: Detailed process info including PID, status, and memory usage
- **Cross-platform Support**: Uses 'spawn' start method for compatibility

### Integration Features
- **Messaging Support**: Works seamlessly with socket messaging and Redis backends
- **Dependency Injection**: Full support for agent dependencies across processes
- **Guild Integration**: Complete integration with guild lifecycle management
- **Statistics**: Comprehensive engine and process statistics

## Basic Usage

### Simple Setup

```python
from rustic_ai.core.guild.execution.multiprocess import MultiProcessExecutionEngine

# Create engine with default CPU count
engine = MultiProcessExecutionEngine(guild_id="my-guild")

# Create engine with specific process limit
engine = MultiProcessExecutionEngine(guild_id="my-guild", max_processes=8)
```

### With Guild

```python
from rustic_ai.core.guild import Guild
from rustic_ai.core.guild.execution.multiprocess import MultiProcessExecutionEngine
from rustic_ai.core.messaging.backend.embedded_backend import create_embedded_messaging_config

# Create messaging config that works well with multiprocess
messaging_config = create_embedded_messaging_config()

# Create guild with multiprocess engine
guild = Guild(
    guild_id="cpu_intensive_guild",
    execution_engine=MultiProcessExecutionEngine(
        guild_id="cpu_intensive_guild",
        max_processes=multiprocessing.cpu_count()
    ),
    messaging_config=messaging_config
)

# Launch CPU-intensive agents
for i in range(4):
    agent_spec = create_cpu_intensive_agent_spec(f"worker_{i}")
    guild.launch_agent(agent_spec)
```

## Advanced Usage

### CPU-Intensive Workloads

```python
from rustic_ai.core.guild import AgentBuilder
import multiprocessing

# Create agents for parallel computation
def create_computation_agents(guild, data_chunks):
    engine = MultiProcessExecutionEngine(
        guild_id=guild.id,
        max_processes=multiprocessing.cpu_count()
    )
    
    agents = []
    for i, chunk in enumerate(data_chunks):
        agent_spec = (AgentBuilder()
            .set_name(f"compute_worker_{i}")
            .set_description(f"Process data chunk {i}")
            .set_class_name("ComputeAgent")
            .add_dependency("data_chunk", chunk)
            .build_spec())
        
        guild.launch_agent(agent_spec, execution_engine=engine)
        agents.append(agent_spec)
    
    return agents
```

### Process Monitoring

```python
# Monitor agent processes
def monitor_agents(engine, guild_id):
    agents = engine.get_agents_in_guild(guild_id)
    
    for agent_id, agent_spec in agents.items():
        process_info = engine.get_process_info(guild_id, agent_id)
        is_alive = engine.is_agent_running(guild_id, agent_id)
        
        print(f"Agent {agent_id}:")
        print(f"  PID: {process_info.get('pid')}")
        print(f"  Alive: {is_alive}")
        print(f"  Name: {agent_spec.name}")

# Get engine statistics
stats = engine.get_engine_stats()
print(f"Total agents: {stats['owned_agents_count']}")
print(f"Max processes: {stats['max_processes']}")
```

### Fault Tolerance

```python
import time

def robust_agent_management(engine, guild_id):
    """Example of robust agent management with fault tolerance."""
    
    while True:
        try:
            # Clean up any dead processes
            engine.cleanup_dead_processes()
            
            # Check each agent
            agents = engine.get_agents_in_guild(guild_id)
            for agent_id in list(agents.keys()):
                if not engine.is_agent_running(guild_id, agent_id):
                    print(f"Agent {agent_id} has died, restarting...")
                    
                    # Get the agent spec for restarting
                    agent_spec = agents[agent_id]
                    
                    # Remove the dead agent
                    engine.stop_agent(guild_id, agent_id)
                    
                    # Restart the agent (would need proper guild integration)
                    # guild.launch_agent(agent_spec, execution_engine=engine)
            
            time.sleep(5)  # Check every 5 seconds
            
        except KeyboardInterrupt:
            print("Shutting down...")
            engine.shutdown()
            break
        except Exception as e:
            print(f"Error in monitoring: {e}")
            time.sleep(0.01)
```

## Configuration Options

### Engine Configuration

```python
engine = MultiProcessExecutionEngine(
    guild_id="my-guild",
    max_processes=8,  # Maximum concurrent processes (default: CPU count)
)
```

### Messaging Configuration

For multiprocess execution, use messaging backends that support cross-process communication:

```python
# Option 1: Embedded Messaging Backend (recommended)
from rustic_ai.core.messaging.backend.embedded_backend import create_embedded_messaging_config

messaging_config = create_embedded_messaging_config()

# Option 2: Redis Backend
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig

messaging_config = MessagingConfig(
    backend_module="rustic_ai.redis.messaging",
    backend_class="RedisMessagingBackend",
    backend_config={
        "host": "localhost",
        "port": 6379,
        "db": 0
    }
)
```

### Process Start Method

The engine automatically sets the multiprocessing start method to 'spawn' for better cross-platform compatibility:

```python
# This is done automatically by the engine
import multiprocessing
multiprocessing.set_start_method('spawn', force=True)
```

## API Reference

### MultiProcessExecutionEngine

#### Constructor

```python
__init__(guild_id: str, max_processes: Optional[int] = None)
```

- `guild_id`: ID of the guild this engine manages
- `max_processes`: Maximum number of processes (defaults to CPU count)

#### Core Methods

```python
# Agent management
run_agent(guild_spec, agent_spec, messaging_config, machine_id, **kwargs)
stop_agent(guild_id: str, agent_id: str)
shutdown()

# Agent querying
get_agents_in_guild(guild_id: str) -> Dict[str, AgentSpec]
is_agent_running(guild_id: str, agent_id: str) -> bool
find_agents_by_name(guild_id: str, agent_name: str) -> List[AgentSpec]

# Process management
get_process_info(guild_id: str, agent_id: str) -> Dict
get_engine_stats() -> Dict
cleanup_dead_processes()
```

### MultiProcessAgentWrapper

#### Core Methods

```python
run()  # Start the agent process
shutdown()  # Stop the agent process
is_alive() -> bool  # Check if process is alive
get_process_id() -> Optional[int]  # Get process PID
```

### MultiProcessAgentTracker

#### Core Methods

```python
# Agent tracking
add_agent(guild_id: str, agent_spec: AgentSpec, wrapper: MultiProcessAgentWrapper)
remove_agent(guild_id: str, agent_id: str)
update_process_info(guild_id: str, agent_id: str)

# Agent querying
get_agent_spec(guild_id: str, agent_id: str) -> Optional[AgentSpec]
get_agent_wrapper(guild_id: str, agent_id: str) -> Optional[MultiProcessAgentWrapper]
is_agent_alive(guild_id: str, agent_id: str) -> bool

# Statistics and management
get_stats() -> Dict
clear()
```

## Performance Considerations

### Advantages
- **True Parallelism**: Completely escapes Python's GIL
- **Fault Isolation**: Process crashes don't affect other agents
- **Memory Isolation**: Each process has its own memory space
- **CPU Utilization**: Can fully utilize multiple CPU cores
- **Scalability**: Can handle CPU-intensive workloads efficiently

### Limitations
- **Memory Overhead**: Each process has its own Python interpreter
- **IPC Overhead**: Inter-process communication has serialization costs
- **Startup Time**: Process creation is slower than thread creation
- **Resource Usage**: More system resources required than threading

### Best Use Cases
- **CPU-intensive computations**: Mathematical calculations, data processing
- **Parallel algorithms**: Monte Carlo simulations, optimization problems
- **Fault-tolerant systems**: Systems that need process isolation
- **Mixed workloads**: Combination of CPU and IO-bound tasks
- **Long-running agents**: Agents that run for extended periods

## Best Practices

### For Performance

1. **Right-size Process Count**: Use `multiprocessing.cpu_count()` as a starting point
2. **Batch Work**: Process larger chunks of work to amortize process overhead
3. **Efficient Serialization**: Use efficient data structures for inter-process communication
4. **Monitor Resource Usage**: Track memory and CPU usage to optimize performance

### For Reliability

1. **Health Monitoring**: Regularly check process health with `is_agent_running()`
2. **Graceful Shutdown**: Always call `engine.shutdown()` for proper cleanup
3. **Error Handling**: Implement proper error handling for process failures
4. **Resource Limits**: Set appropriate `max_processes` to avoid resource exhaustion

### For Development

1. **Start Simple**: Begin with `SyncExecutionEngine` for development and debugging
2. **Test Isolation**: Ensure agents work correctly in process isolation
3. **Logging**: Use proper logging to debug cross-process issues
4. **Messaging Testing**: Test with the shared memory backend for development

### Error Handling

```python
try:
    engine = MultiProcessExecutionEngine(guild_id="my-guild")
    guild.launch_agent(agent_spec, execution_engine=engine)
except RuntimeError as e:
    if "Maximum number of processes" in str(e):
        # Handle process limit exceeded
        engine.cleanup_dead_processes()
        # Retry or reduce load
    else:
        raise
except Exception as e:
    print(f"Failed to start agent: {e}")
    engine.shutdown()
```

## Examples

### Parallel Data Processing

```python
import multiprocessing
from rustic_ai.core.guild import Guild, AgentBuilder
from rustic_ai.core.guild.execution.multiprocess import MultiProcessExecutionEngine

def parallel_data_processing():
    # Create embedded messaging for cross-process communication
    from rustic_ai.core.messaging.backend.embedded_backend import create_embedded_messaging_config
    messaging_config = create_embedded_messaging_config()
    
    # Create guild with multiprocess engine
    guild = Guild(
        guild_id="data_processing",
        messaging_config=messaging_config
    )
    
    engine = MultiProcessExecutionEngine(
        guild_id="data_processing",
        max_processes=multiprocessing.cpu_count()
    )
    
    # Create worker agents for parallel processing
    for i in range(4):
        worker_spec = (AgentBuilder()
            .set_name(f"data_worker_{i}")
            .set_description(f"Process data partition {i}")
            .set_class_name("DataProcessingAgent")
            .add_dependency("partition_id", i)
            .build_spec())
        
        guild.launch_agent(worker_spec, execution_engine=engine)
    
    # Create coordinator agent
    coordinator_spec = (AgentBuilder()
        .set_name("coordinator")
        .set_description("Coordinate data processing tasks")
        .set_class_name("CoordinatorAgent")
        .build_spec())
    
    guild.launch_agent(coordinator_spec, execution_engine=engine)
    
    # Monitor progress
    try:
        while True:
            stats = engine.get_engine_stats()
            print(f"Running agents: {stats['owned_agents_count']}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("Shutting down...")
        guild.shutdown()
```

### CPU-Intensive Monte Carlo Simulation

```python
def monte_carlo_simulation(num_workers=None):
    if num_workers is None:
        num_workers = multiprocessing.cpu_count()
    
    # Setup
    messaging_config = create_embedded_messaging_config()
    guild = Guild(guild_id="monte_carlo", messaging_config=messaging_config)
    engine = MultiProcessExecutionEngine(guild_id="monte_carlo", max_processes=num_workers)
    
    # Create simulation workers
    for i in range(num_workers):
        worker_spec = (AgentBuilder()
            .set_name(f"simulation_worker_{i}")
            .set_class_name("MonteCarloWorkerAgent")
            .add_dependency("worker_id", i)
            .add_dependency("num_samples", 1000000 // num_workers)
            .build_spec())
        
        guild.launch_agent(worker_spec, execution_engine=engine)
    
    # Create results aggregator
    aggregator_spec = (AgentBuilder()
        .set_name("results_aggregator")
        .set_class_name("ResultsAggregatorAgent")
        .add_dependency("expected_workers", num_workers)
        .build_spec())
    
    guild.launch_agent(aggregator_spec, execution_engine=engine)
    
    return guild, engine
```

## Troubleshooting

### Fork() Deprecation Warning

When running tests, you may encounter warnings like:
```
DeprecationWarning: This process (pid=297226) is multi-threaded, use of fork() may lead to deadlocks in the child.
```

This warning occurs because Python's multiprocessing module defaults to using the "fork" start method on POSIX systems. In multi-threaded environments (like test suites running with pytest), fork() can cause deadlocks since only the current thread survives in the child process while other threads' locks remain held.

**Solution**: The codebase is configured to use the "spawn" start method instead:

```python
multiprocessing.set_start_method('spawn', force=True)
```

This creates entirely new Python interpreter processes instead of forking, avoiding the multi-threading issues. This configuration is automatically applied in:

- Core tests via `rustic-ai/core/tests/conftest.py`
- Integration tests via individual test fixtures
- Production code examples in documentation

**Performance Note**: The "spawn" method is slightly slower than "fork" since it needs to create new Python interpreters, but it's much safer and more predictable in multi-threaded environments.

### Pytest Hanging Issue

**Problem**: Tests using multiprocessing were causing pytest to hang and not exit after test completion.

**Root Cause**: The `multiprocessing.Manager()` creates background processes that weren't being properly cleaned up, preventing pytest from exiting.

**Solution**: Enhanced cleanup mechanisms have been implemented:

1. **Manager Shutdown**: The `MultiProcessAgentTracker.clear()` method now explicitly shuts down the multiprocessing manager:
   ```python
   if hasattr(self, 'manager') and self.manager:
       self.manager.shutdown()
   ```

2. **Process Force Cleanup**: The `MultiProcessExecutionEngine.shutdown()` method now includes comprehensive process cleanup:
   - Terminates and kills remaining processes
   - Cleans up process tracking structures
   - Forces cleanup of any remaining multiprocessing children

3. **Test Fixtures Enhanced**: Test fixtures now include additional cleanup steps:
   - Wait for processes to fully terminate
   - Double-check multiprocessing cleanup
   - Session-level cleanup to ensure no processes remain

4. **Session-Level Cleanup**: A session-scoped pytest fixture ensures all multiprocessing resources are cleaned up when the test session ends.

These changes ensure that:
- ✅ **No fork() warnings** - Tests use "spawn" method
- ✅ **No pytest hanging** - All processes properly cleaned up
- ✅ **Fast test execution** - Tests complete quickly without delays
- ✅ **Reliable cleanup** - Comprehensive process termination

## Configuration

### Common Issues

1. **Process Won't Start**: Check process limits and available memory
2. **Serialization Errors**: Ensure all data passed to processes is serializable
3. **Hanging Processes**: Use timeout in shutdown and implement proper cleanup
4. **Memory Leaks**: Monitor process memory usage and implement cleanup

### Debugging

```python
# Check process status
agents = engine.get_agents_in_guild(guild_id)
for agent_id, spec in agents.items():
    process_info = engine.get_process_info(guild_id, agent_id)
    print(f"Agent {agent_id}: PID={process_info.get('pid')}, Alive={process_info.get('is_alive')}")

# Get detailed statistics
stats = engine.get_engine_stats()
print(f"Engine stats: {stats}")

# Manual cleanup
engine.cleanup_dead_processes()
```

### Performance Monitoring

```python
import psutil

def monitor_engine_performance(engine, guild_id):
    """Monitor engine performance metrics."""
    stats = engine.get_engine_stats()
    agents = engine.get_agents_in_guild(guild_id)
    
    total_memory = 0
    total_cpu = 0
    
    for agent_id in agents:
        process_info = engine.get_process_info(guild_id, agent_id)
        pid = process_info.get('pid')
        
        if pid:
            try:
                process = psutil.Process(pid)
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()
                
                total_memory += memory_mb
                total_cpu += cpu_percent
                
                print(f"Agent {agent_id}: Memory={memory_mb:.1f}MB, CPU={cpu_percent:.1f}%")
            except psutil.NoSuchProcess:
                print(f"Agent {agent_id}: Process no longer exists")
    
    print(f"Total: Memory={total_memory:.1f}MB, CPU={total_cpu:.1f}%")
    print(f"Agents: {len(agents)}/{stats['max_processes']}")
```

## Integration with Embedded Messaging Backend

The multiprocess execution engine works particularly well with the [Embedded Messaging Backend](embedded_messaging_backend.md):

```python
from rustic_ai.core.messaging.backend.embedded_backend import (
    EmbeddedMessagingBackend,
    EmbeddedServer
)
import asyncio
import threading

# Start socket server for cross-process messaging
def start_server(port=31134):
    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        server = EmbeddedServer(port=port)
        loop.run_until_complete(server.start())
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(server.stop())
            loop.close()
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return port

port = start_server(31134)

# Create multiprocess engine with embedded messaging
messaging_config = MessagingConfig(
    backend_module="rustic_ai.core.messaging.backend.embedded_backend",
    backend_class="EmbeddedMessagingBackend",
    backend_config={"port": port, "auto_start_server": False}
)

engine = MultiProcessExecutionEngine(guild_id="my-guild")
guild = Guild(guild_id="my-guild", messaging_config=messaging_config)

# Agents can now communicate across processes
# without external dependencies
```

## Conclusion

The Multiprocess Execution Engine provides a powerful solution for CPU-intensive and fault-tolerant agent systems. By escaping Python's GIL and providing process isolation, it enables true parallel execution while maintaining the full feature set of the Rustic AI framework. Combined with the embedded messaging backend, it offers a robust platform for building high-performance, distributed agent systems. 