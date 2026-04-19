from whaletracker.config import Settings
from whaletracker.tracker import WhaleTracker


class DummyPublisher:
    def __init__(self):
        self.points = []

    async def publish(self, dp):
        self.points.append(dp)


def test_extracts_alchemy_transaction_shape(tmp_path):
    settings = Settings(
        redis_url="redis://localhost:6379/0",
        database_path=tmp_path / "db.sqlite",
        chains=("ethereum",),
        api_keys={"ALCHEMY_API_KEY": "test"},
        price_cache_ttl_seconds=300,
        reconnect_base_delay_seconds=1,
        reconnect_max_delay_seconds=2,
        log_level="INFO",
    )
    tracker = WhaleTracker(DummyPublisher(), settings)
    payload = {
        "params": {
            "result": {
                "transaction": {
                    "hash": "0xhash",
                    "from": "0xfrom",
                    "to": "0xto",
                }
            }
        }
    }

    assert tracker._extract_transaction(payload)["hash"] == "0xhash"
