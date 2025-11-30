"""PriceTrackingAgent: Tracks price history and detects trends."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.models import WatchedProduct, PriceHistory, Alert
from database.db import SessionLocal
from config import PRICE_DROP_THRESHOLD
import logging

logger = logging.getLogger(__name__)


class PriceTrackingAgent:
    """Manages price tracking and trend analysis."""
    
    def add_to_watchlist(
        self, 
        product_name: str, 
        url: str, 
        price: float, 
        currency: str = "USD",
        alert_threshold: Optional[float] = None,
        threshold_type: str = "percentage"
    ) -> int:
        """Add a product to watchlist with optional price drop threshold.
        
        Args:
            product_name: Name of the product
            url: Product URL
            price: Current price
            currency: Currency code (default: USD)
            alert_threshold: Threshold value - percentage (0-100) or absolute amount
            threshold_type: "percentage" or "absolute" (default: "percentage")
        """
        db = SessionLocal()
        try:
            existing = db.query(WatchedProduct).filter_by(url=url).first()
            if existing:
                existing.current_price = price
                existing.last_checked = datetime.utcnow()
                existing.is_active = True
                if alert_threshold is not None:
                    existing.alert_threshold = alert_threshold
                    existing.threshold_type = threshold_type
                product_id = existing.id
            else:
                product = WatchedProduct(
                    product_title=product_name,
                    url=url,
                    current_price=price,
                    currency=currency,
                    alert_threshold=alert_threshold,
                    threshold_type=threshold_type,
                )
                db.add(product)
                db.commit()
                db.refresh(product)
                product_id = product.id
            
            # Record initial price
            self._record_price(db, product_id, price, currency)
            db.commit()
            return product_id
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add to watchlist: {e}")
            raise
        finally:
            db.close()
    
    def update_price(self, product_id: int, new_price: float, currency: str = "USD") -> Dict[str, Any]:
        """Update price for a watched product and check against user-defined threshold."""
        db = SessionLocal()
        try:
            product = db.query(WatchedProduct).filter_by(id=product_id).first()
            if not product:
                return {"error": "Product not found"}
            
            old_price = product.current_price
            product.current_price = new_price
            product.last_checked = datetime.utcnow()
            
            # Record price history
            self._record_price(db, product_id, new_price, currency)
            db.commit()
            
            # Check for price drop against user-defined threshold
            drop_info = self._check_price_drop_with_threshold(
                db, product, old_price, new_price
            )
            
            return {
                "product_id": product_id,
                "old_price": old_price,
                "new_price": new_price,
                "price_change": new_price - (old_price or 0),
                "price_drop": drop_info,
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update price: {e}")
            return {"error": str(e)}
        finally:
            db.close()
    
    def _record_price(self, db: Session, product_id: int, price: float, currency: str) -> None:
        """Record price in history."""
        history = PriceHistory(
            product_id=product_id,
            price=price,
            currency=currency,
        )
        db.add(history)
    
    def _check_price_drop(self, old_price: Optional[float], new_price: float) -> Optional[Dict[str, Any]]:
        """Check if price dropped significantly (legacy method using global threshold)."""
        if not old_price or old_price <= 0:
            return None
        
        drop_percent = (old_price - new_price) / old_price
        if drop_percent >= PRICE_DROP_THRESHOLD:
            return {
                "dropped": True,
                "percent": drop_percent * 100,
                "amount": old_price - new_price,
            }
        return None
    
    def _check_price_drop_with_threshold(
        self, 
        db: Session, 
        product: WatchedProduct, 
        old_price: Optional[float], 
        new_price: float
    ) -> Optional[Dict[str, Any]]:
        """Check if price dropped below user-defined threshold and create alert if so."""
        if not old_price or old_price <= 0 or new_price >= old_price:
            return None
        
        drop_amount = old_price - new_price
        drop_percent = (drop_amount / old_price) * 100
        
        # Check against user-defined threshold
        threshold = product.alert_threshold
        threshold_type = product.threshold_type or "percentage"
        
        if threshold is None:
            # No threshold set, use default
            if drop_percent >= PRICE_DROP_THRESHOLD * 100:
                return {
                    "dropped": True,
                    "percent": drop_percent,
                    "amount": drop_amount,
                }
            return None
        
        # Check threshold based on type
        threshold_met = False
        if threshold_type == "percentage":
            threshold_met = drop_percent >= threshold
        elif threshold_type == "absolute":
            threshold_met = drop_amount >= threshold
        
        if threshold_met:
            # Create alert
            alert = Alert(
                product_id=product.id,
                alert_type="price_drop",
                message=f"Price dropped {drop_percent:.1f}% (${drop_amount:.2f}) for {product.product_title}",
                old_price=old_price,
                new_price=new_price,
                drop_amount=drop_amount,
                drop_percent=drop_percent,
                is_read=False,
            )
            db.add(alert)
            db.commit()
            
            logger.info(f"Price alert created for product {product.id}: {drop_percent:.1f}% drop")
            
            return {
                "dropped": True,
                "percent": drop_percent,
                "amount": drop_amount,
                "alert_created": True,
            }
        
        return None
    
    def get_price_history(self, product_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Get price history for a product."""
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            history = db.query(PriceHistory).filter(
                PriceHistory.product_id == product_id,
                PriceHistory.recorded_at >= cutoff
            ).order_by(PriceHistory.recorded_at).all()
            
            return [
                {
                    "price": h.price,
                    "currency": h.currency,
                    "date": h.recorded_at.isoformat(),
                }
                for h in history
            ]
        finally:
            db.close()
    
    def analyze_trend(self, product_id: int) -> Dict[str, Any]:
        """Analyze price trend."""
        history = self.get_price_history(product_id, days=30)
        if len(history) < 2:
            return {"trend": "insufficient_data"}
        
        prices = [h["price"] for h in history]
        first_price = prices[0]
        last_price = prices[-1]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        
        change = last_price - first_price
        change_percent = (change / first_price * 100) if first_price > 0 else 0
        
        trend = "stable"
        if change_percent > 5:
            trend = "increasing"
        elif change_percent < -5:
            trend = "decreasing"
        
        return {
            "trend": trend,
            "current": last_price,
            "average": avg_price,
            "min": min_price,
            "max": max_price,
            "change": change,
            "change_percent": change_percent,
            "data_points": len(history),
        }
    
    def get_all_watched_products(self) -> List[Dict[str, Any]]:
        """Get all active watched products."""
        db = SessionLocal()
        try:
            products = db.query(WatchedProduct).filter_by(is_active=True).all()
            return [
                {
                    "id": p.id,
                    "product_name": p.product_title,
                    "url": p.url,
                    "current_price": p.current_price,
                    "currency": p.currency,
                    "added_at": p.added_at.isoformat(),
                    "last_checked": p.last_checked.isoformat(),
                    "alert_threshold": p.alert_threshold,
                    "threshold_type": p.threshold_type,
                }
                for p in products
            ]
        finally:
            db.close()
    
    def check_all_prices(self) -> List[Dict[str, Any]]:
        """Check prices for all watched products (to be called periodically).
        
        Note: This is a placeholder. In production, you would:
        1. Open each product URL
        2. Extract the current price
        3. Call update_price() for each product
        
        For now, this just returns the list of products that need checking.
        """
        products = self.get_all_watched_products()
        return [
            {
                "product_id": p["id"],
                "url": p["url"],
                "needs_check": True,
            }
            for p in products
        ]


