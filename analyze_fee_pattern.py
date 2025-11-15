#!/usr/bin/env python3
"""
Demonstrate why losing trades result in lower total fees
"""

# Simulate trades similar to your backtest results
# You had: 117 wins, 158 losses, mostly LONG positions

import random
random.seed(42)

INITIAL_CAPITAL = 100
LEVERAGE = 20
MAKER_FEE = 0.0002  # 0.02%
BASE_PRICE = 40000  # Starting BTC price

# Generate 275 simulated trades (117 wins, 158 losses like your results)
trades = []

# Generate winning LONG trades (price goes UP)
for i in range(117):
    entry_price = BASE_PRICE + random.uniform(-1000, 1000)
    # Winners: exit price higher (avg +1.5% move)
    price_change = random.uniform(0.005, 0.03)  # 0.5% to 3% gain
    exit_price = entry_price * (1 + price_change)

    quantity = (INITIAL_CAPITAL * LEVERAGE) / entry_price
    trades.append({
        'direction': 'LONG',
        'entry_price': entry_price,
        'exit_price': exit_price,
        'quantity': quantity,
        'outcome': 'WIN'
    })

# Generate losing LONG trades (price goes DOWN)
for i in range(158):
    entry_price = BASE_PRICE + random.uniform(-1000, 1000)
    # Losers: exit price lower (avg -1.5% move)
    price_change = random.uniform(-0.03, -0.005)  # 0.5% to 3% loss
    exit_price = entry_price * (1 + price_change)

    quantity = (INITIAL_CAPITAL * LEVERAGE) / entry_price
    trades.append({
        'direction': 'LONG',
        'entry_price': entry_price,
        'exit_price': exit_price,
        'quantity': quantity,
        'outcome': 'LOSS'
    })

# Calculate fees
total_fees = 0
winning_trade_fees = 0
losing_trade_fees = 0

print("=" * 80)
print("FEE ANALYSIS: Why Losing Trades Result in Lower Total Fees")
print("=" * 80)
print(f"\nSetup:")
print(f"  Initial Capital: ${INITIAL_CAPITAL}")
print(f"  Leverage: {LEVERAGE}x")
print(f"  Position Size (Notional): ${INITIAL_CAPITAL * LEVERAGE:,.0f}")
print(f"  Maker Fee: {MAKER_FEE} ({MAKER_FEE * 100}%)")
print(f"  Total Trades: {len(trades)} (117 wins, 158 losses)")
print(f"  Strategy: LONG positions")

print(f"\n{'=' * 80}")
print("SAMPLE TRADES:")
print("=" * 80)

# Show first 5 winning and 5 losing trades as examples
print("\n📈 WINNING LONG TRADES (Price Goes UP):")
print(f"{'Entry Price':<12} {'Exit Price':<12} {'Quantity':<12} {'Entry Fee':<12} {'Exit Fee':<12} {'Total Fee':<12}")
print("-" * 80)
for trade in [t for t in trades if t['outcome'] == 'WIN'][:5]:
    entry_fee = trade['entry_price'] * trade['quantity'] * MAKER_FEE
    exit_fee = trade['exit_price'] * trade['quantity'] * MAKER_FEE
    total_trade_fee = entry_fee + exit_fee
    print(f"${trade['entry_price']:>10.2f}  ${trade['exit_price']:>10.2f}  {trade['quantity']:>10.6f}  ${entry_fee:>10.2f}  ${exit_fee:>10.2f}  ${total_trade_fee:>10.2f}")

print("\n📉 LOSING LONG TRADES (Price Goes DOWN):")
print(f"{'Entry Price':<12} {'Exit Price':<12} {'Quantity':<12} {'Entry Fee':<12} {'Exit Fee':<12} {'Total Fee':<12}")
print("-" * 80)
for trade in [t for t in trades if t['outcome'] == 'LOSS'][:5]:
    entry_fee = trade['entry_price'] * trade['quantity'] * MAKER_FEE
    exit_fee = trade['exit_price'] * trade['quantity'] * MAKER_FEE
    total_trade_fee = entry_fee + exit_fee
    print(f"${trade['entry_price']:>10.2f}  ${trade['exit_price']:>10.2f}  {trade['quantity']:>10.6f}  ${entry_fee:>10.2f}  ${exit_fee:>10.2f}  ${total_trade_fee:>10.2f}")

# Calculate all fees
for trade in trades:
    entry_fee = trade['entry_price'] * trade['quantity'] * MAKER_FEE
    exit_fee = trade['exit_price'] * trade['quantity'] * MAKER_FEE
    trade_total_fee = entry_fee + exit_fee

    total_fees += trade_total_fee

    if trade['outcome'] == 'WIN':
        winning_trade_fees += trade_total_fee
    else:
        losing_trade_fees += trade_total_fee

avg_winning_fee = winning_trade_fees / 117
avg_losing_fee = losing_trade_fees / 158
expected_constant_fee = 2000 * MAKER_FEE * 2  # $2000 position, both sides

print(f"\n{'=' * 80}")
print("SUMMARY:")
print("=" * 80)
print(f"\n🔹 Expected fee per trade (if price constant): ${expected_constant_fee:.2f}")
print(f"\n📈 Winning trades (117):")
print(f"   - Total fees: ${winning_trade_fees:,.2f}")
print(f"   - Average fee per trade: ${avg_winning_fee:.2f}")
print(f"   - Why HIGHER: Exit price > Entry price → Pay MORE on exit")
print(f"\n📉 Losing trades (158):")
print(f"   - Total fees: ${losing_trade_fees:,.2f}")
print(f"   - Average fee per trade: ${avg_losing_fee:.2f}")
print(f"   - Why LOWER: Exit price < Entry price → Pay LESS on exit")
print(f"\n💰 TOTAL FEES: ${total_fees:,.2f}")
print(f"   Average per trade: ${total_fees / len(trades):.2f}")
print(f"\n🔍 COMPARISON:")
print(f"   Expected (constant price): ${expected_constant_fee * len(trades):,.2f}")
print(f"   Actual (variable price): ${total_fees:,.2f}")
print(f"   Difference: ${expected_constant_fee * len(trades) - total_fees:,.2f}")
print(f"   Percentage: {((expected_constant_fee * len(trades) - total_fees) / (expected_constant_fee * len(trades))) * 100:.1f}% lower")

print(f"\n{'=' * 80}")
print("KEY INSIGHT:")
print("=" * 80)
print("""
When you have MORE LOSING TRADES than winning trades in a LONG strategy:
  • Entry notional: Always $2,000 ✓
  • Exit notional: VARIES based on price movement
  • Losing LONG trades → Price drops → Exit notional < $2,000 → Lower exit fee
  • Result: Average fee per trade < $0.80

The fee calculation is CORRECT. Fees are based on actual traded values,
not theoretical constant position sizes.
""")
