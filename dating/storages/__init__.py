"""Top-level data-access aggregator.

``DBStorage`` composes one specialised storage per entity. Views never touch a
storage class directly — they receive ``DBStorage`` via ``get_db_storage`` and
reach the sub-storage (``db.user``, ``db.hint``, …).
"""

from dating.storages.hints import HintStorage
from dating.storages.matches import MatchStorage
from dating.storages.paddle_events import PaddleEventStorage
from dating.storages.purchases import PurchaseStorage
from dating.storages.subscriptions import SubscriptionStorage
from dating.storages.users import UserStorage
from dating.types import sessionmaker


class DBStorage:
    """Aggregate of all entity storages, sharing one sessionmaker."""

    def __init__(self, db_session: sessionmaker) -> None:
        """Wire each specialised storage onto this aggregate."""
        self.db_session = db_session
        self.user = UserStorage(db_session)
        self.hint = HintStorage(db_session)
        self.match = MatchStorage(db_session)
        self.purchase = PurchaseStorage(db_session)
        self.paddle_event = PaddleEventStorage(db_session)
        self.subscription = SubscriptionStorage(db_session)
