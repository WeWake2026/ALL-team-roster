import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    if "sqlite" in DATABASE_URL:
        engine = create_engine(
            DATABASE_URL, connect_args={"check_same_thread": False}
        )
    else:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300
        )
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shiftflow.db")
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )

    # SQLite High-Performance PRAGMA Tuning (Zero Disk Bottleneck)
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")       # Write-Ahead Logging for non-blocking concurrent reads
        cursor.execute("PRAGMA synchronous = NORMAL")     # Faster commits with safe crash-recovery
        cursor.execute("PRAGMA cache_size = -64000")      # 64MB In-Memory Page Cache
        cursor.execute("PRAGMA temp_store = MEMORY")      # Keep temporary tables/indices in RAM
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
