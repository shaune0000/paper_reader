#!/usr/bin/env python
"""
錯誤處理測試腳本
驗證系統對各種錯誤情況的處理
"""

import sys
import logging
from datetime import datetime

# 設置測試日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s|%(name)s|%(levelname)s|%(message)s'
)
logger = logging.getLogger("ErrorHandlingTest")

def test_fetch_with_invalid_url():
    """測試：無效的 URL"""
    logger.info("=" * 60)
    logger.info("Test 1: 無效的 URL")
    logger.info("=" * 60)

    from grab_huggingface import fetch_huggingface_dailypapers

    raw_text, output_file, hash = fetch_huggingface_dailypapers(url="https://huggingface.co/invalid-endpoint-123")

    if raw_text is None and hash is None:
        logger.info("✅ Test PASSED: 正確返回 None 值")
        logger.info("✅ 程式沒有崩潰")
        return True
    else:
        logger.error("❌ Test FAILED: 應該返回 None")
        return False

def test_fetch_with_timeout():
    """測試：超時處理"""
    logger.info("\n" + "=" * 60)
    logger.info("Test 2: 超時處理（使用不可達的 IP）")
    logger.info("=" * 60)

    from grab_huggingface import fetch_huggingface_dailypapers

    # 使用一個不可達的 IP 測試超時
    logger.info("注意：此測試需要等待 30 秒超時...")
    raw_text, output_file, hash = fetch_huggingface_dailypapers(url="http://192.0.2.1")

    if raw_text is None and hash is None:
        logger.info("✅ Test PASSED: 超時後正確返回 None")
        logger.info("✅ 程式沒有崩潰")
        return True
    else:
        logger.error("❌ Test FAILED: 應該超時並返回 None")
        return False

def test_update_paper_with_none():
    """測試：處理 None 返回值"""
    logger.info("\n" + "=" * 60)
    logger.info("Test 3: update_paper 處理 None 返回值")
    logger.info("=" * 60)

    # 模擬修改 fetch_huggingface_dailypapers 返回 None
    import grab_huggingface
    original_fetch = grab_huggingface.fetch_huggingface_dailypapers

    def mock_fetch(url="https://huggingface.co/papers"):
        logger.info("Mock: 返回 None 值")
        return None, None, None

    try:
        grab_huggingface.fetch_huggingface_dailypapers = mock_fetch

        from read_daily_papers import update_paper
        update_paper(zulip=False)

        logger.info("✅ Test PASSED: update_paper 正確處理 None")
        logger.info("✅ 程式沒有崩潰")
        return True

    except Exception as e:
        logger.error(f"❌ Test FAILED: {type(e).__name__} - {e}")
        return False

    finally:
        # 恢復原始函數
        grab_huggingface.fetch_huggingface_dailypapers = original_fetch

def test_logger_configuration():
    """測試：日誌配置"""
    logger.info("\n" + "=" * 60)
    logger.info("Test 4: 日誌配置檢查")
    logger.info("=" * 60)

    from read_daily_papers import logger as daily_logger

    handlers = daily_logger.handlers
    logger.info(f"Logger handlers: {len(handlers)}")

    has_file_handler = False
    has_console_handler = False

    for handler in handlers:
        logger.info(f"  - {type(handler).__name__}: {handler}")
        if 'TimedRotatingFileHandler' in type(handler).__name__:
            has_file_handler = True
        if 'StreamHandler' in type(handler).__name__:
            has_console_handler = True

    if has_file_handler and has_console_handler:
        logger.info("✅ Test PASSED: 日誌同時輸出到檔案和 console")
        return True
    else:
        logger.error("❌ Test FAILED: 缺少 handler")
        if not has_file_handler:
            logger.error("  缺少 file handler")
        if not has_console_handler:
            logger.error("  缺少 console handler")
        return False

def main():
    """執行所有測試"""
    logger.info("\n" + "🧪 " * 20)
    logger.info("開始錯誤處理測試")
    logger.info("🧪 " * 20 + "\n")

    tests = [
        ("無效的 URL", test_fetch_with_invalid_url),
        # ("超時處理", test_fetch_with_timeout),  # 註解掉，因為需要 30 秒
        ("處理 None 返回值", test_update_paper_with_none),
        ("日誌配置", test_logger_configuration),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"❌ Test '{name}' 發生異常: {type(e).__name__} - {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 總結
    logger.info("\n" + "=" * 60)
    logger.info("測試總結")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status}: {name}")

    logger.info(f"\n總計: {passed}/{total} 通過")

    if passed == total:
        logger.info("\n🎉 所有測試通過！")
        return 0
    else:
        logger.error(f"\n⚠️  {total - passed} 個測試失敗")
        return 1

if __name__ == "__main__":
    sys.exit(main())
