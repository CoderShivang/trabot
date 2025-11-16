"""
Email progress updates every 15 minutes
Configure your email settings below before running
"""

import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import re

# ============================================================================
# EMAIL CONFIGURATION - UPDATE THESE WITH YOUR CREDENTIALS
# ============================================================================
SMTP_SERVER = "smtp.gmail.com"  # Gmail SMTP server
SMTP_PORT = 587  # TLS port
SENDER_EMAIL = "your-email@gmail.com"  # Your Gmail address
SENDER_PASSWORD = "your-app-password"  # Your Gmail App Password (not regular password)
RECIPIENT_EMAIL = "4454.stkabirnav@gmail.com"
# ============================================================================

LOG_FILE = "/tmp/train_ml_90d_test.log"
UPDATE_INTERVAL = 900  # 15 minutes in seconds

def send_email(subject, body):
    """Send email update"""
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, text)
        server.quit()

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Email sent: {subject}")
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to send email: {e}")
        return False

def extract_progress(log_content):
    """Extract progress information from log"""
    info = {
        'current_step': 'Starting...',
        'progress': 0,
        'trades': 0,
        'capital': 100,
        'status': 'Running'
    }

    lines = log_content.split('\n')

    # Find current step
    for line in reversed(lines):
        if 'STEP' in line:
            info['current_step'] = line.strip()
            break

    # Find backtest progress
    for line in reversed(lines):
        if 'Backtesting:' in line and '%' in line:
            # Extract percentage
            match = re.search(r'(\d+)%', line)
            if match:
                info['progress'] = int(match.group(1))

            # Extract trades and capital
            trades_match = re.search(r'Trades=(\d+)', line)
            capital_match = re.search(r'Capital=\$(\d+)', line)

            if trades_match:
                info['trades'] = int(trades_match.group(1))
            if capital_match:
                info['capital'] = int(capital_match.group(1))
            break

    # Check if completed
    if 'COMPARISON RESULTS' in log_content:
        info['status'] = 'Completed'
    elif 'Error' in log_content or 'Traceback' in log_content:
        info['status'] = 'Error'

    return info

def monitor_and_notify():
    """Monitor log file and send email updates"""
    print("="*70)
    print("EMAIL MONITORING STARTED")
    print("="*70)
    print(f"Monitoring: {LOG_FILE}")
    print(f"Updates every: {UPDATE_INTERVAL // 60} minutes")
    print(f"Recipient: {RECIPIENT_EMAIL}")
    print("")

    last_update_time = time.time()
    update_count = 0

    # Send initial email
    send_email(
        "ML Backtest Started - 180d Training + 90d Testing",
        f"""ML Backtest has started!

Configuration:
- Training: 180 days (Dec 1, 2024 - May 30, 2025)
- Testing: 90 days (May 30 - Aug 28, 2025)
- Train/Test Split: 67/33

Estimated total time: 2-3 hours

You will receive updates every 15 minutes.

Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    )

    try:
        while True:
            current_time = time.time()

            # Check if it's time to send update
            if current_time - last_update_time >= UPDATE_INTERVAL:
                try:
                    with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                        log_content = f.read()

                    info = extract_progress(log_content)
                    update_count += 1

                    # Prepare email body
                    body = f"""ML Backtest Progress Update #{update_count}

Status: {info['status']}
Current Step: {info['current_step']}
Progress: {info['progress']}%
Trades: {info['trades']}
Capital: ${info['capital']}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Next update in 15 minutes (unless completed).
"""

                    subject = f"ML Backtest Update #{update_count} - {info['progress']}% Complete"

                    if info['status'] == 'Completed':
                        subject = "ML Backtest COMPLETED!"
                        body += "\n\nCheck results in the log file or dashboard."
                    elif info['status'] == 'Error':
                        subject = "ML Backtest ERROR!"
                        body += "\n\nAn error occurred. Check the log file."

                    send_email(subject, body)
                    last_update_time = current_time

                    # Exit if completed or error
                    if info['status'] in ['Completed', 'Error']:
                        print("\nMonitoring stopped: Backtest completed or error detected")
                        break

                except FileNotFoundError:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Log file not found yet...")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Error reading log: {e}")

            time.sleep(60)  # Check every minute

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")

if __name__ == "__main__":
    print("\n⚠️  IMPORTANT: Configure your email settings before running!")
    print("    Edit this file and update SENDER_EMAIL and SENDER_PASSWORD\n")

    # Check if credentials are configured
    if SENDER_EMAIL == "your-email@gmail.com" or SENDER_PASSWORD == "your-app-password":
        print("❌ Email credentials not configured!")
        print("\nTo configure Gmail:")
        print("1. Use your Gmail address for SENDER_EMAIL")
        print("2. Generate an App Password:")
        print("   - Go to: https://myaccount.google.com/apppasswords")
        print("   - Create app password for 'Mail'")
        print("   - Use that 16-character password for SENDER_PASSWORD")
        print("\nThen run this script again.")
    else:
        monitor_and_notify()
