import sys
import os
from datetime import datetime

# Add workspace directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.database import SessionLocal, engine
from sqlalchemy import text

def run_migration():
    print("Connecting to database...")
    db = SessionLocal()
    try:
        # Check if the column last_message_at already exists in conversations table
        check_col_query = text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='conversations' AND column_name='last_message_at';"
        )
        result = db.execute(check_col_query).fetchone()
        
        if not result:
            print("Column 'last_message_at' does not exist in 'conversations' table. Adding it now...")
            # Add column
            db.execute(text("ALTER TABLE conversations ADD COLUMN last_message_at TIMESTAMP;"))
            db.commit()
            print("Column added successfully.")
        else:
            print("Column 'last_message_at' already exists in 'conversations' table.")
            
        print("Backfilling 'last_message_at' values...")
        # 1. Update conversations that have messages with the latest message's timestamp
        update_with_msgs_query = text("""
            UPDATE conversations c
            SET last_message_at = (
                SELECT MAX(sent_at)
                FROM messages m
                WHERE m.conversation_id = c.conversation_id
            )
            WHERE EXISTS (
                SELECT 1
                FROM messages m
                WHERE m.conversation_id = c.conversation_id
            );
        """)
        res1 = db.execute(update_with_msgs_query)
        print(f"Updated {res1.rowcount} conversations with their latest message timestamp.")

        # 2. Update conversations with NO messages to use their created_at timestamp
        update_no_msgs_query = text("""
            UPDATE conversations
            SET last_message_at = created_at
            WHERE last_message_at IS NULL;
        """)
        res2 = db.execute(update_no_msgs_query)
        print(f"Updated {res2.rowcount} conversations with their created_at timestamp.")
        
        # 3. Ensure any remaining NULL values are set to now (safety fallback)
        update_fallback_query = text(f"""
            UPDATE conversations
            SET last_message_at = '{datetime.utcnow().isoformat()}'
            WHERE last_message_at IS NULL;
        """)
        res3 = db.execute(update_fallback_query)
        if res3.rowcount > 0:
            print(f"Updated {res3.rowcount} fallback conversations with current timestamp.")
            
        db.commit()
        print("Migration complete!")
    except Exception as e:
        db.rollback()
        print(f"Error executing migration: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
