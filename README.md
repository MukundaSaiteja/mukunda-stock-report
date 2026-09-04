# mukunda-stock-report

A self-serve **single-stock research bot** for the NSE. Post **`/stock <SYMBOL>`**
in the Telegram channel and a poller builds a quant research **PDF** and posts it
back — snapshot, 5Y financials, forensic scores, quant factors, full technicals
and **support/resistance**, plus a rule-based verdict.

> Educational quant snapshot, **not** SEBI-registered advice. Verify live.

## How it works

```
You post "/stock RELIANCE" in Telegram
      │
      ▼
stock-poller.yml (cron */5 on this PUBLIC repo — free unlimited minutes)
      │  getUpdates finds the command
      ▼
Python analyzer (yfinance) computes the layers
      ▼
PDF built (fpdf2 + matplotlib charts)
      ▼
sendDocument → PDF posted back to the same chat
```

Fully isolated from the `nifty-alert` project — separate repo, separate workflow.
It reuses the same Telegram bot (`@Analysis_Stock_Alert_bot`); the bot only ever
*sends* in the alert project, so polling here does not affect it.

## What the PDF contains (real computed numbers)

1. Snapshot — price, mcap, PE/PB, EV/EBITDA, div yield, 52W, holdings
2. 5Y financials — revenue, EBIT, net profit, CFO
3. Cash-flow quality & forensic — CFO/PAT, Sloan accruals, Altman Z, Piotroski (partial), D/E, interest coverage
4. Quant factors — 12-1 momentum, RS vs Nifty, returns, CAGR, max drawdown
5. Technicals — 50/200-DMA, RSI, MACD, ADX, Bollinger, ATR, Stochastic, volume, 52W
6. **Support/Resistance** — pivots S1/S2/S3 · R1/R2/R3 + swings + 52W
7. Analyst view — target/recommendation where available
8. Layers needing deep review (news arc, concall tone, variant view) → marked `n/a`

## Setup

1. This repo is **public** (so Actions polling is free). No secrets live in code.
2. Add repository **secrets** (Settings → Secrets and variables → Actions):
   - `TELEGRAM_BOT_TOKEN` — the bot token.
   - `STOCK_CHAT_ID` — the channel/chat id to accept commands from and reply to.
3. The bot must be an **admin** of that channel (to read your posts and reply).
4. Post `/stock RELIANCE` in the channel; the PDF returns within ~5 min.

## Run locally

```bash
pip install -r requirements.txt
python main.py --symbol RELIANCE            # build PDF only
TELEGRAM_BOT_TOKEN=... python main.py --symbol RELIANCE --send --chat <id>
```

## Notes / limits

- Latency ~5 min (polling interval); GitHub cron can add delay.
- yfinance is the backbone; some fundamentals may be `n/a` on a given run (shown, never guessed).
- India-first, exact NSE symbol most reliable.
