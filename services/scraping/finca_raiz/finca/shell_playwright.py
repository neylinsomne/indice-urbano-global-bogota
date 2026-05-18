import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        url = input("Enter the URL to scrape: ")
        await page.goto(url)
        print(f"Loaded {url}")
        
        while True:
            selector = input("Enter a selector (or 'quit' to exit): ")
            if selector.lower() == 'quit':
                break
            
            elements = await page.query_selector_all(selector)
            print(f"Found {len(elements)} elements")
            
            for i, element in enumerate(elements[:5]):  # Limit to first 5 for brevity
                text = await element.inner_text()
                print(f"Element {i}: {text[:100]}...")  # Print first 100 chars
            
            js_input = input("Enter JavaScript to evaluate (or press enter to skip): ")
            if js_input:
                result = await page.evaluate(js_input)
                print("JavaScript result:", result)
        
        await browser.close()

asyncio.run(main())