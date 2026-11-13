"""Composition root: wires settings, persistence, adapters, use cases, and the outbox worker."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from bangzen_prime.application.discovery import ContinuousDiscoveryUseCase
from bangzen_prime.application.event_bus import EventBus
from bangzen_prime.application.mode_controller import ModeController
from bangzen_prime.application.wallet_access import WalletAccessController, WalletRegistry
from bangzen_prime.application.notifications import (
    SIGNAL_EVENT,
    SUBSCRIBER_NAME,
    LogNotifier,
    ModeGatedNotifier,
    make_notification_handler,
)
from bangzen_prime.application.outbox_worker import OutboxWorker
from bangzen_prime.application.use_cases import AuditTokenUseCase, ScanMarketUseCase, SignalPolicy
from bangzen_prime.application.token_program_evidence import TokenProgramEvidenceUseCase
from bangzen_prime.application.execution_use_case import (
    ExecutionPlan,
    ExecutionPolicy,
    ExecutionUseCase,
)
from bangzen_prime.infrastructure.adapters.market_data.dexscreener import DexScreenerAdapter
from bangzen_prime.infrastructure.adapters.market_data.dexscreener_discovery import DexScreenerDiscoveryAdapter
from bangzen_prime.infrastructure.adapters.market_data.lunarcrush import LunarCrushSentimentAdapter
from bangzen_prime.infrastructure.adapters.market_data.rugcheck import RugCheckAdapter
from bangzen_prime.infrastructure.adapters.chain.helius_token_2022_extensions import HeliusToken2022ExtensionReader
from bangzen_prime.infrastructure.http import Transport, urllib_request_transport, urllib_transport
from bangzen_prime.infrastructure.adapters.notifications.telegram import TelegramNotifier
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.lifecycle import LifecycleStore
from bangzen_prime.infrastructure.persistence.sqlite.outbox import ProcessedEventStore
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork
from bangzen_prime.infrastructure.resilience.policies import (
    CircuitBreaker,
    Clock,
    HealthMonitor,
    ResilientCaller,
    RetryPolicy,
    TokenBucket,
)
from bangzen_prime.application.phase_policy import DEFAULT_POLICY, load_policy
from bangzen_prime.settings import Settings
from bangzen_prime.domain.signals import SignalStatus

from bangzen_prime.application.setup_engine import SetupEngine
from bangzen_prime.application.black_ops_engine import BlackOpsEngine
from bangzen_prime.application.realistic_pumpfun import RealisticPumpfunEngine
from bangzen_prime.application.second_life_strategy import SecondLifeStrategy
from bangzen_prime.application.smart_money_engine import SmartMoneyEngine
from bangzen_prime.application.autopsy_engine import AutopsyEngine
from bangzen_prime.application.auto_blacklist_manager import AutoBlacklistManager
from bangzen_prime.application.ai_commander import AICommander

from bangzen_prime.infrastructure.adapters.onchain.sybil_adapter import SybilAdapter
from bangzen_prime.infrastructure.adapters.onchain.honeypot_adapter import HoneypotAdapter
from bangzen_prime.infrastructure.adapters.onchain.sniper_ban_adapter import SniperBanAdapter
from bangzen_prime.infrastructure.adapters.market_data.lp_sniper_adapter import LPSniperAdapter
from bangzen_prime.infrastructure.adapters.market_data.news_adapter import NewsScraperAdapter
from bangzen_prime.infrastructure.adapters.market_data.cross_chain_radar_adapter import CrossChainRadarAdapter

from bangzen_prime.infrastructure.adapters.execution.wallet_signer import WalletSigner
from bangzen_prime.infrastructure.adapters.chain.jupiter_v2 import JupiterQuoteAdapter as JupiterV2Adapter


@dataclass
class IntelStack:
    birdeye: object | None
    solana_tracker: object | None
    jupiter: object | None
    jito: object | None
    helius: object | None
    ai_brain: object | None
    lunarcrush: object | None


@dataclass
class StrategyStack:
    setup: SetupEngine
    black_ops: BlackOpsEngine
    pumpfun: RealisticPumpfunEngine
    second_life: SecondLifeStrategy
    smart_money: SmartMoneyEngine
    autopsy: AutopsyEngine
    blacklist: AutoBlacklistManager
    sybil: SybilAdapter
    honeypot: HoneypotAdapter
    news: NewsScraperAdapter
    radar: CrossChainRadarAdapter
    lp_sniper: LPSniperAdapter
    sniper_ban: SniperBanAdapter


@dataclass
class Container:
    settings: Settings
    mode_controller: ModeController
    wallet_registry: WalletRegistry
    wallet_access: WalletAccessController
    db: Database
    uow: UnitOfWork
    bus: EventBus
    worker: OutboxWorker
    scan: ScanMarketUseCase
    health: HealthMonitor
    clock: Clock
    intel: IntelStack
    strategy: StrategyStack
    ai_commander: AICommander | None
    lifecycle_store: LifecycleStore
    discovery: ContinuousDiscoveryUseCase
    token_program_evidence: TokenProgramEvidenceUseCase
    live_executor: ExecutionUseCase | None = None


def build_intel_stack(
    settings: Settings,
    *,
    transport,
    clock: Clock | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> IntelStack:
    from bangzen_prime.application.ai_brain import AIBrain
    from bangzen_prime.infrastructure.adapters.chain.helius import HeliusRpc
    from bangzen_prime.infrastructure.adapters.chain.jito import JitoClient
    from bangzen_prime.infrastructure.adapters.chain.jupiter import JupiterQuoteAdapter
    from bangzen_prime.infrastructure.adapters.market_data.intel import BirdeyeAdapter, SolanaTrackerAdapter
    from bangzen_prime.infrastructure.ai.providers import build_provider

    clock = clock or Clock()
    health = HealthMonitor()
    retry = RetryPolicy(max_attempts=settings.http_max_attempts)

    def caller(name: str, rate: float) -> ResilientCaller:
        return ResilientCaller(
            name,
            retry=retry,
            limiter=TokenBucket(rate_per_minute=rate, clock=clock),
            breaker=CircuitBreaker(name, clock=clock),
            health=health,
            sleep=sleep,
            clock=clock,
        )

    t = settings.http_timeout_seconds
    birdeye = (
        BirdeyeAdapter(
            api_key=settings.birdeye_api_key,
            transport=transport,
            caller=caller("birdeye", 300),
            timeout=t,
            clock=clock.now,
        )
        if settings.birdeye_api_key
        else None
    )
    tracker = (
        SolanaTrackerAdapter(
            api_key=settings.solana_tracker_api_key,
            transport=transport,
            caller=caller("solana_tracker", 300),
            timeout=t,
            clock=clock.now,
        )
        if settings.solana_tracker_api_key
        else None
    )
    if settings.jupiter_api_key:
        jupiter = JupiterQuoteAdapter(
            api_key=settings.jupiter_api_key,
            transport=transport,
            caller=caller("jupiter", 600),
            timeout=t,
            clock=clock.now,
            slippage_bps=settings.jupiter_slippage_bps,
        )
    else:

        class _NullJupiter:
            async def check_dynamic_tax(self, mint: str) -> bool:
                raise NotImplementedError("Jupiter API key not configured")

        jupiter = _NullJupiter()
    jito = JitoClient(transport=transport, caller=caller("jito", 300), timeout=t, clock=clock.now)
    helius = (
        HeliusRpc(
            api_key=settings.helius_api_key,
            transport=transport,
            caller=caller("helius", 600),
            timeout=t,
            clock=clock.now,
        )
        if settings.helius_api_key
        else None
    )
    lunarcrush = (
        LunarCrushSentimentAdapter(
            api_key=settings.lunarcrush_api_key,
            transport=transport,
            caller=caller("lunarcrush", 10),
            timeout=t,
            clock=clock.now,
            cache_ttl_seconds=300,
            max_age_seconds=900,
        )
        if settings.lunarcrush_api_key
        else None
    )
    brain = None
    if settings.ai_enabled:
        key = {
            "anthropic": settings.anthropic_api_key,
            "openai": settings.openai_api_key,
            "grok": settings.grok_api_key,
        }[settings.ai_provider]
        provider = build_provider(
            name=settings.ai_provider,
            api_key=key,
            model=settings.ai_model,
            transport=transport,
            caller=caller(settings.ai_provider, 60),
            timeout=t,
        )
        brain = AIBrain(provider, threshold=settings.ai_confidence_threshold)
    return IntelStack(birdeye, tracker, jupiter, jito, helius, brain, lunarcrush)


def build_container(
    settings: Settings,
    *,
    transport: Transport | None = None,
    clock: Clock | None = None,
    sleep: Callable[[float], None] = time.sleep,
    notifier: object | None = None,
    db_path: str | None = None,
    token_2022_reader: object | None = None,
) -> Container:
    clock = clock or Clock()
    intel_transport = transport or urllib_request_transport
    transport = transport or urllib_transport
    db = Database(db_path or settings.db_path)
    db.migrate()
    lifecycle_store = LifecycleStore(db)
    health = HealthMonitor()
    retry = RetryPolicy(max_attempts=settings.http_max_attempts)

    def caller(name: str, rate_per_minute: float) -> ResilientCaller:
        return ResilientCaller(
            name,
            retry=retry,
            limiter=TokenBucket(rate_per_minute=rate_per_minute, clock=clock),
            breaker=CircuitBreaker(name, clock=clock),
            health=health,
            sleep=sleep,
            clock=clock,
        )

    market = DexScreenerAdapter(
        base_url=settings.dexscreener_base_url,
        transport=transport,
        caller=caller("dexscreener", 300),
        timeout=settings.http_timeout_seconds,
        clock=clock.now,
    )
    discovery_feed = DexScreenerDiscoveryAdapter(
        base_url=settings.dexscreener_base_url,
        transport=transport,
        caller=caller("dexscreener_discovery", 60),
        timeout=settings.http_timeout_seconds,
    )
    safety = RugCheckAdapter(
        base_url=settings.rugcheck_base_url,
        transport=transport,
        caller=caller("rugcheck", 60),
        timeout=settings.http_timeout_seconds,
        clock=clock.now,
    )

    uow = UnitOfWork(db)
    bus = EventBus(ProcessedEventStore(db), clock.now)
    mode_controller = ModeController(settings.operating_mode)
    wallet_registry = WalletRegistry(settings.wallet_public_address)
    wallet_access = WalletAccessController(
        registry=wallet_registry,
        mode_controller=mode_controller,
        emergency_stop=settings.emergency_stop,
    )

    if notifier is not None:
        sink = ModeGatedNotifier(notifier, mode_controller)
    elif settings.telegram_bot_token and settings.telegram_allowed_chat_ids:
        telegram = TelegramNotifier(
            token=settings.telegram_bot_token,
            chat_ids=settings.telegram_allowed_chat_ids,
            transport=urllib_request_transport,
            timeout=settings.http_timeout_seconds,
        )
        sink = ModeGatedNotifier(telegram, mode_controller)
    else:
        sink = LogNotifier(logging.getLogger("bangzen_prime.signals"))

    bus.subscribe(SIGNAL_EVENT, SUBSCRIBER_NAME, make_notification_handler(sink))
    worker = OutboxWorker(db=db, bus=bus, clock=clock.now, base_backoff=timedelta(seconds=5))

    intel = build_intel_stack(settings, transport=intel_transport, clock=clock)
    if token_2022_reader is None and intel.helius is not None:
        token_2022_reader = HeliusToken2022ExtensionReader(
            account_info=intel.helius.account_info,
            clock=clock.now,
        )
    token_program_evidence = TokenProgramEvidenceUseCase(token_2022_reader)
    helius_rpc_url = (
        f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
        if settings.helius_api_key
        else ""
    )
    sybil_adapter = SybilAdapter(helius_rpc_url=helius_rpc_url)

    policy = SignalPolicy(
        min_liquidity_usd=settings.min_liquidity_usd,
        max_risk_score=settings.max_risk_score,
        max_data_age_seconds=settings.market_data_max_age_seconds,
    )

    scan = ScanMarketUseCase(
        market=market,
        audit=AuditTokenUseCase(safety),
        uow=uow,
        policy=policy,
        clock=clock.now,
        phase_policy=(load_policy(settings.policy_path) if settings.policy_path else DEFAULT_POLICY),
        ai_brain=intel.ai_brain,
        intel_adapter=None,
        holder_data=intel.solana_tracker,
        sybil_checker=sybil_adapter,
        market_sentiment=intel.lunarcrush,
        token_program_evidence=token_program_evidence,
    )

    discovery = ContinuousDiscoveryUseCase(
        feed=discovery_feed, scanner=scan, lifecycle_registry=lifecycle_store
    )

    setup_engine = SetupEngine()
    black_ops = BlackOpsEngine()
    pumpfun_engine = RealisticPumpfunEngine()
    second_life = SecondLifeStrategy()
    smart_money = SmartMoneyEngine()
    blacklist = AutoBlacklistManager()
    autopsy = AutopsyEngine(db_connection=db._conn)

    honeypot_adapter = HoneypotAdapter(jupiter_client=intel.jupiter, clock=clock.now)
    sniper_ban = SniperBanAdapter()
    lp_sniper = LPSniperAdapter(transport=transport, clock=clock.now)
    news_adapter = NewsScraperAdapter(transport=transport, clock=clock.now)
    radar_adapter = CrossChainRadarAdapter(transport=transport, clock=clock.now)

    strategy_stack = StrategyStack(
        setup=setup_engine,
        black_ops=black_ops,
        pumpfun=pumpfun_engine,
        second_life=second_life,
        smart_money=smart_money,
        autopsy=autopsy,
        blacklist=blacklist,
        sybil=sybil_adapter,
        honeypot=honeypot_adapter,
        news=news_adapter,
        radar=radar_adapter,
        lp_sniper=lp_sniper,
        sniper_ban=sniper_ban,
    )

    ai_commander = None
    if intel.ai_brain:
        ai_commander = AICommander(
            brain=intel.ai_brain,
            sybil=sybil_adapter,
            honeypot=honeypot_adapter,
            news=news_adapter,
            radar=radar_adapter,
            lp_sniper=lp_sniper,
            smart_money=smart_money,
        )

    live_executor: ExecutionUseCase | None = None
    if settings.live_trading and settings.burner_private_key:
        try:
            signer = WalletSigner(private_key_b58=settings.burner_private_key)
            jupiter_v2 = JupiterV2Adapter(
                api_key=settings.jupiter_api_key or "",
                transport=intel_transport,
                caller=caller("jupiter_v2", 600),
                timeout=settings.http_timeout_seconds,
                clock=clock.now,
            )
            exec_policy = ExecutionPolicy(
                paper_trading=settings.paper_trading,
                dry_run=settings.dry_run,
                live_enabled=settings.live_trading,
                emergency_stop=settings.emergency_stop,
            )
            live_executor = ExecutionUseCase(
                mode_controller=mode_controller,
                policy=exec_policy,
                signer=signer,
                jupiter=jupiter_v2,
                helius=intel.helius,
                notifier=sink,
            )

            def make_execution_handler(executor: ExecutionUseCase):
                async def handler(event_name: str, payload: dict) -> None:
                    if payload.get("status") != SignalStatus.ACCEPTED.value:
                        return
                    required = ("input_mint", "output_mint", "amount_raw", "taker")
                    if not all(k in payload for k in required):
                        logging.getLogger(__name__).warning(
                            "[BOOTSTRAP] ACCEPTED signal missing ExecutionPlan fields; skip live path"
                        )
                        return
                    plan = ExecutionPlan(
                        input_mint=str(payload["input_mint"]),
                        output_mint=str(payload["output_mint"]),
                        amount_raw=int(payload["amount_raw"]),
                        taker=str(payload["taker"]),
                        side=str(payload.get("side", "BUY")),
                        client_order_id=payload.get("signal_id") or payload.get("client_order_id"),
                    )
                    await executor.execute(plan)

                return handler

            bus.subscribe(SIGNAL_EVENT, "execution_subscriber", make_execution_handler(live_executor))
            logging.getLogger(__name__).info(
                "[BOOTSTRAP] Live Executor wired (mode=%s)", settings.operating_mode
            )
        except Exception as e:
            logging.getLogger(__name__).error("[BOOTSTRAP] Failed to init Live Executor: %s", e)
            live_executor = None

    return Container(
        settings=settings,
        mode_controller=mode_controller,
        wallet_registry=wallet_registry,
        wallet_access=wallet_access,
        db=db,
        uow=uow,
        bus=bus,
        worker=worker,
        scan=scan,
        health=health,
        clock=clock,
        intel=intel,
        strategy=strategy_stack,
        ai_commander=ai_commander,
        lifecycle_store=lifecycle_store,
        discovery=discovery,
        token_program_evidence=token_program_evidence,
        live_executor=live_executor,
    )
