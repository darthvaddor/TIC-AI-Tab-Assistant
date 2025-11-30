"""MemoryAgent: Stores session and long-term user preferences."""
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MEMORY_ENABLED, SESSION_MEMORY_PATH, LONG_TERM_MEMORY_PATH
from database.models import UserPreference, TabSession
from database.db import SessionLocal
import logging

logger = logging.getLogger(__name__)


class MemoryAgent:
    """Manages session and long-term memory."""
    
    def __init__(self):
        self.enabled = MEMORY_ENABLED
        self.session_memory_path = SESSION_MEMORY_PATH
        self.long_term_memory_path = LONG_TERM_MEMORY_PATH
        self._ensure_dirs()
    
    def _ensure_dirs(self) -> None:
        """Ensure memory directories exist."""
        self.session_memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.long_term_memory_path.parent.mkdir(parents=True, exist_ok=True)
    
    def save_session(self, session_id: str, tabs_data: List[Dict[str, Any]], categories: Optional[Dict[str, Any]] = None) -> None:
        """Save tab session to database."""
        if not self.enabled:
            return
        
        db = SessionLocal()
        try:
            session = db.query(TabSession).filter_by(session_id=session_id).first()
            if session:
                session.tabs_data = tabs_data
                session.categories = categories
                session.updated_at = datetime.utcnow()
            else:
                session = TabSession(
                    session_id=session_id,
                    tabs_data=tabs_data,
                    categories=categories,
                )
                db.add(session)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save session: {e}")
        finally:
            db.close()
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data."""
        db = SessionLocal()
        try:
            session = db.query(TabSession).filter_by(session_id=session_id).first()
            if session:
                return {
                    "session_id": session.session_id,
                    "tabs_data": session.tabs_data,
                    "categories": session.categories,
                    "created_at": session.created_at.isoformat(),
                }
            return None
        finally:
            db.close()
    
    def save_preference(self, key: str, value: Any) -> None:
        """Save user preference."""
        if not self.enabled:
            return
        
        db = SessionLocal()
        try:
            pref = db.query(UserPreference).filter_by(key=key).first()
            if pref:
                pref.value = value
                pref.updated_at = datetime.utcnow()
            else:
                pref = UserPreference(key=key, value=value)
                db.add(pref)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save preference: {e}")
        finally:
            db.close()
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get user preference."""
        db = SessionLocal()
        try:
            pref = db.query(UserPreference).filter_by(key=key).first()
            return pref.value if pref else default
        finally:
            db.close()
    
    def get_recurring_interests(self) -> List[str]:
        """Get recurring interests from memory."""
        interests = self.get_preference("recurring_interests", [])
        return interests if isinstance(interests, list) else []
    
    def add_recurring_interest(self, interest: str) -> None:
        """Add recurring interest."""
        interests = self.get_recurring_interests()
        if interest not in interests:
            interests.append(interest)
            self.save_preference("recurring_interests", interests)
    
    def get_tab_patterns(self) -> Dict[str, Any]:
        """Get learned tab classification patterns."""
        return self.get_preference("tab_patterns", {})


