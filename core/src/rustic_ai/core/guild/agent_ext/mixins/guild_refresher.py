from rustic_ai.core.agents.system.models import GuildUpdatedAnnouncement
from rustic_ai.core.guild.agent import ProcessContext, processor


class GuildRefreshMixin:
    @processor(GuildUpdatedAnnouncement, handle_essential=True)
    def refresh_guild(self, ctx: ProcessContext[GuildUpdatedAnnouncement]):
        gua = ctx.payload
        self.guild_spec = gua.guild_spec
        self.guild_refresh_handler(ctx)

    def guild_refresh_handler(self, ctx: ProcessContext[GuildUpdatedAnnouncement]):
        pass
