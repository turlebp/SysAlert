
"""
Database wrapper using SQLAlchemy with thread-safe session management.
All methods are synchronous but safe to call from asyncio via asyncio.to_thread().
Supports both SQLite (default) and PostgreSQL (production).
"""
import os
import logging
from typing import Optional, List
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.pool import StaticPool

from models import Base, Subscription, Customer, Target, History, AuditLog

logger = logging.getLogger("UltraGigaBot.db")


class DB:
    """
    Thread-safe database wrapper with ORM helpers.
    Use scoped_session for thread safety - safe to call from multiple threads.
    """
    
    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize database connection.
        
        Args:
            db_url: SQLAlchemy connection string. Defaults to env DB_URL or sqlite.
        """
        self.db_url = db_url or os.getenv("DB_URL", "sqlite:///./data/bot.db")
        
        connect_args = {}
        if self.db_url.startswith("sqlite"):
            # SQLite-specific configuration
            connect_args = {"check_same_thread": False}
            # Use StaticPool for testing to avoid threading issues
            if ":memory:" in self.db_url:
                self.engine = create_engine(
                    self.db_url,
                    connect_args=connect_args,
                    poolclass=StaticPool,
                    future=True
                )
            else:
                self.engine = create_engine(
                    self.db_url,
                    connect_args=connect_args,
                    future=True
                )
            
            # Enable WAL mode and foreign keys for SQLite
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        else:
            # PostgreSQL or other database
            self.engine = create_engine(self.db_url, future=True, pool_pre_ping=True)
        
        # Create scoped session factory for thread safety
        session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.Session = scoped_session(session_factory)
        
        # Create all tables if they don't exist
        Base.metadata.create_all(self.engine)
        logger.info(f"Database initialized: {self.db_url}")
    
    @contextmanager
    def session_scope(self):
        """
        Provide a transactional scope for database operations.
        Automatically commits on success, rolls back on error.
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def session(self) -> Session:
        """Get a new session. Caller must close it."""
        return self.Session()
    
    # === Subscription Methods ===
    
    def add_subscription(self, chat_id: int) -> None:
        """Add a chat_id to subscriptions (idempotent)."""
        with self.session_scope() as s:
            existing = s.get(Subscription, chat_id)
            if existing is None:
                import time
                s.add(Subscription(chat_id=chat_id, created_at=int(time.time())))
                logger.info(f"Added subscription: {chat_id}")
    
    def remove_subscription(self, chat_id: int) -> None:
        """Remove a subscription."""
        with self.session_scope() as s:
            obj = s.get(Subscription, chat_id)
            if obj:
                s.delete(obj)
                logger.info(f"Removed subscription: {chat_id}")
    
    def list_subscriptions(self) -> List[int]:
        """Get all subscribed chat_ids."""
        with self.session_scope() as s:
            rows = s.query(Subscription).all()
            return [r.chat_id for r in rows]
    
    def is_subscribed(self, chat_id: int) -> bool:
        """Check if a chat_id is subscribed."""
        with self.session_scope() as s:
            return s.get(Subscription, chat_id) is not None
    
    # === Customer Methods ===
    
    def get_customer_by_chat(self, chat_id: int) -> Optional[Customer]:
        """Get customer by chat_id (with targets loaded)."""
        with self.session_scope() as s:
            cust = s.query(Customer).filter_by(chat_id=chat_id).first()
            if cust:
                # Explicitly load targets to avoid detached instance issues
                _ = cust.targets
            return cust
    
    def create_customer(self, chat_id: int, **kwargs) -> Customer:
        """Create a new customer with default settings."""
        with self.session_scope() as s:
            import time
            c = Customer(
                chat_id=chat_id,
                created_at=int(time.time()),
                **kwargs
            )
            s.add(c)
            s.flush()  # Get the ID
            customer_id = c.id
            logger.info(f"Created customer: {customer_id} for chat {chat_id}")
            return c
    
    def update_customer(self, chat_id: int, **kwargs) -> None:
        """Update customer settings."""
        with self.session_scope() as s:
            import time
            cust = s.query(Customer).filter_by(chat_id=chat_id).first()
            if cust:
                for key, value in kwargs.items():
                    setattr(cust, key, value)
                cust.updated_at = int(time.time())
                logger.info(f"Updated customer {chat_id}: {kwargs}")
    
    def list_all_customers(self) -> List[Customer]:
        """Get all customers (with targets loaded)."""
        with self.session_scope() as s:
            customers = s.query(Customer).all()
            # Load relationships
            for c in customers:
                _ = c.targets
            return customers
    
    # === Target Methods ===
    
    def upsert_target(self, customer_id: int, name: str, ip: str, port: int) -> Target:
        """Create or update a target (by customer_id + name)."""
        with self.session_scope() as s:
            t = s.query(Target).filter_by(customer_id=customer_id, name=name).first()
            if t:
                t.ip = ip
                t.port = port
                t.enabled = True
                logger.info(f"Updated target: {name} for customer {customer_id}")
            else:
                t = Target(customer_id=customer_id, name=name, ip=ip, port=port)
                s.add(t)
                logger.info(f"Created target: {name} for customer {customer_id}")
            s.flush()
            return t
    
    def list_customer_targets(self, customer_id: int) -> List[Target]:
        """Get all targets for a customer."""
        with self.session_scope() as s:
            return s.query(Target).filter_by(customer_id=customer_id).all()
    
    def get_target_by_name(self, customer_id: int, name: str) -> Optional[Target]:
        """Get a specific target by name."""
        with self.session_scope() as s:
            return s.query(Target).filter_by(customer_id=customer_id, name=name).first()
    
    def remove_target(self, customer_id: int, name: str) -> bool:
        """Remove a target. Returns True if removed."""
        with self.session_scope() as s:
            t = s.query(Target).filter_by(customer_id=customer_id, name=name).first()
            if t:
                s.delete(t)
                logger.info(f"Removed target: {name} for customer {customer_id}")
                return True
            return False
    
    def update_target_checked(self, target_id: int, timestamp: int, failed: bool) -> None:
        """Update target's last_checked and consecutive_failures."""
        with self.session_scope() as s:
            t = s.get(Target, target_id)
            if t:
                t.last_checked = timestamp
                if failed:
                    t.consecutive_failures += 1
                else:
                    t.consecutive_failures = 0
    
    # === History Methods ===
    
    def write_history(
        self,
        customer_chat_id: int,
        target_name: str,
        status: str,
        error: str,
        response_time: float
    ) -> None:
        """Record a check result in history."""
        with self.session_scope() as s:
            import time
            h = History(
                timestamp=int(time.time()),
                customer_chat_id=customer_chat_id,
                target_name=target_name,
                status=status,
                error=error or "",
                response_time=response_time
            )
            s.add(h)
    
    def get_recent_history(self, customer_chat_id: int, limit: int = 20) -> List[History]:
        """Get recent history for a customer."""
        with self.session_scope() as s:
            return (
                s.query(History)
                .filter_by(customer_chat_id=customer_chat_id)
                .order_by(History.timestamp.desc())
                .limit(limit)
                .all()
            )
    
    # === Audit Methods ===
    
    def audit(self, actor_chat_id: int, action: str, details: str) -> None:
        """Log an administrative action."""
        with self.session_scope() as s:
            import time
            log = AuditLog(
                actor_chat_id=actor_chat_id,
                action=action,
                details=details,
                created_at=int(time.time())
            )
            s.add(log)
            logger.info(f"Audit: {actor_chat_id} - {action}")