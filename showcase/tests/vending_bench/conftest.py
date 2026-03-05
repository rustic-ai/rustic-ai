"""
Pytest fixtures for VendingBench tests.
"""

import pytest
import shortuuid

from rustic_ai.core.agents.testutils import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.guild import Guild
from rustic_ai.showcase.vending_bench.config import (
    DEFAULT_PRICES,
    DEFAULT_STOCK,
    STARTING_CAPITAL,
    ProductType,
)
from rustic_ai.showcase.vending_bench.customer_simulator_agent import (
    CustomerSimulatorAgent,
)
from rustic_ai.showcase.vending_bench.evaluator_agent import EvaluatorAgent
from rustic_ai.showcase.vending_bench.messages import (
    SimulationTime,
    VendingMachineState,
    WeatherType,
)
from rustic_ai.showcase.vending_bench.simulation_controller_agent import (
    SimulationControllerAgent,
)
from rustic_ai.showcase.vending_bench.supplier_agent import SupplierAgent
from rustic_ai.showcase.vending_bench.supplier_discovery_agent import SupplierDiscoveryAgent
from rustic_ai.showcase.vending_bench.supplier_simulator_agent import SupplierSimulatorAgent
from rustic_ai.showcase.vending_bench.customer_complaint_agent import CustomerComplaintAgent
from rustic_ai.showcase.vending_bench.vending_machine_agent import VendingMachineAgent


@pytest.fixture
def default_simulation_time() -> SimulationTime:
    """Default simulation time for testing."""
    return SimulationTime(
        current_day=1,
        current_time_minutes=0,
        is_daytime=True,
        weather=WeatherType.SUNNY,
        day_of_week=0,
    )


@pytest.fixture
def default_vending_state() -> VendingMachineState:
    """Default vending machine state for testing."""
    return VendingMachineState(
        inventory={p: DEFAULT_STOCK[p] for p in ProductType},
        machine_cash=0.0,
        operator_cash=STARTING_CAPITAL,
        prices={p: DEFAULT_PRICES[p] for p in ProductType},
        day=1,
        total_sales=0,
        total_revenue=0.0,
    )


@pytest.fixture
def vending_machine_spec():
    """Build spec for VendingMachineAgent."""
    return (
        AgentBuilder(VendingMachineAgent)
        .set_id("vending_machine")
        .set_name("VendingMachine")
        .set_description("Test vending machine agent")
        .listen_to_default_topic(True)  # Required to receive SupplierDelivery messages
        .add_additional_topic("VENDING_STATE")
        .add_additional_topic("PURCHASES")
        .add_additional_topic("SIMULATION_EVENTS")
        .build_spec()
    )


@pytest.fixture
def customer_simulator_spec():
    """Build spec for CustomerSimulatorAgent."""
    return (
        AgentBuilder(CustomerSimulatorAgent)
        .set_id("customer_simulator")
        .set_name("CustomerSimulator")
        .set_description("Test customer simulator agent")
        .add_additional_topic("SIMULATION_EVENTS")
        .build_spec()
    )


@pytest.fixture
def supplier_spec():
    """Build spec for SupplierAgent."""
    return (
        AgentBuilder(SupplierAgent)
        .set_id("supplier")
        .set_name("Supplier")
        .set_description("Test supplier agent")
        .set_properties({"use_ai_responses": False})  # Disable LLM for testing
        .add_additional_topic("EMAIL")
        .add_additional_topic("ORDERS")
        .add_additional_topic("SIMULATION_EVENTS")
        .build_spec()
    )


@pytest.fixture
def simulation_controller_spec():
    """Build spec for SimulationControllerAgent."""
    return (
        AgentBuilder(SimulationControllerAgent)
        .set_id("simulation_controller")
        .set_name("SimController")
        .set_description("Test simulation controller agent")
        .listen_to_default_topic(True)
        .add_additional_topic("SIMULATION_CONTROL")
        .build_spec()
    )


@pytest.fixture
def evaluator_spec():
    """Build spec for EvaluatorAgent."""
    return (
        AgentBuilder(EvaluatorAgent)
        .set_id("evaluator")
        .set_name("Evaluator")
        .set_description("Test evaluator agent")
        .add_additional_topic("EVALUATION")
        .add_additional_topic("SIMULATION_EVENTS")
        .build_spec()
    )


