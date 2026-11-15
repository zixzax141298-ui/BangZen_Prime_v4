from bangzen_prime.application.strategies.base_strategy import TradingStrategy, TradeParams

class DummyStrategy(TradingStrategy):
    strategy_id = "dummy_test"
    display_name = "Dummy Test"
    budget_sol = 0.5
    max_concurrent_positions = 2

    async def should_evaluate(self, token_data: dict) -> bool:
        return True

    def get_ai_context(self) -> str:
        return "Test AI context"

    def get_trade_params(self) -> TradeParams:
        return TradeParams(buy_amount_sol=0.1)
