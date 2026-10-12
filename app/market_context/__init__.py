"""Job-market context for the coach (built from the project's data-analytics layer)."""

from app.market_context.service import MarketContextService, detect_role_family

__all__ = ["MarketContextService", "detect_role_family"]
