from rustic_ai.core.guild.dsl import BaseAgentProps, GuildSpec


class GuildManagerAgentProps(BaseAgentProps):
    """
    A class to represent the properties of the guild manager agent.
    """

    guild_spec: GuildSpec
    database_url: str
