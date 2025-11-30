// Price extraction utilities for extension
function extractPriceFromPage() {
  const text = document.body?.innerText || "";
  const pricePatterns = [
    /\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)/g,
    /(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD/g,
    /price[:\s]+(\d+(?:,\d{3})*(?:\.\d{2})?)/gi,
  ];
  
  const prices = [];
  for (const pattern of pricePatterns) {
    const matches = text.matchAll(pattern);
    for (const match of matches) {
      const priceStr = match[1] || match[0];
      const price = parseFloat(priceStr.replace(/,/g, ""));
      if (price > 0 && price < 1000000) {
        prices.push(price);
      }
    }
  }
  
  return prices.length > 0 ? Math.min(...prices) : null;
}

function extractProductName() {
  const title = document.title || "";
  const h1 = document.querySelector("h1")?.innerText || "";
  const metaProduct = document.querySelector('meta[property="og:title"]')?.content || "";
  
  return metaProduct || h1 || title.split(" - ")[0].split(" | ")[0];
}

// Export for content scripts
if (typeof module !== "undefined" && module.exports) {
  module.exports = { extractPriceFromPage, extractProductName };
}

