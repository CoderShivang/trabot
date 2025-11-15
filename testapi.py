from binance.client import Client

api_key = 'vj0CqpSFvjwlesW6ChfbEq19cJ2CbhxNFSQZAWbK38G8U0E3XtaMagjWorPeaI0Z'
api_secret = 'RFtpAsfShO31KkB3xdWWKsTvvWlJWmT4pCSpCd5XbJBgksFIdT7SiDe5r0K0CWMZ'

print('Testing Binance API from your local machine...')
print('=' * 60)

try:
    client = Client(api_key=api_key, api_secret=api_secret, testnet=False)
    price = client.futures_symbol_ticker(symbol='BTCUSDT')
    print(f"SUCCESS! BTC Price: ${float(price['price']):,.2f}")
    print('Your machine CAN access Binance API!')
    print('You can download data and run backtests!')
except Exception as e:
    print(f"FAILED: {e}")
    print('Your machine CANNOT access Binance API')

print('=' * 60)