@pytest.fixture
def supplier_discovery_spec():
    """Build spec for SupplierDiscoveryAgent."""
    return (
        AgentBuilder(SupplierDiscoveryAgent)
        .set_id("supplier_discovery")
        .set_name("SupplierDiscovery")
        .set_description("Test supplier discovery agent")
        .listen_to_default_topic(True)
        .add_additional_topic("SUPPLIER_SEARCH")
        .add_additional_topic("EMAIL")
        .build_spec()
    )


@pytest.fixture
def supplier_simulator_spec():
    """Build spec for SupplierSimulatorAgent."""
    return (
        AgentBuilder(SupplierSimulatorAgent)
        .set_id("supplier_simulator")
        .set_name("SupplierSimulator")
        .set_description("Test supplier simulator agent")
        .listen_to_default_topic(True)
        .add_additional_topic("SUPPLIER_SIMULATION")
        .add_additional_topic("EMAIL")
        .add_additional_topic("SIMULATION_EVENTS")
        .build_spec()
    )


@pytest.fixture
def customer_complaint_spec():
    """Build spec for CustomerComplaintAgent."""
    return (
        AgentBuilder(CustomerComplaintAgent)
        .set_id("customer_complaints")
        .set_name("CustomerComplaints")
        .set_description("Test customer complaint agent")
        .set_properties({"enable_complaints": True, "base_complaint_rate": 0.5})  # Higher rate for testing
        .listen_to_default_topic(True)
        .add_additional_topic("COMPLAINTS")
        .add_additional_topic("EMAIL")
        .add_additional_topic("SIMULATION_EVENTS")
        .build_spec()
    )


@pytest.fixture
def probe_spec():
    """Build spec for ProbeAgent."""
    return (
        AgentBuilder(ProbeAgent)
        .set_id(f"probe_{shortuuid.uuid()}")
        .set_name("ProbeAgent")
        .set_description("Test probe agent")
        .listen_to_default_topic(True)
        .add_additional_topic("VENDING_STATE")
        .add_additional_topic("PURCHASES")
        .add_additional_topic("SIMULATION_EVENTS")
        .add_additional_topic("SIMULATION_CONTROL")
        .add_additional_topic("EMAIL")
        .add_additional_topic("EVALUATION")
        .add_additional_topic("COMPLAINTS")
        .add_additional_topic("SUPPLIER_SEARCH")
        .add_additional_topic("SUPPLIER_SIMULATION")
        .build_spec()
    )


@pytest.fixture
def basic_guild(org_id, vending_machine_spec, probe_spec) -> Guild:
    """Create a basic guild with vending machine agent for testing."""
    builder = GuildBuilder(
        guild_id=f"vending_bench_test_{shortuuid.uuid()}",
        guild_name="VendingBench Test Guild",
        guild_description="Test guild for VendingBench",
    ).set_messaging(
        "rustic_ai.core.messaging.backend",
        "InMemoryMessagingBackend",
        {},
    )

    builder.add_agent_spec(vending_machine_spec)
    guild = builder.launch(org_id)

    yield guild

    guild.shutdown()


@pytest.fixture
def full_guild(
    org_id,
    vending_machine_spec,
    customer_simulator_spec,
    supplier_spec,
    simulation_controller_spec,
    evaluator_spec,
) -> Guild:
    """Create a full guild with all VendingBench agents."""
    builder = GuildBuilder(
        guild_id=f"vending_bench_full_{shortuuid.uuid()}",
        guild_name="VendingBench Full Test Guild",
        guild_description="Full test guild for VendingBench",
    ).set_messaging(
        "rustic_ai.core.messaging.backend",
        "InMemoryMessagingBackend",
        {},
    )

    builder.add_agent_spec(vending_machine_spec)
    builder.add_agent_spec(customer_simulator_spec)
    builder.add_agent_spec(supplier_spec)
    builder.add_agent_spec(simulation_controller_spec)
    builder.add_agent_spec(evaluator_spec)

    guild = builder.launch(org_id)

    yield guild

    guild.shutdown()
