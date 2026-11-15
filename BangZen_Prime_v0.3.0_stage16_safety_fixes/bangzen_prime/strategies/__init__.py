from bangzen_prime.strategies.base_strategy import (
    StrategyState,
    TradeParams,
    TradingStrategy,
)
from bangzen_prime.strategies.degen_ignition import DegenIgnitionStrategy
from bangzen_prime.strategies.flush_recovery import FlushRecoveryStrategy
from bangzen_prime.strategies.graduation import GraduationStrategy
from bangzen_prime.strategies.mean_reversion import MeanReversionStrategy
from bangzen_prime.strategies.migration_snipe import MigrationSniperStrategy
from bangzen_prime.strategies.momentum import MomentumStrategy
from bangzen_prime.strategies.narrative import NarrativeTrackerStrategy
from bangzen_prime.strategies.range_rotation import RangeRotationStrategy
from bangzen_prime.strategies.reversal import ReversalStrategy
from bangzen_prime.strategies.sniper import (
    ConservativeSniperStrategy,
    DegenSniperStrategy,
    SniperStrategy,
)
from bangzen_prime.strategies.volatility_breakout import (
    VolatilityBreakoutStrategy,
)
from bangzen_prime.strategies.volume_anomaly import VolumeAnomalyStrategy
from bangzen_prime.strategies.volume_surge import VolumeSurgeStrategy

STRATEGY_REGISTRY = {
    "sniper": SniperStrategy,
    "sniper_conservative": ConservativeSniperStrategy,
    "sniper_degen": DegenSniperStrategy,
    "graduation": GraduationStrategy,
    "migration_snipe": MigrationSniperStrategy,
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
    "reversal": ReversalStrategy,
    "volume_anomaly": VolumeAnomalyStrategy,
    "narrative_tracker": NarrativeTrackerStrategy,
    "degen_ignition": DegenIgnitionStrategy,
    "volatility_breakout": VolatilityBreakoutStrategy,
    "volume_surge": VolumeSurgeStrategy,
    "range_rotation": RangeRotationStrategy,
    "flush_recovery": FlushRecoveryStrategy,
}
