# Configuration

All keys use the `BANGZEN_` prefix. Unknown `BANGZEN_*` keys are rejected so typos fail closed.
Values are parsed strictly: NaN, Infinity, and floats for money are not accepted.
See `.env.example` for the full list.

The CLI reads a `.env` file in the working directory. Only `BANGZEN_*` keys are read from it. Real environment variables take precedence over the file. Every value goes through the same validation either way. For a Termux install, see `docs/TERMUX.md`.

Locked by design (cannot be changed in this release):
- `BANGZEN_LIVE_TRADING` must be `false`.
- `BANGZEN_PAPER_TRADING` must be `true`.
- `BANGZEN_DRY_RUN` must be `true`.
- `BANGZEN_BROADCAST_ENABLED` must be `false`. Chain broadcast needs owner approval and a
  security review first.

Operational keys: `EMERGENCY_STOP` (blocks new paper orders; the supervisor also skips
order-placing workers), `DB_PATH`, `LOG_LEVEL`.

Limits and units:
- `MAX_RISK_PER_TRADE_PCT`: percent of equity, per trade, including estimated fees.
- `MAX_EXPOSURE_QUOTE`: quote currency, total notional of open positions.
- `MAX_OPEN_POSITIONS`: count.
- `MAX_DRAWDOWN_PCT`: percent from peak equity.
- `MIN_LIQUIDITY_USD`: USD of pair liquidity.
- `MAX_RISK_SCORE`: normalised 0 to 100, higher is riskier.
- `MARKET_DATA_MAX_AGE_SECONDS`: seconds since observation.
- `FEE_RATE`, `SLIPPAGE_RATE`: fraction per side.

Secrets: `BANGZEN_TELEGRAM_BOT_TOKEN` must never be committed. Keep it in an untracked `.env`.

## v0.2.0 keys
Providers: BANGZEN_HELIUS_API_KEY, BANGZEN_BIRDEYE_API_KEY, BANGZEN_SOLANA_TRACKER_API_KEY,
BANGZEN_JUPITER_API_KEY, BANGZEN_GRPC_ENDPOINT (https only).
AI brain: BANGZEN_AI_ENABLED (default false), BANGZEN_AI_PROVIDER (anthropic | openai | grok),
BANGZEN_AI_MODEL, BANGZEN_AI_CONFIDENCE_THRESHOLD (0 to 1), and the key for the chosen provider:
BANGZEN_ANTHROPIC_API_KEY, BANGZEN_OPENAI_API_KEY, or BANGZEN_GROK_API_KEY. Enabling AI without its key is rejected.
Watchdog: BANGZEN_WATCHDOG_TIMEOUT_SECONDS (default 5, range 1 to 60).
Jito and Jupiter: BANGZEN_JITO_TIP_CAP_LAMPORTS (default 100000), BANGZEN_JUPITER_SLIPPAGE_BPS (default 50).
The optional `BANGZEN_WALLET_PUBLIC_ADDRESS` setting stores a public address only; no private key, seed phrase, wallet import, or signing key is accepted. Live trading and broadcast remain locked.

## Legacy wallet-key migration

`BANGZEN_BURNER_PRIVATE_KEY` is no longer a supported setting. If an old local `.env` contains this key, remove the line; the settings loader rejects it as an unknown key. Do not paste the key into chat, Telegram, GitHub, or logs. This release has no wallet-key import or signing configuration.

## Operating and Telegram modes

Set `BANGZEN_OPERATING_MODE` to exactly one of `TELEGRAM_ONLY`, `EXECUTION_ONLY`, or `HYBRID`. The default is `TELEGRAM_ONLY`. `EXECUTION_ONLY` suppresses Telegram signal delivery; `HYBRID` permits Telegram delivery while requesting execution. A requested execution mode does not unlock a wallet: live signing and broadcast remain disabled in every mode in this release.

Telegram delivery is enabled only when both `BANGZEN_TELEGRAM_BOT_TOKEN` and `BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS` are configured. Chat IDs must be numeric and explicitly allowlisted. The bot sends signal notifications only; this adapter exposes no command, wallet, or transaction controls. Never commit the token or send it to ChatGPT, GitHub, or Telegram chats.

## Watch-only wallet address

Optionally set `BANGZEN_WALLET_PUBLIC_ADDRESS` to a syntactically valid base58-form Solana public address. This is public identity metadata and does not prove ownership. The application registry is watch-only; it has no seed phrase/private-key field and no signing method. Do not put recovery material in `.env`. A public address can receive assets on-chain in any app mode, but this release never uses those funds for trading.
