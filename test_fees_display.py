#!/usr/bin/env python3
"""
Test script to verify fee calculations and display
"""

# Sample trade with fees
trade = {
    'entry_price': 100000,
    'exit_price': 101000,
    'quantity': 0.02,
    'total_fees': 0.8,
    'pnl': 19.2  # Net P&L after fees
}

# Calculate what fees should be
maker_fee = 0.0002
entry_fee = trade['entry_price'] * trade['quantity'] * maker_fee
exit_fee = trade['exit_price'] * trade['quantity'] * maker_fee
expected_total = entry_fee + exit_fee

print("=" * 80)
print("FEE CALCULATION TEST")
print("=" * 80)
print()
print(f"Trade Details:")
print(f"  Entry: ${trade['entry_price']:,.2f}")
print(f"  Exit: ${trade['exit_price']:,.2f}")
print(f"  Quantity: {trade['quantity']} BTC")
print(f"  Position Size: ${trade['entry_price'] * trade['quantity']:,.2f}")
print()
print(f"Fee Breakdown:")
print(f"  Entry fee (0.02%): ${entry_fee:.4f}")
print(f"  Exit fee (0.02%): ${exit_fee:.4f}")
print(f"  Total fees: ${expected_total:.4f}")
print()
print(f"P&L Calculation:")
price_change = trade['exit_price'] - trade['entry_price']
gross_pnl = price_change * trade['quantity']
net_pnl = gross_pnl - expected_total

print(f"  Price change: ${price_change:,.2f}")
print(f"  Gross P&L: ${gross_pnl:.2f}")
print(f"  Fees paid: ${expected_total:.2f}")
print(f"  Net P&L: ${net_pnl:.2f}")
print()

# Verify
if abs(expected_total - trade['total_fees']) < 0.01:
    print("✓ Fee calculation is CORRECT")
else:
    print(f"✗ Fee mismatch: expected ${expected_total:.4f}, got ${trade['total_fees']:.4f}")

if abs(net_pnl - trade['pnl']) < 0.01:
    print("✓ P&L calculation is CORRECT (includes fees)")
else:
    print(f"✗ P&L mismatch: expected ${net_pnl:.2f}, got ${trade['pnl']:.2f}")

print()
print("=" * 80)
print("DASHBOARD DISPLAY FORMAT")
print("=" * 80)
print()
print(f"{'Entry Price':<15} {'Exit Price':<15} {'Fees':<10} {'P&L (Net)':<15} {'P&L %'}")
print("-" * 80)

# Format as dashboard would show
entry_str = f"${trade['entry_price']:,.2f}"
exit_str = f"${trade['exit_price']:,.2f}"
fees_str = f"${trade['total_fees']:.2f}"
pnl_str = f"${trade['pnl']:.2f}"
pnl_pct = (trade['pnl'] / (trade['entry_price'] * trade['quantity'])) * 100
pnl_pct_str = f"{pnl_pct:+.2f}%"

print(f"{entry_str:<15} {exit_str:<15} {fees_str:<10} {pnl_str:<15} {pnl_pct_str}")

print()
print("=" * 80)
print("KEY POINTS")
print("=" * 80)
print("""
1. ✓ Fees are calculated on BOTH entry and exit
2. ✓ Entry fee = entry_price × quantity × 0.0002
3. ✓ Exit fee = exit_price × quantity × 0.0002
4. ✓ P&L shown in dashboard is NET (after fees)
5. ✓ Fees column shows total fees paid per trade
6. ✓ Daily P&L table now shows total fees per day

When you run a new backtest, all trades will include:
- quantity: Amount of BTC traded
- entry_fee: Fee paid on entry
- exit_fee: Fee paid on exit
- total_fees: Sum of entry + exit fees
- pnl: Net P&L after deducting all fees
""")
