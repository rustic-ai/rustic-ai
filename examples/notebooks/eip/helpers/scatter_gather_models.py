# Import required libraries and modules
from typing import List

from pydantic import BaseModel


# Main analysis request message
class AnalysisRequest(BaseModel):
    request_id: str
    dataset: List[float]
    query: str


# Specialized request messages for each analysis type
class StatisticsRequest(BaseModel):
    correlation_id: str
    data: List[float]
    analysis_type: str = "statistics"


class TrendRequest(BaseModel):
    correlation_id: str
    data: List[float]
    analysis_type: str = "trends"


class AnomalyRequest(BaseModel):
    correlation_id: str
    data: List[float]
    analysis_type: str = "anomalies"


# Result message types for gathering responses
class StatisticsResult(BaseModel):
    correlation_id: str
    mean: float
    median: float
    std_dev: float
    min_value: float
    max_value: float
    analysis_type: str = "statistics"


class TrendResult(BaseModel):
    correlation_id: str
    trend_direction: str  # "increasing", "decreasing", "stable"
    slope: float
    r_squared: float
    analysis_type: str = "trends"


class AnomalyResult(BaseModel):
    correlation_id: str
    outliers: List[float]
    outlier_count: int
    analysis_type: str = "anomalies"


# Final comprehensive report
class ComprehensiveAnalysisReport(BaseModel):
    correlation_id: str
    statistics: StatisticsResult
    trends: TrendResult
    anomalies: AnomalyResult
    summary: str
