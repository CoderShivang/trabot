# BTC/ETH Scalping Bot - CLC + Big Orders (Paper-first)

This package contains the full project discussed: CLC strategy engine (Context/Location/Confirmation)
+ Big Orders detection, Streamlit dashboard with rectangle-based SR marking (Plotly), feedback/learning loop,
Binance Futures (paper/testnet by default), Docker config and setup scripts.

Defaults chosen by you:
- PAPER TRADING by default (TESTNET=true)
- Plotly/Streamlit charting for SR marking and labeling
- Notifications placeholders (Discord/Telegram) in .env.example
- Bot starts trading immediately; learning updates begin after 10 labeled samples

Files in this zip are ready-to-run on a VPS or locally. Edit `.env` and `config/bot_config.yaml` before running.
