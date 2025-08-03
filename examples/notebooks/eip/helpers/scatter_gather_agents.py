# Statistics analysis agent
import logging

# Import required libraries and modules
import statistics

import numpy as np

from rustic_ai.core.agents.eip.aggregating_agent import (
    AggregatedMessages,
)
from rustic_ai.core.guild.agent import Agent, ProcessContext, processor
from rustic_ai.core.guild.dsl import BaseAgentProps

from .scatter_gather_models import (
    AnomalyRequest,
    AnomalyResult,
    ComprehensiveAnalysisReport,
    StatisticsRequest,
    StatisticsResult,
    TrendRequest,
    TrendResult,
)


class StatisticsAgent(Agent[BaseAgentProps]):
    @processor(StatisticsRequest)
    def analyze_statistics(self, ctx: ProcessContext[StatisticsRequest]):
        """Process statistics analysis request."""

        logging.info(f"🔍 Processing statistics analysis for {ctx.payload.correlation_id}")
        data = ctx.payload.data
        result = StatisticsResult(
            correlation_id=ctx.payload.correlation_id,
            mean=statistics.mean(data),
            median=statistics.median(data),
            std_dev=statistics.stdev(data) if len(data) > 1 else 0.0,
            min_value=min(data),
            max_value=max(data),
        )
        ctx.send(payload=result)
        logging.info(f"📊 Statistics computed for {ctx.payload.correlation_id}: mean={result.mean:.2f}")


# Trend analysis agent
class TrendAgent(Agent[BaseAgentProps]):
    @processor(TrendRequest)
    def analyze_trends(self, ctx: ProcessContext[TrendRequest]):
        data = ctx.payload.data
        x = list(range(len(data)))

        # Simple linear regression
        if len(data) > 1:
            slope, intercept = np.polyfit(x, data, 1)
            y_pred = [slope * i + intercept for i in x]
            ss_res = sum((data[i] - y_pred[i]) ** 2 for i in range(len(data)))
            ss_tot = sum((data[i] - statistics.mean(data)) ** 2 for i in range(len(data)))
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            if slope > 0.1:
                direction = "increasing"
            elif slope < -0.1:
                direction = "decreasing"
            else:
                direction = "stable"
        else:
            slope = 0.0
            r_squared = 0.0
            direction = "stable"

        result = TrendResult(
            correlation_id=ctx.payload.correlation_id, trend_direction=direction, slope=slope, r_squared=r_squared
        )
        ctx.send(payload=result)
        logging.info(f"📈 Trend analyzed for {ctx.payload.correlation_id}: {direction}, slope={slope:.3f}")


# Anomaly detection agent
class AnomalyAgent(Agent[BaseAgentProps]):
    @processor(AnomalyRequest)
    def detect_anomalies(self, ctx: ProcessContext[AnomalyRequest]):
        data = ctx.payload.data

        if len(data) > 1:
            mean_val = statistics.mean(data)
            std_val = statistics.stdev(data)
            threshold = 2 * std_val  # Simple 2-sigma rule

            outliers = [x for x in data if abs(x - mean_val) > threshold]
        else:
            outliers = []

        result = AnomalyResult(
            correlation_id=ctx.payload.correlation_id, outliers=outliers, outlier_count=len(outliers)
        )
        ctx.send(payload=result)
        logging.info(f"🚨 Anomalies detected for {ctx.payload.correlation_id}: {len(outliers)} outliers")


# Report generator agent
class ReportAgent(Agent[BaseAgentProps]):
    @processor(AggregatedMessages)
    def generate_report(self, ctx: ProcessContext[AggregatedMessages]):
        # Extract the three analysis results by type
        messages_by_type = {msg.data["analysis_type"]: msg.data for msg in ctx.payload.messages}

        statistics_data = StatisticsResult.model_validate(messages_by_type["statistics"])
        trends_data = TrendResult.model_validate(messages_by_type["trends"])
        anomalies_data = AnomalyResult.model_validate(messages_by_type["anomalies"])

        # Generate comprehensive summary
        summary = (
            f"Analysis complete: Mean={statistics_data.mean:.2f}, "
            f"Trend={trends_data.trend_direction} (slope={trends_data.slope:.3f}), "
            f"Anomalies={anomalies_data.outlier_count}"
        )

        report = ComprehensiveAnalysisReport(
            correlation_id=ctx.payload.correlation_id,
            statistics=statistics_data,
            trends=trends_data,
            anomalies=anomalies_data,
            summary=summary,
        )

        ctx.send(payload=report)
        logging.info(f"📋 Final Report Generated for {ctx.payload.correlation_id}")
        logging.info(f"   Summary: {summary}")
