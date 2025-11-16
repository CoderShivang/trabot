"""
Test script to verify log suppression logic works correctly.
This tests the handler-level suppression approach without running full backtest.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from utils.logger import setup_logger
import logging as logging_module

def test_log_suppression():
    """Test that we can suppress StreamHandler output while keeping FileHandler"""

    # Set up a few loggers like the real application
    logger1 = setup_logger('test.module1')
    logger2 = setup_logger('test.module2')
    logger3 = setup_logger('test.module3')

    print("=" * 80)
    print("BEFORE SUPPRESSION - You should see colored log messages below:")
    print("=" * 80)

    logger1.debug("DEBUG message from module1")
    logger1.info("INFO message from module1")
    logger2.debug("DEBUG message from module2")
    logger2.info("INFO message from module2")
    logger3.debug("DEBUG message from module3")
    logger3.info("INFO message from module3")

    print("\n" + "=" * 80)
    print("APPLYING SUPPRESSION...")
    print("=" * 80)

    # Apply the same suppression logic from backtest_engine.py
    original_handler_levels = []

    for name in logging_module.Logger.manager.loggerDict:
        log = logging_module.getLogger(name)
        for handler in log.handlers:
            if isinstance(handler, logging_module.StreamHandler) and not isinstance(handler, logging_module.FileHandler):
                original_handler_levels.append((handler, handler.level))
                handler.setLevel(logging_module.ERROR)

    # Also check root logger handlers
    root_logger = logging_module.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging_module.StreamHandler) and not isinstance(handler, logging_module.FileHandler):
            original_handler_levels.append((handler, handler.level))
            handler.setLevel(logging_module.ERROR)

    print(f"\nSuppressed {len(original_handler_levels)} StreamHandlers")

    print("\n" + "=" * 80)
    print("AFTER SUPPRESSION - You should NOT see any log messages below:")
    print("=" * 80)

    logger1.debug("DEBUG message from module1 (should NOT appear)")
    logger1.info("INFO message from module1 (should NOT appear)")
    logger2.debug("DEBUG message from module2 (should NOT appear)")
    logger2.info("INFO message from module2 (should NOT appear)")
    logger3.debug("DEBUG message from module3 (should NOT appear)")
    logger3.info("INFO message from module3 (should NOT appear)")

    # Error messages should still appear
    logger1.error("ERROR message from module1 (SHOULD appear)")

    print("\n" + "=" * 80)
    print("RESTORING HANDLERS...")
    print("=" * 80)

    # Restore handler levels
    for handler, level in original_handler_levels:
        handler.setLevel(level)

    print(f"Restored {len(original_handler_levels)} handlers to original levels")

    print("\n" + "=" * 80)
    print("AFTER RESTORATION - You should see colored log messages again:")
    print("=" * 80)

    logger1.debug("DEBUG message from module1 (restored)")
    logger1.info("INFO message from module1 (restored)")
    logger2.debug("DEBUG message from module2 (restored)")
    logger2.info("INFO message from module2 (restored)")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print("\nExpected behavior:")
    print("  1. BEFORE: You should have seen 6 colored log messages")
    print("  2. AFTER: You should have seen 0 DEBUG/INFO messages, only 1 ERROR")
    print("  3. RESTORED: You should have seen 4 colored log messages")
    print("\nIf this matches what you saw, the log suppression logic is working!")
    print("=" * 80)

if __name__ == '__main__':
    test_log_suppression()
