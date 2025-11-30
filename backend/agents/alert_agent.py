"""AlertAgent: Handles price drop notifications."""
from typing import Dict, Any, Optional, List
from datetime import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.price_tracking_agent import PriceTrackingAgent
from database.models import Alert
from database.db import SessionLocal
from config import ALERT_ENABLED
import logging

logger = logging.getLogger(__name__)


class AlertAgent:
    """Manages alerts for price drops and other events."""
    
    def __init__(self):
        self.price_tracker = PriceTrackingAgent()
        self.enabled = ALERT_ENABLED
    
    def get_unread_alerts(self) -> List[Dict[str, Any]]:
        """Get all unread alerts."""
        if not self.enabled:
            return []
        
        db = SessionLocal()
        try:
            alerts = db.query(Alert).filter_by(is_read=False).order_by(Alert.created_at.desc()).all()
            return [
                {
                    "id": a.id,
                    "product_id": a.product_id,
                    "alert_type": a.alert_type,
                    "message": a.message,
                    "old_price": a.old_price,
                    "new_price": a.new_price,
                    "drop_amount": a.drop_amount,
                    "drop_percent": a.drop_percent,
                    "created_at": a.created_at.isoformat(),
                }
                for a in alerts
            ]
        finally:
            db.close()
    
    def mark_alert_read(self, alert_id: int) -> bool:
        """Mark an alert as read."""
        db = SessionLocal()
        try:
            alert = db.query(Alert).filter_by(id=alert_id).first()
            if alert:
                alert.is_read = True
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark alert as read: {e}")
            return False
        finally:
            db.close()
    
    def mark_all_alerts_read(self) -> int:
        """Mark all alerts as read."""
        db = SessionLocal()
        try:
            count = db.query(Alert).filter_by(is_read=False).update({"is_read": True})
            db.commit()
            return count
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to mark all alerts as read: {e}")
            return 0
        finally:
            db.close()
    
    def check_price_alerts(self, product_id: int) -> Optional[Dict[str, Any]]:
        """Check if product has price drop that warrants alert (legacy method)."""
        if not self.enabled:
            return None
        
        trend = self.price_tracker.analyze_trend(product_id)
        history = self.price_tracker.get_price_history(product_id, days=1)
        
        if len(history) < 2:
            return None
        
        # Check recent price drop
        recent_prices = history[-2:]
        old_price = recent_prices[0]["price"]
        new_price = recent_prices[1]["price"]
        
        if old_price and new_price < old_price:
            drop_percent = ((old_price - new_price) / old_price) * 100
            if drop_percent >= 10:  # 10% drop threshold
                return {
                    "type": "price_drop",
                    "product_id": product_id,
                    "old_price": old_price,
                    "new_price": new_price,
                    "drop_percent": drop_percent,
                    "message": f"Price dropped {drop_percent:.1f}%!",
                }
        
        return None
    
    def create_alert(self, alert_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an alert (legacy method)."""
        return {
            "type": alert_type,
            "timestamp": data.get("timestamp"),
            "data": data,
            "read": False,
        }
    
    def format_alert_message(self, alert: Dict[str, Any]) -> str:
        """Format alert as user-friendly message."""
        alert_type = alert.get("alert_type") or alert.get("type")
        
        if alert_type == "price_drop":
            message = alert.get("message", "Price dropped!")
            drop_percent = alert.get("drop_percent")
            drop_amount = alert.get("drop_amount")
            if drop_percent and drop_amount:
                return f"💰 Price Alert: {message} ({drop_percent:.1f}% / ${drop_amount:.2f})"
            return f"💰 Price Alert: {message}"
        
        return f"Alert: {alert_type}"


