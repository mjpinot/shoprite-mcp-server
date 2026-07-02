"""
Shoprite MCP Server
Implements the Model Context Protocol (MCP) to expose Shoprite product/deal data
as tools and resources consumable by AI assistants.
"""

import asyncio
import logging
import os
from typing import Any

import httpx
from bs4 import BeautifulSoup
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)
from pydantic import AnyUrl
import mcp.types as types

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("shoprite-mcp")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("SHOPRITE_BASE_URL", "https://www.shoprite.com")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_PRODUCTS = int(os.getenv("MAX_PRODUCTS", "50"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ShopriteMCP/1.0; "
        "+https://github.com/mjpinot/shoprite-mcp-server)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------

async def fetch_page(url: str) -> str:
    """Fetch a URL and return its HTML content."""
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers=HEADERS,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


# ---------------------------------------------------------------------------
# Shoprite scraper helpers
# ---------------------------------------------------------------------------

def parse_products_from_html(html: str) -> list[dict[str, Any]]:
    """Parse product listings from a Shoprite category page."""
    soup = BeautifulSoup(html, "html.parser")
    products: list[dict[str, Any]] = []

    # Shoprite uses different selectors depending on the page variant;
    # try the most common patterns.
    selectors = [
        "div.product-grid__item",
        "div[data-testid='product-card']",
        "li.product-item",
        "div.product-tile",
    ]

    items = []
    for selector in selectors:
        items = soup.select(selector)
        if items:
            break

    for item in items[:MAX_PRODUCTS]:
        name_el = (
            item.select_one("span.product-name")
            or item.select_one("h2.product-title")
            or item.select_one("[data-testid='product-name']")
            or item.select_one(".product-item-name")
        )
        price_el = (
            item.select_one("span.product-price")
            or item.select_one("[data-testid='product-price']")
            or item.select_one(".price")
        )
        link_el = item.select_one("a[href]")
        img_el = item.select_one("img[src]")

        products.append(
            {
                "name": name_el.get_text(strip=True) if name_el else "N/A",
                "price": price_el.get_text(strip=True) if price_el else "N/A",
                "url": (BASE_URL + link_el["href"])
                if link_el and link_el["href"].startswith("/")
                else (link_el["href"] if link_el else "N/A"),
                "image": img_el["src"] if img_el else "N/A",
            }
        )

    return products


def parse_weekly_deals(html: str) -> list[dict[str, Any]]:
    """Parse weekly deals / circulars from the Shoprite deals page."""
    soup = BeautifulSoup(html, "html.parser")
    deals: list[dict[str, Any]] = []

    selectors = [
        "div.sale-item",
        "div[data-testid='deal-card']",
        "li.deal-item",
        "div.circular-item",
    ]

    items = []
    for selector in selectors:
        items = soup.select(selector)
        if items:
            break

    for item in items[:MAX_PRODUCTS]:
        title_el = item.select_one("span, h2, h3, p")
        price_el = item.select_one(".sale-price, .deal-price, .price")
        link_el = item.select_one("a[href]")

        deals.append(
            {
                "title": title_el.get_text(strip=True) if title_el else "N/A",
                "sale_price": price_el.get_text(strip=True) if price_el else "N/A",
                "url": (BASE_URL + link_el["href"])
                if link_el and link_el["href"].startswith("/")
                else (link_el["href"] if link_el else "N/A"),
            }
        )

    return deals


def parse_store_locations(html: str) -> list[dict[str, Any]]:
    """Parse store location data from the Shoprite store finder page."""
    soup = BeautifulSoup(html, "html.parser")
    stores: list[dict[str, Any]] = []

    selectors = [
        "div.store-card",
        "li.store-item",
        "div[data-testid='store-card']",
    ]

    items = []
    for selector in selectors:
        items = soup.select(selector)
        if items:
            break

    for item in items[:20]:
        name_el = item.select_one(".store-name, h2, h3")
        addr_el = item.select_one(".store-address, address, .address")
        phone_el = item.select_one(".store-phone, .phone, a[href^='tel:']")
        hours_el = item.select_one(".store-hours, .hours")

        stores.append(
            {
                "name": name_el.get_text(strip=True) if name_el else "N/A",
                "address": addr_el.get_text(strip=True) if addr_el else "N/A",
                "phone": phone_el.get_text(strip=True) if phone_el else "N/A",
                "hours": hours_el.get_text(strip=True) if hours_el else "N/A",
            }
        )

    return stores


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

app = Server("shoprite-mcp-server")


@app.list_resources()
async def list_resources() -> list[Resource]:
    """Expose top-level Shoprite URLs as MCP resources."""
    return [
        Resource(
            uri=AnyUrl(f"{BASE_URL}"),
            name="Shoprite Homepage",
            description="Shoprite main website homepage",
            mimeType="text/html",
        ),
        Resource(
            uri=AnyUrl(f"{BASE_URL}/savings/weekly-specials"),
            name="Weekly Specials",
            description="Current weekly deals and specials at Shoprite",
            mimeType="text/html",
        ),
        Resource(
            uri=AnyUrl(f"{BASE_URL}/store-finder"),
            name="Store Finder",
            description="Shoprite store locations",
            mimeType="text/html",
        ),
    ]


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Fetch and return the raw HTML for a given Shoprite resource URI."""
    url = str(uri)
    logger.info("Reading resource: %s", url)
    try:
        html = await fetch_page(url)
        return html
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"HTTP error {exc.response.status_code} fetching {url}") from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Network error fetching {url}: {exc}") from exc


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Declare all available Shoprite tools."""
    return [
        Tool(
            name="search_products",
            description=(
                "Search for products on Shoprite by keyword. "
                "Returns a list of products with name, price, and URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (e.g. 'chicken breast', 'milk')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 10, max 50)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_weekly_deals",
            description=(
                "Retrieve current weekly deals and specials from Shoprite. "
                "Returns a list of items on sale with their discounted prices."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of deals to return (default 20)",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
            },
        ),
        Tool(
            name="get_store_locations",
            description=(
                "Find Shoprite store locations. "
                "Returns store names, addresses, phone numbers, and hours."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "zip_code": {
                        "type": "string",
                        "description": "ZIP code to find nearby stores",
                    },
                },
            },
        ),
        Tool(
            name="get_product_details",
            description=(
                "Get detailed information about a specific Shoprite product by URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "product_url": {
                        "type": "string",
                        "description": "Full URL of the product page on shoprite.com",
                    },
                },
                "required": ["product_url"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(
    name: str, arguments: dict[str, Any]
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Dispatch and execute the requested tool."""

    if name == "search_products":
        query = arguments.get("query", "").strip()
        if not query:
            raise types.McpError(INVALID_PARAMS, "query parameter is required")
        max_results = min(int(arguments.get("max_results", 10)), MAX_PRODUCTS)

        search_url = f"{BASE_URL}/search?q={httpx.QueryParams({'term': query})}"
        logger.info("Searching products: %s", search_url)

        try:
            html = await fetch_page(search_url)
            products = parse_products_from_html(html)[:max_results]
        except Exception as exc:
            logger.error("search_products failed: %s", exc)
            raise types.McpError(INTERNAL_ERROR, f"Failed to search products: {exc}") from exc

        if not products:
            result_text = f"No products found for '{query}' on Shoprite."
        else:
            lines = [f"Found {len(products)} product(s) for '{query}':\n"]
            for i, p in enumerate(products, 1):
                lines.append(f"{i}. **{p['name']}**")
                lines.append(f"   Price: {p['price']}")
                lines.append(f"   URL:   {p['url']}")
                lines.append("")
            result_text = "\n".join(lines)

        return [TextContent(type="text", text=result_text)]

    elif name == "get_weekly_deals":
        max_results = min(int(arguments.get("max_results", 20)), MAX_PRODUCTS)
        deals_url = f"{BASE_URL}/savings/weekly-specials"
        logger.info("Fetching weekly deals from: %s", deals_url)

        try:
            html = await fetch_page(deals_url)
            deals = parse_weekly_deals(html)[:max_results]
        except Exception as exc:
            logger.error("get_weekly_deals failed: %s", exc)
            raise types.McpError(INTERNAL_ERROR, f"Failed to fetch deals: {exc}") from exc

        if not deals:
            result_text = "No weekly deals found at this time."
        else:
            lines = [f"Shoprite Weekly Deals ({len(deals)} items):\n"]
            for i, d in enumerate(deals, 1):
                lines.append(f"{i}. **{d['title']}**")
                lines.append(f"   Sale price: {d['sale_price']}")
                lines.append(f"   URL: {d['url']}")
                lines.append("")
            result_text = "\n".join(lines)

        return [TextContent(type="text", text=result_text)]

    elif name == "get_store_locations":
        zip_code = arguments.get("zip_code", "").strip()
        store_url = (
            f"{BASE_URL}/store-finder?zip={zip_code}"
            if zip_code
            else f"{BASE_URL}/store-finder"
        )
        logger.info("Fetching store locations from: %s", store_url)

        try:
            html = await fetch_page(store_url)
            stores = parse_store_locations(html)
        except Exception as exc:
            logger.error("get_store_locations failed: %s", exc)
            raise types.McpError(INTERNAL_ERROR, f"Failed to fetch stores: {exc}") from exc

        if not stores:
            result_text = "No store locations found."
        else:
            lines = [f"Shoprite Store Locations ({len(stores)} found):\n"]
            for i, s in enumerate(stores, 1):
                lines.append(f"{i}. **{s['name']}**")
                lines.append(f"   Address: {s['address']}")
                lines.append(f"   Phone:   {s['phone']}")
                lines.append(f"   Hours:   {s['hours']}")
                lines.append("")
            result_text = "\n".join(lines)

        return [TextContent(type="text", text=result_text)]

    elif name == "get_product_details":
        product_url = arguments.get("product_url", "").strip()
        if not product_url:
            raise types.McpError(INVALID_PARAMS, "product_url is required")
        if not product_url.startswith("http"):
            raise types.McpError(INVALID_PARAMS, "product_url must be a full URL")

        logger.info("Fetching product details from: %s", product_url)

        try:
            html = await fetch_page(product_url)
            soup = BeautifulSoup(html, "html.parser")

            title = soup.select_one("h1") or soup.select_one("h2")
            price = (
                soup.select_one("[data-testid='product-price']")
                or soup.select_one(".product-price")
                or soup.select_one(".price")
            )
            description = (
                soup.select_one("[data-testid='product-description']")
                or soup.select_one(".product-description")
                or soup.select_one(".description")
            )

            lines = [f"**Product Details**\n"]
            lines.append(f"Title:       {title.get_text(strip=True) if title else 'N/A'}")
            lines.append(f"Price:       {price.get_text(strip=True) if price else 'N/A'}")
            lines.append(
                f"Description: {description.get_text(strip=True)[:500] if description else 'N/A'}"
            )
            lines.append(f"URL:         {product_url}")
            result_text = "\n".join(lines)

        except Exception as exc:
            logger.error("get_product_details failed: %s", exc)
            raise types.McpError(INTERNAL_ERROR, f"Failed to fetch product details: {exc}") from exc

        return [TextContent(type="text", text=result_text)]

    else:
        raise types.McpError(INVALID_PARAMS, f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    logger.info("Starting Shoprite MCP Server…")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="shoprite-mcp-server",
                server_version="1.0.0",
                capabilities=app.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
