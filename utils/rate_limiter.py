import time

# Free tier = 5 calls per minute = 1 call every 12 seconds to be safe
# If you upgrade to Starter ($29/mo) change this to 0.1
POLYGON_DELAY = 12

_last_call_time = 0

def polygon_wait():
    """Call this before every Polygon API request."""
    global _last_call_time
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < POLYGON_DELAY:
        wait_time = POLYGON_DELAY - elapsed
        time.sleep(wait_time)
    _last_call_time = time.time()