"""Demo mode for TabSensei - runs without live browser."""
from pathlib import Path
from typing import List, Dict, Any
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.tab_reader_agent import TabReaderAgent
from agents.tab_classifier_agent import TabClassifierAgent
from agents.tab_summary_agent import TabSummaryAgent
from agents.price_extraction_agent import PriceExtractionAgent
from agents.price_tracking_agent import PriceTrackingAgent
from agents.alert_agent import AlertAgent
from agents.planner_agent import PlannerAgent
from database.db import init_db
import json


def load_sample_html(filepath: Path) -> str:
    """Load sample HTML file."""
    return filepath.read_text(encoding="utf-8")


def extract_text_from_html(html: str) -> str:
    """Extract visible text from HTML (simplified)."""
    import re
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def create_sample_tabs() -> List[Dict[str, Any]]:
    """Create sample tab data for demo."""
    sample_dir = Path(__file__).parent / "sample_pages"
    sample_dir.mkdir(exist_ok=True)
    
    tabs = [
        {
            "id": 1,
            "title": "MacBook Pro 16-inch - Apple",
            "url": "https://apple.com/macbook-pro",
            "text": "MacBook Pro 16-inch with M3 chip. Price: $2,499.00. 16GB RAM, 512GB SSD. Available now.",
        },
        {
            "id": 2,
            "title": "Dell XPS 15 Laptop - Best Buy",
            "url": "https://bestbuy.com/dell-xps-15",
            "text": "Dell XPS 15 Laptop. Price: $1,299.99. Intel i7, 16GB RAM, 512GB SSD. Free shipping.",
        },
        {
            "id": 3,
            "title": "Python Tutorial - Real Python",
            "url": "https://realpython.com/python-tutorial",
            "text": "Learn Python programming. Comprehensive tutorial covering basics to advanced topics. Free resources available.",
        },
        {
            "id": 4,
            "title": "MacBook Pro 16-inch - Apple",
            "url": "https://apple.com/macbook-pro",
            "text": "MacBook Pro 16-inch with M3 chip. Price: $2,499.00. 16GB RAM, 512GB SSD. Available now.",
        },
        {
            "id": 5,
            "title": "YouTube - Watch Videos",
            "url": "https://youtube.com",
            "text": "Watch videos, music, entertainment. Trending now. Subscribe to channels.",
        },
    ]
    
    return tabs


def demo_tab_reading():
    """Demonstrate tab reading."""
    print("=== Demo: Tab Reading ===")
    reader = TabReaderAgent()
    tabs = create_sample_tabs()
    extracted = reader.extract_multiple_tabs(tabs)
    print(f"Extracted {len(extracted)} tabs")
    for tab in extracted:
        print(f"  - {tab['title'][:50]}: {tab['text_length']} chars")
    print()


def demo_tab_classification():
    """Demonstrate tab classification."""
    print("=== Demo: Tab Classification ===")
    reader = TabReaderAgent()
    classifier = TabClassifierAgent()
    tabs = create_sample_tabs()
    extracted = reader.extract_multiple_tabs(tabs)
    classified = classifier.classify_multiple_tabs(extracted)
    
    for tab in classified:
        cat = tab.get("classification", {}).get("category", "unknown")
        print(f"  - {tab['title'][:40]}: {cat}")
    
    duplicates = classifier.detect_duplicates(classified)
    print(f"\nFound {len(duplicates)} duplicate groups")
    print()


def demo_price_extraction():
    """Demonstrate price extraction."""
    print("=== Demo: Price Extraction ===")
    extractor = PriceExtractionAgent()
    tabs = create_sample_tabs()
    
    for tab in tabs:
        if extractor.is_shopping_page(tab):
            info = extractor.extract_product_info(tab)
            if info:
                print(f"  Product: {info['product_name']}")
                print(f"  Price: {info['price']} {info['currency']}")
                print(f"  URL: {info['url']}")
                print()
    print()


def demo_price_tracking():
    """Demonstrate price tracking."""
    print("=== Demo: Price Tracking ===")
    init_db()
    tracker = PriceTrackingAgent()
    
    # Add products
    product_id1 = tracker.add_to_watchlist("MacBook Pro", "https://apple.com/macbook", 2499.0)
    product_id2 = tracker.add_to_watchlist("Dell XPS 15", "https://bestbuy.com/dell-xps", 1299.99)
    print(f"Added products: {product_id1}, {product_id2}")
    
    # Update prices
    result1 = tracker.update_price(product_id1, 2299.0)
    result2 = tracker.update_price(product_id2, 1199.99)
    print(f"Price updates: {result1.get('price_drop')}, {result2.get('price_drop')}")
    
    # Analyze trends
    trend1 = tracker.analyze_trend(product_id1)
    print(f"Trend for product {product_id1}: {trend1}")
    print()


def demo_alerts():
    """Demonstrate alert system."""
    print("=== Demo: Alerts ===")
    alert_agent = AlertAgent()
    tracker = PriceTrackingAgent()
    
    products = tracker.get_all_watched_products()
    for product in products:
        alert = alert_agent.check_price_alerts(product["id"])
        if alert:
            print(f"  Alert: {alert_agent.format_alert_message(alert_agent.create_alert('price_drop', alert))}")
    print()


def demo_planner():
    """Demonstrate planner agent workflow."""
    print("=== Demo: Planner Agent ===")
    planner = PlannerAgent()
    tabs = create_sample_tabs()
    
    result = planner.process("compare the laptops", tabs)
    print(f"Mode: {result['mode']}")
    print(f"Reply preview: {result['reply'][:200]}...")
    print(f"Workspace summary: {result.get('workspace_summary', {})}")
    print()


def main():
    """Run all demos."""
    print("=" * 60)
    print("TabSensei Demo Mode")
    print("=" * 60)
    print()
    
    try:
        demo_tab_reading()
        demo_tab_classification()
        demo_price_extraction()
        demo_price_tracking()
        demo_alerts()
        demo_planner()
        
        print("=" * 60)
        print("Demo completed successfully!")
        print("=" * 60)
    except Exception as e:
        print(f"Demo error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

