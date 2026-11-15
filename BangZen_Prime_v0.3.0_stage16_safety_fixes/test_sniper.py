import asyncio

from bangzen_prime.strategies.strategy_dispatcher import StrategyDispatcher


async def main():
    dispatcher = StrategyDispatcher()

    token_data = {
        "token_address": "MOCK_SNIPER_COIN",
        "age_minutes": 3,
        "mcap": 30000,
        "vol_1h": 100,
        "change_5m": 0,
        "bonding_curve_state": None,
        "initial_liquidity_sol": 10.0,
    }

    print("=== MENGUJI SNIPER VIA ROUTER ===")
    result = await dispatcher.route_and_evaluate(token_data)
    print(f"Status: {result.get('status')}")
    print(f"Strategi: {result.get('strategy')}")


if __name__ == "__main__":
    asyncio.run(main())
